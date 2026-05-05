"""LLM assistant API - context-enriched chat with project-scoped memory and tool calling."""

import asyncio
import copy
import json
import logging
import os
import re
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Optional, Union


def _message_text(message: Any) -> str:
    """Extract the text portion of a chat message payload.

    `ChatRequest.message` accepts either a plain string (the common
    text-only case) or an OpenAI-style content list for multimodal
    input (text + image_url blocks from the chat-input image
    attachment). Several routing/heuristic code paths only care about
    the text — selecting tools, computing previews for logs, the
    speculative-retrieval gate, etc. This helper flattens to plain
    text without losing the original shape (which still flows through
    memory.append + the LLM call unchanged).

    Strings pass through. Lists are joined from their `text`-typed
    blocks. Anything else stringified defensively.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for block in message:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text", "") or "")
        return " ".join(parts).strip()
    return str(message or "")

from app.managers.llm_router import LLMRouter
from app.managers.llm_context import build_context_message, clean_history
from app.managers.llm_memory import ProjectMemory
from app.managers.llm_tools import parse_tool_call, parse_all_tool_calls, execute_tool, is_write_tool, prepare_write_action, execute_write_tool, expand_batch_tool, expand_find_replace_tool, _tool_graph_and_vector_search
from app.managers.llm_debug import get_debug_log
from app.mcp.tools import is_write_tier
from app.mcp.tool_formats import to_anthropic_tools, to_openai_tools
from app.mcp.gemma_tool_parser import strip_gemma_tokens, strip_gemma_tokens_streaming, translate_gemma_thinking
from app.mcp.context_router import select_tools, expand_tools_for_retry
from app.managers.notebook_manager import NotebookManager
from app.managers.mlflow_manager import MlflowManager
from app.managers.hydra_manager import HydraManager
from app.managers.file_manager import FileManager
from app.managers.airflow_manager import AirflowManager
from app.managers.dvc_manager import DvcManager
from app.managers.graphrag_manager import GraphRagManager
from app.managers.rag_manager import RagManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm", tags=["llm"])

llm_mgr = LLMRouter()
notebook_mgr = NotebookManager()
mlflow_mgr = MlflowManager()
hydra_mgr = HydraManager()
file_mgr = FileManager()
airflow_mgr = AirflowManager()
dvc_mgr = DvcManager()
rag_mgr = RagManager()
graphrag_mgr = GraphRagManager()
memory = ProjectMemory()

# Manager dict passed to context builder and tool executor
# "llm" entry allows run_agent tool to spawn subagents via the Anthropic API
# "rag" entry backs search_docs; graceful degrade if noted-rag is unreachable
_managers = {
    "notebook": notebook_mgr,
    "mlflow": mlflow_mgr,
    "hydra": hydra_mgr,
    "files": file_mgr,
    "airflow": airflow_mgr,
    "dvc": dvc_mgr,
    "llm": llm_mgr,
    "rag": rag_mgr,
    "graphrag": graphrag_mgr,
}

# Maximum tool call rounds to prevent infinite loops, runaway costs, and
# context-window overflow. Bumped from 6 (2026-05-05) to accommodate
# multi-step agentic workflows like "fetch_url + append_to_doc per URL"
# across 5+ URLs. At 12 a typical "summarise these 5 sites into a report"
# request completes in one turn (10 rounds: 5 fetch + 5 append) with
# headroom; pathological loops still hit the cap before becoming costly.
MAX_TOOL_ROUNDS = 12

# Pending write actions awaiting user confirmation
# Key: action_id (str) -> {"action": dict, "messages": list, "memory_key": str, "request": ChatRequest}
_pending_actions = {}

# Compaction prompt
COMPACTION_PROMPT = (
    "Summarize the following conversation concisely. "
    "Preserve key facts, decisions, and context that would help continue the conversation. "
    "Focus on what was discussed, what was concluded, and any pending questions. "
    "Keep the summary under 300 words.\n\n"
)


# ── Request / response models ────────────────────────────────────

class ContextDescriptor(BaseModel):
    project_id: Optional[str] = None
    notebook_path: Optional[str] = None
    notebook_cells: Optional[list[dict]] = None
    file_path: Optional[str] = None
    file_content: Optional[str] = None
    selected_cell_indices: Optional[list[int]] = None
    active_run_id: Optional[str] = None
    hydra_config_hash: Optional[str] = None
    dvc_hash: Optional[str] = None
    dag_id: Optional[str] = None

class ChatRequest(BaseModel):
    # Either plain text (text-only chat — the common case) or an
    # OpenAI-style content list for multimodal input. Each block in the
    # list is a dict like:
    #   {"type": "text", "text": "..."}
    # or
    #   {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}
    # The list shape is forwarded UNCHANGED to memory.append and the
    # LLM call (agent_server's openai_compat.ChatMessage.content already
    # accepts the same Union; llama-server's vision handler renders the
    # image_url blocks via mmproj). Heuristic / preview / logging paths
    # use _message_text() to flatten to plain text without losing the
    # original payload.
    message: Union[str, list[dict]]
    client_id: str = "default"
    context_descriptor: Optional[ContextDescriptor] = None
    think_enabled: bool = True
    # Per-turn retrieval toggles. Both default true for back-compat.
    # When false, the corresponding tools are dropped from the LLM's
    # tool list for THIS turn only — the model never sees them, so no
    # fallback or in-flight cleanup is needed.
    vector_rag_enabled: bool = True
    graph_rag_enabled: bool = True
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=1, le=32768)


# ── Tool call stream filter ────────────────────────────────────────

class ToolCallStreamFilter:
    """Buffers <tool_call>...</tool_call> blocks and raw tool JSON so they never leak to frontend."""

    # Tool names that should be filtered when seen as raw JSON
    _TOOL_NAMES = {'update_cell', 'insert_cell', 'batch_update_cells', 'find_replace_in_cells',
                   'update_file', 'create_file', 'append_to_file',
                   'get_experiment_runs', 'get_run_details',
                   'compare_runs', 'get_file_contents', 'get_hydra_config', 'list_dags',
                   'get_dag_status', 'get_task_log', 'get_dvc_data_overview',
                   'get_dvc_file_history', 'query_knowledge_graph', 'get_skill',
                   'list_files', 'search_files', 'get_notebook_cells', 'run_agent',
                   'scroll_to_cell', 'open_file', 'chart',
                   'create_doc', 'append_to_doc', 'replace_doc', 'read_doc', 'undo_last_change',
                   'get_lint_diagnostics', 'fix_lint_issues'}

    def __init__(self):
        self._buffer = ''
        self._in_tc = False

    def feed(self, token: str):
        """Feed a token. Returns text to send to frontend (may be empty)."""
        import re
        self._buffer += token
        # Inside a <tool_call> block - swallow until closing tag.
        # Two close markers are accepted: `</tool_call>` (OpenAI/anthropic
        # style) and `<tool_call|>` (Gemma 4 style, asymmetric pipes).
        if self._in_tc:
            for close_marker in ('</tool_call>', '<tool_call|>'):
                if close_marker in self._buffer:
                    after = self._buffer.split(close_marker, 1)[1]
                    self._buffer = ''
                    self._in_tc = False
                    if after:
                        return self.feed(after)
                    return ''
            return ''
        # Detect tool-call OPEN markers. Two formats:
        #   `<tool_call>` ........... OpenAI/Anthropic style
        #   `<|tool_call>` .......... Gemma 4 style (asymmetric pipes)
        # The latter was previously missed because `'<tool_call>' in buffer`
        # is False for `<|tool_call>` (the `|` between `<` and `t` breaks
        # the substring match). That hole let the body `call:NAME{...}`
        # fall through to the strip-regex path, which usually catches it -
        # but combined with the think_filt's 17-char tail-hold, race
        # conditions could leave incomplete `call:NAME{...$` in the
        # buffer at stream end and leak verbatim.
        for open_marker in ('<|tool_call>', '<tool_call>'):
            if open_marker in self._buffer:
                before = self._buffer.split(open_marker, 1)[0]
                self._buffer = open_marker + self._buffer.split(open_marker, 1)[1]
                self._in_tc = True
                return before
        # ── Gemma fallback tool-call formats (multi-line, leak past per-chunk
        # strip_gemma_tokens_streaming because the regexes are DOTALL).
        # Format A: `call:NAME{ ... }` (curly-brace alternative)
        # Format B: `tool_code\n ... \n\n` (Python-code alternative)
        # Format C: `tool_output [ {...}, ... ]` (model fabricating tool result)
        # Strip complete blocks; hold the buffer if a block is mid-arrival.
        # Strip any complete `call:name{...}` blocks
        self._buffer = re.sub(r'call:\w+\{[^}]*\}(?:<tool_call\|>)?', '', self._buffer)
        # Hold if buffer ends with a partial `call:` start. This catches the
        # leak that happens BEFORE the `{` ever arrives - tokens `call`, `:`,
        # `search_docs` would otherwise stream verbatim before any guard kicks
        # in. \b ensures we don't trigger on words like "recall".
        if re.search(r'\bcall:?$|\bcall:\w*$|\bcall:\w+\{[^}]*$', self._buffer):
            return ''
        # Strip only COMPLETE `tool_code <body>\n\n` blocks. `\b` matches
        # the word boundary after "tool_code" so we accept space OR newline
        # as the body separator. We deliberately do NOT use `\Z` in the
        # lookahead here - that would strip an unclosed block at end of
        # buffer, eating partial content before it completes. The flush()
        # path uses `\Z` for the final cleanup.
        self._buffer = re.sub(r'tool_code\b.*?(?=\n\n)', '', self._buffer, flags=re.DOTALL)
        # Anything `tool_code\b` left in the buffer is by definition open;
        # hold from the marker onward so the next chunk(s) can complete it.
        m_tc = re.search(r'tool_code\b', self._buffer)
        if m_tc:
            before = self._buffer[:m_tc.start()]
            self._buffer = self._buffer[m_tc.start():]
            return before
        # Format C: `tool_output [ ... ]` - model fabricates a tool result it
        # was never given. Per `tool-call-discipline` skill, the model must
        # never emit this; in practice it sometimes does after using the wrong
        # tool-call syntax (no real tool ran, model fills the gap with fiction).
        # Strip complete bracketed blocks via balanced-bracket scan; hold if
        # the bracket is open. Also handle the older newline-terminated form.
        m_to = re.search(r'tool_output\b', self._buffer)
        if m_to:
            tail = self._buffer[m_to.end():]
            # Skip any whitespace after the marker
            ws_len = len(tail) - len(tail.lstrip())
            body = tail[ws_len:]
            if body.startswith('['):
                # Balanced-bracket scan; respect string quoting so brackets
                # inside strings don't throw off the depth counter.
                depth = 0
                end_idx = -1
                in_str = False
                escape = False
                for i, c in enumerate(body):
                    if escape:
                        escape = False
                        continue
                    if c == '\\' and in_str:
                        escape = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx == -1:
                    # Open bracket - hold from `tool_output` onward
                    before = self._buffer[:m_to.start()]
                    self._buffer = self._buffer[m_to.start():]
                    return before
                # Closed - strip the whole `tool_output[ws][...]` block
                before = self._buffer[:m_to.start()]
                consumed = m_to.end() + ws_len + end_idx
                self._buffer = before + self._buffer[consumed:]
            elif body and not body[0].isspace() and body[0] not in '\n':
                # `tool_output<word>` - looks like prose, not a fabrication
                pass
            else:
                # Newline-terminated form: `tool_output\n<body>\n\n`
                completed = re.search(r'tool_output\b.*?\n\n', self._buffer, flags=re.DOTALL)
                if completed:
                    self._buffer = self._buffer[:m_to.start()] + self._buffer[completed.end():]
                else:
                    # Open - hold from marker onward
                    before = self._buffer[:m_to.start()]
                    self._buffer = self._buffer[m_to.start():]
                    return before
        # Hold back partial '<' that might be start of a tag
        if '<' in self._buffer and len(self._buffer) < 12:
            return ''
        # Hold back partial '{' that might be start of a raw JSON tool call.
        # Streaming delivers one token at a time so '{' may arrive before '"name"'.
        # We hold until the buffer either confirms or rules out a tool call JSON.
        if '{' in self._buffer:
            # Check for full pattern first
            m = re.search(r'\{\s*"name"\s*:\s*"(\w+)"', self._buffer)
            if m:
                if m.group(1) in self._TOOL_NAMES:
                    # Confirmed tool call - find its start and strip it
                    start = m.start()
                    before = self._buffer[:start]
                    rest = self._buffer[start:]
                    depth = 0
                    end = -1
                    for i, c in enumerate(rest):
                        if c == '{': depth += 1
                        elif c == '}': depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                    if end > 0:
                        after = rest[end:]
                        self._buffer = after
                        result = before
                        if after:
                            result += self.feed('')
                        return result
                    else:
                        return ''  # incomplete JSON - hold
                # else: name not a tool - fall through and emit
            else:
                # No full pattern yet - check if buffer could still grow into one.
                # Hold if it ends with a partial prefix of {"name":
                if re.search(r'\{[^}]{0,60}$', self._buffer) and len(self._buffer) < 200:
                    return ''  # hold - might still be growing
                # Buffer is long or closed - not a tool call, emit
        out = self._buffer
        self._buffer = ''
        return out

    def flush(self):
        """Flush remaining buffer. Strip raw JSON tool calls AND Gemma's
        `call:NAME{...}` text format (incomplete or complete) so partial
        tool-call text held by the streaming loop doesn't leak at end-of-
        stream."""
        if not self._buffer or self._in_tc:
            return ''
        import re
        result = self._buffer
        self._buffer = ''
        # Strip complete `call:NAME{...}` blocks (with or without trailing
        # `<tool_call|>` close marker).
        result = re.sub(r'call:\w+\{[^}]*\}(?:<tool_call\|>)?', '', result)
        # If anything still starts with `call:NAME{` and never closed,
        # drop it from that point forward - by definition an incomplete
        # tool call invocation that should never reach the user.
        m_open = re.search(r'\bcall:\w+\{', result)
        if m_open:
            result = result[:m_open.start()]
        # Iteratively remove any tool call JSON using balanced-brace finder
        while True:
            m = re.search(r'\{\s*"name"\s*:\s*"(\w+)"', result)
            if not m or m.group(1) not in self._TOOL_NAMES:
                break
            start = m.start()
            depth = 0
            end = -1
            for i, c in enumerate(result[start:]):
                if c == '{': depth += 1
                elif c == '}': depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
            if end == -1:
                # Incomplete JSON at end of buffer - drop it entirely
                result = result[:start]
                break
            result = result[:start] + result[end:]
        # Final pass: strip any leftover Gemma fallback tool-call blocks that
        # might still be in the buffer at end-of-stream (open `call:foo{` with
        # no closing brace, or open `tool_code <body>` with no terminating
        # blank line). These leak past the streaming filter when they're the
        # LAST thing the model emits before the stream ends.
        # `\b` after `tool_code` matches both space and newline body separators.
        # `\Z` in the tool_code lookahead is safe HERE (we're at end-of-stream).
        result = re.sub(r'call:\w+\{[^}]*\}?(?:<tool_call\|>)?', '', result)
        # Drop any partial `call:NAME` (with or without brace) still hanging.
        result = re.sub(r'\bcall:\w*$', '', result)
        result = re.sub(r'tool_code\b.*?(?=\n\n|\Z)', '', result, flags=re.DOTALL)
        # Reuse the bracket-aware tool_output stripper from gemma_tool_parser
        # so flush() catches the same fabrication shapes the streaming feed()
        # held but couldn't strip (open `[` still without a closing `]`).
        from app.mcp.gemma_tool_parser import _strip_tool_output_bracketed
        result = _strip_tool_output_bracketed(result)
        result = re.sub(r'tool_output\s+.*?(?=\n\n|\Z)', '', result, flags=re.DOTALL)
        return result.strip()


class GemmaThinkingFilter:
    """Streaming filter that translates Gemma 4 thinking blocks into the
    noted frontend's <think>...</think> format so the chat UI renders them
    as a proper collapsible reasoning section instead of inline garbage.

    Gemma emits `<|channel>thought\\n[reasoning]<channel|>[answer]` (and an
    orphan `thought [reasoning]<channel|>` form when the chat template
    consumes the opening `<|channel>`). translate_gemma_thinking() needs
    the entire block - per streaming chunk it can never match - so without
    this filter the raw "thought ..." body leaks token by token.

    Behavior:
      - Outside a block: pass input through, holding back a small tail in
        case a marker is mid-arrival.
      - On detecting an opening marker: emit `<think>` and enter passthrough.
      - Inside a block: stream content live, holding back a tail to detect
        a partial close marker.
      - On detecting `<channel|>`: emit `</think>` and resume normal output.

    The frontend's ThinkingParser handles the `<think>...</think>` pair
    and shows a "thinking" indicator while the close hasn't arrived.
    """

    _START_FULL = '<|channel>thought'   # full opening
    _START_ORPHAN = 'thought '          # orphan opening (chat template ate <|channel>)
    _END = '<channel|>'
    # Hold this many trailing chars when we can't yet rule out a marker
    _TAIL_HOLD = max(len(_START_FULL), len(_END))

    def __init__(self):
        self._in_block = False
        self._buf = ''
        self._seen_any_text = False
        self._opened_think = False  # have we emitted the <think> tag yet?

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ''
        self._buf += chunk
        out_parts: list[str] = []
        while self._buf:
            if self._in_block:
                end_idx = self._buf.find(self._END)
                if end_idx < 0:
                    # Still inside the block; emit safe portion, hold a
                    # tail in case the close marker is mid-arrival.
                    if len(self._buf) > self._TAIL_HOLD:
                        emit = self._buf[:-self._TAIL_HOLD]
                        self._buf = self._buf[-self._TAIL_HOLD:]
                        if emit:
                            out_parts.append(emit)
                    break
                # Block closes here. Emit content before the close marker,
                # then </think>, then exit block state.
                if end_idx > 0:
                    out_parts.append(self._buf[:end_idx])
                out_parts.append('</think>\n')
                self._opened_think = False
                self._buf = self._buf[end_idx + len(self._END):]
                self._in_block = False
                continue
            # Outside a block
            full_idx = self._buf.find(self._START_FULL)
            orphan_idx = -1
            if not self._seen_any_text:
                stripped = self._buf.lstrip()
                if stripped.startswith(self._START_ORPHAN):
                    orphan_idx = len(self._buf) - len(stripped)
            starts = [i for i in (full_idx, orphan_idx) if i >= 0]
            if not starts:
                if len(self._buf) > self._TAIL_HOLD:
                    emit = self._buf[:-self._TAIL_HOLD]
                    self._buf = self._buf[-self._TAIL_HOLD:]
                    if emit:
                        out_parts.append(emit)
                        self._seen_any_text = True
                break
            start = min(starts)
            if start > 0:
                pre = self._buf[:start]
                if pre:
                    out_parts.append(pre)
                    self._seen_any_text = True
            # Open the <think> block in the output stream
            out_parts.append('<think>\n')
            self._opened_think = True
            if start == full_idx:
                self._buf = self._buf[start + len(self._START_FULL):]
            else:
                pos = self._buf.find(self._START_ORPHAN, start)
                self._buf = self._buf[pos + len(self._START_ORPHAN):]
            self._in_block = True
        return ''.join(out_parts)

    def flush(self) -> str:
        out_parts: list[str] = []
        # If we left a thinking block unclosed (defensive), close it.
        if self._in_block:
            if self._buf:
                out_parts.append(self._buf)
                self._buf = ''
            out_parts.append('</think>\n')
            self._opened_think = False
            self._in_block = False
        elif self._buf:
            out_parts.append(self._buf)
            self._buf = ''
        return ''.join(out_parts)


class CitationTagFilter:
    """Strip GraphRAG citation tags from a streaming text. Holds back
    partial bracket sequences so a tag split across chunks is removed
    cleanly (no flicker of half-tags in the UI).

    Recognized tags:
      - [E:entity_id]
      - [R:src>type>tgt]
      - [Cn]                 (community summary index, no colon)
      - [markdown_chunk:hex]

    Tags remain in the upstream tool_result string (memory + downstream
    grounding), only the user-visible stream is cleaned. Plain markdown
    `[link](url)` is untouched (the regex matches only the four prefixes).
    """

    import re as _re
    _TAG = _re.compile(r'\[(?:E:[^\]]*|R:[^\]]*|markdown_chunk:[^\]]*|C\d+)\]')
    # Max bytes of "could-be-growing" tag prefix to hold back at end of stream
    _MAX_PREFIX = 80

    def __init__(self):
        self._buf = ''

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ''
        self._buf += chunk
        # Strip all complete tags first
        cleaned = self._TAG.sub('', self._buf)
        # If the cleaned result ends with an unclosed `[` that could be the
        # start of a tag still arriving, hold it back; otherwise emit all.
        last_open = cleaned.rfind('[')
        if (last_open >= 0
                and ']' not in cleaned[last_open:]
                and len(cleaned) - last_open <= self._MAX_PREFIX):
            emit = cleaned[:last_open]
            self._buf = cleaned[last_open:]
        else:
            emit = cleaned
            self._buf = ''
        return emit

    def flush(self) -> str:
        out = self._TAG.sub('', self._buf)
        self._buf = ''
        return out


# Valid citation tag forms emitted by noted-graph synthesis. Anything
# bracketed that LOOKS LIKE A FAILED CITATION (numeric, hex-ish, or
# starting with a citation prefix but not matching) gets stripped from
# the streamed text. Markdown links `[text](url)` and other bracketed
# prose are left alone — only patterns that look like attempted
# citations are sanitized.
_VALID_CITE_RE = re.compile(
    r'\[(?:'
    r'C\d+'
    r'|E:[^\]]+'
    r'|R:[^\]]+'
    r'|markdown_chunk:[0-9a-f]{8,16}'
    r'|[0-9a-f]{8,16}'
    r')\]'
)
# Pattern for bracketed content that looks like an attempted citation
# (so we know to strip if invalid). Includes pure-numeric and
# comma-joined citation attempts, which Gemma fabricates as `[138]` or
# `[64, 137]` style.
_CITE_LIKE_RE = re.compile(
    r'\[(?:'
    r'\d+(?:\s*,\s*\d+)*'                  # `[138]`, `[64, 137]`
    r'|markdown_chunk:[^\]]*'              # any [markdown_chunk:...]
    r'|C\d+(?:\s*,\s*[^\]]+)*'             # `[C1]` or `[C1, ...]`
    r'|E:[^\]]+(?:\s*,\s*[^\]]+)*'         # `[E:foo]` or `[E:foo, E:bar]`
    r'|R:[^\]]+(?:\s*,\s*[^\]]+)*'         # `[R:src>type>tgt]` etc.
    r'|[0-9a-f]{4,}(?:\s*,\s*[^\]]+)*'     # `[ff563210b963]` (bare hex), `[abc, def]`
    r')\]'
)


class CitationSanitizerFilter:
    """Streaming filter for the chat-path. Buffers `[...]` patterns,
    drops bracketed content that LOOKS like a fabricated citation but
    fails the valid-citation regex. Leaves markdown links and other
    non-citation brackets untouched.
    """

    _MAX_BRACKET_LEN = 200

    def __init__(self) -> None:
        self._in_bracket = False
        self._buf = ''

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ''
        out: list[str] = []
        for ch in chunk:
            if not self._in_bracket:
                if ch == '[':
                    self._in_bracket = True
                    self._buf = ch
                else:
                    out.append(ch)
            else:
                self._buf += ch
                if ch == '[':
                    out.append(self._buf[:-1])
                    self._buf = '['
                elif ch == ']':
                    if _VALID_CITE_RE.fullmatch(self._buf):
                        out.append(self._buf)
                    elif _CITE_LIKE_RE.fullmatch(self._buf):
                        # Looks like a hallucinated citation. Drop.
                        pass
                    else:
                        # Not a citation attempt (e.g., markdown link
                        # text). Keep verbatim.
                        out.append(self._buf)
                    self._in_bracket = False
                    self._buf = ''
                elif len(self._buf) > self._MAX_BRACKET_LEN:
                    out.append(self._buf)
                    self._in_bracket = False
                    self._buf = ''
        return ''.join(out)

    def flush(self) -> str:
        if self._in_bracket:
            tail = self._buf
            self._buf = ''
            self._in_bracket = False
            return tail
        return ''


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/chat")
async def llm_chat(request: ChatRequest):
    """Context-enriched chat with project-scoped memory and tool calling.

    Flow:
    1. Load conversation history from project memory
    2. Check if compaction is needed (auto-summarize old messages)
    3. Assemble: workspace context + history + user message
    4. Stream response with tool call loop
    5. Store user message and assistant response in project memory
    """
    project_id = (request.context_descriptor.project_id
                  if request.context_descriptor else None) or "default"
    memory_key = f"{request.client_id}_{project_id}"

    # Set the per-turn correlation id so every rag-manager call (chat path
    # or speculative) tags its log lines + HTTP headers with it. noted-rag
    # picks the header up via middleware and tags its own EMBED_TIMING /
    # SEARCH_TIMING lines too.
    from app.managers.rag_manager import set_turn_id, set_call_source
    turn_id = set_turn_id()
    # Default source for the chat handler's own work (ctx_message build,
    # main retrieval if any). Speculative coroutine overrides to
    # 'speculative' inside its own context.
    set_call_source("chat")
    logger.info("CHAT_TURN_START turn_id=%s client_id=%s project_id=%s",
                turn_id, request.client_id, project_id)
    # TEMP-DIAG 2026-05-02: trace what the user's message looks like at
    # request entry. Investigating "model said 'no specific request' for a
    # turn the user clearly typed". Strip if confirmed unrelated.
    # Multimodal note: when message is a content list (image attachment),
    # only the text portion is logged — image_url data: URLs are 200 KB+
    # base64 blobs that would flood the log file.
    _msg_preview = _message_text(request.message)
    _has_attachments = isinstance(request.message, list) and any(
        isinstance(b, dict) and b.get("type") == "image_url" for b in request.message
    )
    logger.info("CHAT_TURN_USER_MESSAGE turn_id=%s len=%d has_attachments=%s repr=%r",
                turn_id, len(_msg_preview), _has_attachments, _msg_preview[:200])

    try:
        # ── 1. Compaction check ──────────────────────────────────
        compaction_input = await memory.get_compaction_input(memory_key)
        if compaction_input:
            logger.info("Compacting history for project %s", project_id)
            try:
                summary_resp = await llm_mgr.complete(
                    COMPACTION_PROMPT + compaction_input,
                    max_tokens=512,
                )
                choices = summary_resp.get("choices", [])
                if choices:
                    summary_text = choices[0].get("message", {}).get("content", "")
                    if summary_text:
                        await memory.compact(memory_key, summary_text)
            except Exception as e:
                logger.warning("Compaction failed, continuing without: %s", e)

        # ── 2. Store user message ────────────────────────────────
        await memory.append(memory_key, "user", request.message)

        # ── 3. Build context ────────────────────────────────────
        ctx_dict = request.context_descriptor.model_dump() if request.context_descriptor else {}
        logger.info("Context: project_id=%s notebook_path=%s", ctx_dict.get('project_id'), ctx_dict.get('notebook_path'))

        # Per-request managers: extend shared managers with in-memory notebook cells
        # so get_notebook_cells uses the browser's current state, not stale disk content.
        # _tool_metadata is a side-channel slot; tools that need to emit structured
        # data alongside their string return value (e.g. graph_and_vector_search
        # surfacing the subgraph for the trace UI) write into it. The router resets
        # it before each tool dispatch and emits any stashed payload as SSE.
        req_managers = {
            **_managers,
            "notebook_cells_override": ctx_dict.get("notebook_cells"),
            "_tool_metadata": {},
        }

        # Speculative retrieval — re-enabled 2026-05-03 after the unified
        # llama-server router refactor (Phase 9). Original disable reason
        # was measured prod-side rerank_gpu_ms = 2-5s when overlapping with
        # Gemma's prefill under the SPLIT architecture (bge in noted-rag's
        # separate llama-cpp-python process). Re-measured under the unified
        # router (gemma-4 + bge-m3 + bge-reranker in one llama-server
        # process with continuous batching): overlap rerank ≈ 322 ms, only
        # ~2× warm-baseline 157 ms. See `/tmp/spec_contention_probe.py`
        # results in conversation history 2026-05-03. Net win is ~500 ms-
        # 1 s per tool-using turn (the entire pre-call thinking window
        # gets hidden behind the speculative call's wall time).
        #
        # Eligibility: only when graph_and_vector_search is in the toolset
        # (both vector_rag + graph_rag enabled) AND the user message is
        # substantive (≥10 chars). Cache-hit logic in
        # llm_tools.execute_tool requires exact match on `args.question`;
        # we speculate using the user's verbatim message which the model
        # tends to lightly rephrase, so hit rate isn't 100%. Misses fall
        # through to fresh dispatch with the discarded spec task cancelled
        # in the cleanup at the end of this request (around line ~1573).
        # Speculative retrieval is text-driven (Jaccard match against
        # the user's verbatim words). For multimodal payloads we use
        # the text portion only; image_url blocks aren't queryable
        # against the corpus.
        _spec_text = _message_text(request.message)
        if (
            request.vector_rag_enabled
            and request.graph_rag_enabled
            and _spec_text
            and len(_spec_text) >= 10
        ):
            # Build the spec query. For follow-up questions ("how does this
            # relate to X", "tell me more"), the model uses prior-turn
            # context to resolve "this" → "<prior topic>" before forming
            # its tool_call. The verbatim user message alone often misses
            # those tokens, blowing the Jaccard match. Solution: enrich
            # the spec query with the tail of the previous assistant
            # message, restoring the topic tokens the model will use.
            # First-turn questions (no prior assistant) fall back to
            # verbatim — no enrichment, no harm.
            spec_question = _spec_text
            try:
                _hist = await memory.get_messages_for_llm(memory_key)
                _last_asst = next(
                    (m.get("content", "") for m in reversed(_hist or [])
                     if m.get("role") == "assistant" and m.get("content")),
                    "",
                )
                if _last_asst:
                    # Defensive strip of thinking blocks even though stored
                    # history is supposed to be clean.
                    _clean = re.sub(r"<think>.*?</think>\s*", "", _last_asst, flags=re.DOTALL).strip()
                    if _clean:
                        # Take the last full sentence (period-bounded) if
                        # close enough to the end; otherwise fall back to
                        # the last 300 chars. Bounds keep the spec query
                        # focused — too much prior context dilutes the
                        # retrieval signal.
                        _last_dot = _clean.rfind(".", 0, max(0, len(_clean) - 1))
                        if _last_dot >= len(_clean) - 400 and _last_dot > 0:
                            _tail = _clean[_last_dot + 1:].strip()
                        else:
                            _tail = _clean[-300:].strip()
                        if _tail:
                            spec_question = f"{_tail} {spec_question}"
            except Exception:
                pass  # best-effort enrichment; fall back to user verbatim
            spec_metadata: dict = {}
            spec_managers = {**req_managers, "_tool_metadata": spec_metadata}
            spec_args = {"question": spec_question}
            spec_task = asyncio.create_task(
                _tool_graph_and_vector_search(spec_args, spec_managers)
            )
            req_managers["_speculative"] = {
                "args": spec_args,
                "task": spec_task,
                "metadata": spec_metadata,
                "started_at": time.perf_counter(),
                "consumed": False,
            }
            logger.info(
                "SPECULATIVE_LAUNCH tool=graph_and_vector_search question=%r (enriched=%s)",
                spec_args["question"][:200],
                "yes" if spec_question != _spec_text else "no",
            )

        ctx_message, active_skills = await build_context_message(ctx_dict, _managers)
        dbg = get_debug_log()

        # Log auto-injected skills
        for skill_name in active_skills:
            dbg.log_skill_load(skill_name, auto=True, client_id=request.client_id)

        # ── 4. Assemble messages for LLM ─────────────────────────
        messages = []
        if ctx_message:
            messages.append(ctx_message)

        # Add conversation history (clean, no context blocks)
        history = await memory.get_messages_for_llm(memory_key)
        messages.extend(clean_history(history))

        # Think mode: Anthropic uses /think directive, Gemma uses <|think|> system prompt prefix
        _is_anthropic = llm_mgr._is_anthropic(llm_mgr._active_model)
        if _is_anthropic:
            # Anthropic: append /think or /no_think to last user message
            think_tag = " /think" if request.think_enabled else " /no_think"
            for m in reversed(messages):
                if m.get("role") == "user":
                    m["content"] = m["content"] + think_tag
                    break
        else:
            # Gemma 4: prepend <|think|> to first system/context message when thinking enabled
            if request.think_enabled and messages:
                first = messages[0]
                content = first.get("content", "")
                if isinstance(content, str) and not content.startswith("<|think|>"):
                    messages[0] = {**first, "content": "<|think|>\n" + content}

        # Estimate input tokens (~4 chars per token). Multimodal user
        # messages have list content — sum the text portions only;
        # image_url base64 payloads are not LLM input tokens (the
        # vision encoder consumes them out-of-band).
        def _content_text_chars(c):
            if isinstance(c, str):
                return len(c)
            if isinstance(c, list):
                return sum(len(b.get("text", "")) for b in c
                           if isinstance(b, dict) and b.get("type") == "text")
            return 0
        input_chars = sum(_content_text_chars(m.get("content", "")) for m in messages)
        input_tokens_est = input_chars // 4

        # TEMP-DIAG 2026-05-02: dump the role+last-100-chars of each
        # message about to be sent to the LLM. Shows whether the user's
        # question actually reached the model. Strip if confirmed unrelated.
        # Multimodal payloads are summarised by content-block kinds so
        # the log doesn't dump 200 KB image data: URLs.
        for _i, _m in enumerate(messages):
            _c = _m.get("content", "")
            if isinstance(_c, list):
                _summary = "+".join(b.get("type", "?") for b in _c if isinstance(b, dict))
                _text = " ".join(b.get("text", "") for b in _c
                                 if isinstance(b, dict) and b.get("type") == "text")
                logger.info("CHAT_TURN_LLM_MSG turn_id=%s idx=%d role=%s blocks=[%s] text_len=%d tail=%r",
                            turn_id, _i, _m.get("role"), _summary, len(_text), _text[-200:])
            else:
                _c = _c or ""
                logger.info("CHAT_TURN_LLM_MSG turn_id=%s idx=%d role=%s len=%d tail=%r",
                            turn_id, _i, _m.get("role"), len(_c), _c[-200:])

        # Early usage emit so the chat-bar bottom counter shows real input +
        # budget BEFORE the answer streams. Output ticks up live on the
        # frontend (it accumulates token-event lengths). The authoritative
        # final usage event after [DONE] overrides with end-of-turn counts.
        _early_budget = llm_mgr.get_context_budget()
        # Defer the actual yield until inside the generator below — we
        # reference the variables via closure.

        # ── 5. Stream with tool loop ─────────────────────────────
        _use_native_tools = True  # native for both backends
        # Filter the model-facing tool list to those whose owning Domain
        # is in the active set. `general` tools always present (general
        # is pinned-active); `noted` tools only when noted is activated.
        from app.routers.kb import get_active_domains
        _active_domains = get_active_domains()
        _all_tools = (
            to_anthropic_tools(active_domains=_active_domains) if _is_anthropic
            else to_openai_tools(active_domains=_active_domains)
        )

        # Per-turn retrieval gating. The user's chat-bar checkboxes
        # (`vector_rag_enabled`, `graph_rag_enabled`) deterministically
        # decide WHICH retrieval tool the model can call. The model has
        # no latitude to pick between vector-only / graph-only / both -
        # that's the user's choice. We expose AT MOST ONE retrieval tool
        # per combination:
        #   both ON  -> only graph_and_vector_search (combined)
        #   vec ON,  graph OFF -> only search_docs   (vector)
        #   vec OFF, graph ON  -> only research_topic (graph synthesis)
        #   both OFF -> no retrieval tools at all
        # Read/write workspace tools (get_notebook_cells, update_cell, etc.)
        # are unaffected; this gating only touches the four retrieval ones.
        _ALL_RETRIEVAL = {
            'search_docs',
            'graph_and_vector_search',
            'research_topic',
            'query_knowledge_graph',
        }
        if request.vector_rag_enabled and request.graph_rag_enabled:
            _keep_retrieval = {'graph_and_vector_search'}
        elif request.vector_rag_enabled:
            _keep_retrieval = {'search_docs'}
        elif request.graph_rag_enabled:
            _keep_retrieval = {'research_topic'}
        else:
            _keep_retrieval = set()
        _drop = _ALL_RETRIEVAL - _keep_retrieval

        if _drop:
            def _tname(t):
                # OpenAI: {'function': {'name': ...}}; Anthropic: {'name': ...}
                f = t.get('function') if isinstance(t, dict) else None
                if isinstance(f, dict) and f.get('name'):
                    return f['name']
                return (t or {}).get('name') if isinstance(t, dict) else None
            _all_tools = [t for t in _all_tools if _tname(t) not in _drop]
            logger.info(
                'Tool gating: vector_rag=%s graph_rag=%s -> kept retrieval=%s, dropped=%s',
                request.vector_rag_enabled, request.graph_rag_enabled,
                sorted(_keep_retrieval), sorted(_drop),
            )

        # Dynamic Context Router: filter tools for Anthropic (saves ~2000 tokens/turn),
        # send all tools for local LLM (small models need every tool visible)
        # Tool selection is keyword-driven against the user's text only;
        # multimodal image_url blocks add nothing to the keyword match.
        _native_tools = select_tools(_message_text(request.message), ctx_dict, _all_tools) if _is_anthropic else _all_tools

        async def generate():
            nonlocal _native_tools

            # Emit active skills before streaming starts
            if active_skills:
                yield f"data: {json.dumps({'skills': active_skills})}\n\n"

            # Emit the workspace context block so external test harnesses can
            # see what the Assistant actually received. Frontend ignores this.
            # Truncated to 40K chars to keep the SSE payload reasonable.
            if ctx_message and isinstance(ctx_message.get("content"), str):
                _ctx_preview = ctx_message["content"][:40000]
                yield f"data: {json.dumps({'context_block': {'content': _ctx_preview, 'truncated': len(ctx_message['content']) > 40000}})}\n\n"

            # Early usage so the chat-bar shows real input + budget while
            # the answer is still streaming. Frontend accumulates output
            # token estimates locally as token events arrive; final usage
            # event after [DONE] overrides with authoritative counts.
            yield f"data: {json.dumps({'usage': {'input_tokens': input_tokens_est, 'output_tokens': 0, 'total_tokens': input_tokens_est, 'context_budget': _early_budget}})}\n\n"

            final_answer = ''
            actual_input_tokens = 0
            actual_output_tokens = 0
            actual_context_budget = 0

            # Accumulator for OpenAI-style streamed tool calls (local LLM)
            _openai_tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments_parts}

            def _absorb_chunk(chunk: dict) -> str | None:
                """Extract text content from a chunk; capture real usage if present."""
                nonlocal actual_input_tokens, actual_output_tokens, actual_context_budget
                if chunk.get("usage_tokens"):
                    actual_input_tokens += chunk["usage_tokens"].get("input_tokens", 0)
                    actual_output_tokens += chunk["usage_tokens"].get("output_tokens", 0)
                    actual_context_budget = chunk["usage_tokens"].get("context_budget", 0) or actual_context_budget
                    return None
                # Anthropic native tool call event
                if chunk.get("tool_call"):
                    return None
                choices = chunk.get("choices", [])
                if not choices:
                    return None
                delta = choices[0].get("delta", {})
                # OpenAI-style tool calls in delta (local LLM via llama-cpp-python)
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in _openai_tool_calls:
                            _openai_tool_calls[idx] = {
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments_parts": [],
                            }
                        fn = tc.get("function", {})
                        if fn.get("name") and not _openai_tool_calls[idx]["name"]:
                            _openai_tool_calls[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            _openai_tool_calls[idx]["arguments_parts"].append(fn["arguments"])
                    return None
                return delta.get("content")

            def _collect_tool_calls_from_stream(chunks: list[dict], full_text: str = "") -> list[dict]:
                """Extract native tool_call events from collected stream chunks.

                Structured-only contract: llama-server's chat-template parser
                must produce native `delta.tool_calls` for the asf0 Gemma 4
                template. We deliberately do NOT text-parse `<|tool_call>...`
                from `full_text` as a fallback — silent text-rescue would
                mask llama-server-side parse failures (per
                feedback_no_silent_degradation). If structural parsing
                breaks, the loop should produce no tool_calls and the
                resulting empty answer / error surfaces the regression.
                """
                if _is_anthropic:
                    return [c["tool_call"] for c in chunks if c.get("tool_call")]
                # OpenAI format: assemble from accumulated parts
                calls = []
                for idx in sorted(_openai_tool_calls.keys()):
                    tc = _openai_tool_calls[idx]
                    args_str = ''.join(tc["arguments_parts"])
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse local tool args: %s", args_str[:200])
                        args = {}
                    calls.append({"id": tc["id"], "name": tc["name"], "args": args})
                # Duplicate-call diagnostic (Phase 1E debugging): flag any turn
                # where the same tool name appears more than once so we can
                # trace it back to structured-stream origin.
                names = [c.get('name') for c in calls]
                if len(names) != len(set(names)):
                    logger.info(
                        'tool-call duplicates: names=%s openai_indices=%s raw_text_tail=%r',
                        names,
                        sorted(_openai_tool_calls.keys()),
                        full_text[-600:] if full_text else '',
                    )
                return calls

            def _reset_openai_tool_calls():
                """Reset the accumulator between tool loop rounds."""
                _openai_tool_calls.clear()

            async def _stream_and_collect(msgs, tools=None):
                """Stream LLM response, yield text to frontend, collect full text + tool calls."""
                _reset_openai_tool_calls()
                text_parts = []
                all_chunks = []
                async for chunk in llm_mgr.chat_stream(
                    msgs,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    tools=tools,
                ):
                    all_chunks.append(chunk)
                    content = _absorb_chunk(chunk)
                    if content:
                        text_parts.append(content)
                full_text = ''.join(text_parts)
                native_calls = _collect_tool_calls_from_stream(all_chunks, full_text)
                return full_text, native_calls

            async def _stream_and_yield_sse(msgs, tools=None):
                """Streaming variant of _stream_and_collect.

                Async generator. Yields SSE event strings (`data: ...\\n\\n`) as
                tokens arrive, holding back tool-call markers via the existing
                ToolCallStreamFilter. Final yield is a sentinel dict
                `{'_final': (full_text, native_calls)}` for the caller to extract
                downstream tool-call decisions, just like _stream_and_collect's
                return value. Used for the post-tool reply so the user sees
                tokens as they're generated rather than waiting for the whole
                response to buffer.
                """
                _reset_openai_tool_calls()
                text_parts: list[str] = []
                all_chunks: list[dict] = []
                tc_filt = ToolCallStreamFilter()
                # GemmaThinkingFilter strips multi-line <|channel>thought ...
                # <channel|> blocks during streaming. Without this, Gemma's
                # synthesis-turn reasoning monologue leaks into the chat UI as
                # raw "thoughtTheuserasked..." prose.
                think_filt = GemmaThinkingFilter() if not _is_anthropic else None
                # CitationSanitizerFilter drops fabricated citation tags
                # (e.g. `[138]`, `[64, 137]`, `[markdown_chunk:138]`)
                # before they reach the user. Markdown links and other
                # non-citation brackets pass through untouched.
                cite_filt = CitationSanitizerFilter()
                async for chunk in llm_mgr.chat_stream(
                    msgs,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    tools=tools,
                ):
                    all_chunks.append(chunk)
                    content = _absorb_chunk(chunk)
                    if content:
                        text_parts.append(content)
                        # Thinking-block filter first (consumes <|channel>thought
                        # ...<channel|> blocks), then tool-call filter (strips
                        # <tool_call>...</tool_call>), then per-token cleanup
                        # of stray special tokens. Order matters - the thinking
                        # block can contain text that would confuse the others.
                        out = think_filt.feed(content) if think_filt else content
                        if out:
                            safe = tc_filt.feed(out)
                            if safe:
                                if not _is_anthropic:
                                    safe = strip_gemma_tokens_streaming(safe)
                                if safe:
                                    safe = cite_filt.feed(safe)
                                if safe:
                                    yield f"data: {json.dumps({'token': safe})}\n\n"
                # Flush all filters
                tail_think = think_filt.flush() if think_filt else ''
                if tail_think:
                    safe = tc_filt.feed(tail_think)
                    if safe and not _is_anthropic:
                        safe = strip_gemma_tokens_streaming(safe)
                    if safe:
                        safe = cite_filt.feed(safe)
                    if safe:
                        yield f"data: {json.dumps({'token': safe})}\n\n"
                tail = tc_filt.flush()
                if tail and not _is_anthropic:
                    tail = strip_gemma_tokens_streaming(tail)
                if tail:
                    tail = cite_filt.feed(tail)
                if tail:
                    yield f"data: {json.dumps({'token': tail})}\n\n"
                cite_tail = cite_filt.flush()
                if cite_tail:
                    yield f"data: {json.dumps({'token': cite_tail})}\n\n"
                full_text = ''.join(text_parts)
                native_calls = _collect_tool_calls_from_stream(all_chunks, full_text)
                yield {'_final': (full_text, native_calls)}

            def _make_tool_calls_list(native_calls: list[dict]) -> list[dict]:
                """Normalize native tool calls to [{name, args}] format used by the rest of llm.py."""
                return [{"name": tc["name"], "args": tc.get("args", {}), "id": tc.get("id", "")} for tc in native_calls]

            def _build_assistant_tool_use_message(text: str, tool_calls: list[dict]) -> dict:
                """Build an assistant message with tool calls in the correct format."""
                if _is_anthropic:
                    content = []
                    if text.strip():
                        content.append({"type": "text", "text": text})
                    for tc in tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc["name"],
                            "input": tc.get("args", {}),
                        })
                    return {"role": "assistant", "content": content}
                else:
                    # OpenAI format: assistant message with tool_calls array
                    msg = {"role": "assistant", "content": text or ""}
                    msg["tool_calls"] = [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }
                        for i, tc in enumerate(tool_calls)
                    ]
                    return msg

            def _build_tool_result_message(tool_call_id: str, result: str) -> dict:
                """Build a tool result message in the correct format."""
                if _is_anthropic:
                    return {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": result,
                            }
                        ],
                    }
                else:
                    # OpenAI format: role "tool" with tool_call_id
                    return {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }

            try:
                dbg.log_llm_stream_start(
                    model=llm_mgr._active_model or 'local',
                    provider='anthropic' if _is_anthropic else 'local',
                    client_id=request.client_id)
                dbg.log_api_call(
                    model=llm_mgr._active_model or 'local',
                    messages_count=len(messages),
                    input_tokens=input_tokens_est,
                    client_id=request.client_id)
                dbg.log("context", "sent", {
                    "project_id": ctx_dict.get("project_id", ""),
                    "file_path": ctx_dict.get("file_path", ""),
                    "notebook_path": ctx_dict.get("notebook_path", ""),
                    "user_message": _message_text(request.message)[:100],
                }, client_id=request.client_id)

                def _prepare_text_for_frontend(text: str, intermediate: bool = False) -> str:
                    """Process raw LLM text for frontend display.
                    Anthropic: already clean. Local LLM: translate thinking, strip tool tokens.
                    intermediate=True: also strip any pre-thinking preamble text (model
                    reasoning-out-loud before the formal <|channel>thought block).

                    If the raw text contains a <tool_call|> close token, truncate at the
                    LAST occurrence. Anything the model emits after the final tool call
                    in the same response is speculative text generated before the tool
                    result came back - never the final answer - and would otherwise leak
                    into the UI. This defence works whether the stop sequence fires or
                    not; the stop is belt, this is suspenders.
                    """
                    if _is_anthropic or not text:
                        return text
                    tc_close_idx = text.rfind('<tool_call|>')
                    if tc_close_idx >= 0:
                        text = text[:tc_close_idx + len('<tool_call|>')]
                    text, _ = translate_gemma_thinking(text)
                    text = strip_gemma_tokens(text)
                    if intermediate:
                        # Tool-call turn: drop ALL pre-tool text - the model's
                        # reasoning + conversational lead-in to its tool call
                        # ("The user is asking... I will use X...") is meta-
                        # commentary that just clutters the UI before the real
                        # answer streams in. Even <think>...</think> blocks get
                        # dropped here because the chat UI renders the tags
                        # inline (no collapsible reasoning panel for tool turns).
                        text = ''
                    return text

                # ── Native tool calling (both Anthropic and local) ──
                # Stream the first LLM response per-token so the user sees text
                # as it's generated, not after the whole response is collected.
                # The follow-up after a tool call uses the same path (line ~1161).
                full_text, native_calls = "", []
                async for _ev in _stream_and_yield_sse(messages, tools=_native_tools):
                    if isinstance(_ev, str):
                        yield _ev
                    else:
                        full_text, native_calls = _ev['_final']

                all_calls = _make_tool_calls_list(native_calls)
                tool_call = all_calls[0] if all_calls else None

                # Retry if LLM called an out-of-scope tool. The retry stays
                # buffered (collect-only) because we already streamed an
                # out-of-scope attempt to the user; a second round of streamed
                # text would duplicate it. Buffered fallback yields nothing.
                if tool_call:
                    selected_names = set()
                    for t in _native_tools:
                        selected_names.add(t.get("name") or t.get("function", {}).get("name", ""))
                    if tool_call["name"] not in selected_names:
                        logger.info("Out-of-scope tool '%s', expanding and retrying", tool_call["name"])
                        _native_tools = expand_tools_for_retry(_native_tools, tool_call["name"], _all_tools)
                        full_text, native_calls = await _stream_and_collect(messages, tools=_native_tools)
                        all_calls = _make_tool_calls_list(native_calls)
                        tool_call = all_calls[0] if all_calls else None

                # ── Write tools: batch all into one confirmation ──
                write_calls = [tc for tc in all_calls if is_write_tool(tc)]
                if write_calls:
                    loop_messages = list(messages)
                    loop_messages.append(_build_assistant_tool_use_message(full_text, write_calls))

                    # Snapshot the ORIGINAL tool args (pre-prepare_write_action)
                    # so the tool_badge accurately reflects what the model sent.
                    # prepare_write_action mutates wc["args"] (e.g. 1-based -> 0-based
                    # conversion for update_cell), so reading wc.args later would
                    # show the converted value instead of the model's emission.
                    badge_snapshots = [
                        {"name": wc["name"], "args": copy.deepcopy(wc.get("args", {}))}
                        for wc in write_calls
                    ]

                    actions = []
                    for wc in write_calls:
                        logger.info("Write tool: %s args_keys=%s full_len=%d", wc["name"], list(wc["args"].keys()), len(json.dumps(wc["args"])))
                        if wc["name"] == "batch_update_cells":
                            batch_actions = await expand_batch_tool(wc, req_managers, ctx_dict)
                            actions.extend(batch_actions)
                        elif wc["name"] == "find_replace_in_cells":
                            fr_actions = await expand_find_replace_tool(wc, req_managers, ctx_dict)
                            actions.extend(fr_actions)
                        else:
                            act = await prepare_write_action(wc, req_managers, ctx_dict)
                            act["tool_use_id"] = wc.get("id", "")
                            actions.append(act)
                            if "_extra_actions" in act:
                                actions.extend(act.pop("_extra_actions"))

                    # Emit a tool_badge per original write tool call so external
                    # observers (harness, evaluators) can see WHAT the model
                    # actually called, independent of whether the call
                    # produced actionable items. Do this BEFORE the empty-
                    # actions short-circuit so the badge is always present.
                    for snap in badge_snapshots:
                        yield f"data: {json.dumps({'tool_badge': snap})}\n\n"
                    _write_tool_badge_emitted = True

                    if not actions:
                        # The expansion produced nothing. Distinguish the two
                        # legitimate causes so the model (and harness) see an
                        # accurate outcome instead of a generic parse error:
                        #   - find_replace_in_cells: 0 cells matched the pattern
                        #   - everything else: the args really were unparseable
                        primary = write_calls[0].get("name", "")
                        if primary == "find_replace_in_cells":
                            _args = write_calls[0].get("args", {})
                            error_msg = (
                                f"No cells matched the pattern {_args.get('pattern', '')!r}. "
                                "Either the pattern does not exist in the notebook, or no "
                                "targeted cells contained it. Nothing was changed."
                            )
                        else:
                            error_msg = (
                                "Error: could not parse tool arguments. The 'updates' field must be a "
                                "list of objects, each with cell_index (int), new_content (str), "
                                "description (str). Retry with a properly-formatted call."
                            )
                        logger.warning("Write tool '%s' produced no actionable items: %s", primary, error_msg)
                        loop_messages.append(_build_tool_result_message("", error_msg))
                        yield f"data: {json.dumps({'tool_result': {'name': primary, 'result': error_msg, 'truncated': False}})}\n\n"
                        yield f"data: [DONE]\n\n"
                        return
                    import uuid
                    batch_id = str(uuid.uuid4()) if len(actions) > 1 else actions[0]["id"]
                    pending_data = {
                        "action": actions[0],
                        "actions": actions,
                        "batch_id": batch_id,
                        "messages": loop_messages,
                        "memory_key": memory_key,
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    }
                    _pending_actions[batch_id] = pending_data
                    for act in actions:
                        act["batch_id"] = batch_id
                        _pending_actions[act["id"]] = pending_data

                    if len(actions) == 1:
                        yield f"data: {json.dumps({'pending_action': actions[0]})}\n\n"
                    else:
                        yield f"data: {json.dumps({'pending_actions': actions})}\n\n"

                    final_answer = full_text
                    yield f"data: [DONE]\n\n"
                    clean_partial = _strip_thinking_and_tools(final_answer)
                    if clean_partial:
                        await memory.append(memory_key, "assistant", clean_partial)
                    return

                # ── Read tools: loop ──
                used_read_tool_loop = False
                if tool_call:
                    used_read_tool_loop = True
                    loop_messages = list(messages)
                    loop_messages.append(_build_assistant_tool_use_message(full_text, all_calls))

                    for round_num in range(MAX_TOOL_ROUNDS):
                        logger.info("Tool call (round %d): %s(%s)", round_num + 1,
                                    tool_call["name"], json.dumps(tool_call["args"])[:200])
                        dbg.log_tool_call(tool_call["name"], tool_call.get("args"), client_id=request.client_id)
                        # Reset per-round flag for Phase 3 deep-stream so Phase 2
                        # bypass below knows whether tokens were already emitted.
                        _research_streamed_already = False

                        # Send tool badge to frontend
                        yield f"data: {json.dumps({'tool_badge': {'name': tool_call['name'], 'args': tool_call.get('args', {})}})}\n\n"

                        # ── Navigate tool: yield UI event, no manager call needed ──
                        if tool_call["name"] == "scroll_to_cell":
                            # LLM sends 1-based; frontend expects 0-based
                            cell_index_1 = int(tool_call["args"].get("cell_index", 1))
                            cell_index_0 = cell_index_1 - 1 if cell_index_1 > 0 else 0
                            yield f"data: {json.dumps({'navigate': {'cell_index': cell_index_0}})}\n\n"
                            tool_result = f"Cell {cell_index_1} is now visible."
                        elif tool_call["name"] == "chart":
                            # Two-stage: (1) call chart_designer to get a
                            # ChartIntent JSON from the natural-language
                            # description; (2) hand that intent to the
                            # deterministic builder in app/charts.py to
                            # produce an ECharts option dict; (3) emit
                            # SSE event for the frontend to render.
                            from app import charts as _charts
                            from app.managers.llm_manager import LLM_BASE_URL as _LLM_BASE_URL
                            args = tool_call.get("args") or {}
                            description = (args.get("description") or "").strip()
                            project_id = (args.get("project_id") or "").strip() or None
                            if not description:
                                tool_result = "chart: missing 'description' argument."
                            else:
                                # Stage 1: chart_designer call.
                                user_msg = description
                                if project_id:
                                    user_msg = f"(default project_id: {project_id})\n{description}"
                                designer_payload = {
                                    "model": "chart_designer",
                                    "messages": [{"role": "user", "content": user_msg}],
                                    "stream": False,
                                    "max_tokens": 4096,
                                    "chat_template_kwargs": {"enable_thinking": False},
                                }
                                try:
                                    async with httpx.AsyncClient(timeout=60) as _c:
                                        _r = await _c.post(
                                            f"{_LLM_BASE_URL}/v1/chat/completions",
                                            json=designer_payload,
                                        )
                                    if _r.status_code != 200:
                                        tool_result = (
                                            f"chart: chart_designer call failed "
                                            f"(HTTP {_r.status_code}): {_r.text[:200]}"
                                        )
                                    else:
                                        _data = _r.json()
                                        _content = (_data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                                        try:
                                            intent = json.loads(_content)
                                        except Exception as _e:
                                            tool_result = (
                                                f"chart: chart_designer returned non-JSON "
                                                f"({type(_e).__name__}: {_e}). Raw: {_content[:200]}"
                                            )
                                            intent = None
                                        if intent is not None:
                                            # Stage 2: build option.
                                            projects_root = os.environ.get("PROJECTS_DIR", "/app/data/projects")
                                            result = _charts.build_chart_option(intent, projects_root)
                                            if result["ok"]:
                                                # Stage 3: emit chart event.
                                                chart_payload = {
                                                    "option": result["option"],
                                                    "title": result.get("title", ""),
                                                    "chart_type": result.get("chart_type", ""),
                                                }
                                                yield f"data: {json.dumps({'chart': chart_payload})}\n\n"
                                                tool_result = (
                                                    f"Rendered a {result['chart_type']} chart titled "
                                                    f"'{result.get('title', '')}' in the chat. "
                                                    f"The user can now see it."
                                                )
                                            else:
                                                tool_result = (
                                                    f"chart: render failed — {result.get('error', 'unknown error')}. "
                                                    f"Intent was: {json.dumps(intent)[:200]}"
                                                )
                                except httpx.RequestError as _e:
                                    tool_result = f"chart: agent_server unreachable: {_e}"
                        elif tool_call["name"] == "open_file":
                            # UI-action tool: tells the frontend to open the
                            # named file in the appropriate tab (notebook /
                            # source / document / media) — same action as
                            # double-clicking in the Explorer. No backend
                            # work; the SSE event hands off to the frontend
                            # and we synthesise a confirmation string for
                            # the LLM's chat memory.
                            args = tool_call.get("args") or {}
                            path = (args.get("path") or "").strip()
                            if not path:
                                tool_result = "open_file: missing 'path' argument."
                            else:
                                ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
                                if ext == "ipynb":
                                    kind = "notebook"
                                elif ext in {"pdf", "docx", "pptx", "html", "htm", "md", "markdown"}:
                                    kind = "document"
                                elif ext in {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg",
                                             "mp3", "wav", "m4a", "ogg", "flac", "mp4", "webm"}:
                                    kind = "media"
                                else:
                                    kind = "source"
                                payload = {
                                    "path": path,
                                    "kind": kind,
                                    "project_id": (args.get("project_id") or "").strip() or None,
                                    "domain_id": (args.get("domain_id") or "").strip() or None,
                                }
                                yield f"data: {json.dumps({'open_file': payload})}\n\n"
                                where = (
                                    f"project '{payload['project_id']}'" if payload['project_id']
                                    else f"domain '{payload['domain_id']}'" if payload['domain_id']
                                    else "the active workspace"
                                )
                                tool_result = (
                                    f"Opened {path} in noted as a {kind} tab "
                                    f"({where}). The user can now see it."
                                )
                        elif tool_call["name"] in ("create_doc", "append_to_doc", "replace_doc", "read_doc"):
                            # Take-Notes capability (NOTES-1): the assistant
                            # creates/edits an in-memory document buffer.
                            # Buffer state lives in app.managers.notes_buffer
                            # (singleton). After every op we emit a `data.doc`
                            # SSE event with the full new content so the
                            # frontend document viewer redraws live, and we
                            # return a short confirmation (or the content for
                            # read_doc) to the LLM. Mutations push a pre-state
                            # snapshot to undo_history (NOTES-4).
                            from app.managers import notes_buffer as _notes
                            from app.managers import undo_history as _undo
                            args = tool_call.get("args") or {}
                            op = tool_call["name"]
                            buf = None
                            tool_result = None
                            if op == "create_doc":
                                name = (args.get("name") or "").strip() or None
                                initial = args.get("initial_content") or ""
                                buf = _notes.create(name=name, initial_content=initial)
                                tool_result = (
                                    f"Created document '{buf.name}' (buffer_id={buf.buffer_id}). "
                                    f"It is open in the middle panel and lives only in memory until "
                                    f"the user clicks Save. Use this buffer_id for subsequent "
                                    f"append_to_doc / replace_doc / read_doc calls."
                                )
                            elif op == "append_to_doc":
                                bid = (args.get("buffer_id") or "").strip()
                                content = args.get("content") or ""
                                separator = args.get("separator")
                                if separator is None:
                                    separator = "\n\n"
                                if not bid:
                                    tool_result = "append_to_doc: missing 'buffer_id' argument."
                                else:
                                    pre = _notes.get(bid)
                                    if pre:
                                        _undo.push(f"buffer:{bid}", {
                                            "kind": "buffer", "buffer_id": bid,
                                            "name": pre.name, "content": pre.content,
                                            "path": pre.path,
                                        })
                                    buf = _notes.append(bid, content, separator=separator)
                                    if not buf:
                                        tool_result = f"append_to_doc: no buffer with buffer_id={bid}."
                                    else:
                                        tool_result = (
                                            f"Appended {len(content)} chars to '{buf.name}'. "
                                            f"Document now {len(buf.content)} chars total."
                                        )
                            elif op == "replace_doc":
                                bid = (args.get("buffer_id") or "").strip()
                                content = args.get("content") or ""
                                if not bid:
                                    tool_result = "replace_doc: missing 'buffer_id' argument."
                                else:
                                    pre = _notes.get(bid)
                                    if pre:
                                        _undo.push(f"buffer:{bid}", {
                                            "kind": "buffer", "buffer_id": bid,
                                            "name": pre.name, "content": pre.content,
                                            "path": pre.path,
                                        })
                                    buf = _notes.replace(bid, content)
                                    if not buf:
                                        tool_result = f"replace_doc: no buffer with buffer_id={bid}."
                                    else:
                                        tool_result = (
                                            f"Replaced content of '{buf.name}'. "
                                            f"Document is now {len(buf.content)} chars total."
                                        )
                            elif op == "read_doc":
                                bid = (args.get("buffer_id") or "").strip()
                                if not bid:
                                    tool_result = "read_doc: missing 'buffer_id' argument."
                                else:
                                    buf = _notes.get(bid)
                                    if not buf:
                                        tool_result = f"read_doc: no buffer with buffer_id={bid}."
                                    else:
                                        tool_result = (
                                            f"Document '{buf.name}' ({len(buf.content)} chars):\n\n"
                                            f"{buf.content}"
                                        )
                            if buf is not None:
                                yield f"data: {json.dumps({'doc': _notes.to_dict(buf)})}\n\n"
                        elif tool_call["name"] == "undo_last_change":
                            # NOTES-4 undo. Target is either `buffer:<id>` or
                            # `file:<project_id>/<path>` (or `file:<path>` —
                            # legacy form). Pops the most recent snapshot and
                            # restores it: buffers via notes_buffer.replace,
                            # files via file_manager.write_file. After
                            # restoration we emit the corresponding refresh
                            # event (data.doc / data.file_changed). No
                            # approval gate — undo is the user's explicit
                            # ask and restores prior state, not arbitrary
                            # content.
                            from app.managers import notes_buffer as _notes
                            from app.managers import undo_history as _undo
                            args = tool_call.get("args") or {}
                            target = (args.get("target") or "").strip()
                            if not target:
                                tool_result = "undo_last_change: missing 'target' argument."
                            else:
                                snap = _undo.pop(target)
                                if not snap:
                                    tool_result = f"undo_last_change: no prior snapshot to undo for {target!r}."
                                elif snap.get("kind") == "buffer":
                                    bid = snap.get("buffer_id") or ""
                                    restored = _notes.replace(bid, snap.get("content", ""))
                                    if not restored:
                                        tool_result = f"undo_last_change: buffer {bid} no longer exists."
                                    else:
                                        yield f"data: {json.dumps({'doc': _notes.to_dict(restored)})}\n\n"
                                        tool_result = (
                                            f"Reverted '{restored.name}' to its prior state "
                                            f"({len(restored.content)} chars). "
                                            f"{_undo.depth(target)} earlier snapshot(s) remain."
                                        )
                                elif snap.get("kind") == "file":
                                    project_id = snap.get("project_id") or ""
                                    path = snap.get("path") or ""
                                    content = snap.get("content", "") or ""
                                    if not project_id or not path:
                                        tool_result = "undo_last_change: snapshot missing project_id or path."
                                    else:
                                        try:
                                            from app.managers.project_registry import get_registry
                                            from app.managers.file_manager import FileManager as _FM
                                            registry = get_registry()
                                            clean_id = registry.clean_id(project_id)
                                            root_type = "mount" if registry.is_mount(clean_id) else "project"
                                            _FM().write_file(root_type, clean_id, path, content)
                                            yield f"data: {json.dumps({'file_changed': {'path': path, 'project_id': clean_id}})}\n\n"
                                            tool_result = (
                                                f"Reverted {clean_id}/{path} to its prior state "
                                                f"({len(content)} chars). "
                                                f"{_undo.depth(target)} earlier snapshot(s) remain."
                                            )
                                        except Exception as _e:
                                            tool_result = f"undo_last_change: write failed: {type(_e).__name__}: {_e}"
                                else:
                                    tool_result = f"undo_last_change: unknown snapshot kind {snap.get('kind')!r}."
                        elif (tool_call["name"] == "research_topic"
                              and (tool_call.get("args") or {}).get("mode", "auto") in ("auto", "local", "global")):
                            # Deep-stream research_topic by hitting noted-graph's
                            # /research/query/stream and forwarding tokens to
                            # the user as they arrive. Modes that stream:
                            #   local  -> local_mode_stream (community-driven)
                            #   global -> global_mode_stream (community-driven)
                            #   auto   -> falls back to non-streaming envelope
                            #             on the noted-graph side (auto picks
                            #             between local/global by citation
                            #             count; not a streaming primitive).
                            # The tool_result string is reconstructed from the
                            # streamed tokens + done event for memory
                            # persistence + the Phase 2 bypass detection
                            # (which expects a real answer string, not the
                            # unavailable/error prefixes).
                            import httpx as _httpx
                            _GRAPH_URL = os.environ.get("GRAPH_URL", "http://noted-graph:5523")
                            _stream_args = dict(tool_call.get("args") or {})
                            # Pass the model's chosen mode through. 'auto'
                            # is mapped to 'local' here (prior behavior) so
                            # we get streaming; 'global' streams via the
                            # new global_mode_stream path. noted-graph's
                            # stream endpoint dispatches accordingly.
                            _model_mode = (_stream_args.get("mode") or "auto").strip()
                            _stream_args["mode"] = "local" if _model_mode == "auto" else _model_mode
                            # Domain routing: model picks via `domain_id`
                            # arg (slug OR human-readable name - both are
                            # accepted via `resolve_domain_id`). Falls
                            # back to first active Domain when absent.
                            from app.routers.kb import resolve_domain_id as _resolve_dom, get_active_domains as _get_active
                            _ds_domain = _resolve_dom((tool_call.get("args") or {}).get("domain_id"))
                            if not _ds_domain:
                                _active = _get_active()
                                _ds_domain = _active[0] if _active else "noted"
                            _accum: list[str] = []
                            _envelope: dict | None = None
                            _stream_failed = False
                            _research_streamed_already = False
                            # Strip Gemma's `call:foo{...}` and `<tool_call>...`
                            # text - the synthesis call has no tools defined,
                            # but Gemma occasionally hallucinates the syntax
                            # anyway and it would leak into the user-visible
                            # stream without this guard.
                            _ds_tc_filt = ToolCallStreamFilter()
                            try:
                                async with _httpx.AsyncClient(timeout=120) as _gc:
                                    async with _gc.stream(
                                        "POST",
                                        f"{_GRAPH_URL}/research/{_ds_domain}/query/stream",
                                        json={"question": _stream_args.get("question", ""),
                                              "mode": _stream_args["mode"]},
                                    ) as _gr:
                                        if _gr.status_code != 200:
                                            _stream_failed = True
                                        else:
                                            _ev_name = "message"
                                            _data_buf: list[str] = []
                                            async for _line in _gr.aiter_lines():
                                                if _line == "":
                                                    if _ev_name == "token" and _data_buf:
                                                        try:
                                                            _payload = json.loads("\n".join(_data_buf))
                                                            _tok = _payload.get("text") if isinstance(_payload, dict) else _payload
                                                            if isinstance(_tok, str) and _tok:
                                                                # Keep raw token in _accum so memory + tool_result
                                                                # see the unfiltered text; only the user-visible
                                                                # stream is filtered.
                                                                _accum.append(_tok)
                                                                _safe = _ds_tc_filt.feed(_tok)
                                                                if _safe:
                                                                    yield f"data: {json.dumps({'token': _safe})}\n\n"
                                                        except Exception:
                                                            pass
                                                    elif _ev_name == "done" and _data_buf:
                                                        try:
                                                            _payload = json.loads("\n".join(_data_buf))
                                                            _envelope = _payload.get("envelope") or _payload
                                                        except Exception:
                                                            pass
                                                    elif _ev_name == "error" and _data_buf:
                                                        _stream_failed = True
                                                    _ev_name = "message"
                                                    _data_buf = []
                                                elif _line.startswith("event:"):
                                                    _ev_name = _line[6:].strip()
                                                elif _line.startswith("data:"):
                                                    _data_buf.append(_line[5:].lstrip())
                            except Exception:
                                logger.exception("research_topic deep-stream failed")
                                _stream_failed = True
                            if _stream_failed or _envelope is None:
                                # Fall back to non-streaming tool dispatch.
                                tool_result = await execute_tool(tool_call, req_managers, ctx_dict)
                            else:
                                # Re-build the tool_result string in the same
                                # shape _tool_research_topic returns: answer +
                                # footer of citations / mode / communities.
                                _ans = "".join(_accum) or (_envelope.get("answer") or "")
                                _cits = _envelope.get("citations") or []
                                _mode_used = _envelope.get("mode") or "local"
                                _comms = _envelope.get("communities_used") or []
                                _built = _envelope.get("graph_built_at")
                                _rip = _envelope.get("rebuild_in_progress")
                                _foot: list[str] = []
                                if _cits:
                                    _foot.append(f"citations: {', '.join(_cits[:10])}")
                                    if len(_cits) > 10:
                                        _foot.append(f"(+{len(_cits) - 10} more)")
                                _foot.append(f"mode={_mode_used}")
                                if _comms:
                                    _foot.append(f"communities={_comms}")
                                if _built:
                                    _foot.append(f"graph_built_at={_built}")
                                if _rip:
                                    _foot.append("rebuild_in_progress=true")
                                _footer = "\n\n---\n" + " | ".join(_foot) if _foot else ""
                                # Surface the GraphRAG subgraph as
                                # graph_provenance so the chat router
                                # emits the trace SSE event and the
                                # frontend's "Show graph" button appears.
                                # Mirror what _tool_research_topic does on
                                # the non-streaming fallback path.
                                _ds_subgraph = _envelope.get("subgraph") or {}
                                _ds_meta = req_managers.get("_tool_metadata")
                                if _ds_meta is not None:
                                    _ds_meta["graph_provenance"] = {
                                        "question": _stream_args.get("question", ""),
                                        "entry_entities": [],
                                        "entities": _ds_subgraph.get("nodes") or [],
                                        "edges": _ds_subgraph.get("edges") or [],
                                        "per_entity_chunks": {},
                                        "per_edge_chunks": [],
                                        "chunk_excerpts": [],
                                        "communities_used": _comms,
                                    }
                                tool_result = _ans + _footer
                                _research_streamed_already = bool(_accum)
                        else:
                            # ── Read tool: execute immediately ──
                            tool_result = await execute_tool(tool_call, req_managers, ctx_dict)
                        logger.info("Tool result length: %d chars", len(tool_result))
                        dbg.log_tool_result(tool_call["name"], len(tool_result), client_id=request.client_id)

                        # Emit a tool_result SSE event so external harnesses (test
                        # runners, evaluators) can capture what the tool returned.
                        # Frontend ignores this event. Truncation budget mirrors
                        # the tools' own in-result truncation (e.g. get_task_log
                        # keeps the last 12k chars) so the judge / evaluator can
                        # verify the full content the model was given.
                        _TOOL_RESULT_SSE_MAX = 16000
                        _tool_result_preview = tool_result[:_TOOL_RESULT_SSE_MAX] if isinstance(tool_result, str) else str(tool_result)[:_TOOL_RESULT_SSE_MAX]
                        yield f"data: {json.dumps({'tool_result': {'name': tool_call['name'], 'result': _tool_result_preview, 'truncated': len(tool_result) > _TOOL_RESULT_SSE_MAX if isinstance(tool_result, str) else False}})}\n\n"

                        # Emit any structured side-data the tool stashed (graph
                        # provenance for the trace UI, etc.) and clear the slot
                        # so subsequent tool calls in this round start fresh.
                        _tool_meta = req_managers.get("_tool_metadata") or {}
                        if _tool_meta.get("graph_provenance"):
                            yield f"data: {json.dumps({'graph_provenance': _tool_meta['graph_provenance']})}\n\n"
                        if _tool_meta:
                            req_managers["_tool_metadata"] = {}

                        # Feed tool result back in the format expected by the backend
                        loop_messages.append(_build_tool_result_message(tool_call.get("id", ""), tool_result))

                        # Phase 2: research_topic returns a complete user-ready
                        # markdown answer with citations. Skip the post-tool LLM
                        # synthesis turn entirely - emit the answer directly.
                        # Saves ~2.5s per research_topic turn (the Assistant
                        # Gemma re-paraphrasing pass). Bypass only when the
                        # tool returned a real answer; fall back to LLM
                        # synthesis when the tool returned an unavailable /
                        # no-answer / error hint so the user still gets a
                        # polite explanation rather than a raw error message.
                        _RESEARCH_FALLBACK_PREFIXES = (
                            "GraphRAG is currently unreachable",
                            "GraphRAG returned no answer",
                            "Error:",
                        )
                        if (tool_call["name"] == "research_topic"
                                and isinstance(tool_result, str)
                                and tool_result
                                and not tool_result.startswith(_RESEARCH_FALLBACK_PREFIXES)):
                            # Skip the one-shot bypass yield when Phase 3 has
                            # already streamed tokens to the user; just set up
                            # final_answer + memory persistence.
                            if not _research_streamed_already:
                                # Yield ONLY the answer portion to the user;
                                # the `\n\n---\n` footer (citations list,
                                # mode, communities, graph_built_at) is
                                # observability metadata, not user content.
                                # Inline `[markdown_chunk:hex]` tags in the
                                # answer body already render as badges;
                                # the footer's flat citation list is just
                                # noise. Keep tool_result intact for
                                # `final_answer` / memory below.
                                _user_visible = tool_result.split("\n\n---\n", 1)[0]
                                yield f"data: {json.dumps({'token': _user_visible})}\n\n"
                            final_answer = tool_result
                            # Clear tool_call so the post-loop "force final answer"
                            # branch (which assumes the loop ran out of rounds
                            # without resolving) doesn't fire and re-synthesize.
                            tool_call = None
                            break

                        # Stream the follow-up response token-by-token through
                        # ToolCallStreamFilter so the user sees text as it's
                        # generated. Final yield carries the collected text +
                        # native tool calls for downstream tool-call detection.
                        followup_text, followup_native_calls = "", []
                        async for _ev in _stream_and_yield_sse(
                            loop_messages, tools=_native_tools):
                            if isinstance(_ev, str):
                                yield _ev
                            else:
                                followup_text, followup_native_calls = _ev['_final']

                        logger.info("Follow-up text (first 300): %s", followup_text[:300])

                        next_calls = _make_tool_calls_list(followup_native_calls)
                        tool_call = next_calls[0] if next_calls else None

                        # If the next call is a write tool, route to confirmation flow.
                        next_write_calls = [tc for tc in next_calls if is_write_tool(tc)]
                        if next_write_calls:
                            # Text portion was already streamed in the loop above.
                            # Skip re-emit; just append the assistant message.

                            loop_messages.append(_build_assistant_tool_use_message(followup_text, next_write_calls))
                            # Snapshot original args before prepare_write_action mutates them.
                            next_badge_snapshots = [
                                {"name": wc["name"], "args": copy.deepcopy(wc.get("args", {}))}
                                for wc in next_write_calls
                            ]
                            actions = []
                            for wc in next_write_calls:
                                logger.info("Write tool (from read loop round %d): %s(%s)",
                                            round_num + 1, wc["name"], json.dumps(wc["args"])[:200])
                                if wc["name"] == "batch_update_cells":
                                    batch_actions = await expand_batch_tool(wc, req_managers, ctx_dict)
                                    actions.extend(batch_actions)
                                elif wc["name"] == "find_replace_in_cells":
                                    fr_actions = await expand_find_replace_tool(wc, req_managers, ctx_dict)
                                    actions.extend(fr_actions)
                                else:
                                    act = await prepare_write_action(wc, req_managers, ctx_dict)
                                    actions.append(act)
                                    if "_extra_actions" in act:
                                        actions.extend(act.pop("_extra_actions"))

                            import uuid as _uuid
                            batch_id = str(_uuid.uuid4()) if len(actions) > 1 else actions[0]["id"]
                            pending_data = {
                                "action": actions[0], "actions": actions,
                                "batch_id": batch_id, "messages": loop_messages,
                                "memory_key": memory_key,
                                "temperature": request.temperature,
                                "max_tokens": request.max_tokens,
                            }
                            _pending_actions[batch_id] = pending_data
                            for act in actions:
                                act["batch_id"] = batch_id
                                _pending_actions[act["id"]] = pending_data

                            # See the earlier write-tool branch for why we emit
                            # tool_badge per original call before pending_action(s).
                            for snap in next_badge_snapshots:
                                yield f"data: {json.dumps({'tool_badge': snap})}\n\n"

                            if len(actions) == 1:
                                yield f"data: {json.dumps({'pending_action': actions[0]})}\n\n"
                            else:
                                yield f"data: {json.dumps({'pending_actions': actions})}\n\n"
                            yield f"data: [DONE]\n\n"
                            return

                        if not tool_call:
                            # Final answer was already streamed in the loop above.
                            final_answer = followup_text
                            break

                        # Another read tool - text portion was already streamed
                        # in the loop above; just record the assistant tool-use
                        # message and continue.
                        loop_messages.append(_build_assistant_tool_use_message(followup_text, next_calls))

                    # Force final answer if tool loop exhausted
                    if tool_call and not is_write_tool(tool_call):
                        logger.info("Tool loop exhausted, forcing final answer")
                        loop_messages.append({
                            "role": "user",
                            "content": (
                                "You have used the maximum number of tool rounds for this turn. "
                                "Briefly summarise what you accomplished with the tool calls above "
                                "and tell the user how to continue (e.g. ask them to confirm before "
                                "you fetch more URLs / process more items). Do not call any more "
                                "tools and do not deliberate further; produce the user-facing answer "
                                "directly."
                            )
                        })
                        # Disable thinking for the forced-final call when on
                        # local Gemma. With thinking enabled the model often
                        # spends its entire output budget reasoning about the
                        # next tool it wanted to call, emits </think>, and
                        # stops with no answer body — the "suspended at end
                        # of thinking" symptom. enable_thinking=False routes
                        # the model straight to the user-facing summary.
                        # Anthropic models have no equivalent flag here; we
                        # rely on the strengthened prompt instead.
                        forced_extra = None
                        try:
                            if not llm_mgr._is_anthropic(llm_mgr._active_model):
                                forced_extra = {"chat_template_kwargs": {"enable_thinking": False}}
                        except Exception:
                            forced_extra = None
                        forced_text = ''
                        async for chunk in llm_mgr.chat_stream(
                            loop_messages,
                            temperature=request.temperature,
                            max_tokens=request.max_tokens,
                            tools=None,
                            extra_body=forced_extra,
                        ):
                            content = _absorb_chunk(chunk)
                            if content:
                                forced_text += content
                                yield f"data: {json.dumps({'token': content})}\n\n"
                        final_answer = forced_text
                else:
                    final_answer = full_text

                # ── 6. Store assistant response ──
                # Read-tool path: persist each loop_messages entry STRUCTURED
                # (assistant.tool_calls + role=tool result + ...) so the asf0
                # chat template renders them in its native pipe-marker format
                # on subsequent turns. Earlier flat-string serialization with
                # `<tool_call>...</tool_call>` markers poisoned the template's
                # `strip_thinking` pass and trained the model to imitate that
                # text format - native parsing then failed and the loop ate
                # 6 rounds before the force-final-answer nudge fired.
                # Non-tool path: strip thinking + tool blocks as before.
                if used_read_tool_loop:
                    skip = len(messages)
                    for msg in loop_messages[skip:]:
                        role = msg.get("role")
                        content = msg.get("content")
                        # Skip the in-loop forcing nudge ("Please provide your
                        # answer now...") - it's a transient prompt scaffold,
                        # not real conversation. Anthropic tool_result wrapper
                        # user messages have list content and pass through.
                        if role == "user" and isinstance(content, str):
                            continue
                        # Strip <think>/<voice> wrappers from raw assistant
                        # content before persisting. Tool_calls structure
                        # passes through untouched.
                        if role == "assistant" and isinstance(content, str):
                            msg = {**msg, "content": _strip_thinking_and_tools(content)}
                        # Skip wholly-empty assistant messages (rare, harmless).
                        if role == "assistant" and not (msg.get("tool_calls") or msg.get("content")):
                            continue
                        await memory.append(memory_key, msg)
                    # The final user-visible answer is generated AFTER the last
                    # loop_messages append (either streamed by the no-more-tools
                    # path or by the force-final-answer synthesis). Persist it
                    # as a fresh assistant message so history shows the answer.
                    final_clean = _strip_thinking_and_tools(final_answer) if final_answer else ''
                    if final_clean:
                        await memory.append(memory_key, {"role": "assistant", "content": final_clean})
                else:
                    assistant_text = _strip_thinking_and_tools(final_answer)
                    if assistant_text:
                        await memory.append(memory_key, {"role": "assistant", "content": assistant_text})

                # ── 7. Send usage (real counts from Anthropic, estimates otherwise) ──
                in_tok = actual_input_tokens or input_tokens_est
                out_tok = actual_output_tokens or (len(final_answer) // 4)
                dbg.log_llm_stream_end(
                    model=llm_mgr._active_model or 'local',
                    tokens_in=in_tok, tokens_out=out_tok,
                    client_id=request.client_id)
                budget = actual_context_budget or llm_mgr.get_context_budget()
                yield f"data: {json.dumps({'usage': {'input_tokens': in_tok, 'output_tokens': out_tok, 'total_tokens': in_tok + out_tok, 'context_budget': budget}})}\n\n"

                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception("LLM stream error")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Cancel any unconsumed speculative retrieval. Hits are
                # marked `consumed=True` in execute_tool so we never cancel
                # a result the LLM ended up using; misses (different tool,
                # different question, no tool, or error path) cancel here.
                spec = req_managers.get("_speculative")
                if spec and not spec.get("consumed"):
                    task = spec.get("task")
                    if task is not None and not task.done():
                        elapsed_ms = (time.perf_counter() - spec.get("started_at", time.perf_counter())) * 1000
                        task.cancel()
                        logger.info(
                            "SPECULATIVE_MISS_CANCELLED elapsed_ms=%.1f question=%r",
                            elapsed_ms, spec.get("args", {}).get("question", "")[:80],
                        )
                    elif task is not None and task.done():
                        # Task finished but result wasn't used (LLM picked a
                        # different tool / no tool). Log so we can measure
                        # waste rate.
                        elapsed_ms = (time.perf_counter() - spec.get("started_at", time.perf_counter())) * 1000
                        logger.info(
                            "SPECULATIVE_MISS_DISCARDED elapsed_ms=%.1f question=%r",
                            elapsed_ms, spec.get("args", {}).get("question", "")[:80],
                        )

        return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",  # tells any nginx-family proxy in the chain to bypass its response buffer; SSE per-token events were getting batched at proxy without this even though `proxy_buffering off` was set
            "Cache-Control": "no-cache",
        },
    )

    except Exception as e:
        logger.exception("LLM chat failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


class ConfirmRequest(BaseModel):
    action_id: str
    approved: bool
    feedback: Optional[str] = None


@router.post("/confirm")
async def llm_confirm(request: ConfirmRequest):
    """Confirm or reject pending write action(s), then stream LLM follow-up."""
    pending = _pending_actions.pop(request.action_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending action not found or expired")

    actions = pending.get("actions") or [pending["action"]]
    loop_messages = pending["messages"]
    memory_key = pending["memory_key"]
    temperature = pending["temperature"]
    max_tokens = pending["max_tokens"]

    # Clean up batch refs
    batch_id = pending.get("batch_id")
    if batch_id:
        for act in actions:
            _pending_actions.pop(act.get("id"), None)
        _pending_actions.pop(batch_id, None)

    # Execute all actions (or reject all)
    _is_anthropic = llm_mgr._is_anthropic(llm_mgr._active_model)
    results = []
    for action in actions:
        if request.approved:
            result = await execute_write_tool(action, _managers)
        else:
            result = f"User rejected: {action['args'].get('description', '')}"
        results.append({"tool": action["tool"], "id": action.get("tool_use_id", ""), "result": result})

    async def _emit_results_prelude():
        """Yield tool_result SSE events so external harnesses / judges see the
        write tool's real output before the follow-up text starts. Also emits
        `data.file_changed` for any successful update_file / create_file so
        the frontend can refresh DocumentViewer / FileEditor instances that
        are currently displaying the touched path (NOTES-3)."""
        _TOOL_RESULT_SSE_MAX = 16000
        for r, act in zip(results, actions):
            preview = r["result"][:_TOOL_RESULT_SSE_MAX] if isinstance(r["result"], str) else str(r["result"])[:_TOOL_RESULT_SSE_MAX]
            yield f"data: {json.dumps({'tool_result': {'name': r['tool'], 'result': preview, 'truncated': isinstance(r['result'], str) and len(r['result']) > _TOOL_RESULT_SSE_MAX}})}\n\n"

            executor = act.get("executor_tool") or act.get("tool", "")
            result_str = r["result"] if isinstance(r["result"], str) else ""
            if (executor in ("update_file", "create_file")
                    and result_str
                    and "successfully" in result_str.lower()
                    and not result_str.lower().startswith("error")):
                file_path = act.get("file_path") or (act.get("args", {}) or {}).get("file_path") or ""
                project_id = act.get("project_id") or ""
                if file_path:
                    yield f"data: {json.dumps({'file_changed': {'path': file_path, 'project_id': project_id}})}\n\n"

    if _is_anthropic:
        # Anthropic: feed results as tool_result content blocks
        content_blocks = []
        for r in results:
            content_blocks.append({
                "type": "tool_result",
                "tool_use_id": r["id"],
                "content": r["result"],
            })
        if request.feedback:
            content_blocks.append({"type": "text", "text": f"User message: {request.feedback}"})
        loop_messages.append({"role": "user", "content": content_blocks})
    else:
        # Local LLM: feed results as tool role messages
        for r in results:
            loop_messages.append({
                "role": "tool",
                "tool_call_id": r["id"],
                "content": r["result"],
            })
        if request.feedback:
            loop_messages.append({"role": "user", "content": request.feedback})

    async def generate():
        try:
            # Emit the executed write tool's result(s) BEFORE the follow-up
            # text so downstream consumers (harness, judge) can verify claims
            # against what the tool actually returned.
            async for ev in _emit_results_prelude():
                yield ev
            followup_parts = []
            actual_in = 0
            actual_out = 0
            actual_budget = 0
            async for chunk in llm_mgr.chat_stream(
                loop_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if chunk.get("usage_tokens"):
                    actual_in += chunk["usage_tokens"].get("input_tokens", 0)
                    actual_out += chunk["usage_tokens"].get("output_tokens", 0)
                    actual_budget = chunk["usage_tokens"].get("context_budget", 0) or actual_budget
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content")
                if content:
                    followup_parts.append(content)

            # Clean Gemma tokens before sending to frontend
            followup_text = ''.join(followup_parts)
            if not _is_anthropic:
                followup_text, _ = translate_gemma_thinking(followup_text)
                followup_text = strip_gemma_tokens(followup_text)
            if followup_text.strip():
                yield f"data: {json.dumps({'token': followup_text})}\n\n"

            # Store follow-up in memory
            clean_answer = _strip_thinking_and_tools(followup_text)
            if clean_answer:
                await memory.append(memory_key, "assistant", clean_answer)

            # Usage (real counts from Anthropic, estimates otherwise)
            input_chars = sum(len(m.get("content", "")) for m in loop_messages)
            in_tok = actual_in or (input_chars // 4)
            out_tok = actual_out or (len(followup_text) // 4)
            budget = actual_budget or 32768
            yield f"data: {json.dumps({'usage': {'input_tokens': in_tok, 'output_tokens': out_tok, 'total_tokens': in_tok + out_tok, 'context_budget': budget}})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("LLM confirm stream error")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",  # tells any nginx-family proxy in the chain to bypass its response buffer; SSE per-token events were getting batched at proxy without this even though `proxy_buffering off` was set
            "Cache-Control": "no-cache",
        },
    )


# ── Skills endpoints ──────────────────────────────────────────────

@router.get("/skills")
async def list_skills():
    """List all available skills with metadata."""
    from app.managers.llm_skills import get_registry
    registry = get_registry()
    skills = []
    for name, meta in registry.list_skills():
        has_refs = registry.has_references(name)
        skills.append({
            "name": name,
            "description": meta.get("description", ""),
            "triggers": meta.get("triggers", []),
            "priority": meta.get("priority", 3),
            "max_tokens": meta.get("max_tokens", 500),
            "has_references": has_refs,
            "domain_id": meta.get("domain_id"),
        })
    return {"skills": skills}


@router.get("/skills/{skill_name}")
async def get_skill_detail(skill_name: str):
    """Get full skill content and metadata."""
    from app.managers.llm_skills import get_registry
    registry = get_registry()
    meta = registry.get_skill_meta(skill_name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    content = registry.get_skill(skill_name)
    return {
        "name": skill_name,
        "description": meta.get("description", ""),
        "triggers": meta.get("triggers", []),
        "priority": meta.get("priority", 3),
        "max_tokens": meta.get("max_tokens", 500),
        "domain_id": meta.get("domain_id"),
        "content": content,
    }


@router.get("/mcp-tools")
async def list_mcp_tools():
    """List all MCP tools available to the AI assistant, with tier, schema,
    and `domain_id` (general or noted). The Explorer Tools branch filters
    by domain_id; the chat assembly filters the model-facing tool list by
    active Domains."""
    from app.mcp.tools import _READ_TOOLS, _WRITE_TOOLS, get_tool_domain

    def _serialize(tool, tier: str) -> dict:
        return {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema or {},
            "tier": tier,
            "domain_id": get_tool_domain(tool.name),
        }

    tools = (
        [_serialize(t, "read") for t in _READ_TOOLS]
        + [_serialize(t, "write") for t in _WRITE_TOOLS]
    )
    return {"tools": tools}


class KgAnswerRequest(BaseModel):
    """Body for /api/llm/kg_answer/stream. The frontend caches the
    KG retrieval payload (entities + edges + chunk_excerpts) and
    posts it back here so the LLM can synthesize an answer using the
    SAME subgraph the panel is rendering - no duplicate BFS round-trip.
    Tokens are piped through CitationTagFilter to strip [E:..] [R:..]
    markup from the user-visible stream (same path the chat uses for
    /research/query/stream).

    P3.2: `kb_id` selects the per-KB Retriever upstream. Defaults to
    'noted' so the legacy chat flow keeps working without a frontend
    change."""
    question: str
    entities: list[dict] = []
    edges: list[dict] = []
    chunk_excerpts: list[dict] = []
    kb_id: str = "noted"


@router.post("/kg_answer/stream")
async def llm_kg_answer_stream(req: KgAnswerRequest):
    import httpx as _httpx
    GRAPH_URL = os.environ.get("GRAPH_URL", "http://noted-graph:5523")

    async def gen():
        # Citation tags pass through verbatim - the frontend renders
        # `[markdown_chunk:hex]` as clickable badges; previously stripped.
        try:
            async with _httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    "POST",
                    f"{GRAPH_URL}/research/{req.kb_id}/synthesize/stream",
                    json={
                        "question": req.question,
                        "entities": req.entities,
                        "edges": req.edges,
                        "chunk_excerpts": req.chunk_excerpts,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode(errors='replace')[:300]
                        yield f"event: error\ndata: {json.dumps({'detail': f'upstream HTTP {resp.status_code}: {body}'})}\n\n"
                        return
                    ev_name = "message"
                    data_buf: list[str] = []
                    async for line in resp.aiter_lines():
                        if line == "":
                            if ev_name == "token" and data_buf:
                                try:
                                    payload = json.loads("\n".join(data_buf))
                                    tok = payload.get("text") if isinstance(payload, dict) else payload
                                    if isinstance(tok, str) and tok:
                                        yield f"event: token\ndata: {json.dumps({'text': tok})}\n\n"
                                except Exception:
                                    pass
                            elif ev_name == "done":
                                yield "event: done\ndata: {}\n\n"
                            elif ev_name == "error" and data_buf:
                                yield f"event: error\ndata: {data_buf[0]}\n\n"
                            ev_name = "message"
                            data_buf = []
                        elif line.startswith("event:"):
                            ev_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data_buf.append(line[5:].lstrip())
        except _httpx.RequestError as e:
            yield f"event: error\ndata: {json.dumps({'detail': f'upstream unreachable: {e}'})}\n\n"
        except Exception as e:
            logger.exception("kg_answer/stream failed")
            yield f"event: error\ndata: {json.dumps({'detail': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(
        gen(),
        media_type='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )


@router.post("/complete")
async def llm_complete(prompt: str, max_tokens: int = 256):
    """Single-turn code completion (Phase E). Returns JSON."""
    try:
        result = await llm_mgr.complete(prompt, max_tokens=max_tokens)
        choices = result.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        return {"completion": text}
    except Exception as e:
        logger.exception("LLM complete failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


_NOTED_SECRET = os.environ.get("NOTED_TERMINAL_SECRET", "")


class ModelSelectRequest(BaseModel):
    model_id: str
    secret: str = ""


@router.post("/model")
async def llm_set_model(request: ModelSelectRequest):
    """Switch the active LLM model. Non-local models require the noted access key."""
    if request.model_id.startswith("claude-") and _NOTED_SECRET:
        if request.secret != _NOTED_SECRET:
            raise HTTPException(status_code=403, detail="Invalid access key")
    llm_mgr.set_model(request.model_id)
    return {"active_model": request.model_id}


@router.get("/health")
async def llm_health():
    """Check backend connectivity and list available models."""
    return await llm_mgr.health()


# ── History management endpoints ──────────────────────────────────

@router.get("/history/{client_id}/{project_id}")
async def get_history(client_id: str, project_id: str):
    """Load chat history for a client + project."""
    memory_key = f"{client_id}_{project_id}"
    messages = await memory.load(memory_key)
    return {"project_id": project_id, "messages": messages}


@router.delete("/history/{client_id}/{project_id}")
async def clear_history(client_id: str, project_id: str):
    """Clear chat history for a client + project."""
    memory_key = f"{client_id}_{project_id}"
    await memory.clear(memory_key)
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────

def _text_before_tool_call(text: str) -> str:
    """Return text that appears before the first <tool_call> block (stripped)."""
    import re
    m = re.search(r'<tool_call>', text)
    if m:
        before = text[:m.start()]
        # Also strip thinking blocks from the before portion
        before = re.sub(r'<think>[\s\S]*?</think>\s*', '', before)
        before = re.sub(r'<voice>[\s\S]*?</voice>\s*', '', before)
        return before.strip()
    return ''


def _strip_thinking_and_tools(text: str) -> str:
    """Remove <think>, <tool_call>, and <voice> blocks from text before storing in memory."""
    import re
    # TEMP-DIAG 2026-05-03: log voice block content so we can inspect what
    # TTS spoke (the FE extracts <voice> from the stream and ships it to TTS;
    # by the time we strip here the audio is already playing, but the source
    # text isn't visible elsewhere in our logs). Strip after analysis when
    # not needed any more.
    _matches = re.findall(r'<voice>([\s\S]*?)</voice>', text)
    for _vb in _matches:
        logger.info("VOICE_CAPTURED chars=%d content=%r", len(_vb), _vb[:500])
    if not _matches:
        _has_open = '<voice>' in text
        _tail = text[-300:] if len(text) > 300 else text
        logger.info("VOICE_MISSING has_open=%s text_len=%d tail=%r",
                    _has_open, len(text), _tail)
    text = re.sub(r'<think>[\s\S]*?</think>\s*', '', text)
    text = re.sub(r'<tool_call>[\s\S]*?</tool_call>\s*', '', text)
    text = re.sub(r'<voice>[\s\S]*?</voice>\s*', '', text)
    return text.strip()


# ── Debug endpoints ──────────────────────────────────────────────

class DebugToggleRequest(BaseModel):
    enabled: bool


@router.post("/debug")
async def toggle_debug(request: DebugToggleRequest):
    """Enable or disable LLM debug logging."""
    dbg = get_debug_log()
    if request.enabled:
        dbg.enable()
    else:
        dbg.disable()
    return {"debug": dbg.enabled}


@router.get("/debug/events")
async def get_debug_events(since: float = 0):
    """Get debug events since a timestamp."""
    dbg = get_debug_log()
    return {"events": dbg.get_events(since), "enabled": dbg.enabled}


@router.delete("/debug/events")
async def clear_debug_events():
    """Clear all debug events."""
    dbg = get_debug_log()
    dbg.clear()
    return {"ok": True}

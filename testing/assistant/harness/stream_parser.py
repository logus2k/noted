"""Parse the SSE stream from noted /api/llm/chat into (tool_calls, reasoning, answer, usage).

SSE event types noted emits (as of 2026-04-20):
  - {"skills": [...]}                       auto-injected skill names (informational)
  - {"token": "<chunk>"}                    streamed answer text chunk
  - {"tool_badge": {"name":..., "args":...}}  tool call fired (name + args; no result)
  - {"navigate": {...}}                     UI-only, ignored
  - {"pending_action": {...}} / {"pending_actions": [...]}  write tool needs approval
  - {"usage": {...}}                        token usage at end
  - {"error": "..."}                        error event
  - [DONE]                                  stream terminator (literal line)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: str = ""                   # populated from tool_result SSE events when available
    result_truncated: bool = False


@dataclass
class ParsedResponse:
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    reasoning: str = ""                # extracted from <think>...</think> in streamed tokens
    answer: str = ""                   # streamed tokens with <think> blocks stripped
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    pending_action_id: str = ""        # write-tool approval requested; if set, harness can POST /confirm
    context_block: str = ""            # WORKSPACE CONTEXT the Assistant received (set by context_block SSE event)
    context_block_truncated: bool = False
    raw_chunks: list[dict] = field(default_factory=list)  # for debugging

    @property
    def pending_action(self) -> bool:
        return bool(self.pending_action_id)


_THINK_BLOCK = re.compile(r"<think>([\s\S]*?)</think>", re.MULTILINE)

_WRITE_TOOL_NAMES = {"update_cell", "insert_cell", "batch_update_cells", "find_replace_in_cells",
                      "update_file", "create_file", "fix_lint_issues"}


def _stream_has_write_tool_badge(tool_calls: list) -> bool:
    """True iff a tool_badge for a write tool was already recorded in this
    stream. Used to decide whether pending_action(s) should be recorded as a
    separate tool call or treated as the approval payload for the badge."""
    return any(tc.name in _WRITE_TOOL_NAMES for tc in tool_calls)


def _split_reasoning_and_answer(full_text: str) -> tuple[str, str]:
    """Extract all <think>...</think> content into `reasoning` and strip those
    blocks from the text to yield the user-facing `answer`."""
    reasoning_parts = _THINK_BLOCK.findall(full_text)
    reasoning = "\n".join(p.strip() for p in reasoning_parts).strip()
    answer = _THINK_BLOCK.sub("", full_text).strip()
    return reasoning, answer


def parse_sse_stream(lines: Iterable[str]) -> ParsedResponse:
    """Consume an iterable of SSE lines (as yielded by requests.iter_lines)
    and return the parsed response.

    Lines are either `data: <payload>` or blank (separator) or `[DONE]`.
    """
    result = ParsedResponse()
    full_text_buf: list[str] = []

    for raw in lines:
        if raw is None:
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        line = raw.rstrip()
        if not line:
            continue
        if not line.startswith("data:"):
            continue  # ignore unexpected non-data lines
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            result.errors.append(f"unparseable SSE payload: {payload[:200]}")
            continue

        result.raw_chunks.append(chunk)

        if "skills" in chunk:
            result.skills.extend(chunk["skills"] or [])
        elif "token" in chunk:
            full_text_buf.append(chunk["token"])
        elif "tool_badge" in chunk:
            tb = chunk["tool_badge"] or {}
            result.tool_calls.append(ToolCallRecord(
                name=tb.get("name", ""),
                args=dict(tb.get("args") or {}),
            ))
        elif "context_block" in chunk:
            cb = chunk["context_block"] or {}
            if isinstance(cb, dict):
                result.context_block = cb.get("content", "") or ""
                result.context_block_truncated = bool(cb.get("truncated", False))
        elif "tool_result" in chunk:
            # Tool result for the most-recently-badged call. Attach to the
            # last ToolCallRecord whose `result` is still empty and whose
            # name matches.
            tr = chunk["tool_result"] or {}
            name = tr.get("name", "")
            result_text = tr.get("result", "") or ""
            truncated = bool(tr.get("truncated", False))
            attached = False
            for tc in reversed(result.tool_calls):
                if tc.name == name and not tc.result:
                    tc.result = result_text
                    tc.result_truncated = truncated
                    attached = True
                    break
            if not attached:
                # Write-tool scenario: the matching ToolCallRecord lives in the
                # initial /chat response; this is the /confirm follow-up stream.
                # Record an orphan so merge_followup can reconcile.
                result.tool_calls.append(ToolCallRecord(
                    name=name,
                    args={},
                    result=result_text,
                    result_truncated=truncated,
                ))
        elif "pending_action" in chunk:
            pa = chunk["pending_action"] or {}
            if isinstance(pa, dict):
                if pa.get("id"):
                    result.pending_action_id = pa["id"]
                # If the backend already emitted a tool_badge for the originating
                # model call (new behavior, post 2026-04-21), the pending_action
                # here is just the approval payload - do not re-record it as a
                # separate tool call. Otherwise fall back to recording it so
                # older streams still validate.
                if pa.get("tool") and not _stream_has_write_tool_badge(result.tool_calls):
                    result.tool_calls.append(ToolCallRecord(
                        name=pa.get("tool", ""),
                        args=dict(pa.get("args") or {}),
                    ))
        elif "pending_actions" in chunk:
            # Batch of write tools - approval_id lives at the batch level.
            # Every individual action shares the same batch_id; using the first
            # action's batch_id is equivalent to approving the whole batch.
            pas = chunk.get("pending_actions") or []
            if pas and isinstance(pas, list):
                first = pas[0] or {}
                if isinstance(first, dict):
                    # Prefer batch_id if present, fall back to action id
                    result.pending_action_id = first.get("batch_id") or first.get("id", "")
                # Only record per-action entries when no upstream tool_badge
                # already identified the model's original call (e.g. a batch
                # expansion emits individual update_cell actions internally;
                # the model actually called batch_update_cells).
                if not _stream_has_write_tool_badge(result.tool_calls):
                    for pa in pas:
                        if isinstance(pa, dict) and pa.get("tool"):
                            result.tool_calls.append(ToolCallRecord(
                                name=pa.get("tool", ""),
                                args=dict(pa.get("args") or {}),
                            ))
        elif "usage" in chunk:
            result.usage = dict(chunk["usage"] or {})
        elif "error" in chunk:
            result.errors.append(str(chunk["error"]))
        # navigate + anything else: ignored for harness purposes

    full_text = "".join(full_text_buf)
    result.reasoning, result.answer = _split_reasoning_and_answer(full_text)
    return result

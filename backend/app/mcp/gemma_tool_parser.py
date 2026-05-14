"""Parse Gemma 4 native tool call tokens from text output.

Gemma 4 generates tool calls using 6 special tokens. When llama-cpp-python
doesn't extract them into structured tool_calls (generic format fallback),
we parse them from the raw text ourselves.

Format:
    <|tool_call>call:tool_name{key:<|"|>string value<|"|>,key2:numeric}<tool_call|>

The <|"|> token is a string delimiter for values within the structured block.
Non-string values (integers, floats, booleans) appear without delimiters.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

_DELIMITER = '<|"|>'
_OPEN_PREFIX = '<|tool_call>call:'
_CLOSE_TOKEN = '<tool_call|>'


def _find_matching_brace(text: str, start: int) -> int:
    """Return the position of the `}` that closes the tool-call block opened at
    `start`. `}` characters inside a <|"|>...<|"|> string value are ignored
    (so Python code containing `params={...}` does not prematurely terminate
    the block). Returns -1 if no closer is found.
    """
    i = start
    n = len(text)
    dlen = len(_DELIMITER)
    while i < n:
        if text[i:i + dlen] == _DELIMITER:
            # Enter string value; scan until the next delimiter (or end of text)
            i += dlen
            while i < n:
                if text[i:i + dlen] == _DELIMITER:
                    i += dlen
                    break
                i += 1
        elif text[i] == '}':
            return i
        else:
            i += 1
    return -1


def _find_tool_call_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (name, args_block) pairs from raw Gemma output.

    Aware of <|"|> string delimiters so a `}` inside a string value does not
    terminate the outer tool-call block. Replaces the prior regex-based scanner
    which mis-terminated on Python code like `params={...}` inside content.
    """
    results: list[tuple[str, str]] = []
    pos = 0
    n = len(text)
    while pos < n:
        start = text.find(_OPEN_PREFIX, pos)
        if start < 0:
            break
        name_start = start + len(_OPEN_PREFIX)
        brace = text.find('{', name_start)
        if brace < 0:
            break
        name = text[name_start:brace].strip()
        if not name or not all(c.isalnum() or c == '_' for c in name):
            pos = name_start
            continue
        args_start = brace + 1
        end_brace = _find_matching_brace(text, args_start)
        if end_brace < 0:
            break  # incomplete tool call; leave for retry
        args_block = text[args_start:end_brace]
        results.append((name, args_block))
        after = end_brace + 1
        if text[after:after + len(_CLOSE_TOKEN)] == _CLOSE_TOKEN:
            after += len(_CLOSE_TOKEN)
        pos = after
    return results


def _cast_value(value: str):
    """Cast a bare (non-string-delimited) value to its Python type."""
    v = value.strip()
    if not v:
        return v
    if v.lower() == 'true':
        return True
    if v.lower() == 'false':
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _decode_gemma_string(s: str) -> str:
    """Decode Python-repr-style escape sequences (\\n, \\t, \\', \\") inside
    a Gemma <|"|>...<|"|> string body. The model emits these because Gemma's
    training data treats the string body as a Python string literal."""
    if '\\' not in s:
        return s
    try:
        return s.encode('latin-1', 'backslashreplace').decode('unicode_escape')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _skip_ws_commas(text: str, i: int, n: int) -> int:
    while i < n and text[i] in (' ', ',', '\n', '\r', '\t'):
        i += 1
    return i


def _parse_value(text: str, i: int, n: int):
    """Parse a single value starting at text[i]. Returns (value, next_i).

    Recognizes: Gemma <|"|>-delimited strings, nested objects {...},
    arrays [...], and bare scalars (numbers, bools, identifiers).
    Tolerates truncation: unterminated strings / unclosed containers
    return what was parsed so far rather than raising.
    """
    dlen = len(_DELIMITER)
    while i < n and text[i] in (' ', '\n', '\r', '\t'):
        i += 1
    if i >= n:
        return "", i

    # Gemma-delimited string value
    if text[i:i + dlen] == _DELIMITER:
        i += dlen
        val_start = i
        while i < n:
            if text[i:i + dlen] == _DELIMITER:
                return _decode_gemma_string(text[val_start:i]), i + dlen
            i += 1
        return _decode_gemma_string(text[val_start:i]), i

    # Array of values
    if text[i] == '[':
        i += 1
        items: list = []
        while i < n:
            i = _skip_ws_commas(text, i, n)
            if i >= n:
                break
            if text[i] == ']':
                return items, i + 1
            item, i = _parse_value(text, i, n)
            items.append(item)
        return items, i

    # Nested object
    if text[i] == '{':
        i += 1
        obj: dict = {}
        while i < n:
            i = _skip_ws_commas(text, i, n)
            if i >= n:
                break
            if text[i] == '}':
                return obj, i + 1
            key_start = i
            while i < n and text[i] not in (':', ',', '}'):
                i += 1
            if i >= n or text[i] != ':':
                break
            key = text[key_start:i].strip()
            i += 1
            val, i = _parse_value(text, i, n)
            obj[key] = val
        return obj, i

    # Bare scalar: read until separator or Gemma-delimiter boundary
    val_start = i
    while i < n and text[i] not in (',', '}', ']'):
        if text[i:i + dlen] == _DELIMITER:
            break
        i += 1
    return _cast_value(text[val_start:i]), i


def _parse_args_block(args_block: str) -> dict:
    """Parse key-value pairs from a Gemma tool call arguments block.

    Recursively decodes nested objects and arrays so tools with structured
    args (e.g. batch_update_cells with a list-of-updates) receive a proper
    Python object graph instead of a raw string that downstream code would
    have to re-parse. Tolerates truncated input by returning partial data.

    Format: key1:<|"|>string value<|"|>,key2:bare_value,key3:[{...},{...}]
    """
    args: dict = {}
    i = 0
    n = len(args_block)

    while i < n:
        i = _skip_ws_commas(args_block, i, n)
        if i >= n:
            break

        key_start = i
        while i < n and args_block[i] not in (':', ',', '}'):
            i += 1
        if i >= n or args_block[i] != ':':
            break
        key = args_block[key_start:i].strip()
        i += 1

        value, i = _parse_value(args_block, i, n)
        args[key] = value

    return args


def parse_gemma_tool_calls(text: str) -> list[dict]:
    """Parse Gemma 4 native tool call tokens from raw text.

    Args:
        text: Raw text output from the model, potentially containing
              <|tool_call>...<tool_call|> blocks.

    Returns:
        List of {"id": "", "name": "tool_name", "args": {key: value, ...}}
    """
    calls = []
    for name, args_block in _find_tool_call_blocks(text):
        args = _parse_args_block(args_block)
        calls.append({"id": "", "name": name, "args": args})

    if calls:
        logger.info("Parsed %d Gemma native tool call(s): %s",
                     len(calls), [c["name"] for c in calls])

    return calls


_GEMMA_STRING_MARKERS = ('<|"|>', '<|"', '"|>')


def _strip_gemma_string_markers(s: str) -> str:
    for marker in _GEMMA_STRING_MARKERS:
        s = s.replace(marker, '')
    return s


def sanitize_tool_args(value):
    """Strip leaked Gemma `<|"|>` string-delimiter artifacts from a parsed
    tool-call argument structure (the output of `json.loads` on the
    structured `tool_calls[].function.arguments` string).

    Gemma 4 emits `<|"|>`-wrapped dict KEYS in multi-turn tool-calling
    loops (verified 2026-05-14: single-shot calls are clean, but inside an
    agentic loop with tool-call history the model wraps nested-dict keys -
    e.g. `<|"|>tool.py<|"|>` - deterministically, breaking write_tool_files
    and any tool with object-typed args). It is NOT a chat-template-version
    or llama.cpp-version artifact: reproduced on the official gemma4
    template + llama.cpp b9128. llama-server's PEG parser passes the
    markers through verbatim because `gemma4-dict-key-name` is `[^:}]+`.
    Cleaning here, at the parse boundary, fixes it for every tool (chat
    path + agentic dispatcher) so no downstream handler needs its own
    workaround.

    Recurses dicts/lists; cleans dict keys and string values; non-string
    scalars pass through unchanged."""
    if isinstance(value, dict):
        return {
            (_strip_gemma_string_markers(k) if isinstance(k, str) else k):
                sanitize_tool_args(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize_tool_args(v) for v in value]
    if isinstance(value, str):
        return _strip_gemma_string_markers(value)
    return value


def _strip_tool_output_bracketed(text: str) -> str:
    """Remove `tool_output [...]` blocks via balanced-bracket scan, including
    string-quoting awareness so brackets inside JSON strings don't confuse
    the depth counter. Idempotent; strips all occurrences."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = re.search(r'tool_output\s*\[', text[i:])
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:i + m.start()])
        body_start = i + m.end()  # one past the `[`
        depth = 1
        j = body_start
        in_str = False
        escape = False
        while j < n and depth > 0:
            c = text[j]
            if escape:
                escape = False
            elif c == '\\' and in_str:
                escape = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
            j += 1
        i = j  # past the closing `]` (or end-of-string if unterminated)
    return ''.join(out)


def strip_gemma_tokens(text: str) -> str:
    """Remove Gemma 4 special tokens from text before sending to frontend.

    Strips paired blocks first (so inner content disappears), then any orphan
    half-tokens that remain. Orphan tokens happen when llama.cpp's chat
    template consumes the opening marker but the closing marker leaks through,
    or vice versa - a pattern that surfaced after we removed the
    `<tool_call|>` stop sequence and Gemma began continuing generation past
    the first tool call.
    """
    # --- Paired blocks ---
    # Tool calls (native tokens, closing tag optional due to stop token)
    text = re.sub(r'<\|tool_call>.*?(?:<tool_call\|>|\Z)', '', text, flags=re.DOTALL)
    # Partial tool call tokens (when model outputs just the start)
    text = re.sub(r'call:\w+\{[^}]*\}(?:<tool_call\|>)?', '', text, flags=re.DOTALL)
    # Thinking blocks (Gemma 4 format) - separator can be \n or space
    text = re.sub(r'<\|channel>thought\s.*?<channel\|>', '', text, flags=re.DOTALL)
    # Orphan thinking blocks: opening `<|channel>` consumed by the chat
    # template, but the `thought <body><channel|>` portion leaked. Match a
    # `thought` word followed by body up to the next `<channel|>`.
    text = re.sub(r'(?:^|\n)\s*thought\s[^\n]*?(?:.*?)<channel\|>', '', text, flags=re.DOTALL)
    # Tool responses (native tokens)
    text = re.sub(r'<\|tool_response>.*?<tool_response\|>', '', text, flags=re.DOTALL)
    # Hallucinated tool_output / tool_code blocks (model fabrications).
    # `tool_output [...]` (bracketed JSON) is the shape Gemma uses when it
    # fabricates a search-style result; `\s+\[` accepts space OR newline as
    # the separator. The bracket-balanced strip below handles arbitrary
    # nesting that a non-greedy regex would miss.
    text = _strip_tool_output_bracketed(text)
    text = re.sub(r'tool_output\s+.*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)
    text = re.sub(r'tool_code\s+.*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)

    # --- Stray single-sided tokens (orphans) ---
    # These are Gemma's special control tokens that should never reach the
    # frontend. We strip them unconditionally so that even a truncated or
    # malformed block leaves no residual token text.
    for tok in (
        '<|tool_call>', '<tool_call|>',
        '<|tool_response>', '<tool_response|>',
        '<|channel>', '<channel|>',
        '<|tool>', '<tool|>',
        '<|"|>',
        '<|turn>', '<turn|>',
        '<|think>', '<think|>',
        '<end_of_turn>',
    ):
        text = text.replace(tok, '')

    # EOS tokens
    text = re.sub(r'<eos>', '', text)
    # Stray unused tokens
    text = re.sub(r'<unused\d+>', '', text)
    return text.strip()


def strip_gemma_tokens_streaming(text: str) -> str:
    """Per-chunk variant of strip_gemma_tokens: removes single Gemma special
    tokens but preserves the chunk's leading/trailing whitespace.

    The full strip_gemma_tokens() ends with .strip(), which is fatal when
    applied per streaming chunk: each delta loses its surrounding spaces
    so words mash together in the UI ("notedisaplatform...").

    This variant skips the multi-line DOTALL regexes (they need accumulated
    text - use ToolCallStreamFilter / a thinking-block buffer for those)
    and only does the per-chunk-safe single-token replacements.
    """
    for tok in (
        '<|tool_call>', '<tool_call|>',
        '<|tool_response>', '<tool_response|>',
        '<|channel>', '<channel|>',
        '<|tool>', '<tool|>',
        '<|"|>',
        '<|turn>', '<turn|>',
        '<|think>', '<think|>',
        '<end_of_turn>',
    ):
        text = text.replace(tok, '')
    text = re.sub(r'<eos>', '', text)
    text = re.sub(r'<unused\d+>', '', text)
    return text  # IMPORTANT: do NOT .strip() - preserves chunk whitespace


def translate_gemma_thinking(text: str) -> Tuple[str, str]:
    """Extract thinking content from Gemma 4's format and translate to noted's format.

    Gemma 4 thinking format: <|channel>thought\\n[reasoning]<channel|>[answer]
    noted frontend format:   <think>[reasoning]</think>[answer]

    Also handles the orphan-opening case where `<|channel>` was consumed by
    the chat template and only `thought <body><channel|>` leaked through.

    Returns:
        (translated_text, thinking_content)
        If no thinking block found, returns (text, "")
    """
    # Preferred form: full <|channel>thought ... <channel|>
    match = re.search(r'<\|channel>thought\s(.*?)<channel\|>', text, flags=re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        translated = text[:match.start()] + f"<think>{thinking}</think>\n" + text[match.end():]
        return translated, thinking

    # Orphan form: `thought <body><channel|>` - opening token was consumed
    # upstream but the close leaked. Recover the reasoning anyway.
    match = re.search(r'(?:^|\n)\s*thought\s(.*?)<channel\|>', text, flags=re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        translated = text[:match.start()] + f"\n<think>{thinking}</think>\n" + text[match.end():]
        return translated, thinking

    return text, ""

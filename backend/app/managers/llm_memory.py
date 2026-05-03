"""Project-scoped LLM conversation memory (in-memory, session-scoped).

Keeps conversation history per client_id + project_id in memory.
File persistence will be added when Google identity integration is ready.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Token budget (conservative: ~4 chars per token).
# Sized for Gemma 4 (131K n_ctx) and Claude (200K+); leaves room for
# context block, skills, tool schemas, and generation. Compaction kicks in
# at 75% so the active turn always has headroom.
CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 96_000
COMPACTION_THRESHOLD = 0.75  # Trigger compaction at 75% of budget


# Fields preserved when round-tripping messages through memory. Anything
# else gets dropped on append. Mirrors the OpenAI chat-completions schema
# subset we actually rely on for native tool calling.
_PRESERVED_FIELDS = ("role", "content", "tool_calls", "tool_call_id", "name")


def _normalize_message(msg: dict) -> dict:
    """Keep only the fields that matter for replay; drop bookkeeping keys."""
    return {k: msg[k] for k in _PRESERVED_FIELDS if k in msg}


def _message_chars(msg: dict) -> int:
    """Char count for compaction budgeting; covers content + serialized tool_calls."""
    content = msg.get("content")
    if isinstance(content, str):
        n = len(content)
    elif isinstance(content, list):
        n = sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    else:
        n = 0
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if isinstance(fn, dict):
            n += len(fn.get("name") or "")
            args = fn.get("arguments")
            n += len(args) if isinstance(args, str) else 0
    return n


class ProjectMemory:
    """Thread-safe, in-memory conversation memory keyed by memory_key (client_id + project_id)."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._store: dict[str, list[dict]] = {}

    async def load(self, key: str) -> list[dict]:
        """Load conversation history."""
        async with self._lock:
            return [dict(m) for m in self._store.get(key, [])]

    async def append(self, key: str, *args, **kwargs):
        """Append a message.

        Two call shapes for caller convenience:
          - append(key, message_dict)  -> structured (role + optional tool_calls/tool_call_id/name)
          - append(key, role, content) -> legacy two-arg form for plain text messages

        The token-volume compaction in get_compaction_input is the only
        mechanism for bounding history; messages are never silently dropped here.
        """
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            msg = _normalize_message(args[0])
        elif len(args) == 2:
            role, content = args
            msg = {"role": role, "content": content}
        elif "role" in kwargs and "content" in kwargs:
            msg = _normalize_message(kwargs)
        else:
            raise TypeError("append() expects (key, message_dict) or (key, role, content)")
        if "role" not in msg:
            raise ValueError("message must have a 'role' field")
        async with self._lock:
            self._store.setdefault(key, []).append(msg)

    async def get_messages_for_llm(self, key: str) -> list[dict]:
        """Get conversation history formatted for the LLM messages array.

        Returns full structured messages (role + content + optional tool_calls /
        tool_call_id / name) so the asf0 chat template can render prior tool
        calls in its native pipe-marker format.
        """
        return await self.load(key)

    async def needs_compaction(self, key: str) -> bool:
        """Check if the conversation history exceeds the compaction threshold."""
        messages = await self.load(key)
        total_chars = sum(_message_chars(m) for m in messages)
        budget = int(MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * COMPACTION_THRESHOLD)
        return total_chars > budget

    async def compact(self, key: str, summary: str):
        """Replace older messages with a summary, keeping recent ones."""
        async with self._lock:
            messages = self._store.get(key, [])
            if len(messages) <= 4:
                return
            recent = messages[-4:]
            self._store[key] = [
                {"role": "assistant", "content": f"[Conversation summary]\n{summary}"},
                *recent,
            ]
            logger.info("Compacted history for %s: %d -> %d messages",
                        key, len(messages), len(self._store[key]))

    async def get_compaction_input(self, key: str) -> Optional[str]:
        """Get the older messages that should be summarized, or None if not needed."""
        if not await self.needs_compaction(key):
            return None

        messages = await self.load(key)
        if len(messages) <= 4:
            return None

        to_summarize = messages[:-4]
        lines = []
        for m in to_summarize:
            role = m.get("role", "?").upper()
            content = m.get("content")
            if isinstance(content, list):
                content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            elif not isinstance(content, str):
                content = ""
            # Surface tool_calls so the summarizer sees what the assistant did,
            # not just what it said.
            tcs = m.get("tool_calls") or []
            if tcs:
                names = ", ".join(
                    (tc.get("function") or {}).get("name", "?") if isinstance(tc, dict) else "?"
                    for tc in tcs
                )
                content = (content + f" [tool_calls: {names}]").strip()
            if m.get("tool_call_id"):
                content = f"[tool_result for {m['tool_call_id']}] {content}"
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def clear(self, key: str):
        """Clear conversation history."""
        async with self._lock:
            self._store.pop(key, None)

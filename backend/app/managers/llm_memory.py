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


class ProjectMemory:
    """Thread-safe, in-memory conversation memory keyed by memory_key (client_id + project_id)."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._store: dict[str, list[dict]] = {}

    async def load(self, key: str) -> list[dict]:
        """Load conversation history."""
        async with self._lock:
            return list(self._store.get(key, []))

    async def append(self, key: str, role: str, content: str):
        """Append a message. The token-volume compaction in get_compaction_input
        is the only mechanism for bounding history; messages are never silently
        dropped here."""
        async with self._lock:
            self._store.setdefault(key, []).append({
                "role": role,
                "content": content,
            })

    async def get_messages_for_llm(self, key: str) -> list[dict]:
        """Get conversation history formatted for the LLM messages array."""
        messages = await self.load(key)
        return [{"role": m["role"], "content": m["content"]} for m in messages]

    async def needs_compaction(self, key: str) -> bool:
        """Check if the conversation history exceeds the compaction threshold."""
        messages = await self.load(key)
        total_chars = sum(len(m.get("content", "")) for m in messages)
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
            role = m["role"].upper()
            content = m["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def clear(self, key: str):
        """Clear conversation history."""
        async with self._lock:
            self._store.pop(key, None)

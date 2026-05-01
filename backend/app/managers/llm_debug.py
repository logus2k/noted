"""LLM Debug Log - collects timestamped events from LLM interactions.

Events are stored in a ring buffer and optionally pushed to connected
clients via Socket.IO for real-time display in the Debug Panel.
"""

import logging
import time
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MAX_EVENTS = 500


class LLMDebugLog:
    """Thread-safe ring buffer of debug events."""

    def __init__(self, sio=None):
        self._events = deque(maxlen=MAX_EVENTS)
        self._sio = sio
        self._enabled = False  # per-client debug state tracked separately

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    @property
    def enabled(self):
        return self._enabled

    def clear(self):
        self._events.clear()

    def get_events(self, since: float = 0) -> list:
        """Get events since a timestamp (epoch seconds)."""
        return [e for e in self._events if e["ts_epoch"] >= since]

    def log(self, category: str, action: str, detail: dict = None,
            client_id: str = None):
        """Log a debug event.

        Args:
            category: 'api', 'skill', 'file', 'tool', 'llm'
            action: what happened (e.g. 'call', 'response', 'load', 'read')
            detail: dict with event-specific data
            client_id: optional client identifier
        """
        if not self._enabled:
            return

        now = time.time()
        event = {
            "ts": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
            "ts_epoch": now,
            "category": category,
            "action": action,
            "detail": detail or {},
            "client_id": client_id,
        }
        self._events.append(event)

        # Push to frontend via Socket.IO
        if self._sio:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(
                        self._sio.emit("llm:debug_event", event)
                    )
            except Exception:
                pass

    # Convenience methods for common event types

    def log_api_call(self, model: str, messages_count: int,
                     input_tokens: int = 0, client_id: str = None):
        self.log("api", "call", {
            "model": model,
            "messages": messages_count,
            "input_tokens_est": input_tokens,
        }, client_id)

    def log_api_response(self, model: str, output_tokens: int = 0,
                         duration_ms: int = 0, client_id: str = None):
        self.log("api", "response", {
            "model": model,
            "output_tokens_est": output_tokens,
            "duration_ms": duration_ms,
        }, client_id)

    def log_tool_call(self, tool_name: str, args: dict = None,
                      client_id: str = None):
        # Truncate large args for display
        display_args = {}
        for k, v in (args or {}).items():
            sv = str(v)
            display_args[k] = sv[:200] + "..." if len(sv) > 200 else sv
        self.log("tool", "call", {
            "name": tool_name,
            "args": display_args,
        }, client_id)

    def log_tool_result(self, tool_name: str, result_length: int = 0,
                        client_id: str = None):
        self.log("tool", "result", {
            "name": tool_name,
            "result_chars": result_length,
        }, client_id)

    def log_skill_load(self, skill_name: str, auto: bool = False,
                       client_id: str = None):
        self.log("skill", "load", {
            "name": skill_name,
            "auto_injected": auto,
        }, client_id)

    def log_file_read(self, path: str, lines: int = 0,
                      client_id: str = None):
        self.log("file", "read", {
            "path": path,
            "lines": lines,
        }, client_id)

    def log_file_write(self, path: str, action: str = "update",
                       client_id: str = None):
        self.log("file", action, {
            "path": path,
        }, client_id)

    def log_llm_stream_start(self, model: str, provider: str = "local",
                             client_id: str = None):
        self.log("llm", "stream_start", {
            "model": model,
            "provider": provider,
        }, client_id)

    def log_llm_stream_end(self, model: str, tokens_in: int = 0,
                           tokens_out: int = 0, client_id: str = None):
        self.log("llm", "stream_end", {
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }, client_id)


# Module-level singleton
_debug_log: Optional[LLMDebugLog] = None


def get_debug_log() -> LLMDebugLog:
    global _debug_log
    if _debug_log is None:
        _debug_log = LLMDebugLog()
    return _debug_log


def init_debug_log(sio) -> LLMDebugLog:
    global _debug_log
    _debug_log = LLMDebugLog(sio=sio)
    return _debug_log

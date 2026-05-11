"""Workflow → frontend pub-sub for doc-buffer changes (and future
workflow-state events).

Motivation: the chat path emits SSE events inline whenever it writes a
doc (`yield f"data: {json.dumps({'doc': ...})}\\n\\n"`), so the frontend
viewer refreshes live. Background workflows (e.g. `research_topic`)
write the same buffers via `execute_tool`, but they have no per-turn
SSE channel to write into. Without a broadcast, the user can't see
research progress until they manually refresh.

This module provides:
  - `publish_doc_changed(buf)` — fanout doc-changed events to subscribers.
  - `subscribe()` — async generator yielding events as they arrive.
  - The SSE endpoint that exposes these events to the frontend lives in
    `routers/buffers.py`.

Single-process; uvicorn single-worker today. Subscribers are bounded
async Queues (maxsize=64) so a slow consumer doesn't pin memory; on
overflow the event is dropped (the frontend can re-fetch the buffer
on next event to catch up).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


# Module-level subscriber registry. Snapshot-and-iterate pattern avoids
# concurrent-mutation issues without needing a lock for the hot path.
_subscribers: list[asyncio.Queue] = []


def publish_doc_changed(buf) -> None:
    """Fan a doc-changed event out to every subscriber.

    `buf` is a `notes_buffer.DocBuffer`. Payload shape mirrors the
    chat path's existing `data: {'doc': notes_buffer.to_dict(buf)}`
    event so the frontend can route both through the same
    `App._handleDocBuffer(payload)` handler — no special-case code
    in the SSE listener.
    """
    event = {
        "type": "doc_changed",
        "doc": {
            "buffer_id": buf.buffer_id,
            "name": buf.name,
            "content": buf.content or "",
            "path": buf.path,
        },
        "size": len(buf.content or ""),
        "ts": time.time(),
    }
    _fanout(event)


def publish_workflow_event(workflow_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
    """Generic workflow lifecycle event (started, iteration_done,
    suspended, completed, aborted, ...). Surfaces in the same SSE
    stream so the frontend can update the Workflow Monitor and trigger
    chat-side reactions (e.g. noted reading the doc when state goes to
    suspended-for-review) without polling."""
    event = {
        "type": "workflow_event",
        "workflow_id": workflow_id,
        "kind": kind,
        "payload": payload or {},
        "ts": time.time(),
    }
    _fanout(event)


def _fanout(event: dict[str, Any]) -> None:
    """Best-effort push to every live subscriber. Drops events on a
    backed-up queue rather than blocking the publisher. Never raises."""
    snapshot = list(_subscribers)
    for q in snapshot:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "doc_events: subscriber queue full, dropping %s event",
                event.get("type"),
            )
        except Exception:
            logger.debug("doc_events: fanout to one subscriber failed", exc_info=True)


async def subscribe() -> AsyncGenerator[dict[str, Any], None]:
    """Async generator yielding events as they arrive. The caller (an
    SSE endpoint) iterates and serialises each event onto the wire.

    The subscriber's queue is registered on entry and removed on exit
    so disconnected clients don't accumulate. Heartbeat events are NOT
    emitted here; the SSE endpoint is free to inject them on its own
    schedule via `StreamingResponse` keep-alive."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.append(q)
    try:
        while True:
            ev = await q.get()
            yield ev
    finally:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def subscriber_count() -> int:
    """Diagnostic accessor used by health probes."""
    return len(_subscribers)

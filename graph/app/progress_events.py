"""Socket.IO live-progress channel for the knowledge-graph build.

Clients (job2cool / cv / noted) subscribe per-domain to receive ingestion and
rebuild progress in real time instead of polling ``/status``. The build runs in
worker threads, so :func:`emit_progress` bridges sync -> async via
``run_coroutine_threadsafe`` onto the ASGI event loop captured at startup. It is
strictly best-effort: a failed emit never propagates into the build.

Wire protocol
-------------
- Event ``kb:progress`` -> ``{"domain_id": str, "progress": {...}}`` (the same
  shape the build keeps in ``ResearchGraphBuilder.progress``), delivered to the
  room ``kb:<domain_id>``.
- A client subscribes to a domain with ``emit('join', {'domain_id': '<id>'})``
  (or by connecting with ``auth={'domain_id': '<id>'}``) and unsubscribes with
  ``emit('leave', {'domain_id': '<id>'})``.
"""
from __future__ import annotations

import asyncio
import logging

import socketio

logger = logging.getLogger(__name__)

# Shared async Socket.IO server; mounted by app.main via socketio.ASGIApp so
# uvicorn serves both the REST API and this channel on the same port.
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# The ASGI event loop, captured at startup. Worker threads schedule emits onto
# it; until it's set (or if it's None) emits are silently skipped.
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Record the running ASGI loop so build threads can schedule emits."""
    global _loop
    _loop = loop


def _room(domain_id: str) -> str:
    return f"kb:{domain_id}"


async def _enter(sid: str, room: str) -> None:
    # enter_room is sync on most python-socketio versions but a coroutine on
    # some; handle both so we're version-agnostic.
    res = sio.enter_room(sid, room)
    if asyncio.iscoroutine(res):
        await res


async def _leave(sid: str, room: str) -> None:
    res = sio.leave_room(sid, room)
    if asyncio.iscoroutine(res):
        await res


@sio.event
async def connect(sid, environ, auth=None):
    """Optionally join a domain room at connect time via ``auth.domain_id``."""
    dom = auth.get("domain_id") if isinstance(auth, dict) else None
    if dom:
        await _enter(sid, _room(dom))


@sio.event
async def join(sid, data):
    """Subscribe this client to a domain's progress. ``data={'domain_id': id}``."""
    dom = data.get("domain_id") if isinstance(data, dict) else None
    if not dom:
        return {"error": "domain_id required"}
    await _enter(sid, _room(dom))
    return {"joined": _room(dom)}


@sio.event
async def leave(sid, data):
    dom = data.get("domain_id") if isinstance(data, dict) else None
    if dom:
        await _leave(sid, _room(dom))
    return {"left": dom}


def emit_progress(domain_id: str, progress: dict) -> None:
    """Emit a progress snapshot to a domain's room. Sync, thread-safe, best-effort.

    Called from the build worker threads, so it never awaits and never raises.
    """
    loop = _loop
    if loop is None or not domain_id:
        return
    payload = {"domain_id": domain_id, "progress": dict(progress)}
    try:
        asyncio.run_coroutine_threadsafe(
            sio.emit("kb:progress", payload, room=_room(domain_id)), loop
        )
    except Exception as exc:  # never break a build over telemetry
        logger.debug("kb:progress emit failed for %s: %s", domain_id, exc)

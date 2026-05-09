"""Workflow telemetry: thin wrapper over the existing Socket.io pipeline.

The same `sio` instance that powers `services:health` (proven 2026-05-08
end-to-end with the LED strip going red on a real noted-rag failure) is
reused here. Workflow events ride the same pipeline, scoped to the tenant
when relevant.

Event names follow the schema declared in the plan:
  workflow_started, step_started, step_completed, step_failed,
  workspace_sync, system_request, workflow_suspended, workflow_resumed,
  workflow_completed, workflow_failed.

`emit` is fire-and-forget; failures are logged but never raised - telemetry
must not block workflow progress.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_sio_instance: Any = None


def set_sio(sio: Any) -> None:
    """Wired in lifespan with the Socket.io instance from main.py."""
    global _sio_instance
    _sio_instance = sio


async def emit(event: str, payload: dict[str, Any]) -> None:
    """Push a workflow event to all connected clients.

    Best-effort: if Socket.io isn't available or the emit raises, log and
    swallow. The workflow loop must remain responsive even when no UI is
    connected (CLI / probe execution must work).
    """
    sio = _sio_instance
    if sio is None:
        logger.debug("telemetry emit skipped (no sio): %s", event)
        return
    try:
        await sio.emit(event, payload)
    except Exception as e:
        logger.warning("telemetry emit failed for %s: %s", event, e)


# Convenience wrappers per event type (encourage payload consistency):

async def workflow_started(tenant_id: str, workflow_id: str, workflow_type: str,
                           outcomes: list[str], plan: list[dict[str, Any]]) -> None:
    await emit("workflow_started", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "workflow_type": workflow_type,
        "outcomes": outcomes,
        "plan": plan,
    })


async def step_started(tenant_id: str, workflow_id: str, step_index: int, step_name: str) -> None:
    await emit("step_started", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "step_index": step_index,
        "step_name": step_name,
    })


async def step_completed(tenant_id: str, workflow_id: str, step_index: int,
                         step_name: str, result_summary: dict[str, Any]) -> None:
    await emit("step_completed", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "step_index": step_index,
        "step_name": step_name,
        "result_summary": result_summary,
    })


async def step_failed(tenant_id: str, workflow_id: str, step_index: int,
                      step_name: str, error_summary: str, retry_count: int) -> None:
    await emit("step_failed", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "step_index": step_index,
        "step_name": step_name,
        "error_summary": error_summary,
        "retry_count": retry_count,
    })


async def workspace_sync(tenant_id: str, workflow_id: str, snapshot: dict[str, Any]) -> None:
    await emit("workspace_sync", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "snapshot": snapshot,
    })


async def workflow_suspended(tenant_id: str, workflow_id: str, reason: str,
                             snapshot_path: str | None = None) -> None:
    await emit("workflow_suspended", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "reason": reason,
        "snapshot_path": snapshot_path,
    })


async def workflow_resumed(tenant_id: str, workflow_id: str) -> None:
    await emit("workflow_resumed", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
    })


async def workflow_completed(tenant_id: str, workflow_id: str,
                             outcomes: list[str]) -> None:
    await emit("workflow_completed", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "outcomes": outcomes,
    })


async def workflow_failed(tenant_id: str, workflow_id: str, error_summary: str) -> None:
    await emit("workflow_failed", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "error_summary": error_summary,
    })


async def system_request(tenant_id: str, workflow_id: str,
                         request_type: str, prompt: str) -> None:
    """HITL approval / clarification request. Frontend pauses + asks the user."""
    await emit("system_request", {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "type": request_type,
        "prompt": prompt,
    })

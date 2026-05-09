"""Suspend / resume mechanism for the workflow loop.

Mirrors the proven pattern shipped for KB ingestion (research_builder._push_caches
+ _suspend_for): a per-workflow `threading.Event` blocks the worker thread
until an operator chooses Resume or Abort, with a wall-clock auto-abort safety
net.

The on-disk snapshot persists workspace state so the inspector UI can show
context after a noted restart, even though the worker thread itself can't
resume across a process boundary in this implementation. (For multi-host T2+
this becomes "workspace lives in Redis," same external interface.)

Snapshot path: data/tenants/<tenant_id>/workflows/<workflow_id>/state.json
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from .workspace import WorkspaceState, get_workspace_store

logger = logging.getLogger(__name__)

DEFAULT_SUSPEND_TIMEOUT_S = 3600  # 1 hour auto-abort safety net


@dataclass
class SuspensionHandle:
    """Per-workflow suspend state.

    `event.set()` from the resume handler unblocks the worker. `aborted`
    True means the operator chose Abort; the worker should propagate the
    failure up rather than continue.
    """
    tenant_id: str
    workflow_id: str
    event: threading.Event
    aborted: bool = False
    suspended_at: float = 0.0


class SuspensionManager:
    """Tracks active suspensions across all workflows."""

    def __init__(self) -> None:
        self._handles: dict[tuple[str, str], SuspensionHandle] = {}
        self._lock = threading.RLock()

    def begin(self, tenant_id: str, workflow_id: str) -> SuspensionHandle:
        """Register a new suspension and return its handle.

        The caller (the worker thread) then calls `wait()` on the handle,
        which blocks until Resume or Abort lands.
        """
        key = (tenant_id, workflow_id)
        handle = SuspensionHandle(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            event=threading.Event(),
            suspended_at=time.time(),
        )
        with self._lock:
            self._handles[key] = handle
        return handle

    def wait(self, handle: SuspensionHandle, timeout_s: int = DEFAULT_SUSPEND_TIMEOUT_S) -> bool:
        """Block until resume / abort / timeout. Returns True if resumed
        cleanly, False if aborted or timed out.
        """
        unblocked = handle.event.wait(timeout=timeout_s)
        if not unblocked:
            # Auto-abort safety net: caller should treat this as abort.
            logger.warning(
                "workflow %s/%s suspend timed out after %ds, auto-aborting",
                handle.tenant_id, handle.workflow_id, timeout_s,
            )
            self.abort(handle.tenant_id, handle.workflow_id)
            return False
        return not handle.aborted

    def resume(self, tenant_id: str, workflow_id: str) -> bool:
        with self._lock:
            handle = self._handles.pop((tenant_id, workflow_id), None)
        if handle is None:
            return False
        handle.aborted = False
        handle.event.set()
        return True

    def abort(self, tenant_id: str, workflow_id: str) -> bool:
        with self._lock:
            handle = self._handles.pop((tenant_id, workflow_id), None)
        if handle is None:
            return False
        handle.aborted = True
        handle.event.set()
        return True

    def is_suspended(self, tenant_id: str, workflow_id: str) -> bool:
        with self._lock:
            return (tenant_id, workflow_id) in self._handles


_manager = SuspensionManager()


def get_suspension_manager() -> SuspensionManager:
    return _manager


# ---------- snapshot helpers ----------

def _snapshot_path(tenant_id: str, workflow_id: str) -> Path:
    return Path(DATA_DIR) / "tenants" / tenant_id / "workflows" / workflow_id / "state.json"


def write_snapshot(state: WorkspaceState) -> Path:
    """Persist a workspace's serialized form to disk.

    Atomic via write-temp + rename; never leaves a partial file behind.
    Returns the path on success; raises OSError on failure.
    """
    path = _snapshot_path(state.tenant_id, state.workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(state.to_serializable(), default=str, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
    tmp.replace(path)
    return path


def read_snapshot(tenant_id: str, workflow_id: str) -> WorkspaceState | None:
    """Load a previously-written snapshot. Returns None if missing or
    unreadable; logs the failure."""
    path = _snapshot_path(tenant_id, workflow_id)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("snapshot read failed for %s/%s: %s", tenant_id, workflow_id, e)
        return None
    return WorkspaceState.from_serializable(data)


def hydrate_workspace_from_snapshot(tenant_id: str, workflow_id: str) -> WorkspaceState | None:
    """Read a snapshot from disk and load it into the workspace store.
    Idempotent: if already in-memory, returns the live state."""
    store = get_workspace_store()
    existing = store.get(tenant_id, workflow_id)
    if existing is not None:
        return existing
    state = read_snapshot(tenant_id, workflow_id)
    if state is None:
        return None
    store.upsert(state)
    return state


def remove_snapshot(tenant_id: str, workflow_id: str) -> bool:
    path = _snapshot_path(tenant_id, workflow_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.warning("snapshot remove failed for %s/%s: %s", tenant_id, workflow_id, e)
        return False

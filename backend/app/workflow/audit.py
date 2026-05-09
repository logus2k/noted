"""Per-workflow audit log writer.

Each step transition lands one JSONL line at:
  data/tenants/<tenant_id>/workflows/<workflow_id>/audit.jsonl

Distinct from noted-tools' per-tool audit (Phase A.6) which records
tool invocations. This file records workflow-level lifecycle events:
workflow_started, step_started, step_completed, step_failed,
workflow_suspended, workflow_resumed, workflow_completed, workflow_failed.

Append-only, append-on-event, no rotation in V1 (audit volumes per
workflow are small).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _audit_path(tenant_id: str, workflow_id: str) -> Path:
    return Path(DATA_DIR) / "tenants" / tenant_id / "workflows" / workflow_id / "audit.jsonl"


def record(
    tenant_id: str,
    workflow_id: str,
    event: str,
    payload: dict[str, Any] | None = None,
    actor_id: str = "default",
) -> None:
    """Append one audit line for a workflow lifecycle event.

    `event` is the Socket.io-aligned name (workflow_started, step_completed,
    workflow_suspended, ...). `payload` carries event-specific fields; secrets
    must never be passed in (use hashes / placeholders, same discipline as
    noted-tools' per-tool audit).
    """
    path = _audit_path(tenant_id, workflow_id)
    line = {
        "at": _now_iso(),
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "actor_id": actor_id,
        "event": event,
        "payload": payload or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("audit dir create failed for %s/%s: %s", tenant_id, workflow_id, e)
        return
    try:
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, default=str) + "\n")
    except OSError as e:
        logger.warning("audit write failed for %s/%s: %s", tenant_id, workflow_id, e)


def read(
    tenant_id: str,
    workflow_id: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return up to `limit` most recent audit lines (oldest first within the slice)."""
    path = _audit_path(tenant_id, workflow_id)
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out

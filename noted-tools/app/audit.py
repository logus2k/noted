"""Audit log writer.

Phase A.6: every `tools/call` lands one JSONL line in
`<tool_dir>/history/audit.jsonl`.

Recorded:
- tool_name, version (from _meta), actor_id (V1 constant "system")
- started_at / finished_at as RFC 3339 UTC strings
- elapsed_s, exit_code, status (ok | error | timeout | oom)
- input_hash + output_hash: sha256 truncated to 16 chars. Never the
  actual values, so secrets passed via {"$secret": "..."} indirection
  cannot leak into the log.
- error: stderr tail (last 1000 chars) on non-ok status, else null.

Append-only; no rotation in V1 (audit volumes are tiny per tool).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .executor import ExecResult
from .registry import ToolEntry

logger = logging.getLogger(__name__)

_lock = RLock()


def _hash_json(obj: Any) -> str:
    try:
        s = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        s = str(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _status(result: ExecResult) -> str:
    if result.timed_out:
        return "timeout"
    if result.oom_killed:
        return "oom"
    return "ok" if result.ok else "error"


def record(
    entry: ToolEntry,
    arguments: dict[str, Any],
    result: ExecResult,
    started_at: str,
    finished_at: str,
    actor_id: str = "system",
) -> None:
    audit_dir = Path(entry.tool_dir) / "history"
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("audit dir create failed for %s: %s", entry.name, e)
        return

    line = {
        "tool_name": entry.name,
        "version": (entry.meta or {}).get("version"),
        "actor_id": actor_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_s": round(result.elapsed_s, 3),
        "status": _status(result),
        "exit_code": result.exit_code,
        "input_hash": _hash_json(arguments),
        "output_hash": _hash_json(result.stdout) if result.stdout else None,
        "error": (result.stderr.strip()[-1000:] or None) if not result.ok else None,
    }

    audit_path = audit_dir / "audit.jsonl"
    try:
        with _lock:
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, default=str) + "\n")
    except OSError as e:
        logger.warning("audit write failed for %s: %s", entry.name, e)


def read_audit(tool_dir: Path, limit: int = 100) -> list[dict[str, Any]]:
    """Return the last `limit` audit entries for a tool. Newest last."""
    path = tool_dir / "history" / "audit.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out

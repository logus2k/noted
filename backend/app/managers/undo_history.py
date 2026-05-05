"""Per-target snapshot ring for the Take-Notes undo capability (NOTES-4).

Stores the last N=10 snapshots of each target's content keyed by a
namespaced string (`buffer:<id>` or `file:<project_id>:<path>`).
A snapshot is pushed BEFORE any write that mutates the target, so
undo_last_change pops the most recent snapshot and restores it.

Single-process singleton; uvicorn runs noted with one worker today,
so a module-level dict is enough. Multi-worker scaling would move
this to Redis or chat_id-keyed shared storage.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional


_MAX_SNAPSHOTS = 10
_lock = threading.Lock()
_history: dict[str, "deque[dict]"] = {}


def push(target: str, snapshot: dict) -> None:
    """Stash a pre-write snapshot for `target`.

    Snapshot shape:
      {"kind": "buffer", "buffer_id": str, "name": str, "content": str, "path": str | None}
      {"kind": "file",   "project_id": str, "path": str, "content": str}
    """
    if not target:
        return
    with _lock:
        d = _history.setdefault(target, deque(maxlen=_MAX_SNAPSHOTS))
        d.append(snapshot)


def pop(target: str) -> Optional[dict]:
    with _lock:
        d = _history.get(target)
        if not d:
            return None
        return d.pop()


def peek(target: str) -> Optional[dict]:
    with _lock:
        d = _history.get(target)
        if not d:
            return None
        return d[-1] if d else None


def depth(target: str) -> int:
    with _lock:
        d = _history.get(target)
        return len(d) if d else 0


def clear(target: str) -> None:
    with _lock:
        _history.pop(target, None)

"""In-memory document buffers for the Take-Notes capability.

Used by the Assistant's note-taking tools (create_doc, append_to_doc,
replace_doc, read_doc). Buffers live only until the user saves them
(NOTES-2 Save flow), at which point they become path-bound and the
buffer is retired in favour of normal on-disk file edits.

Single-process singleton; uvicorn runs noted with one worker today,
so a module-level dict is sufficient. If we add workers, move to a
shared store keyed by chat_id.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, asdict


@dataclass
class DocBuffer:
    buffer_id: str
    name: str
    content: str
    path: str | None = None  # set by NOTES-2 Save flow once persisted


_lock = threading.Lock()
_buffers: dict[str, DocBuffer] = {}


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def create(name: str | None = None, initial_content: str = "") -> DocBuffer:
    bid = uuid.uuid4().hex
    if not name:
        name = f"notes-{_short_id()}.md"
    buf = DocBuffer(buffer_id=bid, name=name, content=initial_content or "")
    with _lock:
        _buffers[bid] = buf
    return buf


def get(buffer_id: str) -> DocBuffer | None:
    with _lock:
        return _buffers.get(buffer_id)


def append(buffer_id: str, content: str, separator: str = "\n\n") -> DocBuffer | None:
    with _lock:
        buf = _buffers.get(buffer_id)
        if not buf:
            return None
        if buf.content and content:
            buf.content = buf.content + separator + content
        else:
            buf.content = (buf.content or "") + (content or "")
        return buf


def replace(buffer_id: str, content: str) -> DocBuffer | None:
    with _lock:
        buf = _buffers.get(buffer_id)
        if not buf:
            return None
        buf.content = content or ""
        return buf


def to_dict(buf: DocBuffer) -> dict:
    return asdict(buf)

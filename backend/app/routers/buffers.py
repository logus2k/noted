"""In-memory document buffer persistence (NOTES-2 Save flow).

Endpoints:
  POST /api/buffers/{buffer_id}/save
    Persist a Take-Notes buffer to disk under a project. Body specifies
    project_id and the relative path within that project. After a
    successful save the buffer is marked path-bound and subsequent saves
    can skip the Save-As dialog on the frontend.

  GET /api/buffers/{buffer_id}
    Read the current state of a buffer (for debug / UI sync).

Buffers themselves are managed in app.managers.notes_buffer; this router
is the bridge between the frontend Save flow and on-disk persistence.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.managers import notes_buffer
from app.managers.file_manager import FileManager
from app.managers.project_registry import get_registry
from app.workflow import doc_events


router = APIRouter(prefix="/api/buffers", tags=["buffers"])
_file_mgr = FileManager()
logger = logging.getLogger(__name__)


class SaveBufferRequest(BaseModel):
    project_id: str
    path: str
    content: str | None = None


@router.get("/{buffer_id}")
def get_buffer(buffer_id: str):
    buf = notes_buffer.get(buffer_id)
    if not buf:
        raise HTTPException(status_code=404, detail=f"Buffer {buffer_id} not found")
    return notes_buffer.to_dict(buf)


@router.post("/{buffer_id}/save")
def save_buffer(buffer_id: str, body: SaveBufferRequest):
    buf = notes_buffer.get(buffer_id)
    if not buf:
        raise HTTPException(status_code=404, detail=f"Buffer {buffer_id} not found")

    project_id = (body.project_id or "").strip()
    rel_path = (body.path or "").strip().lstrip("/")
    if not project_id or not rel_path:
        raise HTTPException(status_code=400, detail="project_id and path are required")

    # If the frontend is editing in-place, ship the textarea content with the
    # save call so the server-side buffer reflects the user's current edits
    # before the on-disk write.
    if body.content is not None:
        notes_buffer.replace(buffer_id, body.content)
        buf = notes_buffer.get(buffer_id)

    registry = get_registry()
    root_type = "mount" if registry.is_mount(project_id) else "project"
    try:
        result = _file_mgr.write_file(root_type, project_id, rel_path, buf.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    bound_path = f"{project_id}/{result.get('path', rel_path)}"
    notes_buffer.bind_path(buffer_id, bound_path)

    return {
        "saved": True,
        "buffer_id": buffer_id,
        "project_id": project_id,
        "path": result.get("path", rel_path),
        "bound_path": bound_path,
    }


@router.get("/events/stream")
async def buffer_events_stream():
    """SSE stream of doc-buffer and workflow lifecycle events.

    The frontend connects here once on app boot and listens for:
      - `doc_changed`: a buffer was written (by any code path). Carries
        buffer_id, name, size. The viewer re-fetches via
        `GET /api/buffers/<id>` to pick up the new content.
      - `workflow_event`: lifecycle changes (started, suspended for
        review, completed, ...). Drives Workflow Monitor + chat-side
        reactions without polling.

    Background research workflows write into doc buffers via
    `execute_tool` (server-side, not chat-driven) and have no per-turn
    SSE channel to write into. This stream fills that gap so the
    frontend viewer updates live while research is running.
    """
    async def gen():
        # Immediate hello so the EventSource opens with a confirmed
        # connection (some proxies need bytes before they unblock).
        yield "event: hello\ndata: {}\n\n"
        last_heartbeat = asyncio.get_event_loop().time()
        try:
            async for ev in doc_events.subscribe():
                yield f"data: {json.dumps(ev)}\n\n"
                # Heartbeat every ~25s to keep intermediaries from
                # closing an idle connection. Cheap: just a comment
                # line, not parsed by EventSource.
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > 25:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
        except asyncio.CancelledError:
            # Normal disconnect; subscribe()'s finally clause removes
            # the queue from the registry.
            raise
        except Exception:
            logger.exception("buffer_events_stream crashed")
            raise

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            # Per feedback_sse_needs_x_accel_buffering: required to keep
            # nginx from buffering per-event chunks; without it, events
            # bunch until end-of-stream.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )

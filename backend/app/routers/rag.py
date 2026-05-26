"""RAG API - proxy + write side for the noted-rag sidecar.

noted-rag sees the corpus tree as read-only (DOC_ROOT bind-mounted ro).
Every write therefore happens here: file uploads, edits to the persistent
source inventory (`rag_sources.json`), and removal of source entries.
After mutating, this router asks noted-rag to (re)ingest or drop chunks.

The frontend cannot reach noted-rag directly anyway - all of its tree
calls go through this prefix - so consolidating writes here keeps the
blast radius small and matches the read-only mount.
"""

import asyncio
import base64
import json
import os
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.config import DATA_DIR
from app.managers.rag_manager import RagManager

router = APIRouter(prefix="/api/rag", tags=["rag"])

_manager = RagManager()

# Where uploaded markdown files land. Sibling of `data/documents/files/`,
# created on demand. noted-rag's DOC_ROOT mount surfaces this folder
# read-only at the path `/docs/data/documents/rag_sources/`.
RAG_UPLOAD_DIR = os.path.join(DATA_DIR, "documents", "rag_sources")
# Where the persistent source inventory lives. Read-only from noted-rag,
# read-write from here.
SOURCES_JSON = os.path.join(DATA_DIR, "documents", "rag_sources.json")
# `source_path` values stored in the inventory and reported to noted-rag
# are relative to its DOC_ROOT (== the noted repo root).
RAG_UPLOAD_REL = "data/documents/rag_sources"

MAX_TAGS = 10
ALLOWED_EXTS = {".md", ".markdown"}
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Mirror of noted-rag's in-memory seed; used only when SOURCES_JSON is
# absent and we need to materialise it. Keeps the two sides agreed on
# the bootstrap corpus.
_SEED_SOURCES = [
    {"source_path": "documents/architecture/noted_technical_architecture.md",      "tags": ["architecture"]},
    {"source_path": "documents/developer/noted_platform_developer_manual.md",      "tags": ["developer-manual"]},
    {"source_path": "documents/developer/noted_project_notebook_companion.md",     "tags": ["developer-manual"]},
    {"source_path": "documents/noted_architecture_principles.md",                  "tags": ["principles"]},
    {"source_path": "documents/noted_vision.md",                                   "tags": ["vision"]},
    {"source_path": "data/documents/files/noted_platform_user_manual.md",          "tags": ["user-manual"]},
    {"source_path": "README.md",                                                   "tags": ["readme"]},
    {"source_path": "NOTED_SETUP.md",                                              "tags": ["setup-guide"]},
    {"source_path": "jena_weather_report/FINAL/noted_platform_final_delivery_project_report.md", "tags": ["project-report"]},
]

# Reentrant lock - the upsert/remove paths acquire it and then call the
# read/write helpers which used to acquire it again. With a plain Lock
# that nests itself the worker DEADLOCKS (single-threaded async loop sits
# forever inside the second .acquire()), freezing every request piling up
# behind it. RLock is reentrant on the same thread, so the nested call is
# safe.
_SOURCES_LOCK = threading.RLock()


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _ensure_upload_dir() -> None:
    os.makedirs(RAG_UPLOAD_DIR, exist_ok=True)


def _read_sources_unlocked() -> list[dict]:
    """Read the inventory without acquiring the lock. Caller is responsible
    for locking. Materialises the seed file if missing."""
    if not os.path.isfile(SOURCES_JSON):
        os.makedirs(os.path.dirname(SOURCES_JSON), exist_ok=True)
        seeded = [{**s, "added_utc": _now_utc()} for s in _SEED_SOURCES]
        with open(SOURCES_JSON, "w") as f:
            json.dump({"sources": seeded}, f, indent=2)
        return seeded
    try:
        with open(SOURCES_JSON) as f:
            data = json.load(f)
        return data.get("sources") or []
    except Exception:
        return [{**s, "added_utc": _now_utc()} for s in _SEED_SOURCES]


def _write_sources_unlocked(sources: list[dict]) -> None:
    """Write the inventory without acquiring the lock. Caller locks."""
    os.makedirs(os.path.dirname(SOURCES_JSON), exist_ok=True)
    with open(SOURCES_JSON, "w") as f:
        json.dump({"sources": sources}, f, indent=2)


def _upsert_source_local(
    source_path: str,
    tags: list[str],
    chunking_profile_id: str | None = None,
) -> dict:
    """Add or update a source inventory entry. Returns the stored record.

    `chunking_profile_id` is persisted so a subsequent bulk re-ingest of
    the parent collection rechunks this source with the same profile
    that produced its current chunks. Pass None to leave the field
    untouched on update (existing rows keep their old value); the
    `chunking_profile_id` key is omitted entirely on new rows when
    None."""
    with _SOURCES_LOCK:
        sources = _read_sources_unlocked()
        existing = next((s for s in sources if s.get("source_path") == source_path), None)
        if existing:
            existing["tags"] = tags
            if chunking_profile_id is not None:
                existing["chunking_profile_id"] = chunking_profile_id
        else:
            entry = {
                "source_path": source_path,
                "tags": tags,
                "added_utc": _now_utc(),
            }
            if chunking_profile_id is not None:
                entry["chunking_profile_id"] = chunking_profile_id
            sources.append(entry)
        _write_sources_unlocked(sources)
    record = {"source_path": source_path, "tags": tags}
    if chunking_profile_id is not None:
        record["chunking_profile_id"] = chunking_profile_id
    return record


def _remove_source_local(source_path: str) -> bool:
    with _SOURCES_LOCK:
        sources = _read_sources_unlocked()
        remaining = [s for s in sources if s.get("source_path") != source_path]
        if len(remaining) == len(sources):
            return False
        _write_sources_unlocked(remaining)
    return True


def _validate_filename(name: str) -> str:
    base = os.path.basename(name or "")
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not SAFE_NAME_RE.match(base):
        raise HTTPException(
            status_code=400,
            detail="filename must use only letters, digits, dot, underscore, hyphen",
        )
    ext = os.path.splitext(base)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported extension {ext!r}; allowed: {sorted(ALLOWED_EXTS)}",
        )
    return base


def _parse_tags(raw: str) -> list[str]:
    seen: list[str] = []
    for tok in (raw or "").split():
        tok = tok.strip()
        if not tok:
            continue
        if tok not in seen:
            seen.append(tok)
    if not seen:
        raise HTTPException(status_code=400, detail="at least one tag is required")
    if len(seen) > MAX_TAGS:
        raise HTTPException(status_code=400, detail=f"maximum {MAX_TAGS} tags per source")
    return seen


def _decode_source_b64(source_b64: str) -> str:
    try:
        padded = source_b64 + "=" * (-len(source_b64) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid source id (bad base64)")


# ── Read-only proxies (browser feeds the Explorer tree) ────────────────

@router.get("/health")
async def health():
    return await _manager.health()


@router.get("/index/sources")
async def index_sources(collection: str | None = None):
    return await _manager.list_sources(collection=collection)


@router.get("/index/format_breakdown")
async def index_format_breakdown(collection: str | None = None):
    return await _manager.format_breakdown(collection=collection)


@router.get("/index/sources/{source_b64}/chunks")
async def index_source_chunks(source_b64: str, collection: str | None = None):
    return await _manager.list_source_chunks(source_b64, collection=collection)


@router.get("/index/chunks/{chunk_b64}")
async def index_chunk(chunk_b64: str, collection: str | None = None):
    return await _manager.get_chunk(chunk_b64, collection=collection)


# ── Inventory + upload (writes own DOC_ROOT subtree) ───────────────────

@router.get("/sources/check")
async def sources_check(filename: str):
    """Tell the frontend whether the chosen filename already exists in the
    rag_sources/ folder so it can prompt for overwrite confirmation."""
    base = _validate_filename(filename)
    full_path = os.path.join(RAG_UPLOAD_DIR, base)
    return {"filename": base, "exists": os.path.isfile(full_path)}


@router.post("/sources/upload")
async def sources_upload(
    file: UploadFile,
    tags: str = Form(...),
    overwrite: str = Form("false"),
    collection: str = Form(""),
    chunking_profile: str = Form(""),
):
    """Upload a markdown file into rag_sources/, add it to the inventory,
    and kick off an asynchronous ingest.

    Returns IMMEDIATELY with the ingest job_id; the caller polls
    `/api/rag/ingest/status/{job_id}` (or, when SSE lands, subscribes to
    a stream) for progress. Never blocks on the embedding work - that
    would freeze the noted API for the duration of the ingest.

    P3.2: `collection` form field selects the per-KB ChromaDB collection
    name; default empty -> noted-rag uses legacy `noted_corpus`."""
    base = _validate_filename(file.filename or "")
    tag_list = _parse_tags(tags)
    overwrite_flag = (overwrite or "false").strip().lower() in ("true", "1", "yes")

    _ensure_upload_dir()
    dest = os.path.join(RAG_UPLOAD_DIR, base)
    if os.path.isfile(dest) and not overwrite_flag:
        raise HTTPException(
            status_code=409,
            detail=f"{base} already exists; resubmit with overwrite=true to replace",
        )

    payload = await file.read()
    with open(dest, "wb") as f:
        f.write(payload)

    relative = f"{RAG_UPLOAD_REL}/{base}"
    record = _upsert_source_local(
        relative, tag_list,
        chunking_profile_id=chunking_profile or None,
    )

    # Fire-and-forget. noted-rag returns the job_id straight away; we hand
    # it to the frontend so it can show progress + refresh on completion.
    # `source_path` scopes the run to JUST the file we wrote — otherwise
    # noted-rag's /ingest walks the whole inventory and dumps every
    # source into the target collection (the pre-existing "polluted
    # cv__corpus" bug, see documents/plans/noted_rag_per_source_ingest.md).
    job = await _manager.trigger_ingest(
        collection=collection or None,
        chunking_profile=chunking_profile or None,
        source_path=relative,
    )
    if job.get("status") == "unavailable":
        # Roll back so a phantom inventory entry doesn't point at content
        # that was never indexed.
        _remove_source_local(relative)
        try:
            os.remove(dest)
        except OSError:
            pass
        raise HTTPException(
            status_code=502,
            detail=f"noted-rag unreachable: {job.get('detail', '')}",
        )
    return {
        "filename": base,
        "source": record,
        "job_id": job.get("job_id", ""),
        "ingest_status": job.get("status", "queued"),
    }


@router.get("/ingest/status/{job_id}")
async def ingest_status(job_id: str):
    """One-shot status proxy. The frontend should prefer the streaming
    endpoint below; this is here for cases where opening an SSE channel
    is overkill (e.g. a quick recheck)."""
    return await _manager.get_ingest_status(job_id)


@router.get("/ingest/stream/{job_id}")
async def ingest_stream(job_id: str):
    """Server-sent events stream of ingest progress. The frontend opens
    this with EventSource and updates the toast / tree as events arrive.
    The server polls noted-rag (loopback over the docker network is
    cheap) and forwards each status. Stops when terminal."""
    async def event_generator():
        terminal = ("done", "error", "not_found", "unavailable")
        last_payload = None
        # Hard cap on the stream length so a stuck ingest cannot leak a
        # connection forever. 5 minutes is well past the worst-case
        # embedding time on this corpus (single source typically <30s).
        max_iters = 200
        for _ in range(max_iters):
            payload = await _manager.get_ingest_status(job_id)
            if payload != last_payload:
                yield f"data: {json.dumps(payload)}\n\n"
                last_payload = payload
            if payload.get("status") in terminal:
                return
            await asyncio.sleep(1.5)
        yield f"data: {json.dumps({'status': 'timeout', 'job_id': job_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest")
async def trigger_reingest(
    collection: str | None = None,
    chunking_profile: str | None = None,
):
    """Kick a fresh ingest pass without an upload. Useful for the user
    who edits a file already on disk and wants the index refreshed.
    Fire-and-forget; returns the job_id.

    `chunking_profile` (optional) overrides the run-level default
    chunking profile for this pass."""
    return await _manager.trigger_ingest(
        collection=collection,
        chunking_profile=chunking_profile,
    )


@router.get("/chunking-profiles")
async def chunking_profiles():
    """Proxy the catalog of named chunking profiles from noted-rag so
    the frontend can populate the Document Import dropdown without
    needing to know about the noted-rag service."""
    return await _manager.list_chunking_profiles()


@router.delete("/sources/{source_b64}")
async def sources_delete(
    source_b64: str,
    delete_file: bool = False,
    collection: str | None = None,
):
    """Remove a source from the corpus.

    Order matters: drop the inventory entry FIRST so a concurrent /ingest
    cannot resurrect the chunks we are about to delete from Chroma. The
    underlying file in rag_sources/ is left on disk by default.

    P3.2: `collection` selects per-KB ChromaDB collection name."""
    source_path = _decode_source_b64(source_b64)
    removed_inventory = _remove_source_local(source_path)
    upstream = await _manager.delete_source(source_b64, collection=collection)
    if upstream.get("status") in ("invalid_id", "unavailable"):
        raise HTTPException(
            status_code=502,
            detail=f"noted-rag delete failed: {upstream.get('detail', upstream.get('status'))}",
        )
    file_removed = False
    if delete_file and source_path.startswith(RAG_UPLOAD_REL + "/"):
        full = os.path.join(DATA_DIR, *source_path.split("/")[1:])
        try:
            os.remove(full)
            file_removed = True
        except OSError:
            pass
    return {
        "removed_from_inventory": removed_inventory,
        "file_removed": file_removed,
        **upstream,
    }

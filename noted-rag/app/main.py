"""noted-rag FastAPI app.

Endpoints:
  GET  /health                   - liveness (no model load required)
  POST /search                   - dense + rerank retrieval
  POST /ingest                   - kicks off a background re-ingest; returns job_id
  GET  /ingest/status/{job_id}   - polls an ingest job
  GET  /collections              - current collections + counts
  GET  /index/sources            - distinct source files + chunk counts (Explorer tree root)
  DELETE /index/sources/{b64}    - drop a source's chunks from Chroma (the noted side
                                    is responsible for first updating the JSON inventory)
  GET  /index/sources/{b64}/chunks - chunks for one source (Explorer tree leaves)
  GET  /index/chunks/{b64}       - single chunk detail (click-through)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import config, ingest
from .ingest import COLLECTION_NAME, ChunkRecord, _content_hash, _slug
from .rag_service import RagService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

rag = RagService()
_jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("noted-rag starting; CHROMA_DIR=%s MODEL_CACHE=%s DOC_ROOT=%s DEVICE=%s",
                config.CHROMA_DIR, config.MODEL_CACHE, config.DOC_ROOT, config.DEVICE)
    config.ensure_dirs()

    # Pre-load the embedder + reranker so the FIRST /search request hits
    # warm GPU instead of racing the noted-side 8 s client timeout against
    # a ~30 s cold model load. Without this warm-up the first user-facing
    # search reliably comes back as "unavailable" even though the service
    # is healthy. asyncio.to_thread keeps the event loop responsive
    # (only matters if anything else were running during startup, which
    # it isn't, but keeps the pattern correct).
    #
    # If a model fails to load we let the exception propagate. Per
    # `feedback_no_silent_degradation` partial readiness (/health OK but
    # /search broken) is worse than a crash loop the operator can see.
    t0 = time.perf_counter()
    await asyncio.to_thread(rag._get_embedder)
    t_embed = time.perf_counter() - t0
    await asyncio.to_thread(rag._get_reranker)
    t_rerank = (time.perf_counter() - t0) - t_embed
    # Also warm the chroma client. Without this, the FIRST /search_multi
    # call after startup races chromadb's internal `_instances` dict with
    # any concurrent caller (e.g., a speculative + chat call landing
    # near-simultaneously), surfacing as
    # `RuntimeError: dictionary changed size during iteration`.
    await asyncio.to_thread(rag._get_client)
    t_chroma = (time.perf_counter() - t0) - t_embed - t_rerank
    logger.info("noted-rag warm-up done: embedder=%.1fs reranker=%.1fs chroma=%.1fs total=%.1fs",
                t_embed, t_rerank, t_chroma, time.perf_counter() - t0)

    yield
    logger.info("noted-rag shutting down")


app = FastAPI(title="noted-rag", version="0.1.0", lifespan=lifespan)


# ── Per-request trace context (turn-id / call-source) ─────────────
# Read X-Turn-Id and X-Call-Source from incoming requests and stash in
# rag_service's contextvars so EMBED_TIMING / SEARCH_TIMING log lines
# can include them. Lets us correlate noted-side and noted-rag-side
# log entries for one chat turn.
@app.middleware("http")
async def _attach_trace_context(request, call_next):
    from .rag_service import set_trace_context
    turn_id = request.headers.get("x-turn-id") or "no-turn"
    source = request.headers.get("x-call-source") or "unknown"
    tokens = set_trace_context(turn_id, source)
    try:
        return await call_next(request)
    finally:
        from .rag_service import reset_trace_context
        reset_trace_context(tokens)


# ── Schemas ──────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    tags: list[str] | None = Field(default=None, description="Optional 'key:value' tag filters (AND'd)")
    top_k: int = Field(default=config.FINAL_TOP_K, ge=1, le=20)
    collection: str | None = Field(
        default=None,
        description="Per-Domain corpus collection name. Defaults to legacy noted_corpus.",
    )
    source_paths: list[str] | None = Field(
        default=None,
        description="Optional restriction to chunks whose source_path is in this list (per-document scoping).",
    )


class SearchResponse(BaseModel):
    status: str
    chunks: list[dict]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Strings to embed")


class EmbedResponse(BaseModel):
    status: str
    dim: int
    vectors: list[list[float]]


class CacheUpsertRequest(BaseModel):
    """Embed and store strings in a named ChromaDB collection. Used by
    noted-graph at GraphRAG rebuild time to cache entity-name and
    community-summary embeddings, so query time becomes a vector search
    rather than a re-embed cycle."""
    collection: str = Field(..., min_length=1)
    ids: list[str] = Field(..., min_length=1)
    texts: list[str] = Field(..., min_length=1)
    replace: bool = Field(
        default=True,
        description="If true, drop the entire collection before upserting "
                    "(use for full-rebuild flows; ensures stale ids are gone).",
    )


class CacheUpsertResponse(BaseModel):
    status: str
    collection: str
    upserted: int
    replaced: bool


class CacheSearchRequest(BaseModel):
    collection: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=200)


class CacheSearchByVectorRequest(BaseModel):
    collection: str = Field(..., min_length=1)
    vector: list[float] = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=200)


class SearchByVectorRequest(BaseModel):
    query_text: str = Field(..., min_length=1, description="Original query text - reranker pairs it with each chunk")
    vector: list[float] = Field(..., min_length=1, description="Pre-computed bge-m3 query embedding")
    tags: list[str] | None = Field(default=None)
    top_k: int = Field(default=5, ge=1, le=20)
    collection: str | None = Field(
        default=None,
        description="Per-Domain corpus collection name. Defaults to legacy noted_corpus.",
    )
    source_paths: list[str] | None = Field(
        default=None,
        description="Optional restriction to chunks whose source_path is in this list (per-document scoping).",
    )


class CacheSearchHit(BaseModel):
    id: str
    score: float
    text: str | None = None


class CacheSearchResponse(BaseModel):
    status: str
    collection: str
    hits: list[CacheSearchHit]


class CacheDropRequest(BaseModel):
    collection: str = Field(..., min_length=1)


# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "device": config.DEVICE}


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    try:
        chunks = rag.search(
            req.query, tags=req.tags, top_k=req.top_k,
            collection=req.collection, source_paths=req.source_paths,
        )
        return SearchResponse(status="ok", chunks=chunks)
    except Exception as e:
        logger.exception("search failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/cache/upsert", response_model=CacheUpsertResponse)
async def cache_upsert(req: CacheUpsertRequest) -> CacheUpsertResponse:
    """Embed + store strings in a named ChromaDB collection."""
    try:
        n, replaced = rag.cache_upsert(req.collection, req.ids, req.texts, req.replace)
        return CacheUpsertResponse(
            status="ok", collection=req.collection,
            upserted=n, replaced=replaced,
        )
    except Exception as e:
        logger.exception("cache upsert failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/cache/search", response_model=CacheSearchResponse)
def cache_search(req: CacheSearchRequest) -> CacheSearchResponse:
    """Vector-search a cached collection and return ranked hits."""
    try:
        hits = rag.cache_search(req.collection, req.query, req.top_k)
        return CacheSearchResponse(
            status="ok", collection=req.collection,
            hits=[CacheSearchHit(**h) for h in hits],
        )
    except Exception as e:
        logger.exception("cache search failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/cache/search_by_vector", response_model=CacheSearchResponse)
def cache_search_by_vector(req: CacheSearchByVectorRequest) -> CacheSearchResponse:
    """Same as /cache/search but takes a pre-computed query vector,
    skipping the bge-m3 embed step. Used by the parallel-retrieval tool
    so we embed once in the caller and fan out to multiple stores
    without GPU contention on this service's embed model."""
    try:
        hits = rag.cache_search_by_vector(req.collection, req.vector, req.top_k)
        return CacheSearchResponse(
            status="ok", collection=req.collection,
            hits=[CacheSearchHit(**h) for h in hits],
        )
    except Exception as e:
        logger.exception("cache search_by_vector failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/search_by_vector", response_model=SearchResponse)
def search_by_vector(req: SearchByVectorRequest) -> SearchResponse:
    """Same as /search but takes a pre-computed query vector. The
    cross-encoder reranker still needs the original query text (it
    pairs query+chunk for relevance scoring), so the request carries
    both. Used by the parallel-retrieval tool."""
    try:
        chunks = rag.search_by_vector(
            query_text=req.query_text, query_vec=req.vector,
            tags=req.tags, top_k=req.top_k,
            collection=req.collection, source_paths=req.source_paths,
        )
        return SearchResponse(status="ok", chunks=chunks)
    except Exception as e:
        logger.exception("search_by_vector failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


class SearchMultiRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collections: list[str] = Field(..., min_length=1)
    tags: list[str] | None = None
    top_k: int = Field(default=config.FINAL_TOP_K, ge=1, le=50)
    merge_top_n: int | None = Field(
        default=None,
        description=(
            "How many candidates from the merged-by-distance union are "
            "passed to the reranker. Defaults to DENSE_TOP_K."
        ),
    )
    source_paths: list[str] | None = None
    vector: list[float] | None = Field(
        default=None,
        description="Optional pre-computed query vector to skip the embed step.",
    )


@app.post("/search_multi", response_model=SearchResponse)
def search_multi(req: SearchMultiRequest) -> SearchResponse:
    """Multi-collection search with single-batch rerank.

    See RagService.search_multi for the pipeline. Replaces N parallel
    /search_by_vector calls with one HTTP round trip and one reranker
    batch — eliminates GPU contention between concurrent rerank batches
    and trims the rerank work from N*DENSE_TOP_K pairs to merge_top_n
    pairs (typically DENSE_TOP_K, ~3x reduction for 4 active Domains).
    """
    try:
        chunks = rag.search_multi(
            query=req.query,
            collections=req.collections,
            tags=req.tags,
            top_k=req.top_k,
            merge_top_n=req.merge_top_n,
            source_paths=req.source_paths,
            query_vec=req.vector,
        )
        return SearchResponse(status="ok", chunks=chunks)
    except Exception as e:
        logger.exception("search_multi failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/cache/drop")
async def cache_drop(req: CacheDropRequest) -> dict:
    return {"status": "ok", "dropped": rag.cache_drop(req.collection)}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    """Return bge-m3 dense embeddings for a list of strings.

    Used by noted-graph for GraphRAG's sameAs edges, community-summary
    routing, and local-mode entry-entity vector search.
    """
    try:
        vectors = rag.embed(req.texts)
        dim = len(vectors[0]) if vectors else 0
        return EmbedResponse(status="ok", dim=dim, vectors=vectors)
    except Exception as e:
        logger.exception("embed failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


class UpsertChunk(BaseModel):
    chunk_index: int
    section_path: str
    text: str
    page_no: int | None = None
    bbox: list[float] | None = None  # [x0, y0, x1, y1] in PDF coords
    section_level: int | None = None


class UpsertChunksRequest(BaseModel):
    """Pre-chunked input from noted-graph (Plan B): noted-graph parses
    PDFs/DOCX/PPTX with Docling, then ships the resulting chunks here for
    embedding + ChromaDB upsert. noted-rag never sees the source file."""
    source_path: str
    tags: list[str] = Field(default_factory=list)
    last_modified: str  # ISO timestamp from caller
    format: str = "pdf"
    collection: str | None = Field(
        default=None,
        description="P3.2: per-KB corpus collection. Defaults to legacy noted_corpus.",
    )
    chunks: list[UpsertChunk]


class UpsertChunksResponse(BaseModel):
    status: str
    indexed: int
    skipped_unchanged: int
    deleted_stale: int


@app.post("/upsert_chunks", response_model=UpsertChunksResponse)
def upsert_chunks(req: UpsertChunksRequest) -> UpsertChunksResponse:
    """Embed + upsert pre-chunked text into noted_corpus.

    Idempotent on content_hash like /ingest, scoped to a single source_path.
    Stale chunks for the same source (present before, absent now) are deleted.
    bbox is flattened to bbox_x0..bbox_y1 because Chroma metadata is flat.
    """
    records: list[ChunkRecord] = []
    for c in req.chunks:
        text = c.text or ""
        if not text.strip():
            continue
        section = c.section_path or "root"
        meta = {
            "source_path": req.source_path,
            "section_path": section,
            "title": section.split(" > ")[-1],
            "doc_type": req.tags[0] if req.tags else "",
            "tags": ",".join(req.tags),
            "content_hash": _content_hash(text),
            "last_modified": req.last_modified,
            "format": req.format,
        }
        if c.page_no is not None:
            meta["page_no"] = int(c.page_no)
        if c.bbox and len(c.bbox) == 4:
            meta["bbox_x0"] = float(c.bbox[0])
            meta["bbox_y0"] = float(c.bbox[1])
            meta["bbox_x1"] = float(c.bbox[2])
            meta["bbox_y1"] = float(c.bbox[3])
        if c.section_level is not None:
            meta["section_level"] = int(c.section_level)
        # Section paths can repeat across long-section splits; suffix the
        # chunk_index so ids stay unique within a doc.
        chunk_id = f"{req.source_path}#{_slug(section)}#{c.chunk_index}"
        records.append(ChunkRecord(id=chunk_id, document=text, metadata=meta))

    if not records:
        return UpsertChunksResponse(status="ok", indexed=0, skipped_unchanged=0, deleted_stale=0)

    client = rag._get_client()
    collection = client.get_or_create_collection(
        name=req.collection or COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Existing chunks for this source (only) — scope the hash diff per-doc.
    existing = collection.get(where={"source_path": req.source_path}, include=["metadatas"])
    existing_ids = set(existing.get("ids") or [])
    existing_hashes = {
        id_: (m or {}).get("content_hash", "")
        for id_, m in zip(existing.get("ids") or [], existing.get("metadatas") or [])
    }

    to_embed = [r for r in records if existing_hashes.get(r.id) != r.metadata["content_hash"]]
    skipped = len(records) - len(to_embed)

    if to_embed:
        embeddings = rag.embed([r.document for r in to_embed])
        collection.upsert(
            ids=[r.id for r in to_embed],
            documents=[r.document for r in to_embed],
            embeddings=embeddings,
            metadatas=[r.metadata for r in to_embed],
        )

    produced_ids = {r.id for r in records}
    stale_ids = list(existing_ids - produced_ids)
    if stale_ids:
        collection.delete(ids=stale_ids)

    logger.info(
        "upsert_chunks: source=%s indexed=%d skipped=%d deleted=%d",
        req.source_path, len(to_embed), skipped, len(stale_ids),
    )
    return UpsertChunksResponse(
        status="ok",
        indexed=len(to_embed),
        skipped_unchanged=skipped,
        deleted_stale=len(stale_ids),
    )


@app.post("/ingest")
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    collection: str | None = None,
) -> dict:
    """Trigger a corpus re-ingest (P3.2: `collection` query param targets
    per-KB corpora; defaults to legacy noted_corpus)."""
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {"status": "running", "collection": collection or COLLECTION_NAME}

    def _run() -> None:
        try:
            result = ingest.run_ingest(rag, collection=collection)
            _jobs[job_id] = {"status": "done", "collection": collection or COLLECTION_NAME, **result}
            logger.info("ingest %s done: %s", job_id, result)
        except Exception as e:
            logger.exception("ingest %s failed", job_id)
            _jobs[job_id] = {"status": "error", "error": f"{type(e).__name__}: {e}"}

    background_tasks.add_task(_run)
    return {"job_id": job_id, "status": "running", "collection": collection or COLLECTION_NAME}


@app.get("/ingest/status/{job_id}")
async def ingest_status(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return _jobs[job_id]


@app.get("/collections")
async def collections() -> dict:
    try:
        return {"collections": rag.list_collections()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Explorer tree endpoints ──────────────────────────────────────────
# Feed the Assistant/Embeddings node. Source paths and chunk ids can
# contain '/' and '#' which FastAPI path params don't accept directly;
# we base64-urlsafe encode them for /sources/{b64}/... and /chunks/{b64}.

def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _b64_decode(s: str) -> str:
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _get_corpus_collection(name: str | None = None):
    """Return a corpus ChromaDB collection, or None if it doesn't exist.

    P3.2: takes an optional `name` so per-KB callers can target their
    own collection (e.g. `<kb_id>__corpus`). Default is `COLLECTION_NAME`
    (legacy `noted_corpus`) for backward compat with non-KB-aware callers.
    """
    client = rag._get_client()
    try:
        return client.get_collection(name or COLLECTION_NAME)
    except Exception:
        return None


@app.delete("/index/sources/{source_b64}")
async def delete_source(source_b64: str, collection: str | None = None) -> dict:
    """Drop every chunk for a source from a Chroma collection (P3.2:
    `collection` query param targets per-KB collections; default is
    legacy `noted_corpus`).

    noted-rag's view of the source list is read-only (DOC_ROOT is mounted
    ro), so this endpoint only handles the Chroma-side cleanup. The noted
    side must remove the entry from `rag_sources.json` BEFORE calling
    here (otherwise the next `/ingest` will re-create the chunks)."""
    try:
        source_path = _b64_decode(source_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid source id (bad base64)")
    deleted_chunks = ingest.delete_source_chunks(rag, source_path, collection=collection)
    return {
        "source_path": source_path,
        "deleted_chunks": deleted_chunks,
        "collection": collection or COLLECTION_NAME,
    }


@app.get("/index/sources")
async def index_sources(collection: str | None = None) -> dict:
    """Distinct source files in the corpus with chunk counts.

    Feeds the 'Embeddings' tree root. Each entry's `id` is the opaque
    token the client passes back to /index/sources/{id}/chunks.

    P3.2: `collection` query param targets per-KB corpora; default is
    legacy `noted_corpus`.
    """
    coll = _get_corpus_collection(collection)
    if coll is None or coll.count() == 0:
        return {"total_chunks": 0, "sources": []}

    all_meta = coll.get(include=["metadatas"])
    metas = all_meta.get("metadatas") or []

    # All chunks for a source share the same tag set; a single chunk's
    # value is representative. We surface both `tags` (list) and the
    # legacy `doc_type` (first tag) so older callers keep working.
    bucket: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "last_modified_utc": "", "tags": [], "doc_type": "",
    })
    for meta in metas:
        if not meta:
            continue
        sp = meta.get("source_path") or ""
        if not sp:
            continue
        entry = bucket[sp]
        entry["count"] += 1
        lm = meta.get("last_modified") or ""
        if lm > entry["last_modified_utc"]:
            entry["last_modified_utc"] = lm
        if not entry["tags"]:
            tags_csv = meta.get("tags") or ""
            entry["tags"] = [t for t in tags_csv.split(",") if t]
            if not entry["tags"] and meta.get("doc_type"):
                entry["tags"] = [meta["doc_type"]]
        if not entry["doc_type"]:
            entry["doc_type"] = meta.get("doc_type") or (entry["tags"][0] if entry["tags"] else "")

    sources = [
        {
            "id": _b64(sp),
            "source_path": sp,
            "name": os.path.basename(sp) or sp,
            "chunk_count": info["count"],
            "tags": info["tags"],
            "doc_type": info["doc_type"],
            "last_modified_utc": info["last_modified_utc"],
        }
        for sp, info in bucket.items()
    ]
    # Alphabetical by basename (then full path to disambiguate collisions)
    sources.sort(key=lambda s: (s["name"].lower(), s["source_path"]))
    return {"total_chunks": coll.count(), "sources": sources}


@app.get("/index/format_breakdown")
async def index_format_breakdown(collection: str | None = None) -> dict:
    """Per-format chunk counts for the corpus collection (P3.2:
    `collection` query param targets per-KB corpora).

    Powers the KB Monitor's "by format" chips. Chunks ingested through
    the legacy `/ingest` markdown path do NOT carry a `format` metadata
    field (it predates the field); they're bucketed under `md`. Chunks
    written by `/upsert_chunks` (PDF / DOCX / PPTX via noted-graph) carry
    an explicit `format`. The `total` field matches the collection count
    so the UI can verify it sums correctly.
    """
    coll = _get_corpus_collection(collection)
    if coll is None:
        return {"total": 0, "by_format": {}}
    total = coll.count()
    if total == 0:
        return {"total": 0, "by_format": {}}
    all_meta = coll.get(include=["metadatas"])
    counts: dict[str, int] = defaultdict(int)
    for meta in all_meta.get("metadatas") or []:
        fmt = (meta or {}).get("format") or "md"
        counts[fmt] += 1
    return {"total": total, "by_format": dict(counts)}


@app.get("/index/sources/{source_b64}/chunks")
async def index_source_chunks(source_b64: str, collection: str | None = None) -> dict:
    """Chunks belonging to one source, sorted by section_path.

    Today's ingest does not stamp an ordinal per chunk, so the ordering
    approximates document structure via lexical sort of `section_path`.
    Re-ingest with an `ord` field can be added later without breaking
    this response shape.
    """
    try:
        source_path = _b64_decode(source_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid source id (bad base64)")

    coll = _get_corpus_collection(collection)
    if coll is None:
        raise HTTPException(status_code=503, detail="index not available")

    got = coll.get(
        where={"source_path": source_path},
        include=["metadatas"],
    )
    ids = got.get("ids") or []
    metas = got.get("metadatas") or []
    if not ids:
        raise HTTPException(status_code=404, detail=f"no chunks for source {source_path!r}")

    chunks = []
    for chunk_id, meta in zip(ids, metas):
        meta = meta or {}
        tags_csv = meta.get("tags") or ""
        tags = [t for t in tags_csv.split(",") if t]
        if not tags and meta.get("doc_type"):
            tags = [meta["doc_type"]]
        chunks.append({
            "id": _b64(chunk_id),
            "chunk_id": chunk_id,
            "section_path": meta.get("section_path") or "",
            "title": meta.get("title") or "",
            "tags": tags,
            "doc_type": meta.get("doc_type") or (tags[0] if tags else ""),
            "last_modified_utc": meta.get("last_modified") or "",
        })
    chunks.sort(key=lambda c: c["section_path"].lower())
    return {
        "source_path": source_path,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


@app.get("/index/chunks/{chunk_b64}")
async def index_chunk(chunk_b64: str, collection: str | None = None) -> dict:
    """Full text + metadata for a single chunk (click-through from the tree)."""
    try:
        chunk_id = _b64_decode(chunk_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid chunk id (bad base64)")

    coll = _get_corpus_collection(collection)
    if coll is None:
        raise HTTPException(status_code=503, detail="index not available")

    got = coll.get(ids=[chunk_id], include=["documents", "metadatas"])
    if not got.get("ids"):
        raise HTTPException(status_code=404, detail="chunk not found")

    docs = got.get("documents") or [""]
    metas = got.get("metadatas") or [{}]
    text = docs[0] or ""
    meta = metas[0] or {}
    tags_csv = meta.get("tags") or ""
    tags = [t for t in tags_csv.split(",") if t]
    if not tags and meta.get("doc_type"):
        tags = [meta["doc_type"]]
    return {
        "id": _b64(chunk_id),
        "chunk_id": chunk_id,
        "source_path": meta.get("source_path") or "",
        "section_path": meta.get("section_path") or "",
        "title": meta.get("title") or "",
        "tags": tags,
        "doc_type": meta.get("doc_type") or (tags[0] if tags else ""),
        # Approximate token count; cheap enough at read time that we do
        # not need to persist it in the ingest metadata.
        "token_count": len(text) // 4,
        "text": text,
        "last_modified_utc": meta.get("last_modified") or "",
    }

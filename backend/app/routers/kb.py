"""Domain orchestration endpoints (noted-backend side).

The noted backend's view of Domains:
  - Threads `domain_id` from path through to noted-graph's per-Domain
    endpoints (`/api/graph/research/{domain_id}/...`)
  - Threads the corpus `collection` query param through to noted-rag's
    Domain-aware corpus endpoints. Convention is `<domain_id>__corpus`
    (no legacy soft-mapping for noted - the migration on noted-graph
    rewrites the noted Domain's manifest to the convention names).
  - Owns the active-Domain state (in-memory, defaulted from
    `NOTED_ACTIVE_DOMAINS` env, fallback `general`). Tool dispatchers
    consult `get_active_domains()`.
  - Manages the Domain lifecycle (CRUD via /api/domains*).

Source-of-truth for Domain existence + collection naming lives in
noted-graph (`domain_registry` walks `data/domains/*/manifest.json`).
The noted backend MIRRORS the same registry view via the `/api/domains`
endpoints proxied to noted-graph. We don't keep an independent registry
on this side - that would invite drift.

Backward-compat aliases (`get_active_kb`, `get_active_kbs`) are kept for
unupdated callers; remove once they're swapped to the *_domain* names.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/domains", tags=["domains"])

# Loopback to noted's own routers (graph_proxy / rag_manager). Cheap.
NOTED_BASE = os.environ.get("NOTED_LOOPBACK_URL", "http://localhost:8123")
NOTED_GRAPH_BASE = os.environ.get("GRAPH_URL", "http://noted-graph:5523")

GENERAL_DOMAIN_ID = os.environ.get("GENERAL_DOMAIN_ID", "general")


# -- Active-Domain state (in-memory, env-defaulted) -----------------

_active_lock = threading.Lock()


_RESOLVE_ALL_SENTINEL = ["__resolve_all__"]


def _initial_active() -> list[str]:
    """Parse NOTED_ACTIVE_DOMAINS env (comma-separated). When unset,
    return a sentinel that triggers lazy-resolve to the FULL list of
    registered Domains on first access (queries noted-graph). This means:
    by default every Domain on disk is active out of the box; only an
    explicit env var pins a subset.

    Falls back to NOTED_ACTIVE_KBS for one transition cycle so existing
    deployments keep their setting until they update the env file.
    """
    raw = os.environ.get("NOTED_ACTIVE_DOMAINS", "").strip()
    if not raw:
        raw = os.environ.get("NOTED_ACTIVE_KBS", "").strip()
    if not raw:
        return list(_RESOLVE_ALL_SENTINEL)
    out = [s.strip() for s in raw.split(",") if s.strip()]
    return out or list(_RESOLVE_ALL_SENTINEL)


_active_domains: list[str] = _initial_active()


def _resolve_all_domains() -> list[str]:
    """Fetch the full Domain id list from noted-graph. Used to lazy-
    expand the default sentinel so every registered Domain becomes
    active out of the box. Falls back to [general, noted] if noted-graph
    is unreachable at the moment of first call."""
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{NOTED_GRAPH_BASE}/domains")
            if r.status_code == 200:
                domains = (r.json() or {}).get("domains") or []
                ids = [d.get("domain_id") for d in domains if d.get("domain_id")]
                if ids:
                    return ids
    except Exception as e:
        logger.warning("default-active resolve failed (noted-graph unreachable): %s", e)
    return [GENERAL_DOMAIN_ID, "noted"]


def _ensure_resolved() -> None:
    """If active set is still the lazy sentinel, expand to all Domains
    via a noted-graph fetch. Idempotent; safe to call from any reader."""
    global _active_domains
    if _active_domains == _RESOLVE_ALL_SENTINEL:
        resolved = _resolve_all_domains()
        _active_domains = resolved


def get_active_domain() -> str:
    """Return the first active Domain id. View-style callers (GraphPanel,
    ExplorerPanel knowledge tree, Domain Monitor) target this."""
    with _active_lock:
        _ensure_resolved()
        return _active_domains[0] if _active_domains else GENERAL_DOMAIN_ID


def get_active_domains() -> list[str]:
    """Return the active Domain list (multi-active). Tool dispatchers
    fan out across this list."""
    with _active_lock:
        _ensure_resolved()
        return list(_active_domains)


# Backward-compat aliases. Drop once llm_tools / graphrag_manager / etc.
# are updated to the *_domain* names.
def get_active_kb() -> str:
    return get_active_domain()


def get_active_kbs() -> list[str]:
    return get_active_domains()


# -- Helpers --------------------------------------------------------

def resolve_domain_id(value: str | None) -> str | None:
    """Accept either a Domain slug (e.g. `sw_arch`) or its human-readable
    name (e.g. `Software Agents`) and return the canonical slug. Returns
    None if `value` is empty/missing or doesn't match any Domain.

    The model usually picks the human name from the workspace context
    even when the tool description says to use the slug. Rather than
    fight the model, we resolve both forms here. Lookup is async-free
    (uses an in-process httpx call to noted-graph for the registry)."""
    if not value:
        return None
    target = value.strip()
    if not target:
        return None
    target_lower = target.lower()
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{NOTED_GRAPH_BASE}/domains")
            if r.status_code != 200:
                return target  # graceful: pass through, caller will 404
            domains = (r.json() or {}).get("domains") or []
    except httpx.HTTPError:
        return target  # graceful
    # Exact slug match wins
    for d in domains:
        if d.get("domain_id") == target:
            return target
    # Case-insensitive name match
    for d in domains:
        if (d.get("name") or "").strip().lower() == target_lower:
            return d.get("domain_id")
    # Case-insensitive slug match (handles `SW_ARCH` etc.)
    for d in domains:
        if (d.get("domain_id") or "").lower() == target_lower:
            return d.get("domain_id")
    return target  # no match - pass through


def _domain_collection(domain_id: str) -> str:
    """Resolve a Domain id to its corpus ChromaDB collection name.
    Convention only - no legacy soft-mapping. The Domain migration on
    noted-graph rewrites the noted Domain's manifest from `noted_corpus`
    to `noted__corpus`.
    """
    return f"{domain_id}__corpus"


async def _domain_exists(client: httpx.AsyncClient, domain_id: str) -> bool:
    """Check whether `domain_id` is in the noted-graph Domain registry."""
    try:
        r = await client.get(
            f"{NOTED_GRAPH_BASE}/research/{domain_id}/status", timeout=10,
        )
        return r.status_code == 200
    except httpx.RequestError:
        return False


async def _list_domains_from_graph(client: httpx.AsyncClient) -> list[dict]:
    """Mirror the Domain list from noted-graph (which owns the registry)."""
    try:
        r = await client.get(f"{NOTED_GRAPH_BASE}/domains", timeout=10)
        if r.status_code == 200:
            return r.json().get("domains", [])
    except httpx.RequestError as e:
        logger.warning("domain list: noted-graph unreachable: %s", e)
    return []


# -- Domain lifecycle (CRUD) ----------------------------------------

@router.get("")
async def list_domains():
    """List every Domain known to the registry. Mirrors noted-graph's view."""
    async with httpx.AsyncClient() as client:
        domains = await _list_domains_from_graph(client)
    return {"domains": domains, "active": get_active_domains(), "general": GENERAL_DOMAIN_ID}


@router.post("")
async def create_domain(
    domain_id: str = Query(..., min_length=1, max_length=32),
    name: str | None = None,
    description: str = "",
    capability_only: bool = False,
):
    """Create a new Domain (mints an empty manifest in noted-graph). The
    Domain starts with no docs; client uploads via
    POST /api/domains/{domain_id}/documents populate it. ChromaDB
    collections + ArcadeDB project are created lazily on first write."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{NOTED_GRAPH_BASE}/domains",
                json={
                    "domain_id": domain_id,
                    "name": name,
                    "description": description,
                    "capability_only": capability_only,
                },
            )
            if r.status_code != 200:
                raise HTTPException(
                    status_code=r.status_code,
                    detail=r.json().get("detail", r.text[:300]),
                )
            return r.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


# -- Active-Domain endpoints ----------------------------------------
# IMPORTANT: registered BEFORE the wildcard /{domain_id} handlers so
# FastAPI doesn't route PATCH /active to update_domain (treating "active"
# as a domain_id literal).

@router.get("/active")
def get_active():
    """Return the currently-active Domain set."""
    return {"active": get_active_domains()}


@router.patch("/active")
async def set_active(active: list[str] = Query(..., description="Domain ids to mark active")):
    """Replace the active Domain set. Multi-active: query tools (currently
    just `graph_and_vector_search`) fan out across every entry and merge
    results. View-style callers (GraphPanel, ExplorerPanel knowledge tree,
    Domain Monitor) still target the FIRST entry.

    The pinned Domain is always present in the active set. If a request
    omits it, it is prepended automatically.
    """
    if not active:
        raise HTTPException(status_code=400, detail="active cannot be empty")
    seen: set[str] = set()
    deduped: list[str] = []
    if GENERAL_DOMAIN_ID not in active:
        deduped.append(GENERAL_DOMAIN_ID)
        seen.add(GENERAL_DOMAIN_ID)
    for domain_id in active:
        if domain_id not in seen:
            seen.add(domain_id)
            deduped.append(domain_id)
    async with httpx.AsyncClient() as client:
        for domain_id in deduped:
            if domain_id == GENERAL_DOMAIN_ID:
                # General is capability-only; no /research/.../status to
                # probe. Treat as known if the registry lists it.
                graph_list = await _list_domains_from_graph(client)
                if not any(d.get("domain_id") == GENERAL_DOMAIN_ID for d in graph_list):
                    raise HTTPException(
                        status_code=404,
                        detail=f"unknown Domain: {GENERAL_DOMAIN_ID!r}",
                    )
                continue
            if not await _domain_exists(client, domain_id):
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
    with _active_lock:
        _active_domains.clear()
        _active_domains.extend(deduped)
    return {"active": deduped}


# -- Domain mutation (must come AFTER /active to avoid the wildcard
#    swallowing PATCH /active / GET /active) -----------------------

@router.patch("/{domain_id}")
async def update_domain(
    domain_id: str,
    name: str | None = None,
    description: str | None = None,
):
    """Update name + description on the Domain manifest. Proxies to
    noted-graph's PATCH /domains/{id}."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if not body:
        raise HTTPException(status_code=400, detail="provide at least one field to update")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.patch(
                f"{NOTED_GRAPH_BASE}/domains/{domain_id}", json=body,
            )
            if r.status_code != 200:
                raise HTTPException(
                    status_code=r.status_code,
                    detail=r.json().get("detail", r.text[:300]),
                )
            return r.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


@router.delete("/{domain_id}")
async def delete_domain(domain_id: str):
    """Drop a Domain: removes manifest, drops ChromaDB collections, drops
    ArcadeDB project. Cannot delete a pinned Domain."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.delete(f"{NOTED_GRAPH_BASE}/domains/{domain_id}")
            if r.status_code != 200:
                raise HTTPException(
                    status_code=r.status_code,
                    detail=r.json().get("detail", r.text[:300]),
                )
            with _active_lock:
                if domain_id in _active_domains:
                    _active_domains.remove(domain_id)
                if not _active_domains:
                    _active_domains.append(GENERAL_DOMAIN_ID)
            return r.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


# -- Per-Domain orchestration ---------------------------------------

@router.get("/{domain_id}/status")
async def domain_status(domain_id: str):
    """Combined progress + health for the Domain."""
    out: dict[str, Any] = {"domain_id": domain_id}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{NOTED_BASE}/api/graph/research/{domain_id}/status")
            if r.status_code == 200:
                out["graph"] = r.json()
            elif r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            else:
                out["graph"] = {"error": f"HTTP {r.status_code}"}
        except httpx.RequestError as e:
            out["graph"] = {"error": f"unreachable: {e}"}
        try:
            r = await client.get(
                f"{NOTED_BASE}/api/rag/index/sources",
                params={"collection": _domain_collection(domain_id)},
            )
            out["vector"] = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
        except httpx.RequestError as e:
            out["vector"] = {"error": f"unreachable: {e}"}
    pending = (out.get("graph") or {}).get("pending_recluster") or {}
    out["pending_recluster"] = pending.get(domain_id)
    return out


@router.post("/{domain_id}/documents", status_code=202)
async def add_document(
    domain_id: str,
    file: UploadFile = File(...),
    mode: str = Query(
        "read_store",
        description="read_store: indexed in vector + graph (default). "
                    "read_only: file on disk + visible in tree, no DB ingestion.",
    ),
    category: str = Query(
        "",
        description="Optional free-text category for Documents tree grouping. "
                    "Empty = uncategorized.",
    ),
):
    """Add a document to the Domain. Returns 202 IMMEDIATELY after the file
    lands on disk and the manifest is updated. The slow per-doc graph
    extraction (~1-25 min depending on size, only when mode=read_store)
    runs in the background; progress is visible via the Domain Monitor.

    Per `feedback_never_block_noted_api.md`: never block a noted handler
    on a long upstream call. The previous synchronous flow timed out at
    the outer nginx (60s) even though server-side work completed fine.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    if mode not in ("read_only", "read_store"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid mode {mode!r}; must be 'read_only' or 'read_store'",
        )

    payload = await file.read()
    filename = file.filename
    content_type = file.content_type or "application/octet-stream"
    out: dict[str, Any] = {
        "status": "accepted",
        "domain_id": domain_id,
        "filename": filename,
        "mode": mode,
    }
    ext = os.path.splitext(filename)[1].lower()
    is_md = ext == ".md"

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Vector ingest only when mode=read_store and file is markdown.
        #    PDFs go through the graph-side Docling pipeline and ship to
        #    noted-rag via /upsert_chunks (handled in the bg task below).
        if mode == "read_store" and is_md:
            try:
                files = {"file": (filename, payload, content_type)}
                data = {
                    "tags": domain_id,
                    "overwrite": "true",
                    "collection": _domain_collection(domain_id),
                }
                r = await client.post(
                    f"{NOTED_BASE}/api/rag/sources/upload",
                    files=files, data=data,
                )
                out["vector"] = r.json() if r.status_code == 200 else {
                    "status": "error", "code": r.status_code, "detail": r.text[:300],
                }
            except httpx.RequestError as e:
                out["vector"] = {"status": "error", "detail": f"unreachable: {e}"}

        # 2. Manifest update: write file to data/domains/<id>/sources/,
        #    append entry with mode + added_at to manifest. Fast (<1s).
        graph_corpus_path: str | None = None
        try:
            files = {"file": (filename, payload, content_type)}
            params = {"mode": mode}
            if category:
                params["category"] = category
            r = await client.post(
                f"{NOTED_BASE}/api/graph/research/{domain_id}/corpus/upload",
                files=files,
                params=params,
            )
            if r.status_code == 200:
                corpus_resp = r.json()
                out["graph_corpus"] = corpus_resp
                graph_corpus_path = corpus_resp.get("path")
            elif r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            else:
                out["graph_corpus"] = {
                    "status": "error", "code": r.status_code, "detail": r.text[:300],
                }
        except httpx.RequestError as e:
            out["graph_corpus"] = {"status": "error", "detail": f"unreachable: {e}"}

    # 3. Per-doc graph extraction is FIRE-AND-FORGET, only for read_store
    #    files. read_only files skip extraction entirely (file on disk
    #    only). The HTTP request lives in the asyncio loop until noted-
    #    graph completes (could be 25 min); we don't await its result.
    #    The user watches progress in the Domain Monitor.
    if mode == "read_store" and graph_corpus_path:
        out["graph_extract"] = {"status": "background_started"}
        path_for_bg = graph_corpus_path

        async def _bg_doc_add():
            try:
                # /doc/add now returns 202 immediately after enqueueing
                # (per-Domain queue + worker on noted-graph). 200 retained
                # for backward compat with older noted-graph builds.
                async with httpx.AsyncClient(timeout=30) as bg_client:
                    r = await bg_client.post(
                        f"{NOTED_BASE}/api/graph/research/{domain_id}/doc/add",
                        json={"path": path_for_bg},
                    )
                    if r.status_code not in (200, 202):
                        logger.warning(
                            "background doc/add for %s/%s returned HTTP %d: %s",
                            domain_id, path_for_bg, r.status_code, r.text[:300],
                        )
                    else:
                        logger.info(
                            "background doc/add for %s/%s queued: %s",
                            domain_id, path_for_bg, r.json(),
                        )
            except httpx.RequestError as e:
                logger.warning(
                    "background doc/add for %s/%s transport error: %s",
                    domain_id, path_for_bg, e,
                )
            except Exception:
                logger.exception(
                    "background doc/add for %s/%s failed",
                    domain_id, path_for_bg,
                )

        asyncio.create_task(_bg_doc_add())
    elif mode == "read_only":
        out["graph_extract"] = {"status": "skipped_read_only"}

    out["pending_recluster"] = (mode == "read_store")
    return out


@router.patch("/{domain_id}/documents/category")
async def set_document_category(
    domain_id: str,
    path: str = Query(..., description="Doc path (Domain sources/-relative)"),
    category: str = Query("", description="New category. Empty = uncategorized."),
):
    """Update the category metadata of a document. Hits noted-graph
    directly (NOTED_GRAPH_BASE), not via the local /api/graph proxy:
    that proxy doesn't accept PATCH and returns 405. Pure metadata -
    no re-index."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.patch(
                f"{NOTED_GRAPH_BASE}/research/{domain_id}/corpus/category",
                params={"path": path, "category": category},
            )
            if r.status_code != 200:
                raise HTTPException(
                    status_code=r.status_code,
                    detail=r.json().get("detail", r.text[:300]),
                )
            return r.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


@router.patch("/{domain_id}/documents/display_name")
async def set_document_display_name(
    domain_id: str,
    path: str = Query(..., description="Doc path (Domain sources/-relative)"),
    display_name: str = Query("", description="User-friendly title. Empty = use basename(path)."),
):
    """Update the user-friendly display_name of a document. Hits
    noted-graph directly (the /api/graph proxy doesn't accept PATCH).
    Pure metadata change - the file on disk and all DB ids stay tied
    to the original `path`. Empty display_name clears the override."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.patch(
                f"{NOTED_GRAPH_BASE}/research/{domain_id}/corpus/display_name",
                params={"path": path, "display_name": display_name},
            )
            if r.status_code != 200:
                raise HTTPException(
                    status_code=r.status_code,
                    detail=r.json().get("detail", r.text[:300]),
                )
            return r.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


@router.delete("/{domain_id}/documents")
async def delete_document(
    domain_id: str,
    path: str = Query(..., description="Doc path (Domain sources/-relative)"),
    rag_source_b64: str = Query("", description="Base64-encoded rag source path"),
):
    """Remove a doc from this Domain. Branches on the manifest mode:
    read_only files just drop the manifest entry + file; read_store files
    also drop graph chunks/entities + vector chunks."""
    out: dict[str, Any] = {"domain_id": domain_id, "path": path}

    async with httpx.AsyncClient(timeout=300) as client:
        # 1. Per-doc graph cleanup FIRST (chunk_ids must still be
        #    resolvable). For read_only docs this is a no-op upstream.
        try:
            r = await client.post(
                f"{NOTED_BASE}/api/graph/research/{domain_id}/doc/remove",
                json={"path": path},
            )
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            out["graph_extract"] = r.json() if r.status_code == 200 else {
                "status": "error", "code": r.status_code, "detail": r.text[:300],
            }
        except httpx.RequestError as e:
            out["graph_extract"] = {"status": "error", "detail": f"unreachable: {e}"}

        # 2. Manifest removal (sets pending_recluster server-side when
        #    the removed entry was read_store).
        try:
            r = await client.delete(
                f"{NOTED_BASE}/api/graph/research/{domain_id}/corpus",
                params={"path": path},
            )
            out["graph_corpus"] = r.json() if r.status_code == 200 else {
                "status": "error", "code": r.status_code, "detail": r.text[:300],
            }
        except httpx.RequestError as e:
            out["graph_corpus"] = {"status": "error", "detail": f"unreachable: {e}"}

        # 3. Vector RAG removal (only for .md - PDFs are cleaned by the
        #    /upsert_chunks counterpart on the graph side).
        if rag_source_b64:
            try:
                r = await client.delete(
                    f"{NOTED_BASE}/api/rag/sources/{rag_source_b64}",
                    params={"collection": _domain_collection(domain_id)},
                )
                out["vector"] = r.json() if r.status_code == 200 else {
                    "status": "error", "code": r.status_code, "detail": r.text[:300],
                }
            except httpx.RequestError as e:
                out["vector"] = {"status": "error", "detail": f"unreachable: {e}"}

    out["pending_recluster"] = True
    return out


@router.post("/{domain_id}/preflight")
async def preflight(
    domain_id: str,
    path: str = Query(
        "",
        description=("Source-relative path of the doc to validate. "
                     "Empty = system-health mode (skip Docling + manifest + disk checks)."),
    ),
):
    """Run the preflight scan for a per-doc add OR a system-health diagnostic
    (when `path` is empty — KB Manager 'Run Diagnostics' button uses this).
    See documents/kb/kb_import_export.md Phase 0a."""
    async with httpx.AsyncClient(timeout=320) as client:
        try:
            r = await client.post(
                f"{NOTED_BASE}/api/graph/research/{domain_id}/preflight",
                json={"path": path} if path else {},
            )
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            return r.json() if r.status_code == 200 else {
                "status": "error", "code": r.status_code, "detail": r.text[:300],
            }
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


@router.post("/{domain_id}/recluster")
async def recluster(domain_id: str):
    """Re-run analytics + community summaries over the Domain's CURRENT
    graph. Much faster than full rebuild. Clears pending_recluster on
    success."""
    async with httpx.AsyncClient(timeout=3600) as client:
        try:
            r = await client.post(f"{NOTED_BASE}/api/graph/research/{domain_id}/recluster")
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            return r.json() if r.status_code == 200 else {
                "status": "error", "code": r.status_code, "detail": r.text[:300],
            }
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")


@router.post("/{domain_id}/rebuild")
async def rebuild(domain_id: str):
    """Trigger a full graph rebuild for the Domain. Slow (~25 min for the
    noted corpus); needed only when extractor changes or graph state is
    suspect. Day-to-day, prefer Recluster Now (POST /recluster)."""
    async with httpx.AsyncClient(timeout=14400) as client:
        try:
            r = await client.post(f"{NOTED_BASE}/api/graph/research/{domain_id}/rebuild")
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"unknown Domain: {domain_id!r}")
            return r.json() if r.status_code == 200 else {
                "status": "error", "code": r.status_code, "detail": r.text[:300],
            }
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"noted-graph unreachable: {e}")

"""RAG Manager - HTTP client for the noted-rag sidecar.

Lives entirely on the noted side; has zero knowledge of chromadb or any
embedding library. The sole dependency is httpx, already in noted's deps.

Follows the EvidentlyManager pattern: async httpx, graceful degradation on
any error so a missing / unhealthy noted-rag cannot break a chat turn.
"""

from __future__ import annotations

import contextvars
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RAG_URL = os.environ.get("RAG_URL", "http://noted-rag:8200")
TIMEOUT = 8.0

# Per-turn correlation key + source label. Set at the top of llm_chat (and
# overridden inside speculative coroutines) so every embed / search call
# can be tagged in BOTH noted's logs and noted-rag's logs and grouped per
# chat turn. Default is "no-turn" / "unknown" so admin paths still log
# something meaningful.
_turn_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "rag_turn_id", default="no-turn",
)
_call_source_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "rag_call_source", default="unknown",
)


def set_turn_id(turn_id: str | None = None) -> str:
    """Set (or generate) the per-turn correlation id. Call once at the
    top of the chat handler. Returns the id so callers can echo it
    elsewhere (e.g., into noted-graph headers)."""
    tid = turn_id or uuid.uuid4().hex[:8]
    _turn_id_var.set(tid)
    return tid


def set_call_source(source: str) -> contextvars.Token:
    """Set the call_source label for downstream rag calls. Use as:
        token = set_call_source('speculative'); try: ...; finally: reset_call_source(token)
    Or context-style with a contextvars.copy_context()."""
    return _call_source_var.set(source)


def reset_call_source(token: contextvars.Token) -> None:
    _call_source_var.reset(token)


def _trace_headers() -> dict:
    return {
        "X-Turn-Id": _turn_id_var.get(),
        "X-Call-Source": _call_source_var.get(),
    }


def _log_call(kind: str, t_start: float, t_end: float, ok: bool, extra: str = "") -> None:
    logger.info(
        "RAG_CLIENT turn_id=%s source=%s kind=%s wall_ms=%.1f ok=%s%s",
        _turn_id_var.get(),
        _call_source_var.get(),
        kind,
        (t_end - t_start) * 1000,
        ok,
        f" {extra}" if extra else "",
    )


class RagManager:
    """Client for noted-rag's HTTP API."""

    def __init__(self, base_url: str = RAG_URL):
        self._base_url = base_url
        # Shared AsyncClient for HTTP keepalive: avoids the TCP handshake
        # cost on every per-request short-lived AsyncClient. The instance
        # lives for the manager's (singleton) lifetime; httpx cleans up at
        # process exit. Per-call timeout overrides go through
        # client.X(..., timeout=...).
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT)
        yield self._client

    async def health(self) -> dict:
        try:
            async with self._get_client() as client:
                resp = await client.get(f"{self._base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            return {"status": "unreachable", "detail": str(e)}

    async def search(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        top_k: int = 5,
        collection: Optional[str] = None,
        source_paths: Optional[list[str]] = None,
    ) -> dict:
        """Search docs. Always returns a dict with a `status` field.

        Never raises: any transport error yields {"status": "unavailable",
        "chunks": []} so the caller can degrade cleanly.

        `collection` selects the per-Domain ChromaDB collection name.
        `source_paths` (optional) restricts results to chunks belonging
        to the named source documents."""
        payload: dict = {"query": query, "top_k": top_k}
        if tags:
            payload["tags"] = tags
        if collection:
            payload["collection"] = collection
        if source_paths:
            payload["source_paths"] = source_paths
        t_start = time.perf_counter()
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/search", json=payload, headers=_trace_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                _log_call("search", t_start, time.perf_counter(), True,
                          f"chunks={len(data.get('chunks') or [])}")
                return data
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for search: %s", e)
            _log_call("search", t_start, time.perf_counter(), False, f"err={type(e).__name__}")
            return {"status": "unavailable", "chunks": []}

    async def embed(self, texts: list[str]) -> dict:
        """Get bge-m3 embeddings for a list of texts via noted-rag /embed.

        Returns {"status": "ok"|"unavailable", "vectors": [[...], ...], "dim": int}.
        Used by graph_and_vector_search to embed the query ONCE up front,
        then fan out to multiple stores via the *_by_vector endpoints
        without re-embedding (avoids GPU contention)."""
        t_start = time.perf_counter()
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/embed", json={"texts": texts}, headers=_trace_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                _log_call("embed", t_start, time.perf_counter(), True, f"n={len(texts)}")
                return data
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for embed: %s", e)
            _log_call("embed", t_start, time.perf_counter(), False, f"err={type(e).__name__}")
            return {"status": "unavailable", "vectors": [], "dim": 0}

    async def search_by_vector(
        self,
        query_text: str,
        vector: list[float],
        tags: Optional[list[str]] = None,
        top_k: int = 5,
        collection: Optional[str] = None,
        source_paths: Optional[list[str]] = None,
    ) -> dict:
        """Same shape as search() but takes a pre-computed query vector
        (skips noted-rag's embed step). The reranker still needs the
        original query text - it pairs query+chunk for cross-encoder
        scoring - so we send both.

        `source_paths` (optional) restricts results to chunks belonging
        to the named source documents."""
        payload: dict = {"query_text": query_text, "vector": vector, "top_k": top_k}
        if tags:
            payload["tags"] = tags
        if collection:
            payload["collection"] = collection
        if source_paths:
            payload["source_paths"] = source_paths
        t_start = time.perf_counter()
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/search_by_vector", json=payload, headers=_trace_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                _log_call("search_by_vector", t_start, time.perf_counter(), True,
                          f"chunks={len(data.get('chunks') or [])}")
                return data
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for search_by_vector: %s", e)
            _log_call("search_by_vector", t_start, time.perf_counter(), False, f"err={type(e).__name__}")
            return {"status": "unavailable", "chunks": []}

    async def search_multi(
        self,
        query: str,
        collections: list[str],
        tags: Optional[list[str]] = None,
        top_k: int = 5,
        merge_top_n: Optional[int] = None,
        source_paths: Optional[list[str]] = None,
        vector: Optional[list[float]] = None,
    ) -> dict:
        """Multi-collection search that does ChromaDB fan-out + single
        reranker batch server-side. Replaces N parallel /search_by_vector
        calls when the caller wants to query several Domains at once.

        Returns {status, chunks[]} where each chunk has a `kb_id` field
        identifying which Domain it came from.
        """
        payload: dict = {
            "query": query,
            "collections": collections,
            "top_k": top_k,
        }
        if tags:
            payload["tags"] = tags
        if merge_top_n is not None:
            payload["merge_top_n"] = merge_top_n
        if source_paths:
            payload["source_paths"] = source_paths
        if vector is not None:
            payload["vector"] = vector
        t_start = time.perf_counter()
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/search_multi", json=payload, headers=_trace_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                _log_call("search_multi", t_start, time.perf_counter(), True,
                          f"colls={len(collections)} chunks={len(data.get('chunks') or [])}")
                return data
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for search_multi: %s", e)
            _log_call("search_multi", t_start, time.perf_counter(), False, f"err={type(e).__name__}")
            return {"status": "unavailable", "chunks": []}

    async def list_collections(self) -> dict:
        try:
            async with self._get_client() as client:
                resp = await client.get(f"{self._base_url}/collections")
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            return {"status": "unavailable", "detail": str(e)}

    # ── Explorer tree views ────────────────────────────────────────
    # These back the Assistant/Embeddings node in the ExplorerPanel.
    # They return the upstream shape verbatim so the frontend does not
    # have to know anything about noted-rag's URL or path space.

    async def list_sources(self, collection: str | None = None) -> dict:
        params = {"collection": collection} if collection else None
        try:
            async with self._get_client() as client:
                resp = await client.get(f"{self._base_url}/index/sources", params=params)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for list_sources: %s", e)
            return {"status": "unavailable", "total_chunks": 0, "sources": []}

    async def format_breakdown(self, collection: str | None = None) -> dict:
        """Per-format chunk counts (powers the KB Monitor's chips)."""
        params = {"collection": collection} if collection else None
        try:
            async with self._get_client() as client:
                resp = await client.get(
                    f"{self._base_url}/index/format_breakdown", params=params,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for format_breakdown: %s", e)
            return {"status": "unavailable", "total": 0, "by_format": {}}

    async def list_source_chunks(self, source_b64: str, collection: str | None = None) -> dict:
        params = {"collection": collection} if collection else None
        try:
            async with self._get_client() as client:
                resp = await client.get(
                    f"{self._base_url}/index/sources/{source_b64}/chunks",
                    params=params,
                )
                if resp.status_code == 404:
                    return {"status": "not_found", "chunks": []}
                if resp.status_code == 400:
                    return {"status": "invalid_id", "chunks": []}
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for list_source_chunks: %s", e)
            return {"status": "unavailable", "chunks": []}

    async def get_chunk(self, chunk_b64: str, collection: str | None = None) -> dict:
        params = {"collection": collection} if collection else None
        try:
            async with self._get_client() as client:
                resp = await client.get(
                    f"{self._base_url}/index/chunks/{chunk_b64}", params=params,
                )
                if resp.status_code == 404:
                    return {"status": "not_found"}
                if resp.status_code == 400:
                    return {"status": "invalid_id"}
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for get_chunk: %s", e)
            return {"status": "unavailable"}

    async def trigger_ingest(
        self,
        collection: str | None = None,
        chunking_profile: str | None = None,
        source_path: str | None = None,
    ) -> dict:
        """Kick a fire-and-forget ingest. Returns the upstream job_id
        immediately so the caller can stream progress separately. Never
        blocks the noted API handler on the actual embedding work.

        `chunking_profile` is an optional named profile id (see
        noted-rag's chunking_profiles.json). None → noted-rag uses its
        default profile.

        `source_path` (optional) scopes the run to a single inventory
        entry. Used by the per-upload path so a single-file import
        doesn't re-walk the full inventory into the target collection.
        None → bulk rebuild (walk every entry)."""
        params: dict[str, str] = {}
        if collection:
            params["collection"] = collection
        if chunking_profile:
            params["chunking_profile"] = chunking_profile
        if source_path:
            params["source_path"] = source_path
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/ingest",
                    params=params or None,
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for trigger_ingest: %s", e)
            return {"status": "unavailable", "detail": str(e)}

    async def list_chunking_profiles(self) -> dict:
        """Proxy the catalog of named chunking profiles from noted-rag.
        Used by the frontend's document-import dropdown."""
        try:
            async with self._get_client() as client:
                resp = await client.get(
                    f"{self._base_url}/chunking-profiles",
                    timeout=5.0,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for list_chunking_profiles: %s", e)
            return {"status": "unavailable", "detail": str(e),
                    "default_profile": None, "profiles": []}

    async def get_ingest_status(self, job_id: str) -> dict:
        try:
            async with self._get_client() as client:
                resp = await client.get(f"{self._base_url}/ingest/status/{job_id}")
                if resp.status_code == 404:
                    return {"status": "not_found"}
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for get_ingest_status: %s", e)
            return {"status": "unavailable", "detail": str(e)}

    async def delete_source(self, source_b64: str, collection: str | None = None) -> dict:
        """Tell noted-rag to drop a source's chunks from Chroma. The caller
        should already have removed the entry from rag_sources.json."""
        params = {"collection": collection} if collection else None
        try:
            async with self._get_client() as client:
                resp = await client.delete(
                    f"{self._base_url}/index/sources/{source_b64}",
                    params=params,
                )
                if resp.status_code == 400:
                    return {"status": "invalid_id"}
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-rag unreachable for delete_source: %s", e)
            return {"status": "unavailable", "detail": str(e)}

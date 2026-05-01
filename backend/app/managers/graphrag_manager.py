"""GraphRAG Manager - HTTP client for the noted-graph service's /research API.

Mirrors the RagManager pattern: async httpx, graceful degradation on transport
errors. Used by the research_topic and rebuild_knowledge_graph tools.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx

logger = logging.getLogger(__name__)

GRAPH_URL = os.environ.get("GRAPH_URL", "http://noted-graph:5523")

# Query timeout: global+local runs both, each includes Gemma synthesis.
# 60s covers a warm shared-pool call; cold start or contention may push
# higher, but the caller's chat turn can't block longer than this.
QUERY_TIMEOUT = 60.0

# Rebuild timeout: full rebuild can run many minutes (Gemma extraction over
# the full corpus). We don't block the chat turn that long - the tool
# returns immediately after firing the request OR after a short grace
# period. Phase 1 implementation keeps it synchronous with a generous cap;
# Phase 1.5 (auto-update) will make this event-driven.
REBUILD_TIMEOUT = 3600.0


class GraphRagManager:
    """Client for noted-graph's /research API."""

    def __init__(self, base_url: str = GRAPH_URL):
        self._base_url = base_url
        # Shared AsyncClient for HTTP keepalive: the per-call short-lived
        # AsyncClient was paying the TCP handshake on every retrieve.
        # The client lives for the manager's (singleton) lifetime;
        # per-call timeout overrides go via client.X(..., timeout=...).
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=QUERY_TIMEOUT)
        yield self._client

    async def query(self, question: str, mode: str = "auto", kb_id: str | None = None) -> dict:
        """Run a GraphRAG query. Returns the envelope dict, OR a fallback
        {status: unavailable, ...} dict on transport failure.

        P3.2: `kb_id` selects the per-KB Retriever upstream. When omitted,
        falls back to the active KB from kb.py (or the default if not set)."""
        kb_id = kb_id or _active_kb()
        payload = {"question": question, "mode": mode}
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/research/{kb_id}/query", json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-graph /research/query failed: %s", e)
            return {
                "status": "unavailable",
                "detail": str(e),
                "answer": None,
                "citations": [],
                "subgraph": {"nodes": [], "edges": []},
                "mode": mode,
            }

    async def retrieve(self, question: str, mode: str = "local", kb_id: str | None = None) -> dict:
        """Retrieval-only call (no Gemma synthesis on the graph side).

        Used by graph_and_vector_search to fan out to noted-graph in
        parallel with noted-rag, then have the chat-side Assistant Gemma
        synthesize from both sources in one pass.

        P3.2: `kb_id` selects the per-KB Retriever upstream. Defaults to
        the active KB."""
        kb_id = kb_id or _active_kb()
        payload = {"question": question, "mode": mode}
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/research/{kb_id}/retrieve", json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-graph /research/retrieve failed: %s", e)
            return {
                "status": "unavailable",
                "detail": str(e),
                "mode": mode,
                "entities": [],
                "edges": [],
                "chunk_excerpts": [],
            }

    async def retrieve_by_vector(self, query_vector: list[float], kb_id: str | None = None) -> dict:
        """Retrieval-only call with a pre-computed query vector. Skips
        noted-graph's internal embed (which would otherwise contend with
        the chunk-side embed on noted-rag's GPU). Local mode only - the
        parallel-retrieval tool path uses local.

        P3.2: `kb_id` selects the per-KB Retriever. Defaults to active KB."""
        kb_id = kb_id or _active_kb()
        payload = {"query_vector": query_vector, "mode": "local"}
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"{self._base_url}/research/{kb_id}/retrieve", json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-graph /research/retrieve (vector) failed: %s", e)
            return {
                "status": "unavailable",
                "detail": str(e),
                "mode": "local",
                "entities": [],
                "edges": [],
                "chunk_excerpts": [],
            }

    async def rebuild(self, kb_id: str | None = None) -> dict:
        kb_id = kb_id or _active_kb()
        try:
            async with self._get_client() as client:
                resp = await client.post(f"{self._base_url}/research/{kb_id}/rebuild", timeout=REBUILD_TIMEOUT)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("noted-graph /research/rebuild failed: %s", e)
            return {"status": "unavailable", "detail": str(e)}

    async def status(self, kb_id: str | None = None) -> dict:
        kb_id = kb_id or _active_kb()
        try:
            async with self._get_client() as client:
                resp = await client.get(f"{self._base_url}/research/{kb_id}/status", timeout=5.0)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            return {"status": "unavailable", "detail": str(e)}


def _active_kb() -> str:
    """Lazy-import to avoid a circular dependency: kb.py imports nothing
    from this module, but importing kb at module load time creates one."""
    from app.routers.kb import get_active_kb
    return get_active_kb()

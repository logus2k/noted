"""HTTP client for noted-rag's /embed endpoint.

Used by the sameAs pass, community-summary routing, and local-mode
entry-entity vector search. Keeps a minimal surface: we only need embeddings.
"""

from __future__ import annotations

import logging

import requests

from app.config import RAG_BASE_URL, LLM_TIMEOUT

logger = logging.getLogger(__name__)


class RagClientError(RuntimeError):
    pass


class RagClient:
    def __init__(self):
        self._base = RAG_BASE_URL.rstrip('/')
        self._timeout = LLM_TIMEOUT
        # HTTP keepalive: cheaper than fresh TCP per query, especially
        # during retrieval where we issue several /cache/search_by_vector
        # calls per request.
        self._session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return normalized bge-m3 embeddings. Empty list for empty input."""
        if not texts:
            return []
        try:
            r = self._session.post(
                f'{self._base}/embed',
                json={'texts': texts},
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag /embed request failed: {e}') from e
        if not r.ok:
            raise RagClientError(f'noted-rag /embed HTTP {r.status_code}: {r.text[:300]}')
        data = r.json()
        vectors = data.get('vectors')
        if not isinstance(vectors, list):
            raise RagClientError(f'noted-rag /embed: missing vectors in response')
        return vectors

    def upsert_chunks(
        self,
        source_path: str,
        tags: list[str],
        last_modified: str,
        chunks: list[dict],
        format: str = 'pdf',
        collection: str | None = None,
    ) -> dict:
        """Ship pre-chunked text + provenance to noted-rag for embedding +
        ChromaDB upsert. Used by the PDF/DOCX/PPTX add path so noted-rag
        doesn't need to re-parse the source file (Plan B - noted-graph is
        the only Docling-equipped container).

        Each chunk dict: {chunk_index, section_path, text,
                          page_no?, bbox?, section_level?}.

        `collection`: ChromaDB collection name (P3.2 multi-KB). When
        omitted, noted-rag falls back to its default (legacy `noted_corpus`).
        """
        if not chunks:
            return {'status': 'ok', 'indexed': 0, 'skipped_unchanged': 0, 'deleted_stale': 0}
        body = {
            'source_path': source_path,
            'tags': tags,
            'last_modified': last_modified,
            'format': format,
            'chunks': chunks,
        }
        if collection:
            body['collection'] = collection
        try:
            r = self._session.post(
                f'{self._base}/upsert_chunks',
                json=body,
                # Embedding many chunks + Chroma upsert is multi-second work;
                # mirror /cache/upsert's headroom.
                timeout=max(self._timeout, 300),
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag /upsert_chunks failed: {e}') from e
        if not r.ok:
            raise RagClientError(f'noted-rag /upsert_chunks HTTP {r.status_code}: {r.text[:300]}')
        return r.json()

    def delete_source(self, source_path: str, collection: str | None = None) -> dict:
        """Delete every chunk for `source_path` from a noted-rag
        collection. Idempotent: returns `{deleted_chunks: 0}` when nothing
        matched. Used by `remove_doc` to keep the vector DB in sync with
        the graph DB after per-doc removal.

        `collection`: ChromaDB collection name (P3.2 multi-KB). When
        omitted, noted-rag falls back to its default (legacy `noted_corpus`).
        """
        import base64
        src_b64 = base64.urlsafe_b64encode(source_path.encode()).decode().rstrip('=')
        params = {'collection': collection} if collection else None
        try:
            r = self._session.delete(
                f'{self._base}/index/sources/{src_b64}',
                params=params,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag DELETE /index/sources failed: {e}') from e
        if r.status_code == 404:
            return {'source_path': source_path, 'deleted_chunks': 0}
        if not r.ok:
            raise RagClientError(f'noted-rag DELETE HTTP {r.status_code}: {r.text[:300]}')
        return r.json()

    # ── Cache (named-collection) ────────────────────────────────────

    def cache_upsert(self, collection: str, ids: list[str], texts: list[str],
                     replace: bool = True) -> dict:
        """Embed + store strings in a noted-rag/ChromaDB collection."""
        if not ids:
            return {'status': 'ok', 'upserted': 0, 'replaced': False}
        if len(ids) != len(texts):
            raise RagClientError('ids and texts length mismatch')
        try:
            r = self._session.post(
                f'{self._base}/cache/upsert',
                json={'collection': collection, 'ids': ids, 'texts': texts, 'replace': replace},
                # Embedding 1000s of strings + Chroma upsert is multi-second
                # work; give it more headroom than per-query embed.
                timeout=max(self._timeout, 300),
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag /cache/upsert failed: {e}') from e
        if not r.ok:
            raise RagClientError(f'noted-rag /cache/upsert HTTP {r.status_code}: {r.text[:300]}')
        return r.json()

    def cache_search(self, collection: str, query: str, top_k: int = 10) -> list[dict]:
        """Vector-search a cached collection. Returns [{id, score, text}, ...]."""
        try:
            r = self._session.post(
                f'{self._base}/cache/search',
                json={'collection': collection, 'query': query, 'top_k': top_k},
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag /cache/search failed: {e}') from e
        if not r.ok:
            raise RagClientError(f'noted-rag /cache/search HTTP {r.status_code}: {r.text[:300]}')
        return r.json().get('hits', [])

    def cache_search_by_vector(
        self, collection: str, vector: list[float], top_k: int = 10,
    ) -> list[dict]:
        """Same as cache_search but takes a pre-computed query vector,
        skipping noted-rag's bge-m3 embed step. Used by the parallel
        retrieval path."""
        try:
            r = self._session.post(
                f'{self._base}/cache/search_by_vector',
                json={'collection': collection, 'vector': vector, 'top_k': top_k},
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise RagClientError(f'noted-rag /cache/search_by_vector failed: {e}') from e
        if not r.ok:
            raise RagClientError(f'noted-rag /cache/search_by_vector HTTP {r.status_code}: {r.text[:300]}')
        return r.json().get('hits', [])

    def cache_drop(self, collection: str) -> bool:
        try:
            r = self._session.post(
                f'{self._base}/cache/drop',
                json={'collection': collection},
                timeout=self._timeout,
            )
            return r.ok and r.json().get('dropped', False)
        except requests.RequestException:
            return False

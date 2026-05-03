"""Core RAG service: dense retrieval + cross-encoder rerank.

Single `noted_corpus` collection. `search` runs over the whole corpus by
default; optional `tags` narrow via Chroma `where` filters. A minimum
rerank score guards against hallucinating on empty-signal queries.

Embeddings + reranking are forwarded over HTTP to a llama-server router
(default `http://llama-vision:8500`) hosting bge-m3 (CLS pool) and
bge-reranker-v2-m3 (RANK pool). The previous in-process llama-cpp-python
path is gone — the router is shared with agent_server so the bge models
are loaded once GPU-side instead of once per service.
"""

from __future__ import annotations

import contextvars
import logging
import math
from typing import Optional

import chromadb
import httpx

from . import config
from .ingest import COLLECTION_NAME

logger = logging.getLogger(__name__)


# Per-request correlation context. Set by the FastAPI middleware in main.py
# from X-Turn-Id and X-Call-Source headers; logged in EMBED_TIMING /
# SEARCH_TIMING lines so noted-side and noted-rag-side logs can be grouped
# per chat turn.
_turn_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("noted_rag_turn_id", default="no-turn")
_source_var: contextvars.ContextVar[str] = contextvars.ContextVar("noted_rag_source", default="unknown")


def set_trace_context(turn_id: str, source: str):
    return (_turn_id_var.set(turn_id), _source_var.set(source))


def reset_trace_context(tokens) -> None:
    try:
        _turn_id_var.reset(tokens[0])
        _source_var.reset(tokens[1])
    except Exception:
        pass


def _trace_tag() -> str:
    return f"turn_id={_turn_id_var.get()} source={_source_var.get()}"


def _parse_tags_to_where(tags: Optional[list[str]]) -> Optional[dict]:
    """Convert a list of 'key:value' tag strings into a Chroma `where` filter.

    - ["doc_type:architecture"]                  -> {"doc_type": "architecture"}
    - ["doc_type:architecture", "lang:en"]       -> {"$and": [{"doc_type": "..."}, {"lang": "en"}]}
    Entries without a ':' are ignored.
    """
    if not tags:
        return None
    filters: list[dict] = []
    for t in tags:
        if not isinstance(t, str) or ":" not in t:
            continue
        k, v = t.split(":", 1)
        k, v = k.strip(), v.strip()
        if k and v:
            filters.append({k: v})
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def _sigmoid(x: float) -> float:
    # Numerically stable sigmoid. /v1/rerank returns raw logits; we map
    # to 0-1 so RERANK_MIN_SCORE keeps the same meaning the in-process
    # path established (sentence-transformers default + sigmoid).
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class RagService:
    def __init__(self) -> None:
        self._client: Optional[chromadb.ClientAPI] = None
        # Shared httpx.Client with keep-alive to llama-vision. Keeps the
        # TCP connection warm across requests so a chat turn's two embed
        # calls + rerank batch don't pay handshake cost three times.
        self._http: Optional[httpx.Client] = None

    # ── Lazy accessors ─────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            config.ensure_dirs()
            self._client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        return self._client

    def _get_http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                base_url=config.LLAMA_SERVER_URL,
                timeout=httpx.Timeout(60.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._http

    # ── Public API ────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalized dense embeddings for a list of strings.

        Forwards to llama-server's `/v1/embeddings` with the bge-m3 model.
        Batched in a single POST — the multi-sequence-decode bug that
        forced per-input loops in the in-process path does not affect
        llama-server (different code path).

        bge-m3 is CLS-pooled server-side; we explicitly L2-normalize
        client-side so cosine similarity in Chroma matches what the
        sentence-transformers path produced (which had
        normalize_embeddings=True). Cheap relative to network +
        embedding cost.
        """
        import time
        t0 = time.perf_counter()
        if not texts:
            return []
        http = self._get_http()
        t_client = time.perf_counter()

        resp = http.post(
            "/v1/embeddings",
            json={"model": config.EMBED_MODEL_NAME, "input": list(texts)},
        )
        resp.raise_for_status()
        body = resp.json()
        t_http = time.perf_counter()

        # Server returns entries possibly in input order with an `index`
        # field. Sort by index defensively, then normalize.
        entries = sorted(body.get("data", []), key=lambda e: int(e.get("index", 0)))
        out: list[list[float]] = []
        for entry in entries:
            v = entry["embedding"]
            if v and isinstance(v[0], (list, tuple)):
                v = v[0]
            norm_sq = 0.0
            for x in v:
                norm_sq += x * x
            if norm_sq > 0:
                inv = 1.0 / math.sqrt(norm_sq)
                out.append([x * inv for x in v])
            else:
                out.append(list(v))
        t_done = time.perf_counter()

        logger.info(
            'EMBED_TIMING %s n=%d chars=%d total_ms=%.1f get_client_ms=%.1f http_ms=%.1f normalize_ms=%.1f',
            _trace_tag(),
            len(texts),
            sum(len(t) for t in texts),
            (t_done - t0) * 1000,
            (t_client - t0) * 1000,
            (t_http - t_client) * 1000,
            (t_done - t_http) * 1000,
        )
        return out

    def _rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return one 0-1 relevance score per document, in input order.

        Forwards to llama-server's `/v1/rerank` with bge-reranker-v2-m3.
        Server returns raw logits; we apply sigmoid client-side so
        RERANK_MIN_SCORE=0.15 keeps the meaning it had under the
        in-process sigmoid-of-RANK-pool path.
        """
        if not documents:
            return []
        http = self._get_http()
        resp = http.post(
            "/v1/rerank",
            json={
                "model": config.RERANK_MODEL_NAME,
                "query": query,
                "documents": list(documents),
            },
        )
        resp.raise_for_status()
        body = resp.json()
        # Defensive sort by `index` — server returns input-order today
        # but the API contract puts the index field there for a reason.
        results = sorted(body.get("results", []), key=lambda r: int(r.get("index", 0)))
        return [_sigmoid(float(r["relevance_score"])) for r in results]

    def list_collections(self) -> list[dict]:
        client = self._get_client()
        return [
            {"name": c.name, "count": c.count()}
            for c in client.list_collections()
        ]

    def search(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        top_k: int = config.FINAL_TOP_K,
        collection: Optional[str] = None,
        source_paths: Optional[list[str]] = None,
    ) -> list[dict]:
        """Dense retrieve top-N, then cross-encoder rerank down to top_k.

        Returns chunks with rerank score >= config.RERANK_MIN_SCORE. If
        the top-1 score is below that threshold, returns an empty list
        (the tool layer turns this into a 'no strong match' message so
        the Assistant won't hallucinate from noise).

        `collection` selects per-Domain ChromaDB collection name.
        `source_paths` (optional) restricts the search to chunks whose
        `source_path` metadata is in the given list - used by Assistant
        tools that scope a query to specific document(s)."""
        query_vec = self.embed([query])[0]
        return self.search_by_vector(
            query, query_vec, tags=tags, top_k=top_k,
            collection=collection, source_paths=source_paths,
        )

    def search_by_vector(
        self,
        query_text: str,
        query_vec: list[float],
        tags: Optional[list[str]] = None,
        top_k: int = config.FINAL_TOP_K,
        collection: Optional[str] = None,
        source_paths: Optional[list[str]] = None,
    ) -> list[dict]:
        """Same shape as search() but takes a pre-computed query vector,
        skipping the bge-m3 embed step. The reranker still needs the
        query_text for cross-encoder scoring (it pairs query+chunk text),
        so we accept both. Used by the parallel-retrieval path so we
        embed once and fan out without GPU contention.

        `source_paths` (optional) AND-merges with the tags-derived where
        clause to restrict the search to chunks belonging to the named
        documents."""
        import time as _time
        _t0 = _time.perf_counter()
        client = self._get_client()
        try:
            coll = client.get_collection(collection or COLLECTION_NAME)
        except Exception:
            return []  # Corpus not ingested yet
        _t_coll = _time.perf_counter()
        coll_count = coll.count()
        _t_count = _time.perf_counter()
        if coll_count == 0:
            return []

        where = _parse_tags_to_where(tags)
        if source_paths:
            sp_filter = (
                {"source_path": source_paths[0]}
                if len(source_paths) == 1
                else {"source_path": {"$in": list(source_paths)}}
            )
            where = sp_filter if where is None else {"$and": [where, sp_filter]}
        dense_k = min(config.DENSE_TOP_K, coll_count)
        raw = coll.query(
            query_embeddings=[query_vec],
            n_results=dense_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        _t_query = _time.perf_counter()
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]

        if not docs:
            logger.info(
                'SEARCH_TIMING %s coll=%s coll_count=%d dense_k=%d returned=0 '
                'get_coll_ms=%.1f count_ms=%.1f chroma_query_ms=%.1f rerank_ms=0',
                _trace_tag(),
                collection, coll_count, dense_k,
                (_t_coll - _t0) * 1000, (_t_count - _t_coll) * 1000,
                (_t_query - _t_count) * 1000,
            )
            return []

        _t_rerank_start = _time.perf_counter()
        scores = self._rerank(query_text, docs)
        _t_rerank = _time.perf_counter()
        logger.info(
            'SEARCH_TIMING %s coll=%s coll_count=%d dense_k=%d returned=%d '
            'get_coll_ms=%.1f count_ms=%.1f chroma_query_ms=%.1f rerank_ms=%.1f',
            _trace_tag(),
            collection, coll_count, dense_k, len(docs),
            (_t_coll - _t0) * 1000, (_t_count - _t_coll) * 1000,
            (_t_query - _t_count) * 1000,
            (_t_rerank - _t_rerank_start) * 1000,
        )

        ranked = sorted(
            zip(ids, docs, metas, scores),
            key=lambda x: float(x[3]),
            reverse=True,
        )

        # Min-score guard: bail out if best match is noise.
        if not ranked or float(ranked[0][3]) < config.RERANK_MIN_SCORE:
            return []

        ranked = ranked[:top_k]
        return [
            {
                "id": id_,
                "source_path": (meta or {}).get("source_path", ""),
                "section_path": (meta or {}).get("section_path", ""),
                "title": (meta or {}).get("title", ""),
                "doc_type": (meta or {}).get("doc_type", ""),
                "score": float(score),
                "text": text,
            }
            for id_, text, meta, score in ranked
        ]

    def search_multi(
        self,
        query: str,
        collections: list[str],
        tags: Optional[list[str]] = None,
        top_k: int = config.FINAL_TOP_K,
        merge_top_n: Optional[int] = None,
        source_paths: Optional[list[str]] = None,
        query_vec: Optional[list[float]] = None,
    ) -> list[dict]:
        """Multi-collection search with single-batch rerank.

        Pipeline:
          1. Embed query once (or use the provided query_vec).
          2. Per-collection ChromaDB query for top DENSE_TOP_K candidates
             (no rerank). Cheap, ~30 ms each.
          3. Merge candidates across collections, sort by Chroma distance
             (smaller = closer; bge-m3 + cosine is comparable across
             collections that share the same embedding model).
          4. Take top `merge_top_n` (default DENSE_TOP_K) from the union.
          5. Run ONE reranker batch over those candidates.
          6. Apply RERANK_MIN_SCORE threshold to the merged set.
          7. Return top `top_k` results tagged with `kb_id`.

        Each result row carries a `kb_id` field (= collection prefix
        before `__corpus`) so downstream callers can attribute provenance.

        Compared to N parallel /search_by_vector calls:
          - 1 reranker batch instead of N (no GPU contention)
          - 1 HTTP round trip from caller instead of N
          - Same Chroma work (still N HNSW lookups, parallelizable)
        """
        import time as _time
        _t0 = _time.perf_counter()
        # 1. Embed once.
        if query_vec is None:
            q_vec = self.embed([query])[0]
        else:
            q_vec = query_vec
        _t_embed = _time.perf_counter()

        client = self._get_client()
        where = _parse_tags_to_where(tags)
        if source_paths:
            sp_filter = (
                {"source_path": source_paths[0]}
                if len(source_paths) == 1
                else {"source_path": {"$in": list(source_paths)}}
            )
            where = sp_filter if where is None else {"$and": [where, sp_filter]}

        merge_top_n = merge_top_n or config.DENSE_TOP_K

        # 2. Per-collection Chroma query (no rerank). Each candidate keeps
        # its kb_id so we can attribute provenance after merging.
        candidates: list[tuple] = []  # (distance, id, doc, meta, kb_id)
        per_coll_counts: dict[str, int] = {}
        for coll_name in collections:
            try:
                coll = client.get_collection(coll_name)
            except Exception:
                continue
            cc = coll.count()
            if cc == 0:
                continue
            per_coll_counts[coll_name] = cc
            dense_k = min(config.DENSE_TOP_K, cc)
            raw = coll.query(
                query_embeddings=[q_vec],
                n_results=dense_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            ids = raw.get("ids", [[]])[0]
            docs = raw.get("documents", [[]])[0]
            metas = raw.get("metadatas", [[]])[0]
            dists = raw.get("distances", [[]])[0]
            kb_id = (
                coll_name[:-len("__corpus")]
                if coll_name.endswith("__corpus") else coll_name
            )
            for i, doc in enumerate(docs):
                candidates.append((
                    float(dists[i]) if i < len(dists) else 0.0,
                    ids[i] if i < len(ids) else "",
                    doc,
                    metas[i] if i < len(metas) else {},
                    kb_id,
                ))
        _t_chroma = _time.perf_counter()

        if not candidates:
            logger.info(
                'SEARCH_MULTI_TIMING %s n_coll=%d total_ms=%.1f embed_ms=%.1f '
                'chroma_ms=%.1f rerank_ms=0 candidates=0 returned=0',
                _trace_tag(),
                len(collections),
                (_t_chroma - _t0) * 1000,
                (_t_embed - _t0) * 1000,
                (_t_chroma - _t_embed) * 1000,
            )
            return []

        # 3. Merge by Chroma distance (smaller = closer), trim to top-N.
        candidates.sort(key=lambda c: c[0])
        candidates = candidates[:merge_top_n]

        # 4. Single reranker batch.
        docs_only = [c[2] for c in candidates]
        scores = self._rerank(query, docs_only)
        _t_rerank = _time.perf_counter()

        ranked = sorted(
            zip(scores, candidates),
            key=lambda x: float(x[0]),
            reverse=True,
        )
        if not ranked or float(ranked[0][0]) < config.RERANK_MIN_SCORE:
            logger.info(
                'SEARCH_MULTI_TIMING %s n_coll=%d total_ms=%.1f embed_ms=%.1f '
                'chroma_ms=%.1f rerank_ms=%.1f candidates=%d returned=0_below_threshold',
                _trace_tag(),
                len(collections),
                (_t_rerank - _t0) * 1000,
                (_t_embed - _t0) * 1000,
                (_t_chroma - _t_embed) * 1000,
                (_t_rerank - _t_chroma) * 1000,
                len(candidates),
            )
            return []
        ranked = ranked[:top_k]

        out = []
        for score, (_dist, id_, doc, meta, kb_id) in ranked:
            out.append({
                "id": id_,
                "source_path": (meta or {}).get("source_path", ""),
                "section_path": (meta or {}).get("section_path", ""),
                "title": (meta or {}).get("title", ""),
                "doc_type": (meta or {}).get("doc_type", ""),
                "score": float(score),
                "text": doc,
                "kb_id": kb_id,
            })
        logger.info(
            'SEARCH_MULTI_TIMING %s n_coll=%d total_ms=%.1f embed_ms=%.1f '
            'chroma_ms=%.1f rerank_ms=%.1f candidates=%d returned=%d',
            _trace_tag(),
            len(collections),
            (_t_rerank - _t0) * 1000,
            (_t_embed - _t0) * 1000,
            (_t_chroma - _t_embed) * 1000,
            (_t_rerank - _t_chroma) * 1000,
            len(candidates),
            len(out),
        )
        return out

    # ── Cache for arbitrary collections ───────────────────────────────
    # Used by noted-graph at GraphRAG rebuild time to cache entity-name
    # and community-summary embeddings, so queries become vector lookups
    # instead of re-embed cycles.

    def cache_upsert(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        replace: bool = True,
    ) -> tuple[int, bool]:
        """Embed `texts` and upsert into `collection`. If replace, delete
        the entire collection first (atomic-rebuild semantics)."""
        if len(ids) != len(texts):
            raise ValueError("ids and texts must be same length")
        client = self._get_client()
        replaced = False
        if replace:
            try:
                client.delete_collection(collection)
                replaced = True
            except Exception:
                pass  # collection didn't exist, that's fine
        col = client.get_or_create_collection(collection)
        vectors = self.embed(texts)
        # Upsert in batches to keep memory reasonable
        BATCH = 256
        n = len(ids)
        for start in range(0, n, BATCH):
            end = min(start + BATCH, n)
            col.upsert(
                ids=ids[start:end],
                documents=texts[start:end],
                embeddings=vectors[start:end],
            )
        return n, replaced

    def cache_search(self, collection: str, query: str, top_k: int) -> list[dict]:
        """Vector-search a cached collection. Returns list of
        {id, score, text} ordered by descending score."""
        q_vec = self.embed([query])[0]
        return self.cache_search_by_vector(collection, q_vec, top_k)

    def cache_search_by_vector(
        self, collection: str, vector: list[float], top_k: int,
    ) -> list[dict]:
        """Same as cache_search but takes a pre-computed query vector,
        skipping the bge-m3 embed step. Used by the parallel-retrieval
        path so we embed once in the caller and fan out to both stores
        without GPU contention."""
        client = self._get_client()
        try:
            col = client.get_collection(collection)
        except Exception:
            return []
        if col.count() == 0:
            return []
        raw = col.query(
            query_embeddings=[vector],
            n_results=min(top_k, col.count()),
            include=["documents", "distances"],
        )
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        dists = raw.get("distances", [[]])[0]
        # Chroma returns L2 distance for normalized embeddings; convert
        # back to cosine similarity for an intuitive score (1.0 = identical).
        return [
            {
                "id": id_,
                "score": max(0.0, 1.0 - float(dist) / 2.0),
                "text": doc,
            }
            for id_, doc, dist in zip(ids, docs, dists)
        ]

    def cache_drop(self, collection: str) -> bool:
        client = self._get_client()
        try:
            client.delete_collection(collection)
            return True
        except Exception:
            return False

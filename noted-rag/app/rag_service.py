"""Core RAG service: lazy model loading, dense retrieval + cross-encoder rerank.

Single `noted_corpus` collection. `search` runs over the whole corpus by
default; optional `tags` narrow via Chroma `where` filters. A minimum
rerank score guards against hallucinating on empty-signal queries.

Models are loaded on first use (not at startup) so `/health` is always fast
and the service is resilient to a cold model cache.
"""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Optional

import chromadb

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


class RagService:
    def __init__(self) -> None:
        self._client: Optional[chromadb.ClientAPI] = None
        self._embedder = None  # sentence_transformers.SentenceTransformer
        self._reranker = None  # sentence_transformers.CrossEncoder

    # ── Lazy accessors ─────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            config.ensure_dirs()
            self._client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        return self._client

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading embedder %s on %s (cache=%s)",
                config.EMBED_MODEL, config.DEVICE, config.MODEL_CACHE,
            )
            self._embedder = SentenceTransformer(
                config.EMBED_MODEL,
                cache_folder=str(config.MODEL_CACHE),
                device=config.DEVICE,
            )
        return self._embedder

    def _get_reranker(self):
        if self._reranker is None:
            from sentence_transformers import CrossEncoder

            logger.info(
                "Loading reranker %s on %s",
                config.RERANK_MODEL, config.DEVICE,
            )
            self._reranker = CrossEncoder(
                config.RERANK_MODEL,
                device=config.DEVICE,
                trust_remote_code=True,
            )
            # bge-reranker-v2-m3 with trust_remote_code uses a custom
            # model class that ignores the `device=` constructor arg —
            # it stays on CPU, where 20 long-chunk forward passes take
            # ~5 seconds. Force the underlying nn.Module onto the target
            # device explicitly. ~57x speedup observed (5000ms -> 87ms).
            try:
                self._reranker.model.to(config.DEVICE)
            except Exception as e:
                logger.warning('reranker .to(%s) failed: %s', config.DEVICE, e)
        return self._reranker

    # ── Public API ────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return normalized dense embeddings for a list of strings."""
        import time, torch
        t0 = time.perf_counter()
        model = self._get_embedder()
        t_model = time.perf_counter()

        # GPU state + per-stage timing. We separate model.encode() (CPU
        # tokenize + GPU forward + host-device transfers + CPU to_numpy)
        # from pure GPU kernel time (CUDA events, only counts compute on
        # the GPU stream). The gap between encode_ms and gpu_kernel_ms is
        # CPU-side / transfer / synchronization overhead.
        gpu_extra = ''
        start_evt = end_evt = None
        if torch.cuda.is_available():
            try:
                mem_alloc = torch.cuda.memory_allocated() / 1024 / 1024
                mem_resv = torch.cuda.memory_reserved() / 1024 / 1024
                gpu_extra = f' gpu_alloc_mb={mem_alloc:.0f} gpu_resv_mb={mem_resv:.0f}'
                start_evt = torch.cuda.Event(enable_timing=True)
                end_evt = torch.cuda.Event(enable_timing=True)
                start_evt.record()
            except Exception:
                start_evt = end_evt = None

        vectors = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        if start_evt is not None:
            try:
                end_evt.record()
                torch.cuda.synchronize()
                gpu_extra += f' gpu_kernel_ms={start_evt.elapsed_time(end_evt):.1f}'
            except Exception:
                pass
        t_encode = time.perf_counter()

        out = vectors.tolist()
        t_done = time.perf_counter()

        logger.info(
            'EMBED_TIMING %s n=%d chars=%d total_ms=%.1f get_model_ms=%.1f encode_ms=%.1f tolist_ms=%.1f%s',
            _trace_tag(),
            len(texts),
            sum(len(t) for t in texts),
            (t_done - t0) * 1000,
            (t_model - t0) * 1000,
            (t_encode - t_model) * 1000,
            (t_done - t_encode) * 1000,
            gpu_extra,
        )
        return out

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

        reranker = self._get_reranker()
        _t_rerank_start = _time.perf_counter()
        scores = reranker.predict([(query_text, d) for d in docs])
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
        reranker = self._get_reranker()
        docs_only = [c[2] for c in candidates]
        # DEBUG: dump (query, docs) to disk so an isolated probe can
        # reproduce the reranker call and isolate its latency. Set
        # RERANK_DUMP_DIR=/data/rerank_dumps in noted-rag's env to enable.
        _dump_dir = os.environ.get("RERANK_DUMP_DIR")
        if _dump_dir:
            try:
                os.makedirs(_dump_dir, exist_ok=True)
                import json as _json, time as _ts
                fname = f"{int(_ts.time()*1000)}_{_turn_id_var.get()}_search_multi.json"
                with open(os.path.join(_dump_dir, fname), "w") as f:
                    _json.dump({
                        "turn_id": _turn_id_var.get(),
                        "source": _source_var.get(),
                        "kind": "search_multi",
                        "n_coll": len(collections),
                        "n_candidates": len(docs_only),
                        "query": query,
                        "docs": docs_only,
                    }, f, ensure_ascii=False)
            except Exception as _e:
                logger.warning("rerank dump failed: %s", _e)
        # GPU-kernel timing around the predict call. If gpu_kernel_ms is
        # fast (~200 ms) but rerank_ms wall is slow, the slowdown is
        # OUTSIDE the GPU work — Python overhead, tokenization, transfer,
        # blocking on a lock, etc. If both are slow, the kernel itself is
        # slow in production for a reason we haven't isolated.
        import torch as _torch_rk
        _gpu_kernel_ms = 0.0
        _rerank_pairs = [(query, d) for d in docs_only]
        if _torch_rk.cuda.is_available():
            try:
                _evt_a = _torch_rk.cuda.Event(enable_timing=True)
                _evt_b = _torch_rk.cuda.Event(enable_timing=True)
                _evt_a.record()
                scores = reranker.predict(_rerank_pairs)
                _evt_b.record()
                _torch_rk.cuda.synchronize()
                _gpu_kernel_ms = _evt_a.elapsed_time(_evt_b)
            except Exception:
                # Fall back to plain predict if event timing breaks
                scores = reranker.predict(_rerank_pairs)
        else:
            scores = reranker.predict(_rerank_pairs)
        _t_rerank = _time.perf_counter()

        ranked = sorted(
            zip(scores, candidates),
            key=lambda x: float(x[0]),
            reverse=True,
        )
        if not ranked or float(ranked[0][0]) < config.RERANK_MIN_SCORE:
            logger.info(
                'SEARCH_MULTI_TIMING %s n_coll=%d total_ms=%.1f embed_ms=%.1f '
                'chroma_ms=%.1f rerank_ms=%.1f rerank_gpu_ms=%.1f candidates=%d returned=0_below_threshold',
                _trace_tag(),
                len(collections),
                (_t_rerank - _t0) * 1000,
                (_t_embed - _t0) * 1000,
                (_t_chroma - _t_embed) * 1000,
                (_t_rerank - _t_chroma) * 1000,
                _gpu_kernel_ms,
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
            'chroma_ms=%.1f rerank_ms=%.1f rerank_gpu_ms=%.1f candidates=%d returned=%d',
            _trace_tag(),
            len(collections),
            (_t_rerank - _t0) * 1000,
            (_t_embed - _t0) * 1000,
            (_t_chroma - _t_embed) * 1000,
            (_t_rerank - _t_chroma) * 1000,
            _gpu_kernel_ms,
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

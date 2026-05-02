"""GraphRAG retrieval (Phase 1E).

Implements the two retrieval paths specified in graph_rag_notes.md §5.3:

  global mode (FR-1) - thematic questions:
    1. Embed question via bge-m3.
    2. Vector-search community_summary.text embeddings (computed on the fly
       because Phase 1 does not persist these vectors into ArcadeDB).
    3. For each top-K community, fetch top-N entities by PageRank plus
       their immediate edges via Cypher.
    4. Pull supporting markdown_chunk excerpts via :mentions.
    5. Gemma synthesizes an answer.

  local mode (FR-2) - relational questions:
    1. Embed question.
    2. Vector-search thematic entities by `name + description` similarity.
    3. Cypher N-hop traversal from entry entities.
    4. Pull supporting chunks.
    5. Gemma synthesizes.

  auto mode: run both in parallel (sequentially on the shared Gemma pool
  in Phase 1) and return the better-scoring answer OR merge. For now we
  simply run both and return both envelopes tagged mode=auto.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
from app.config import (
    GLOBAL_PROJECT_ID,
    GLOBAL_TOP_COMMUNITIES,
    LOCAL_TRAVERSAL_HOPS,
    SAMEAS_EXPAND_CONFIDENCE,
    SUBGRAPH_CAP,
    TOP_ENTITIES_N,
)
from app.llm_client import LLMClient, LLMError
from app.rag_client import RagClient, RagClientError

logger = logging.getLogger(__name__)


# NOTE: this module no longer carries its own _SYSTEM_PROMPT constant.
# The agent_server preset (`noted_graph` / `noted_graph_answer`) loads its
# system prompt from data/prompts/*.txt server-side, and that's the single
# source of truth. Sending an additional system message from here used to
# create a dual-prompt conflict where the local constant's loose
# `[chunk_id]` placeholder undermined the preset's strict "copy verbatim"
# rule, leading Gemma to fabricate short numeric chunk citations.


@dataclass
class RetrievalEnvelope:
    answer: str
    citations: list[str] = field(default_factory=list)
    subgraph: dict = field(default_factory=lambda: {'nodes': [], 'edges': []})
    mode: str = 'auto'
    communities_used: list[int] = field(default_factory=list)
    graph_built_at: str | None = None
    rebuild_in_progress: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Retriever:
    """Main entry point for /research/query.

    P3.2: parameterized at construction with `project_id` +
    `entity_cache_collection` + `summary_cache_collection`. Multiple KBs
    each have their own Retriever instance via KBContext; the underlying
    HTTP clients (ArcadeDB / noted-rag / Gemma) are stateless and shared.

    KNOWN GAP (P3.2 -> P4): only one Cypher query in this file filters
    by `project_ids` (`_graph_built_at`). The 19 others assume single-KB
    operation. Today this is correct because the active KB's
    cache_search returns only its own entities (cache collections are
    per-KB), and traversal hops then stay within those entities. But if
    the same canonical entity (e.g. `concept:mlflow`) exists in two KBs
    with overlapping doc sets, traversal CAN return edges/entities of
    the OTHER KB. Multi-active KB query (P4) intentionally UNIONs across
    KBs anyway, so we'll address this when P4 lands - either by adding
    `WHERE $pid IN n.project_ids` to every MATCH, or by switching to
    explicit per-KB entity ids.
    """

    def __init__(
        self,
        kb_id: str | None = None,
        project_id: str | None = None,
        arcadedb_database: str | None = None,
        entity_cache_collection: str | None = None,
        summary_cache_collection: str | None = None,
        arcadedb: ArcadeDBClient | None = None,
        rag: RagClient | None = None,
        llm: LLMClient | None = None,
    ):
        # Per-Domain ArcadeDB database (one per Domain inside the shared
        # noted-arcadedb container). `project_id` is the legacy alias,
        # same value as arcadedb_database under the new architecture.
        self.kb_id = kb_id or 'noted'
        db = arcadedb_database or project_id or GLOBAL_PROJECT_ID
        self.arcadedb_database = db
        self.project_id = db  # back-compat alias
        self.entity_cache_collection = entity_cache_collection or 'gr_entities'
        self.summary_cache_collection = summary_cache_collection or 'gr_summaries'
        self._db = arcadedb or ArcadeDBClient(database=db)
        self._rag = rag or RagClient()
        self._llm = llm or LLMClient()

    # ── Public ───────────────────────────────────────────────────────

    def query(self, question: str, mode: str = 'auto') -> RetrievalEnvelope:
        question = (question or '').strip()
        if not question:
            raise ValueError('query: question is required')
        if mode == 'global':
            return self._global_mode(question)
        if mode == 'local':
            return self._local_mode(question)
        if mode == 'auto':
            # In Phase 1, auto runs both and returns whichever has more
            # citations; when they tie, prefer local (more specific).
            # Phase 1F will tune this heuristic against real scenarios.
            gl = self._safe_mode(question, 'global')
            lo = self._safe_mode(question, 'local')
            if len(lo.citations) >= len(gl.citations):
                lo.mode = 'auto:local'
                return lo
            gl.mode = 'auto:global'
            return gl
        raise ValueError(f'query: unknown mode {mode!r}')

    # ── Helpers ──────────────────────────────────────────────────────

    def _safe_mode(self, question: str, mode: str) -> RetrievalEnvelope:
        try:
            return (self._global_mode if mode == 'global' else self._local_mode)(question)
        except Exception as e:
            logger.exception('%s mode failed', mode)
            return RetrievalEnvelope(
                answer=f'({mode} mode error: {type(e).__name__}: {e})',
                mode=f'auto:{mode}:error',
            )

    # ── Global mode ──────────────────────────────────────────────────

    def _global_mode_prepare(self, question: str):
        """Run global-mode retrieval and assemble the synthesis user_prompt.

        Returns either:
          - RetrievalEnvelope: early-exit (no community summaries available, etc.)
          - dict with keys {user_prompt, entities, edges, communities_used,
            citations}: ready-to-synthesize state.

        Used by both `_global_mode` (non-streaming, calls _ask_gemma) and
        `global_mode_stream` (yields tokens via chat_text_stream).
        """
        # 1. Vector-search the gr_summaries cache. Sub-100 ms regardless
        #    of corpus size; the embeddings were computed at rebuild time.
        hits = self._rag.cache_search(self.summary_cache_collection, question, top_k=GLOBAL_TOP_COMMUNITIES)
        if not hits:
            return RetrievalEnvelope(
                answer='No community summaries are available yet. Trigger a rebuild first.',
                mode='global',
                graph_built_at=self._graph_built_at(),
            )

        # 2. Resolve each hit (community_summary id) to its community_id +
        #    text via one ArcadeDB query.
        summary_ids = [h['id'] for h in hits]
        rows = self._db.query(
            # Drop the {type: "community_summary"} filter - id is selective
            # enough (`community_summary:N`) and the type index can hold
            # stale references after recluster's DETACH DELETE on these nodes.
            '''MATCH (cs:Entity)
               WHERE cs.id IN $ids
               RETURN cs.id AS id, cs.community_id AS cid, cs.properties_json AS props''',
            {'ids': summary_ids},
        )
        # Index by id, preserve hit order. community_id is now a top-level
        # Entity property (hoisted from properties_json at write time);
        # `text` still lives in the JSON blob.
        by_id = {r['id']: r for r in rows}
        top = []
        for h in hits:
            row = by_id.get(h['id'])
            if not row:
                continue
            props = _load_json(row.get('props'))
            text = (props.get('text') or '').strip()
            cid = row.get('cid')
            if not text or cid is None:
                continue
            top.append(({'id': h['id'], 'community_id': cid, 'text': text}, h['score']))
        if not top:
            return RetrievalEnvelope(answer='Community summaries cache is stale.', mode='global')

        chosen_cids = [m['community_id'] for m, _ in top]

        # 3. Batched fetch (was: 3*N sequential per-community queries).
        # Q1: ALL entities in any chosen community, tagged with their cid.
        # Then in-memory: group by cid, sort by rank, take TOP_ENTITIES_N
        # per cid. community_id is hoisted to a hot indexed column so the
        # IN-list filter is selective.
        entities_payload: list[dict] = []
        edges_payload: list[dict] = []
        citations: set[str] = set()

        ent_rows = self._db.query(
            '''MATCH (e:Entity)-[:RELATES {type: "member_of"}]->(c:Entity)
               WHERE c.community_id IN $cids
               RETURN c.community_id AS cid, e.id AS id, e.label AS label,
                      e.type AS type, e.properties_json AS props''',
            {'cids': chosen_cids},
        )

        by_cid: dict[int, list[dict]] = {}
        for r in ent_rows:
            cid_v = r.get('cid')
            if cid_v is None:
                continue
            by_cid.setdefault(cid_v, []).append(r)

        for cid_v in chosen_cids:
            rows_for_cid = by_cid.get(cid_v, [])
            decoded = _decode_entity_rows(rows_for_cid)
            decoded.sort(key=lambda e: -float((e.get('properties') or {}).get('rank', 0.0)))
            entities_payload.extend(decoded[:TOP_ENTITIES_N])

        entity_ids = [e['id'] for e in entities_payload]

        # Q2 || Q3: edges from entity_ids and chunks-mentions of entity_ids.
        # Both depend only on entity_ids; independent of each other.
        # Caps are scaled by community count to preserve approximate volume
        # vs the original per-community-loop behavior.
        if entity_ids:
            n_communities = max(1, len(chosen_cids))

            def _fetch_edges() -> list[dict]:
                # Node-centric pattern: start from indexed Entity then
                # traverse outgoing edges (3.4x faster than global form).
                return self._db.query(
                    '''MATCH (n:Entity) WHERE n.id IN $ids
                       MATCH (n)-[r:RELATES]->(b:Entity)
                       RETURN n.id AS source, b.id AS target, r.type AS type, r.properties_json AS props
                       LIMIT $cap''',
                    {'ids': entity_ids, 'cap': SUBGRAPH_CAP * n_communities},
                )

            def _fetch_chunks() -> list[dict]:
                # Node-centric: start from the entity nodes (indexed),
                # then follow incoming :mentions edges from chunk nodes.
                return self._db.query(
                    '''MATCH (e:Entity) WHERE e.id IN $ids
                       MATCH (e)<-[:RELATES {type: "mentions"}]-(c:Entity)
                       RETURN DISTINCT c.id AS id LIMIT $cap''',
                    {'ids': entity_ids, 'cap': 20 * n_communities},
                )

            with ThreadPoolExecutor(max_workers=2) as ex:
                f_edges = ex.submit(_fetch_edges)
                f_chunks = ex.submit(_fetch_chunks)
                edges = f_edges.result()
                chunks = f_chunks.result()

            for er in edges:
                edges_payload.append({
                    'source': er['source'],
                    'target': er['target'],
                    'type': er['type'],
                    'properties': _load_json(er.get('props')),
                })
            for cr in chunks:
                citations.add(cr['id'])

        # 4. Assemble prompt. Synthesis is run by callers (non-streaming
        # via _global_mode -> _ask_gemma; streaming via global_mode_stream
        # -> chat_text_stream).
        user_prompt = _build_user_prompt(
            question,
            summaries=[m['text'] for m, _ in top],
            entities=entities_payload,
            edges=edges_payload,
            chunk_excerpts=self._chunk_excerpts(list(citations)),
        )
        return {
            'user_prompt': user_prompt,
            'entities': entities_payload,
            'edges': edges_payload,
            'communities_used': chosen_cids,
            'citations': list(citations),
        }

    def _global_mode(self, question: str) -> RetrievalEnvelope:
        prep = self._global_mode_prepare(question)
        if isinstance(prep, RetrievalEnvelope):
            return prep
        answer = _sanitize_citations(self._ask_gemma(prep['user_prompt']))
        return RetrievalEnvelope(
            answer=answer,
            citations=_extract_used_citations(answer),
            subgraph={
                'nodes': prep['entities'],
                'edges': prep['edges'],
            },
            mode='global',
            communities_used=prep['communities_used'],
            graph_built_at=self._graph_built_at(),
        )

    def global_mode_stream(self, question: str):
        """Streaming variant of _global_mode for /research/query/stream.
        Yields the same event tuples as `local_mode_stream`'s synthesis
        phase: ('retrieval_done', {...}) -> ('token', '<delta>') ... ->
        ('done', {'envelope': {...}}).
        """
        prep = self._global_mode_prepare(question)
        if isinstance(prep, RetrievalEnvelope):
            yield ('done', {'envelope': prep.to_dict()})
            return
        yield ('retrieval_done', {
            'mode': 'global',
            'subgraph': {
                'nodes': prep['entities'],
                'edges': prep['edges'],
            },
            'citations_pool_count': len(prep['citations']),
        })
        answer_parts: list[str] = []
        cite_filt = _CitationStreamFilter()
        try:
            for delta in self._llm.chat_text_stream(
                user_prompt=prep['user_prompt'],
                temperature=0.2,
                max_tokens=2048,
            ):
                answer_parts.append(delta)
                safe = cite_filt.feed(delta)
                if safe:
                    yield ('token', safe)
            tail = cite_filt.flush()
            if tail:
                yield ('token', tail)
        except LLMError as e:
            err = f'(Gemma synthesis failed: {e})'
            answer_parts.append(err)
            yield ('token', err)
        answer = _sanitize_citations(''.join(answer_parts)) or '(empty answer)'
        envelope = RetrievalEnvelope(
            answer=answer,
            citations=_extract_used_citations(answer),
            subgraph={
                'nodes': prep['entities'],
                'edges': prep['edges'],
            },
            mode='global',
            communities_used=prep['communities_used'],
            graph_built_at=self._graph_built_at(),
        )
        yield ('done', {'envelope': envelope.to_dict()})

    # ── Local mode ───────────────────────────────────────────────────

    def _local_mode(self, question: str) -> RetrievalEnvelope:
        # 1. Vector-search the gr_entities cache to find entry points.
        #    Sub-100 ms - embeddings were computed at rebuild time.
        hits = self._rag.cache_search(self.entity_cache_collection, question, top_k=7)
        if not hits:
            return RetrievalEnvelope(
                answer='No thematic entities in the graph yet. Trigger a rebuild first.',
                mode='local',
            )
        entry_ids = [h['id'] for h in hits]

        # 2. Explicit BFS from entry entities, hop-by-hop. We do NOT use
        #    a variable-length pattern (`[r:RELATES*1..N]`) because ArcadeDB
        #    applies LIMIT only AFTER expansion, so dense graphs (lots of
        #    `mentions` edges) blow it up.
        #
        #    Traverse only entity-entity edges (sameAs, similar_to,
        #    member_of). Skip `mentions` and `chunked_into` here - they're
        #    used for the chunk-bridge in community formation, not for
        #    semantic neighborhood expansion.
        TRAVERSAL_EDGE_TYPES = ['sameAs', 'similar_to', 'member_of']
        # Per-hop frontier cap keeps the search bounded.
        HOP_FRONTIER_CAP = 30

        reached_ids: set[str] = set(entry_ids)
        frontier: list[str] = list(entry_ids)
        hops = max(1, min(LOCAL_TRAVERSAL_HOPS, 2))   # hop 3+ is too aggressive at our density
        for _hop in range(hops):
            if not frontier:
                break
            hop_rows = self._db.query(
                '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                   WHERE a.id IN $front
                     AND r.type IN $rtypes
                     AND NOT b.id IN $seen
                   RETURN DISTINCT b.id AS id, b.rank AS rank
                   ORDER BY b.rank DESC
                   LIMIT $cap''',
                {
                    'front': frontier,
                    'rtypes': TRAVERSAL_EDGE_TYPES,
                    'seen': list(reached_ids),
                    'cap': HOP_FRONTIER_CAP,
                },
            )
            new_ids = [row['id'] for row in hop_rows if row.get('id')]
            if not new_ids:
                break
            reached_ids.update(new_ids)
            frontier = new_ids
            if len(reached_ids) >= SUBGRAPH_CAP:
                break

        # Pull node props + direct edges between reached nodes.
        if reached_ids:
            ids_list = list(reached_ids)

            # Switched 2026-05-02 from Cypher to ArcadeDB native SQL.
            # Cypher 129 ms → SQL 2.6 ms (49× speedup) for nodes, and
            # Cypher 146 ms → SQL 5.8 ms (25×) for edges, both with
            # identical row sets. The SQL forms anchor on Entity (uses
            # the `id` UNIQUE index) then expand outE — same logic as
            # the Cypher node-centric pattern but without the
            # Cypher→Gremlin translation overhead.
            def _fetch_nodes() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT id, label, type, community_id, rank,
                              properties_json AS props
                       FROM Entity WHERE id IN :ids''',
                    {'ids': ids_list},
                )

            def _fetch_edges() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT outV().id AS source, inV().id AS target,
                              type, properties_json AS props
                       FROM (SELECT expand(outE('RELATES'))
                             FROM (SELECT FROM Entity WHERE id IN :ids))
                       WHERE inV().id IN :ids''',
                    {'ids': ids_list},
                )

            # Independent reads against the same reached_ids set; ArcadeDB
            # client is HTTP-per-call, so two concurrent posts are safe.
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_nodes = ex.submit(_fetch_nodes)
                f_edges = ex.submit(_fetch_edges)
                nodes_rows = f_nodes.result()
                edges_rows = f_edges.result()

            entities_payload = _decode_entity_rows(nodes_rows)
            edges_payload = [
                {
                    'source': er['source'],
                    'target': er['target'],
                    'type': er['type'],
                    'properties': _load_json(er.get('props')),
                }
                for er in edges_rows
            ]
        else:
            entities_payload, edges_payload = [], []

        # 3. Supporting chunks.
        chunks_rows = self._db.query(
            '''MATCH (c:Entity)-[:RELATES {type: "mentions"}]->(e:Entity)
               WHERE e.id IN $ids
               RETURN DISTINCT c.id AS id, c.properties_json AS props LIMIT 30''',
            {'ids': list(reached_ids)},
        )
        citations = [row['id'] for row in chunks_rows]

        # 4. Prompt Gemma.
        user_prompt = _build_user_prompt(
            question,
            summaries=[],
            entities=entities_payload,
            edges=edges_payload,
            chunk_excerpts=self._chunk_excerpts(citations),
        )
        answer = _sanitize_citations(self._ask_gemma(user_prompt))

        return RetrievalEnvelope(
            answer=answer,
            citations=_extract_used_citations(answer),
            subgraph={'nodes': entities_payload, 'edges': edges_payload},
            mode='local',
            graph_built_at=self._graph_built_at(),
        )

    def local_mode_retrieve_by_vector(self, query_vector: list[float]) -> dict:
        """Same as local_mode_retrieve but starts from a pre-computed query
        vector instead of a question string. Skips the bge-m3 embed step
        on noted-rag, so the parallel-retrieval tool path doesn't double-
        embed (which serializes at the GPU and kills the parallelism win).

        Logic mirrors local_mode_retrieve from step 2 onwards (BFS +
        node/edge fetch + supporting chunks).
        """
        if not query_vector:
            raise ValueError('local_mode_retrieve_by_vector: query_vector is required')

        _t0 = time.perf_counter()

        hits = self._rag.cache_search_by_vector(self.entity_cache_collection, query_vector, top_k=7)
        _t_entry = time.perf_counter()
        if not hits:
            return {
                'mode': 'local',
                'entry_entities': [],
                'entities': [],
                'edges': [],
                'chunk_excerpts': [],
                'graph_built_at': self._graph_built_at(),
                'note': 'No thematic entities in the graph yet. Trigger a rebuild first.',
            }
        entry_ids = [h['id'] for h in hits]

        TRAVERSAL_EDGE_TYPES = ['sameAs', 'similar_to', 'member_of']
        HOP_FRONTIER_CAP = 30
        reached_ids: set[str] = set(entry_ids)
        frontier: list[str] = list(entry_ids)
        hops = max(1, min(LOCAL_TRAVERSAL_HOPS, 2))
        # Stage A — BFS hops. Switched 2026-05-02 from Cypher to ArcadeDB
        # native SQL after benchmarking: Cypher 122 ms → SQL 4.4 ms (28×
        # speedup, identical results). The Cypher engine in ArcadeDB is a
        # translation layer over the native engine and pays substantial
        # parse/translate overhead per call; native SQL skips that.
        # Earlier rewrite (anchor-first + max(rank) aggregate) is preserved
        # in the SQL form. Pattern stays undirected via `bothE().bothV()`:
        # `sameAs` and `similar_to` are semantically symmetric.
        _t_bfs_start = time.perf_counter()
        n_hop_rows = 0
        for _hop in range(hops):
            if not frontier:
                break
            hop_rows = self._db.command_sql(
                '''SELECT id, MAX(rank) AS rank FROM (
                     SELECT expand(bothE('RELATES')[type IN :rtypes].bothV())
                     FROM (SELECT FROM Entity WHERE id IN :front)
                   )
                   WHERE id NOT IN :seen
                   GROUP BY id
                   ORDER BY rank DESC LIMIT :cap''',
                {'front': frontier, 'rtypes': TRAVERSAL_EDGE_TYPES,
                 'seen': list(reached_ids), 'cap': HOP_FRONTIER_CAP},
            )
            n_hop_rows += len(hop_rows)
            new_ids = [row['id'] for row in hop_rows if row.get('id')]
            if not new_ids:
                break
            reached_ids.update(new_ids)
            frontier = new_ids
            if len(reached_ids) >= SUBGRAPH_CAP:
                break
        _t_bfs_end = time.perf_counter()

        if reached_ids:
            ids_list = list(reached_ids)

            # Switched 2026-05-02 from Cypher to ArcadeDB native SQL.
            # Cypher 129 ms → SQL 2.6 ms (49× speedup) for nodes, and
            # Cypher 146 ms → SQL 5.8 ms (25×) for edges, both with
            # identical row sets. The SQL forms anchor on Entity (uses
            # the `id` UNIQUE index) then expand outE — same logic as
            # the Cypher node-centric pattern but without the
            # Cypher→Gremlin translation overhead.
            def _fetch_nodes() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT id, label, type, community_id, rank,
                              properties_json AS props
                       FROM Entity WHERE id IN :ids''',
                    {'ids': ids_list},
                )

            def _fetch_edges() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT outV().id AS source, inV().id AS target,
                              type, properties_json AS props
                       FROM (SELECT expand(outE('RELATES'))
                             FROM (SELECT FROM Entity WHERE id IN :ids))
                       WHERE inV().id IN :ids''',
                    {'ids': ids_list},
                )

            # Independent reads against the same reached_ids set; ArcadeDB
            # client is HTTP-per-call, so two concurrent posts are safe.
            _t_fetch_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_nodes = ex.submit(_fetch_nodes)
                f_edges = ex.submit(_fetch_edges)
                nodes_rows = f_nodes.result()
                edges_rows = f_edges.result()
            _t_fetch_end = time.perf_counter()

            entities_payload = _decode_entity_rows(nodes_rows)
            edges_payload = [
                {'source': er['source'], 'target': er['target'],
                 'type': er['type'], 'properties': _load_json(er.get('props'))}
                for er in edges_rows
            ]
        else:
            entities_payload, edges_payload = [], []
            _t_fetch_start = _t_fetch_end = time.perf_counter()

        # ── Per-entity AND per-relationship chunk grounding (denormalized).
        # Entity records carry `mentioned_in_chunks` (populated at ingestion
        # in research_builder). Read it directly - no Cypher query.
        # Per-relationship grounding is set intersection of two endpoints'
        # chunk lists. All in-memory.
        # ────────────────────────────────────────────────────────────
        TOP_ENTITIES_FOR_GROUNDING = 12
        TOP_EDGES_FOR_GROUNDING = 30
        CHUNKS_PER_ENTITY = 2
        CHUNKS_PER_EDGE = 2

        entity_chunks_by_id: dict[str, list[str]] = {}
        for e in entities_payload:
            chunks = (e.get('properties') or {}).get('mentioned_in_chunks') or []
            entity_chunks_by_id[e['id']] = list(chunks)

        def _rank(e):
            return float((e.get('properties') or {}).get('rank') or 0)
        ranked_entities = sorted(entities_payload, key=_rank, reverse=True)
        per_entity_chunks: dict[str, list[str]] = {}
        for e in ranked_entities[:TOP_ENTITIES_FOR_GROUNDING]:
            chunks = entity_chunks_by_id.get(e['id']) or []
            if chunks:
                per_entity_chunks[e['id']] = chunks[:CHUNKS_PER_ENTITY]

        per_edge_chunks: list[dict] = []
        for er in edges_payload[:TOP_EDGES_FOR_GROUNDING]:
            src = er['source']; tgt = er['target']
            common = list(set(entity_chunks_by_id.get(src) or []) &
                          set(entity_chunks_by_id.get(tgt) or []))
            if common:
                per_edge_chunks.append({
                    'source': src, 'target': tgt, 'type': er['type'],
                    'chunk_ids': common[:CHUNKS_PER_EDGE],
                })

        candidate_chunk_ids: set = set()
        for cs in per_entity_chunks.values():
            candidate_chunk_ids.update(cs)
        for ec in per_edge_chunks:
            candidate_chunk_ids.update(ec['chunk_ids'])

        # Load chunk texts for the candidates, then run the name-presence
        # filter (cheap belt-and-suspenders on top of ingestion-side
        # strength sort). One DB query, reused for both filtering and
        # final excerpts.
        _t_chunks_start = time.perf_counter()
        if candidate_chunk_ids:
            loaded_excerpts = self._chunk_excerpts(list(candidate_chunk_ids))
            text_by_id = {c['id']: (c.get('text') or '') for c in loaded_excerpts}
            excerpt_by_id = {c['id']: c for c in loaded_excerpts}
            per_entity_chunks, per_edge_chunks = _filter_grounding_by_name_presence(
                per_entity_chunks, per_edge_chunks, entities_payload, text_by_id,
            )
            used_ids: set = set()
            for cs in per_entity_chunks.values():
                used_ids.update(cs)
            for ec in per_edge_chunks:
                used_ids.update(ec['chunk_ids'])
            chunk_excerpts = [excerpt_by_id[cid] for cid in used_ids if cid in excerpt_by_id]
        else:
            chunk_excerpts = []

        # Defensive fallback: if grounding produced nothing, surface up to
        # 30 chunks from any reached entity so the LLM still has chunk
        # context to work with.
        if not chunk_excerpts:
            fallback_ids: list[str] = []
            for chunks in entity_chunks_by_id.values():
                for c in chunks[:5]:
                    if c not in fallback_ids:
                        fallback_ids.append(c)
                if len(fallback_ids) >= 30:
                    break
            if fallback_ids:
                chunk_excerpts = self._chunk_excerpts(fallback_ids)
        _t_chunks_end = time.perf_counter()

        entity_by_id = {e['id']: e for e in entities_payload}
        entry_payload = [
            {
                'id': h['id'],
                'label': (entity_by_id.get(h['id']) or {}).get('label'),
                'type': (entity_by_id.get(h['id']) or {}).get('type'),
                'score': h.get('score'),
            }
            for h in hits
        ]

        # Per-stage timing summary. Use this to drive optimization decisions:
        # the BFS Cypher ran with the rewritten anchor-first + max(rank)
        # form (2026-05-01) — compare bfs_ms vs the prior baseline.
        logger.info(
            'RETRIEVE_BY_VECTOR_TIMING entry_n=%d reached_n=%d nodes_n=%d edges_n=%d '
            'chunks_n=%d total_ms=%.1f entry_lookup_ms=%.1f bfs_ms=%.1f '
            'fetch_nodes_edges_ms=%.1f chunks_ms=%.1f hops_returned=%d',
            len(hits), len(reached_ids), len(entities_payload), len(edges_payload),
            len(chunk_excerpts),
            (_t_chunks_end - _t0) * 1000,
            (_t_entry - _t0) * 1000,
            (_t_bfs_end - _t_bfs_start) * 1000,
            (_t_fetch_end - _t_fetch_start) * 1000,
            (_t_chunks_end - _t_chunks_start) * 1000,
            n_hop_rows,
        )

        return {
            'mode': 'local',
            'entry_entities': entry_payload,
            'entities': entities_payload,
            'edges': edges_payload,
            'chunk_excerpts': chunk_excerpts,
            'per_entity_chunks': per_entity_chunks,
            'per_edge_chunks': per_edge_chunks,
            'graph_built_at': self._graph_built_at(),
        }

    def local_mode_retrieve(self, question: str) -> dict:
        """Retrieval-only variant of _local_mode (no Gemma synthesis).

        Returns the raw graph context for an external synthesizer (the
        chat assistant's Gemma) to fuse with vector chunks. This is what
        powers the parallel graph+vector retrieval tool: the heavy
        synthesis happens once in the chat layer with both stores'
        results in a single prompt, instead of synthesizing twice.

        Returns:
            {
              'mode': 'local',
              'entry_entities': [{'id', 'score'}, ...],   # vector hits
              'entities': [{'id', 'label', 'type', 'properties'}, ...],
              'edges':    [{'source', 'target', 'type', 'properties'}, ...],
              'chunk_excerpts': [{'id', 'text'}, ...],    # supporting chunks
              'graph_built_at': str | None,
            }
        """
        question = (question or '').strip()
        if not question:
            raise ValueError('local_mode_retrieve: question is required')

        hits = self._rag.cache_search(self.entity_cache_collection, question, top_k=7)
        if not hits:
            return {
                'mode': 'local',
                'entry_entities': [],
                'entities': [],
                'edges': [],
                'chunk_excerpts': [],
                'graph_built_at': self._graph_built_at(),
                'note': 'No thematic entities in the graph yet. Trigger a rebuild first.',
            }
        entry_ids = [h['id'] for h in hits]

        TRAVERSAL_EDGE_TYPES = ['sameAs', 'similar_to', 'member_of']
        HOP_FRONTIER_CAP = 30
        reached_ids: set[str] = set(entry_ids)
        frontier: list[str] = list(entry_ids)
        hops = max(1, min(LOCAL_TRAVERSAL_HOPS, 2))
        for _hop in range(hops):
            if not frontier:
                break
            hop_rows = self._db.query(
                '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                   WHERE a.id IN $front
                     AND r.type IN $rtypes
                     AND NOT b.id IN $seen
                   RETURN DISTINCT b.id AS id, b.rank AS rank
                   ORDER BY b.rank DESC
                   LIMIT $cap''',
                {'front': frontier, 'rtypes': TRAVERSAL_EDGE_TYPES,
                 'seen': list(reached_ids), 'cap': HOP_FRONTIER_CAP},
            )
            new_ids = [row['id'] for row in hop_rows if row.get('id')]
            if not new_ids:
                break
            reached_ids.update(new_ids)
            frontier = new_ids
            if len(reached_ids) >= SUBGRAPH_CAP:
                break

        if reached_ids:
            ids_list = list(reached_ids)

            # Switched 2026-05-02 from Cypher to ArcadeDB native SQL.
            # Cypher 129 ms → SQL 2.6 ms (49× speedup) for nodes, and
            # Cypher 146 ms → SQL 5.8 ms (25×) for edges, both with
            # identical row sets. The SQL forms anchor on Entity (uses
            # the `id` UNIQUE index) then expand outE — same logic as
            # the Cypher node-centric pattern but without the
            # Cypher→Gremlin translation overhead.
            def _fetch_nodes() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT id, label, type, community_id, rank,
                              properties_json AS props
                       FROM Entity WHERE id IN :ids''',
                    {'ids': ids_list},
                )

            def _fetch_edges() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT outV().id AS source, inV().id AS target,
                              type, properties_json AS props
                       FROM (SELECT expand(outE('RELATES'))
                             FROM (SELECT FROM Entity WHERE id IN :ids))
                       WHERE inV().id IN :ids''',
                    {'ids': ids_list},
                )

            # Independent reads against the same reached_ids set; ArcadeDB
            # client is HTTP-per-call, so two concurrent posts are safe.
            _t_fetch_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_nodes = ex.submit(_fetch_nodes)
                f_edges = ex.submit(_fetch_edges)
                nodes_rows = f_nodes.result()
                edges_rows = f_edges.result()
            _t_fetch_end = time.perf_counter()

            entities_payload = _decode_entity_rows(nodes_rows)
            edges_payload = [
                {'source': er['source'], 'target': er['target'],
                 'type': er['type'], 'properties': _load_json(er.get('props'))}
                for er in edges_rows
            ]
        else:
            entities_payload, edges_payload = [], []
            _t_fetch_start = _t_fetch_end = time.perf_counter()

        # ── Per-entity AND per-relationship chunk grounding (denormalized).
        # Entity records carry `mentioned_in_chunks` (populated at ingestion
        # in research_builder). Read it directly - no Cypher query.
        # Per-relationship grounding is set intersection of two endpoints'
        # chunk lists. All in-memory.
        # ────────────────────────────────────────────────────────────
        TOP_ENTITIES_FOR_GROUNDING = 12
        TOP_EDGES_FOR_GROUNDING = 30
        CHUNKS_PER_ENTITY = 2
        CHUNKS_PER_EDGE = 2

        entity_chunks_by_id: dict[str, list[str]] = {}
        for e in entities_payload:
            chunks = (e.get('properties') or {}).get('mentioned_in_chunks') or []
            entity_chunks_by_id[e['id']] = list(chunks)

        def _rank(e):
            return float((e.get('properties') or {}).get('rank') or 0)
        ranked_entities = sorted(entities_payload, key=_rank, reverse=True)
        per_entity_chunks: dict[str, list[str]] = {}
        for e in ranked_entities[:TOP_ENTITIES_FOR_GROUNDING]:
            chunks = entity_chunks_by_id.get(e['id']) or []
            if chunks:
                per_entity_chunks[e['id']] = chunks[:CHUNKS_PER_ENTITY]

        per_edge_chunks: list[dict] = []
        for er in edges_payload[:TOP_EDGES_FOR_GROUNDING]:
            src = er['source']; tgt = er['target']
            common = list(set(entity_chunks_by_id.get(src) or []) &
                          set(entity_chunks_by_id.get(tgt) or []))
            if common:
                per_edge_chunks.append({
                    'source': src, 'target': tgt, 'type': er['type'],
                    'chunk_ids': common[:CHUNKS_PER_EDGE],
                })

        candidate_chunk_ids: set = set()
        for cs in per_entity_chunks.values():
            candidate_chunk_ids.update(cs)
        for ec in per_edge_chunks:
            candidate_chunk_ids.update(ec['chunk_ids'])

        # Same name-presence filter as local_mode_retrieve_by_vector.
        if candidate_chunk_ids:
            loaded_excerpts = self._chunk_excerpts(list(candidate_chunk_ids))
            text_by_id = {c['id']: (c.get('text') or '') for c in loaded_excerpts}
            excerpt_by_id = {c['id']: c for c in loaded_excerpts}
            per_entity_chunks, per_edge_chunks = _filter_grounding_by_name_presence(
                per_entity_chunks, per_edge_chunks, entities_payload, text_by_id,
            )
            used_ids: set = set()
            for cs in per_entity_chunks.values():
                used_ids.update(cs)
            for ec in per_edge_chunks:
                used_ids.update(ec['chunk_ids'])
            chunk_excerpts = [excerpt_by_id[cid] for cid in used_ids if cid in excerpt_by_id]
        else:
            chunk_excerpts = []

        if not chunk_excerpts:
            fallback_ids: list[str] = []
            for chunks in entity_chunks_by_id.values():
                for c in chunks[:5]:
                    if c not in fallback_ids:
                        fallback_ids.append(c)
                if len(fallback_ids) >= 30:
                    break
            if fallback_ids:
                chunk_excerpts = self._chunk_excerpts(fallback_ids)

        entity_by_id = {e['id']: e for e in entities_payload}
        entry_payload = [
            {
                'id': h['id'],
                'label': (entity_by_id.get(h['id']) or {}).get('label'),
                'type': (entity_by_id.get(h['id']) or {}).get('type'),
                'score': h.get('score'),
            }
            for h in hits
        ]

        return {
            'mode': 'local',
            'entry_entities': entry_payload,
            'entities': entities_payload,
            'edges': edges_payload,
            'chunk_excerpts': chunk_excerpts,
            'per_entity_chunks': per_entity_chunks,
            'per_edge_chunks': per_edge_chunks,
            'graph_built_at': self._graph_built_at(),
        }

    def local_mode_stream(self, question: str):
        """Streaming variant of _local_mode for /research/query/stream.

        Yields:
          ('retrieval_done', {'mode': 'local', 'subgraph': {...}, 'citations_pool': [...]})
          ('token', '<chunk>')
          ('token', '<chunk>')
          ...
          ('done', {'envelope': <full RetrievalEnvelope dict>})

        Retrieval is performed eagerly (the same code path as _local_mode);
        only the synthesis Gemma call is streamed. This is what saves the
        user-perceived latency: tokens start arriving as soon as the
        retrieval completes (~50-300 ms), not after the full Gemma pass.
        """
        question = (question or '').strip()
        if not question:
            raise ValueError('local_mode_stream: question is required')

        # ── Replicate _local_mode retrieval (would refactor into a shared
        # helper if a third caller appeared). ────────────────────────────
        hits = self._rag.cache_search(self.entity_cache_collection, question, top_k=7)
        if not hits:
            envelope = RetrievalEnvelope(
                answer='No thematic entities in the graph yet. Trigger a rebuild first.',
                mode='local',
            )
            yield ('done', {'envelope': envelope.to_dict()})
            return
        entry_ids = [h['id'] for h in hits]

        TRAVERSAL_EDGE_TYPES = ['sameAs', 'similar_to', 'member_of']
        HOP_FRONTIER_CAP = 30
        reached_ids: set[str] = set(entry_ids)
        frontier: list[str] = list(entry_ids)
        hops = max(1, min(LOCAL_TRAVERSAL_HOPS, 2))
        for _hop in range(hops):
            if not frontier:
                break
            hop_rows = self._db.query(
                '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                   WHERE a.id IN $front
                     AND r.type IN $rtypes
                     AND NOT b.id IN $seen
                   RETURN DISTINCT b.id AS id, b.rank AS rank
                   ORDER BY b.rank DESC
                   LIMIT $cap''',
                {'front': frontier, 'rtypes': TRAVERSAL_EDGE_TYPES,
                 'seen': list(reached_ids), 'cap': HOP_FRONTIER_CAP},
            )
            new_ids = [row['id'] for row in hop_rows if row.get('id')]
            if not new_ids:
                break
            reached_ids.update(new_ids)
            frontier = new_ids
            if len(reached_ids) >= SUBGRAPH_CAP:
                break

        if reached_ids:
            ids_list = list(reached_ids)

            # Switched 2026-05-02 from Cypher to ArcadeDB native SQL.
            # Cypher 129 ms → SQL 2.6 ms (49× speedup) for nodes, and
            # Cypher 146 ms → SQL 5.8 ms (25×) for edges, both with
            # identical row sets. The SQL forms anchor on Entity (uses
            # the `id` UNIQUE index) then expand outE — same logic as
            # the Cypher node-centric pattern but without the
            # Cypher→Gremlin translation overhead.
            def _fetch_nodes() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT id, label, type, community_id, rank,
                              properties_json AS props
                       FROM Entity WHERE id IN :ids''',
                    {'ids': ids_list},
                )

            def _fetch_edges() -> list[dict]:
                return self._db.command_sql(
                    '''SELECT outV().id AS source, inV().id AS target,
                              type, properties_json AS props
                       FROM (SELECT expand(outE('RELATES'))
                             FROM (SELECT FROM Entity WHERE id IN :ids))
                       WHERE inV().id IN :ids''',
                    {'ids': ids_list},
                )

            # Independent reads against the same reached_ids set; ArcadeDB
            # client is HTTP-per-call, so two concurrent posts are safe.
            _t_fetch_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_nodes = ex.submit(_fetch_nodes)
                f_edges = ex.submit(_fetch_edges)
                nodes_rows = f_nodes.result()
                edges_rows = f_edges.result()
            _t_fetch_end = time.perf_counter()

            entities_payload = _decode_entity_rows(nodes_rows)
            edges_payload = [
                {'source': er['source'], 'target': er['target'],
                 'type': er['type'], 'properties': _load_json(er.get('props'))}
                for er in edges_rows
            ]
        else:
            entities_payload, edges_payload = [], []
            _t_fetch_start = _t_fetch_end = time.perf_counter()

        chunks_rows = self._db.query(
            '''MATCH (c:Entity)-[:RELATES {type: "mentions"}]->(e:Entity)
               WHERE e.id IN $ids
               RETURN DISTINCT c.id AS id, c.properties_json AS props LIMIT 30''',
            {'ids': list(reached_ids)},
        )
        citations_pool = [row['id'] for row in chunks_rows]

        # Retrieval is done. Tell the caller before we touch Gemma.
        yield ('retrieval_done', {
            'mode': 'local',
            'subgraph': {'nodes': entities_payload, 'edges': edges_payload},
            'citations_pool_count': len(citations_pool),
        })

        # ── Stream the synthesis. ────────────────────────────────────────
        user_prompt = _build_user_prompt(
            question,
            summaries=[],
            entities=entities_payload,
            edges=edges_payload,
            chunk_excerpts=self._chunk_excerpts(citations_pool),
        )

        answer_parts: list[str] = []
        cite_filt = _CitationStreamFilter()
        try:
            for delta in self._llm.chat_text_stream(
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=2048,
            ):
                answer_parts.append(delta)
                safe = cite_filt.feed(delta)
                if safe:
                    yield ('token', safe)
            tail = cite_filt.flush()
            if tail:
                yield ('token', tail)
        except LLMError as e:
            err = f'(Gemma synthesis failed: {e})'
            answer_parts.append(err)
            yield ('token', err)

        answer = _sanitize_citations(''.join(answer_parts)) or '(empty answer)'
        envelope = RetrievalEnvelope(
            answer=answer,
            citations=_extract_used_citations(answer),
            subgraph={'nodes': entities_payload, 'edges': edges_payload},
            mode='local',
            graph_built_at=self._graph_built_at(),
        )
        yield ('done', {'envelope': envelope.to_dict()})

    def synthesize_stream(self, question, entities, edges, chunk_excerpts):
        """Stream an LLM answer from a PRE-LOADED subgraph - skips the
        retrieve step entirely. The frontend caches the /research/retrieve
        payload and posts it back here when the user clicks "Ask the
        assistant", avoiding a duplicate BFS round-trip.

        Yields the same event tuples as `local_mode_stream`'s synthesis
        phase: ('token', '<delta>') ... ('done', {'envelope': {...}}).
        """
        question = (question or '').strip()
        if not question:
            raise ValueError('synthesize_stream: question is required')

        user_prompt = _build_user_prompt(
            question,
            summaries=[],
            entities=entities or [],
            edges=edges or [],
            chunk_excerpts=chunk_excerpts or [],
        )
        # Route through the dedicated `noted_graph_answer` preset whose
        # system prompt enforces prose markdown (vs the structured/JSON
        # output the analyst-style `noted_graph` preset produces for the
        # chat tool flow). The preset's persona handles the format rules,
        # so the user prompt body stays exactly as the chat path's.
        answer_parts: list[str] = []
        cite_filt = _CitationStreamFilter()
        try:
            for delta in self._llm.chat_text_stream(
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=2048,
                model='noted_graph_answer',
            ):
                answer_parts.append(delta)
                safe = cite_filt.feed(delta)
                if safe:
                    yield ('token', safe)
            tail = cite_filt.flush()
            if tail:
                yield ('token', tail)
        except LLMError as e:
            err = f'(Gemma synthesis failed: {e})'
            answer_parts.append(err)
            yield ('token', err)

        answer = _sanitize_citations(''.join(answer_parts)) or '(empty answer)'
        envelope = RetrievalEnvelope(
            answer=answer,
            citations=_extract_used_citations(answer),
            subgraph={'nodes': entities or [], 'edges': edges or []},
            mode='local',
            graph_built_at=self._graph_built_at(),
        )
        yield ('done', {'envelope': envelope.to_dict()})

    # ── Shared ───────────────────────────────────────────────────────

    def _chunk_excerpts(self, chunk_ids: list[str]) -> list[dict]:
        if not chunk_ids:
            return []
        # Match by id only (no `type: "markdown_chunk"` filter). ArcadeDB's
        # type index can hold stale references after recluster's heavy
        # DETACH DELETE pass; ids are unique (sha1-based) so the filter is
        # redundant. Same defensive pattern as graph_storage.py P2 fix.
        # Native SQL via id-IN-list — Entity.id UNIQUE index is used,
        # same fast path as the fetch_nodes call.
        rows = self._db.command_sql(
            '''SELECT id, properties_json AS props
               FROM Entity WHERE id IN :ids''',
            {'ids': chunk_ids[:30]},
        )
        out = []
        for r in rows:
            props = _load_json(r.get('props'))
            out.append({
                'id': r['id'],
                'doc_path': props.get('doc_path'),
                'section_path': props.get('section_path'),
                'text': (props.get('text') or '')[:1200],
            })
        return out

    def _ask_gemma(self, user_prompt: str) -> str:
        """Synthesize a markdown answer from the assembled context."""
        try:
            answer = self._llm.chat_text(
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=2048,
            )
            return answer or '(empty answer)'
        except LLMError as e:
            return f'(Gemma synthesis failed: {e})'


    def _graph_built_at(self) -> str | None:
        # Match by id-prefix instead of `type: "markdown_doc"` filter:
        # ArcadeDB's type index can hold stale references after recluster's
        # heavy DETACH DELETE pass, surfacing as "Record not found" 500s.
        # markdown_doc ids are `markdown_doc:<basename>` so the prefix is
        # equally selective. Same defensive pattern as
        # `_chunk_excerpts` and `graph_storage.add_doc_merge`.
        rows = self._db.query(
            '''MATCH (n:Entity)
               WHERE n.id STARTS WITH "markdown_doc:"
                 AND $pid IN n.project_ids
               RETURN n.properties_json AS props
               LIMIT 200''',
            {'pid': self.project_id},
        )
        # The last_modified of a markdown_doc is its file mtime, not the
        # build time. For the envelope we report the max last_modified as
        # a proxy. Phase 2 would persist the ResearchBuildStats.finished_at.
        max_ts = 0.0
        for r in rows:
            props = _load_json(r.get('props'))
            lm = props.get('last_modified') or 0
            try:
                lm = float(lm)
            except (TypeError, ValueError):
                lm = 0.0
            if lm > max_ts:
                max_ts = lm
        if max_ts == 0:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(max_ts, tz=timezone.utc).isoformat()


# ── Prompt assembly + helpers ────────────────────────────────────────

# Validate-and-collect tags from the answer text. Recognised forms:
#   [Cn]                     - community summary index
#   [E:<entity_id>]          - entity (we encode with E: prefix)
#   [R:<src>>type>><tgt>]    - relationship triple
#   [markdown_chunk:<hex>]   - chunk by full id
#   [<hex>]                  - chunk by short id (Gemma sometimes drops the prefix)
_VALID_TAG_RE = re.compile(
    r'\[('
    r'C\d+'
    r'|E:[^\]]+'
    r'|R:[^\]]+'
    r'|markdown_chunk:[0-9a-f]{8,16}'
    r'|[0-9a-f]{8,16}'
    r')\]'
)


# Pattern for bracketed content that LOOKS LIKE an attempted citation
# (so we know to strip if invalid). Includes pure-numeric, hex, and
# prefixed forms. Markdown links `[text](url)` and other prose brackets
# don't match this and are left alone.
_CITE_LIKE_RE = re.compile(
    r'\[(?:'
    r'\d+(?:\s*,\s*\d+)*'                  # `[138]`, `[64, 137]`
    r'|markdown_chunk:[^\]]*'              # any [markdown_chunk:...]
    r'|C\d+(?:\s*,\s*[^\]]+)*'             # `[C1]` or `[C1, ...]`
    r'|E:[^\]]+(?:\s*,\s*[^\]]+)*'         # `[E:foo]` or `[E:foo, E:bar]`
    r'|R:[^\]]+(?:\s*,\s*[^\]]+)*'         # `[R:src>type>tgt]` etc.
    r'|[0-9a-f]{4,}(?:\s*,\s*[^\]]+)*'     # bare hex, possibly comma-joined
    r')\]'
)


class _CitationStreamFilter:
    """Streaming filter that drops bracketed text WHICH LOOKS LIKE a
    failed citation but doesn't validate. Markdown links and other
    arbitrary prose brackets pass through.
    """

    def __init__(self) -> None:
        self._in_bracket = False
        self._buffer = ''

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ''
        out: list[str] = []
        for ch in chunk:
            if not self._in_bracket:
                if ch == '[':
                    self._in_bracket = True
                    self._buffer = ch
                else:
                    out.append(ch)
            else:
                self._buffer += ch
                # Defensive: if a stray `[` appears inside a buffer, treat
                # it as the start of a new bracket — flush the prior one.
                if ch == '[':
                    out.append(self._buffer[:-1])
                    self._buffer = '['
                elif ch == ']':
                    if _VALID_TAG_RE.fullmatch(self._buffer):
                        out.append(self._buffer)
                    elif _CITE_LIKE_RE.fullmatch(self._buffer):
                        # Looks like a fabricated citation, drop.
                        pass
                    else:
                        # Not citation-like, keep verbatim (markdown link
                        # text, prose etc.)
                        out.append(self._buffer)
                    self._in_bracket = False
                    self._buffer = ''
                # Bound the buffer: if a bracket runs unreasonably long
                # without closing, give up and emit so we don't swallow
                # large chunks of legit prose.
                elif len(self._buffer) > 200:
                    out.append(self._buffer)
                    self._in_bracket = False
                    self._buffer = ''
        return ''.join(out)

    def flush(self) -> str:
        # End-of-stream: anything still buffered (unclosed bracket) is
        # emitted as-is — prefer to leak weird text over swallow content.
        if self._in_bracket:
            tail = self._buffer
            self._buffer = ''
            self._in_bracket = False
            return tail
        return ''


def _sanitize_citations(text: str) -> str:
    """Non-streaming variant. Strips bracketed content that LOOKS LIKE a
    failed citation but doesn't validate. Leaves markdown links and
    other prose brackets alone."""
    if not text:
        return text

    def _replace(m: re.Match) -> str:
        token = m.group(0)
        if _VALID_TAG_RE.fullmatch(token):
            return token
        if _CITE_LIKE_RE.fullmatch(token):
            return ''
        return token

    return re.sub(r'\[[^\[\]]+\]', _replace, text)


def _extract_used_citations(answer_text: str) -> list[str]:
    """Pull every valid bracketed citation tag actually used in the answer,
    deduped, in first-occurrence order. Short chunk-id form (no
    `markdown_chunk:` prefix) gets normalized back to the full form so
    downstream consumers see one shape."""
    if not answer_text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _VALID_TAG_RE.finditer(answer_text):
        tag = m.group(1)
        if re.fullmatch(r'[0-9a-f]{8,16}', tag):
            tag = f'markdown_chunk:{tag}'
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _build_user_prompt(
    question: str,
    summaries: list[str],
    entities: list[dict],
    edges: list[dict],
    chunk_excerpts: list[dict],
) -> str:
    """Assemble the user prompt for synthesis.

    Output rules go at the TOP so Gemma sees them while constructing the
    answer (instructions seen later are weighted less). Non-citable
    sections are marked inline as 'reference material - do not cite' so
    Gemma can't lift their headers or item names into invented citations.
    """
    parts: list[str] = []

    # Rules FIRST. The two cite-token forms Gemma is allowed to use are
    # named explicitly - this echoes the system prompt but right where
    # the answer-construction happens.
    # NOTE on placeholder syntax: avoid showing `...` inside example
    # citation patterns. Gemma observed pattern-matching `[markdown_chunk:...]`
    # by emitting `[markdown_chunk:138]` style fabricated short numerics.
    # Citations MUST be COPIED VERBATIM from the tags listed below; do not
    # write a generic shape and fill in numbers.
    parts.append(
        '## Rules for your answer\n'
        '- Use ONLY the evidence shown below.\n'
        '- Bracketed tags listed under the section headers are the ONLY '
        'valid citations. Their forms are `[Cn]` (theme number n), '
        '`[E:<exact_entity_id>]`, `[R:<exact_triple>]`, and '
        '`[markdown_chunk:<exact_12_hex_string>]`. **Copy a tag verbatim '
        'from a section below; never substitute or invent the value '
        'after the colon.** A bracketed phrase that is not present '
        'verbatim in the section listings below is invalid.\n'
        '- Each citation goes in its OWN brackets. Write `[C1] [E:foo] '
        '[E:bar]` (three brackets) - NOT `[C1, E:foo, E:bar]` (one '
        'bracket with commas).\n'
        '- DO NOT invent tags. Section headers (e.g. `Themes`, '
        '`Relevant entities`), free-form labels (e.g. `entity list`, '
        '`source`, `evidence`), or paraphrases in brackets are forbidden. '
        'If no real tag fits a claim, leave the claim uncited rather '
        'than invent one.\n'
        '- If the evidence does not answer the question, say so plainly.\n'
    )

    parts.append(f'## Question\n{question}\n')

    if summaries:
        parts.append('## Themes')
        for i, s in enumerate(summaries, 1):
            parts.append(f'`[C{i}]` {s}')
        parts.append('')

    if entities:
        parts.append('## Relevant entities')
        for e in entities[:30]:
            props = e.get('properties') or {}
            name = props.get('canonical_name') or e.get('label', '')
            desc = props.get('description', '')
            etype = e.get('type', '')
            tag = f'[E:{e.get("id", "")}]'
            parts.append(f'`{tag}` {name} ({etype}): {desc[:200]}')
        parts.append('')

    if edges:
        parts.append('## Relationships')
        for e in edges[:40]:
            tag = f'[R:{e["source"]}>{e["type"]}>{e["target"]}]'
            parts.append(f'`{tag}` {e["source"]} --[{e["type"]}]--> {e["target"]}')
        parts.append('')

    if chunk_excerpts:
        parts.append('## Source excerpts')
        for c in chunk_excerpts[:8]:
            parts.append(f'`[{c["id"]}]` {c.get("doc_path")}')
            parts.append(f'> {c.get("text", "")[:500]}')
            parts.append('')

    return '\n'.join(parts)


def _load_json(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _decode_entity_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        props = _load_json(r.get('props'))
        # Promote hoisted top-level columns (community_id, rank) into the
        # properties dict if the SELECT projected them. The trace UI uses
        # these for community-color and rank-size visual encoding.
        if r.get('community_id') is not None and 'community_id' not in props:
            props['community_id'] = r.get('community_id')
        if r.get('rank') is not None and 'rank' not in props:
            props['rank'] = r.get('rank')
        out.append({
            'id': r.get('id'),
            'label': r.get('label'),
            'type': r.get('type'),
            'properties': props,
        })
    return out


def _filter_grounding_by_name_presence(
    per_entity_chunks: dict[str, list[str]],
    per_edge_chunks: list[dict],
    entities_payload: list[dict],
    chunk_text_by_id: dict[str, str],
) -> tuple[dict[str, list[str]], list[dict]]:
    """Drop grounding chunks where the entity's canonical name (or both
    endpoints, for edges) doesn't actually appear in the chunk text.

    Belt-and-suspenders for the ingestion-side strength sort: catches
    cases where the entity extractor picked up an incidental mention
    that shouldn't count as evidence (e.g. a brace-matching code snippet
    grounding the Hydra entity because Hydra was named in a comment).
    """
    name_by_id: dict[str, str] = {}
    for e in entities_payload:
        props = e.get('properties') or {}
        name_by_id[e['id']] = (
            (props.get('canonical_name') or e.get('label') or '').lower()
        )

    def _has(name: str, cid: str) -> bool:
        return bool(name) and name in (chunk_text_by_id.get(cid) or '').lower()

    filtered_entity_chunks = {
        ent: [c for c in chunks if _has(name_by_id.get(ent, ''), c)]
        for ent, chunks in per_entity_chunks.items()
    }
    filtered_entity_chunks = {k: v for k, v in filtered_entity_chunks.items() if v}

    filtered_edge_chunks: list[dict] = []
    for ec in per_edge_chunks:
        sn = name_by_id.get(ec.get('source', ''), '')
        tn = name_by_id.get(ec.get('target', ''), '')
        kept = [c for c in (ec.get('chunk_ids') or [])
                if _has(sn, c) and _has(tn, c)]
        if kept:
            filtered_edge_chunks.append({**ec, 'chunk_ids': kept})

    return filtered_entity_chunks, filtered_edge_chunks


def _cosine(a: list[float], b: list[float]) -> float:
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    # Defensive normalization for producers that don't normalize.
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(-1.0, min(1.0, s / (na * nb)))

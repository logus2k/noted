"""Entity/Relationship persistence layer on top of ArcadeDB.

Responsibility: translate Pydantic Entity/Relationship models into ArcadeDB
vertex/edge upserts via Cypher, and provide a project-scoped replace-all
primitive for atomic rebuilds.

Phase 1B model:
  - Single :Entity vertex label. Vertex property `type` carries the entity
    taxonomy type (run, data_file, concept, ...).
  - Single :RELATES edge label. Edge property `type` carries the relationship
    taxonomy type (produces, contains, ...).
  - `project_ids` list property tracks which projects have scanned each
    entity. Lets filesystem mounts / shared entities stay visible to every
    project that knows them. Global-layer entities (GraphRAG thematic
    layer) carry `project_ids = ['__global__']`.

Atomic rebuild strategy for a project:
  - Remove this project's id from every entity's project_ids list. Delete
    entities left with an empty list (no project still references them).
    Delete edges whose endpoints were deleted.
  - Bulk-upsert the new entity set, appending this project's id to every
    entity's project_ids list (idempotent via de-dup).
  - Bulk-upsert relationships.
  - The server-side transaction makes the swap visible only on commit.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


# Max parameters per batched call. Vertex inserts can chunk large; edge
# inserts need smaller batches because each MERGE has to resolve two
# endpoints via index lookup per row.
_CHUNK_VERTICES = 500
_CHUNK_EDGES = 200


class GraphStorage:
    """Persistence wrapper. Owns the ArcadeDB client and schema bootstrap.

    P3.2: parameterized at construction with `project_id`. All per-KB
    methods read it from `self.project_id` instead of taking it per call.
    Multiple KBs each have their own GraphStorage instance with their
    own project_id; the underlying ArcadeDB client is shared (stateless).
    """

    def __init__(
        self,
        project_id: str | None = None,
        arcadedb_database: str | None = None,
        client: ArcadeDBClient | None = None,
    ):
        # Per-Domain ArcadeDB database. Each Domain owns its own DB inside
        # the shared noted-arcadedb container; entities live there with no
        # cross-Domain mixing. `project_id` is the legacy alias - kept for
        # backward compat with code that reads `self.project_id`. Both
        # values are the same string under the new architecture.
        from app.config import GLOBAL_PROJECT_ID
        db = arcadedb_database or project_id or GLOBAL_PROJECT_ID
        self.arcadedb_database = db
        self.project_id = db  # back-compat alias
        self._c = client or ArcadeDBClient(database=db)
        self._bootstrapped = False

    # ── One-time setup ───────────────────────────────────────────────
    def ensure_ready(self) -> None:
        """Verify connectivity and create schema on first use."""
        if self._bootstrapped:
            return
        if not self._c.ready():
            raise ArcadeDBError('ArcadeDB is not reachable')
        if self._c.databases() == []:
            raise ArcadeDBError('ArcadeDB has no databases configured')
        self._c.ensure_schema()
        self._bootstrapped = True

    # ── Atomic replace for the configured project ───────────────────
    def replace_project_graph(
        self,
        entities: Iterable[Entity],
        relationships: Iterable[Relationship],
        progress_cb=None,
    ) -> dict[str, int]:
        """Atomically replace every vertex/edge for the configured project_id.

        Returns counts of what was written, so callers can log the outcome.

        `progress_cb` is an optional callable `(sub_phase: str, done: int,
        total: int) -> None` invoked between sub-steps so the Monitor can
        show what's happening during the otherwise-silent ~10-15 minute
        bulk-write. Mirrors the callback already wired through
        `add_doc_merge`. Each `progress_cb` call is wrapped in try/except
        so a misbehaving consumer can never break the write.
        """
        self.ensure_ready()
        project_id = self.project_id

        entities = list(entities)
        relationships = list(relationships)

        def _report(sub_phase: str, done: int, total: int) -> None:
            if progress_cb is None:
                return
            try:
                progress_cb(sub_phase, done, total)
            except Exception:
                logger.exception('replace_project_graph progress_cb raised; ignoring')

        phase_t0 = time.perf_counter()
        logger.info('writing.replace_project_graph: start (entities=%d, relationships=%d, project=%s)',
                    len(entities), len(relationships), project_id)

        # 1. Remove this project's id from every entity that lists it.
        #    ArcadeDB Cypher does not support list comprehension syntax yet,
        #    so we use ArcadeDB SQL for the two-step cleanup.
        t0 = time.perf_counter()
        logger.info('writing.replace_project_graph.step1a: SQL strip project_ids — start')
        _report('writing.strip_project_ids', 0, 1)
        self._c.command_sql(
            "UPDATE Entity REMOVE project_ids = :pid WHERE project_ids CONTAINS :pid",
            {'pid': project_id},
        )
        _report('writing.strip_project_ids', 1, 1)
        logger.info('writing.replace_project_graph.step1a: end (%.2fs)', time.perf_counter() - t0)

        # Delete entities whose project_ids list is now empty. DETACH DELETE
        # via Cypher drops incident edges in one shot.
        t0 = time.perf_counter()
        logger.info('writing.replace_project_graph.step1b: DETACH DELETE empty entities — start')
        _report('writing.delete_orphans', 0, 1)
        self._c.command(
            'MATCH (n:Entity) WHERE size(n.project_ids) = 0 DETACH DELETE n',
        )
        _report('writing.delete_orphans', 1, 1)
        logger.info('writing.replace_project_graph.step1b: end (%.2fs)', time.perf_counter() - t0)

        # 2. Bulk-upsert entities, chunked. Hot retrieval properties
        #    (community_id, rank) are promoted from the properties dict
        #    to top-level Entity columns so they can be indexed and queried
        #    without doing a substring match on the JSON blob.
        t0 = time.perf_counter()
        n_chunks_2 = (len(entities) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
        logger.info('writing.replace_project_graph.step2: insert %d entities in %d chunks — start',
                    len(entities), n_chunks_2)
        _report('writing.entities', 0, n_chunks_2)
        n_entities = 0
        for ci, chunk in enumerate(_chunks(entities, _CHUNK_VERTICES), 1):
            ct0 = time.perf_counter()
            rows = []
            for e in chunk:
                # Pop hot fields from properties so they aren't duplicated
                # in properties_json. Caller (research_builder) puts them
                # there during analytics; we hoist them at write time.
                props = dict(e.properties)
                cid = props.pop('community_id', None)
                rank = props.pop('rank', None)
                rows.append({
                    'id': e.id,
                    'type': e.type,
                    'label': e.label,
                    'community_id': cid,
                    'rank': rank,
                    'properties_json': _safe_json(props),
                    'tags_json': _safe_json(e.tags),
                })
            self._c.command(
                '''UNWIND $rows AS row
                   MERGE (n:Entity {id: row.id})
                   SET n.type = row.type,
                       n.label = row.label,
                       n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json,
                       n.tags_json = row.tags_json,
                       n.project_ids = CASE
                         WHEN n.project_ids IS NULL THEN [$pid]
                         WHEN $pid IN n.project_ids THEN n.project_ids
                         ELSE n.project_ids + $pid
                       END''',
                {'rows': rows, 'pid': project_id},
            )
            n_entities += len(chunk)
            _report('writing.entities', ci, n_chunks_2)
            logger.info('writing.replace_project_graph.step2: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_2, len(chunk), time.perf_counter() - ct0)
        logger.info('writing.replace_project_graph.step2: end (%.2fs)', time.perf_counter() - t0)

        # 3. Bulk-upsert relationships. Endpoints must already exist (they
        #    were just written). MERGE on the edge pattern avoids duplicates.
        t0 = time.perf_counter()
        n_chunks_3 = (len(relationships) + _CHUNK_EDGES - 1) // _CHUNK_EDGES
        logger.info('writing.replace_project_graph.step3: insert %d edges in %d chunks — start',
                    len(relationships), n_chunks_3)
        _report('writing.relationships', 0, n_chunks_3)
        n_rels = 0
        for ci, chunk in enumerate(_chunks(relationships, _CHUNK_EDGES), 1):
            ct0 = time.perf_counter()
            rows = [
                {
                    'source': r.source,
                    'target': r.target,
                    'type': r.type,
                    'properties_json': _safe_json(r.properties),
                }
                for r in chunk
            ]
            # CREATE, not MERGE. The prior DETACH DELETE guarantees no
            # existing edges collide; MERGE's existence check is expensive
            # (tens of seconds per 200-row batch in ArcadeDB).
            # Caller is responsible for providing a deduped relationship list.
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (a:Entity {id: row.source})
                   MATCH (b:Entity {id: row.target})
                   CREATE (a)-[e:RELATES]->(b)
                   SET e.type = row.type, e.properties_json = row.properties_json''',
                {'rows': rows},
            )
            n_rels += len(chunk)
            _report('writing.relationships', ci, n_chunks_3)
            logger.info('writing.replace_project_graph.step3: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_3, len(chunk), time.perf_counter() - ct0)
        logger.info('writing.replace_project_graph.step3: end (%.2fs)', time.perf_counter() - t0)

        logger.info(
            'writing.replace_project_graph: complete (%.2fs total) — project=%s wrote %d entities, %d rels',
            time.perf_counter() - phase_t0, project_id, n_entities, n_rels,
        )
        return {'entities': n_entities, 'relationships': n_rels}

    # ── Per-doc incremental ops (P2) ─────────────────────────────────
    def add_doc_merge(
        self,
        doc_entity: Entity,
        chunk_entities: list[Entity],
        chunked_into_rels: list[Relationship],
        thematic_new: list[Entity],
        mention_rels: list[Relationship],
        progress_cb=None,
    ) -> dict[str, int]:
        """Merge a single doc + its chunks + extracted entities into the
        existing graph, idempotent on re-add (doc + chunks are dropped first
        so re-adding the same path replaces cleanly).

        Thematic entity merge semantics:
          - mention_count: existing + new
          - description: keep higher-confidence one
          - mentioned_in_chunks: union (capped 50, new ones first)
          - source_doc_paths: union (capped 20, new path first)
          - aliases: union

        `progress_cb` is an optional callable `(sub_phase: str, done: int,
        total: int) -> None`. When supplied, every batched UNWIND loop
        reports its progress so the caller (research_builder) can promote
        sub-phase fields up to `self.progress` and the KB Monitor can
        render movement during the otherwise-silent ~12 minute writing
        phase. Called freely from the same thread as the writes — no
        synchronization required by the callback.
        """
        self.ensure_ready()
        project_id = self.project_id

        def _report(sub_phase, done, total):
            if progress_cb:
                try:
                    progress_cb(sub_phase, done, total)
                except Exception:
                    # Progress reporting must NEVER break ingestion.
                    pass

        phase_t0 = time.perf_counter()
        logger.info('writing.add_doc_merge: start (doc=%s, chunks=%d, thematic_new=%d, mention_rels=%d)',
                    doc_entity.id, len(chunk_entities), len(thematic_new), len(mention_rels))

        # 1. Drop existing doc + its chunks for this path. Each chunk is
        #    DETACH DELETE'd so its incident mentions edges go too.
        #    We traverse from the doc via chunked_into rather than type-
        #    filtering markdown_chunk + CONTAINS-matching the path, because
        #    ArcadeDB's type index gets stale references after DETACH DELETE
        #    that surface as "Record not found" on subsequent queries.
        t0 = time.perf_counter()
        logger.info('writing.add_doc_merge.step1a: query existing chunks for doc — start')
        existing_chunk_rows = self._c.query(
            '''MATCH (d:Entity {id: $doc_id})-[r:RELATES]->(c:Entity)
               WHERE r.type = "chunked_into"
               RETURN c.id AS id''',
            {'doc_id': doc_entity.id},
        )
        existing_chunk_ids = [r.get('id') for r in existing_chunk_rows if r.get('id')]
        logger.info('writing.add_doc_merge.step1a: end %.2fs (%d existing chunks)',
                    time.perf_counter() - t0, len(existing_chunk_ids))

        if existing_chunk_ids:
            t0 = time.perf_counter()
            logger.info('writing.add_doc_merge.step1b: DETACH DELETE %d existing chunks — start',
                        len(existing_chunk_ids))
            self._c.command(
                'MATCH (c:Entity) WHERE c.id IN $ids DETACH DELETE c',
                {'ids': existing_chunk_ids},
            )
            logger.info('writing.add_doc_merge.step1b: end (%.2fs)', time.perf_counter() - t0)

        # Drop the doc node itself if present (re-add will recreate it).
        t0 = time.perf_counter()
        logger.info('writing.add_doc_merge.step1c: DETACH DELETE doc node — start')
        self._c.command(
            'MATCH (d:Entity {id: $doc_id}) DETACH DELETE d',
            {'doc_id': doc_entity.id},
        )
        logger.info('writing.add_doc_merge.step1c: end (%.2fs)', time.perf_counter() - t0)

        # 2. Insert the new doc + chunks + chunked_into edges using the
        #    same UNWIND pattern as replace_project_graph (CREATE since we
        #    just deleted these ids).
        md_entities = [doc_entity] + list(chunk_entities)
        t0 = time.perf_counter()
        n_chunks_2 = (len(md_entities) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
        logger.info('writing.add_doc_merge.step2: insert %d md entities (doc+chunks) in %d chunks — start',
                    len(md_entities), n_chunks_2)
        for ci, chunk in enumerate(_chunks(md_entities, _CHUNK_VERTICES), 1):
            ct0 = time.perf_counter()
            rows = []
            for e in chunk:
                props = dict(e.properties)
                cid = props.pop('community_id', None)
                rank = props.pop('rank', None)
                rows.append({
                    'id': e.id,
                    'type': e.type,
                    'label': e.label,
                    'community_id': cid,
                    'rank': rank,
                    'properties_json': _safe_json(props),
                    'tags_json': _safe_json(e.tags),
                })
            self._c.command(
                '''UNWIND $rows AS row
                   MERGE (n:Entity {id: row.id})
                   SET n.type = row.type,
                       n.label = row.label,
                       n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json,
                       n.tags_json = row.tags_json,
                       n.project_ids = CASE
                         WHEN n.project_ids IS NULL THEN [$pid]
                         WHEN $pid IN n.project_ids THEN n.project_ids
                         ELSE n.project_ids + $pid
                       END''',
                {'rows': rows, 'pid': project_id},
            )
            _report('writing.chunks_insert', ci, n_chunks_2)
            logger.info('writing.add_doc_merge.step2: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_2, len(chunk), time.perf_counter() - ct0)
        logger.info('writing.add_doc_merge.step2: end (%.2fs)', time.perf_counter() - t0)

        t0 = time.perf_counter()
        n_chunks_2b = (len(chunked_into_rels) + _CHUNK_EDGES - 1) // _CHUNK_EDGES
        logger.info('writing.add_doc_merge.step2b: insert %d chunked_into edges in %d chunks — start',
                    len(chunked_into_rels), n_chunks_2b)
        for ci, chunk in enumerate(_chunks(list(chunked_into_rels), _CHUNK_EDGES), 1):
            ct0 = time.perf_counter()
            rows = [
                {'source': r.source, 'target': r.target, 'type': r.type,
                 'properties_json': _safe_json(r.properties)}
                for r in chunk
            ]
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (a:Entity {id: row.source})
                   MATCH (b:Entity {id: row.target})
                   CREATE (a)-[e:RELATES]->(b)
                   SET e.type = row.type, e.properties_json = row.properties_json''',
                {'rows': rows},
            )
            _report('writing.chunked_into_edges', ci, n_chunks_2b)
            logger.info('writing.add_doc_merge.step2b: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_2b, len(chunk), time.perf_counter() - ct0)
        logger.info('writing.add_doc_merge.step2b: end (%.2fs)', time.perf_counter() - t0)

        # 3. Thematic entity merge: load existing, merge in Python, write
        #    back. Avoids fragile Cypher list ops.
        new_by_id = {e.id: e for e in thematic_new}
        if new_by_id:
            t0 = time.perf_counter()
            logger.info('writing.add_doc_merge.step3a: load %d existing thematic entities — start',
                        len(new_by_id))
            existing_rows = self._c.query(
                '''MATCH (n:Entity)
                   WHERE $pid IN n.project_ids AND n.id IN $ids
                   RETURN n.id AS id, n.type AS type, n.label AS label,
                          n.community_id AS community_id, n.rank AS rank,
                          n.properties_json AS props, n.tags_json AS tags''',
                {'pid': project_id, 'ids': list(new_by_id.keys())},
            )
            existing_by_id: dict[str, dict] = {}
            for row in existing_rows:
                existing_by_id[row['id']] = {
                    'props': _load_json_or_dict(row.get('props')),
                    'community_id': row.get('community_id'),
                    'rank': row.get('rank'),
                    'tags': _load_json_or_list(row.get('tags')),
                }
            logger.info('writing.add_doc_merge.step3a: end %.2fs (%d existing matched)',
                        time.perf_counter() - t0, len(existing_by_id))

            merged_rows = []
            for ent_id, new_ent in new_by_id.items():
                old = existing_by_id.get(ent_id)
                if old is None:
                    # New entity. Same shape as full-build write.
                    props = dict(new_ent.properties)
                    cid = props.pop('community_id', None)
                    rank = props.pop('rank', None)
                    merged_rows.append({
                        'id': ent_id,
                        'type': new_ent.type,
                        'label': new_ent.label,
                        'community_id': cid,
                        'rank': rank,
                        'properties_json': _safe_json(props),
                        'tags_json': _safe_json(new_ent.tags),
                    })
                    continue
                # Merge into existing properties.
                old_props = old['props']
                new_props = dict(new_ent.properties)
                # Higher confidence wins for description.
                old_conf = float(old_props.get('extraction_confidence') or 0)
                new_conf = float(new_props.get('extraction_confidence') or 0)
                if new_conf > old_conf and new_props.get('description'):
                    old_props['description'] = new_props['description']
                    old_props['extraction_confidence'] = new_conf
                # Aliases: union (preserve order, dedupe).
                old_aliases = old_props.get('aliases') or []
                for a in (new_props.get('aliases') or []):
                    if a and a not in old_aliases:
                        old_aliases.append(a)
                old_props['aliases'] = old_aliases
                # mentioned_in_chunks: prepend new (strength-sorted), dedupe,
                # cap at 50.
                old_mc = old_props.get('mentioned_in_chunks') or []
                new_mc = new_props.get('mentioned_in_chunks') or []
                merged_mc: list[str] = []
                seen: set[str] = set()
                for cid in list(new_mc) + list(old_mc):
                    if cid and cid not in seen:
                        merged_mc.append(cid)
                        seen.add(cid)
                        if len(merged_mc) >= 50:
                            break
                old_props['mentioned_in_chunks'] = merged_mc
                # mention_count derived from the deduped chunk list so re-add
                # of the same doc is idempotent (was double-counting because
                # the previous extraction's count was already in old_props).
                old_props['mention_count'] = len(merged_mc)
                # source_doc_paths: prepend new, dedupe, cap 20.
                old_sp = old_props.get('source_doc_paths') or []
                new_sp = new_props.get('source_doc_paths') or []
                merged_sp: list[str] = []
                seen_sp: set[str] = set()
                for p in list(new_sp) + list(old_sp):
                    if p and p not in seen_sp:
                        merged_sp.append(p)
                        seen_sp.add(p)
                        if len(merged_sp) >= 20:
                            break
                old_props['source_doc_paths'] = merged_sp
                # Keep existing community_id/rank (analytics will refresh
                # them on the next recluster). Strip from props if present
                # so they don't shadow the column values.
                cid = old.get('community_id')
                rank = old.get('rank')
                old_props.pop('community_id', None)
                old_props.pop('rank', None)
                merged_rows.append({
                    'id': ent_id,
                    'type': new_ent.type,
                    'label': new_ent.label,
                    'community_id': cid,
                    'rank': rank,
                    'properties_json': _safe_json(old_props),
                    'tags_json': _safe_json(new_ent.tags or old.get('tags') or []),
                })

            t0 = time.perf_counter()
            n_chunks_3b = (len(merged_rows) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
            logger.info('writing.add_doc_merge.step3b: write %d merged thematic entities in %d chunks — start',
                        len(merged_rows), n_chunks_3b)
            for ci, chunk in enumerate(_chunks(merged_rows, _CHUNK_VERTICES), 1):
                ct0 = time.perf_counter()
                self._c.command(
                    '''UNWIND $rows AS row
                       MERGE (n:Entity {id: row.id})
                       SET n.type = row.type,
                           n.label = row.label,
                           n.community_id = row.community_id,
                           n.rank = row.rank,
                           n.properties_json = row.properties_json,
                           n.tags_json = row.tags_json,
                           n.project_ids = CASE
                             WHEN n.project_ids IS NULL THEN [$pid]
                             WHEN $pid IN n.project_ids THEN n.project_ids
                             ELSE n.project_ids + $pid
                           END''',
                    {'rows': chunk, 'pid': project_id},
                )
                _report('writing.thematic_merge', ci, n_chunks_3b)
                logger.info('writing.add_doc_merge.step3b: chunk %d/%d (%d rows) %.2fs',
                            ci, n_chunks_3b, len(chunk), time.perf_counter() - ct0)
            logger.info('writing.add_doc_merge.step3b: end (%.2fs)', time.perf_counter() - t0)

        # 4. CREATE mentions edges. Chunk endpoints are brand new (we just
        #    inserted them above) so duplicates aren't possible.
        n_mentions = 0
        t0 = time.perf_counter()
        n_chunks_4 = (len(mention_rels) + _CHUNK_EDGES - 1) // _CHUNK_EDGES
        logger.info('writing.add_doc_merge.step4: insert %d mentions edges in %d chunks — start',
                    len(mention_rels), n_chunks_4)
        for ci, chunk in enumerate(_chunks(list(mention_rels), _CHUNK_EDGES), 1):
            ct0 = time.perf_counter()
            rows = [
                {'source': r.source, 'target': r.target, 'type': r.type,
                 'properties_json': _safe_json(r.properties)}
                for r in chunk
            ]
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (a:Entity {id: row.source})
                   MATCH (b:Entity {id: row.target})
                   CREATE (a)-[e:RELATES]->(b)
                   SET e.type = row.type, e.properties_json = row.properties_json''',
                {'rows': rows},
            )
            n_mentions += len(rows)
            _report('writing.mention_edges', ci, n_chunks_4)
            logger.info('writing.add_doc_merge.step4: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_4, len(chunk), time.perf_counter() - ct0)
        logger.info('writing.add_doc_merge.step4: end (%.2fs)', time.perf_counter() - t0)
        logger.info('writing.add_doc_merge: complete (%.2fs total) — %d entities, %d mentions, %d chunks',
                    time.perf_counter() - phase_t0, len(new_by_id), n_mentions, len(chunk_entities))

        return {
            'entities_upserted': len(new_by_id),
            'mentions_written': n_mentions,
            'chunks_written': len(chunk_entities),
            'chunks_replaced': len(existing_chunk_ids),
        }

    # ── GraphBatch v2 path (Phase 2 of kb_import_export.md) ─────────────
    def add_doc_merge_v2(
        self,
        doc_entity: Entity,
        chunk_entities: list[Entity],
        chunked_into_rels: list[Relationship],
        thematic_new: list[Entity],
        mention_rels: list[Relationship],
        progress_cb=None,
    ) -> dict[str, int]:
        """Same contract as `add_doc_merge` but the bulk vertex+edge insert
        goes through ArcadeDB's GraphBatch HTTP endpoint
        (`POST /api/v1/batch/<db>`). For a typical 700-chunk PDF this drops
        the ~12-15 min mention-edge step to ~30s.

        Hybrid strategy because GraphBatch is CREATE-only:
          - Chunks (always brand new — DETACH DELETE happens first) and the
            doc node go in via GraphBatch.
          - Thematic entities are split: NEW ones (not yet in the graph)
            via GraphBatch; EXISTING ones get a small UNWIND UPDATE batch
            (Cypher) that merges their property dicts in place.
          - Edges (chunked_into + mentions) go in via GraphBatch with
            `@from`/`@to` resolved by `@id` for new vertices in the same
            batch and by RID string for pre-existing ones (probed working
            in v26.3.2).
        """
        self.ensure_ready()
        project_id = self.project_id

        phase_t0 = time.perf_counter()
        logger.info('writing.add_doc_merge_v2: start (doc=%s, chunks=%d, thematic_new=%d, mention_rels=%d)',
                    doc_entity.id, len(chunk_entities), len(thematic_new), len(mention_rels))

        # ── Step 1: drop existing chunks + doc node (same as legacy path).
        #            Cypher is fine here — these are small DETACH DELETE ops
        #            that compile to LSM page erases. The slow MATCH-heavy
        #            work is in steps 2-4 which GraphBatch replaces.
        t0 = time.perf_counter()
        existing_chunk_rows = self._c.query(
            '''MATCH (d:Entity {id: $doc_id})-[r:RELATES]->(c:Entity)
               WHERE r.type = "chunked_into"
               RETURN c.id AS id''',
            {'doc_id': doc_entity.id},
        )
        existing_chunk_ids = [r.get('id') for r in existing_chunk_rows if r.get('id')]
        if existing_chunk_ids:
            self._c.command(
                'MATCH (c:Entity) WHERE c.id IN $ids DETACH DELETE c',
                {'ids': existing_chunk_ids},
            )
        self._c.command(
            'MATCH (d:Entity {id: $doc_id}) DETACH DELETE d',
            {'doc_id': doc_entity.id},
        )
        logger.info('writing.add_doc_merge_v2.step1: dropped %d existing chunks + doc node (%.2fs)',
                    len(existing_chunk_ids), time.perf_counter() - t0)

        # ── Step 2: pre-fetch RIDs for thematic entities that already
        #            exist. One bulk query against the unique `Entity[id]`
        #            index. Returns `{id → "#1:967834"}` for entities
        #            present in the graph; absent ones are new.
        t0 = time.perf_counter()
        new_by_id: dict[str, Entity] = {e.id: e for e in thematic_new}
        existing_rid_map: dict[str, str] = {}
        existing_props_by_id: dict[str, dict] = {}
        if new_by_id:
            existing_rows = self._c.query(
                '''MATCH (n:Entity)
                   WHERE $pid IN n.project_ids AND n.id IN $ids
                   RETURN n.id AS id, n.@rid AS rid,
                          n.properties_json AS props, n.tags_json AS tags,
                          n.community_id AS community_id, n.rank AS rank,
                          n.label AS label, n.type AS type''',
                {'pid': project_id, 'ids': list(new_by_id.keys())},
            )
            for row in existing_rows:
                eid = row.get('id')
                rid = row.get('rid')
                if eid and rid:
                    existing_rid_map[eid] = rid
                    existing_props_by_id[eid] = {
                        'props': _load_json_or_dict(row.get('props')),
                        'tags': _load_json_or_list(row.get('tags')),
                        'community_id': row.get('community_id'),
                        'rank': row.get('rank'),
                        'label': row.get('label'),
                        'type': row.get('type'),
                    }
        logger.info('writing.add_doc_merge_v2.step2: pre-fetched %d existing RIDs (%.2fs)',
                    len(existing_rid_map), time.perf_counter() - t0)

        # ── Step 3: build NDJSON for GraphBatch — doc_node + all new
        #            chunks + truly-new thematic entities + all edges.
        t0 = time.perf_counter()
        ndjson_lines: list[str] = []

        def _vertex_line(e: Entity) -> str:
            props = dict(e.properties)
            cid = props.pop('community_id', None)
            rank = props.pop('rank', None)
            row: dict = {
                '@type': 'vertex',
                '@class': 'Entity',
                '@id': e.id,
                'id': e.id,
                'type': e.type,
                'label': e.label,
                'properties_json': _safe_json(props),
                'tags_json': _safe_json(e.tags or []),
                'project_ids': [project_id],
            }
            if cid is not None:
                row['community_id'] = cid
            if rank is not None:
                row['rank'] = rank
            return json.dumps(row, ensure_ascii=False)

        ndjson_lines.append(_vertex_line(doc_entity))
        for ce in chunk_entities:
            ndjson_lines.append(_vertex_line(ce))
        for e in thematic_new:
            if e.id in existing_rid_map:
                continue  # handled by the property-merge UPDATE pass below
            ndjson_lines.append(_vertex_line(e))

        def _resolve_endpoint(node_id: str) -> str:
            """Edge endpoint — RID string for pre-existing thematic
            entity, otherwise the @id (in-batch reference)."""
            return existing_rid_map.get(node_id, node_id)

        for r in chunked_into_rels:
            ndjson_lines.append(json.dumps({
                '@type': 'edge',
                '@class': 'RELATES',
                '@from': _resolve_endpoint(r.source),
                '@to': _resolve_endpoint(r.target),
                'type': r.type,
                'properties_json': _safe_json(r.properties),
            }, ensure_ascii=False))
        for r in mention_rels:
            ndjson_lines.append(json.dumps({
                '@type': 'edge',
                '@class': 'RELATES',
                '@from': _resolve_endpoint(r.source),
                '@to': _resolve_endpoint(r.target),
                'type': r.type,
                'properties_json': _safe_json(r.properties),
            }, ensure_ascii=False))
        logger.info('writing.add_doc_merge_v2.step3: built %d NDJSON lines (%.2fs)',
                    len(ndjson_lines), time.perf_counter() - t0)

        # ── Step 4: single GraphBatch POST. Single op so we surface
        #             0/1 then 1/1 around it; the UI shows it as the
        #             write hitting the wire.
        if progress_cb:
            try: progress_cb('writing.graphbatch_post', 0, 1)
            except Exception: pass
        t0 = time.perf_counter()
        result = self._c.graphbatch_post(ndjson_lines, light_edges=False)
        if progress_cb:
            try: progress_cb('writing.graphbatch_post', 1, 1)
            except Exception: pass
        logger.info('writing.add_doc_merge_v2.step4: GraphBatch POST verticesCreated=%s edgesCreated=%s server_elapsed=%sms (%.2fs wall)',
                    result.get('verticesCreated'), result.get('edgesCreated'),
                    result.get('elapsedMs'), time.perf_counter() - t0)

        # ── Step 5: property-merge UPDATE for thematic entities that
        #            already existed. Same merge semantics as legacy
        #            add_doc_merge step 3 (description / aliases /
        #            mentioned_in_chunks / source_doc_paths / mention_count).
        t0 = time.perf_counter()
        merged_rows: list[dict] = []
        for ent_id, new_ent in new_by_id.items():
            old = existing_props_by_id.get(ent_id)
            if old is None:
                continue  # truly new — already inserted via GraphBatch
            old_props = old['props']
            new_props = dict(new_ent.properties)
            old_conf = float(old_props.get('extraction_confidence') or 0)
            new_conf = float(new_props.get('extraction_confidence') or 0)
            if new_conf > old_conf and new_props.get('description'):
                old_props['description'] = new_props['description']
                old_props['extraction_confidence'] = new_conf
            old_aliases = old_props.get('aliases') or []
            for a in (new_props.get('aliases') or []):
                if a and a not in old_aliases:
                    old_aliases.append(a)
            old_props['aliases'] = old_aliases
            old_mc = old_props.get('mentioned_in_chunks') or []
            new_mc = new_props.get('mentioned_in_chunks') or []
            merged_mc: list[str] = []
            seen: set[str] = set()
            for cid in list(new_mc) + list(old_mc):
                if cid and cid not in seen:
                    merged_mc.append(cid)
                    seen.add(cid)
                    if len(merged_mc) >= 50:
                        break
            old_props['mentioned_in_chunks'] = merged_mc
            old_props['mention_count'] = len(merged_mc)
            old_sp = old_props.get('source_doc_paths') or []
            new_sp = new_props.get('source_doc_paths') or []
            merged_sp: list[str] = []
            seen_sp: set[str] = set()
            for p in list(new_sp) + list(old_sp):
                if p and p not in seen_sp:
                    merged_sp.append(p)
                    seen_sp.add(p)
                    if len(merged_sp) >= 20:
                        break
            old_props['source_doc_paths'] = merged_sp
            old_props.pop('community_id', None)
            old_props.pop('rank', None)
            merged_rows.append({
                'id': ent_id,
                'properties_json': _safe_json(old_props),
                'tags_json': _safe_json(new_ent.tags or old.get('tags') or []),
                'label': new_ent.label,
            })

        if merged_rows:
            n_chunks_5 = (len(merged_rows) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
            for ci, chunk in enumerate(_chunks(merged_rows, _CHUNK_VERTICES), 1):
                self._c.command(
                    '''UNWIND $rows AS row
                       MATCH (n:Entity {id: row.id})
                       SET n.properties_json = row.properties_json,
                           n.tags_json = row.tags_json,
                           n.label = row.label''',
                    {'rows': chunk},
                )
                if progress_cb:
                    try: progress_cb('writing.thematic_merge', ci, n_chunks_5)
                    except Exception: pass
        logger.info('writing.add_doc_merge_v2.step5: property-merged %d existing entities (%.2fs)',
                    len(merged_rows), time.perf_counter() - t0)

        n_mentions = len(mention_rels)
        n_truly_new = len(new_by_id) - len(existing_rid_map)
        logger.info('writing.add_doc_merge_v2: complete (%.2fs total) — %d new entities, %d merged, %d mentions, %d chunks',
                    time.perf_counter() - phase_t0,
                    n_truly_new, len(merged_rows), n_mentions, len(chunk_entities))

        return {
            'entities_upserted': len(new_by_id),
            'mentions_written': n_mentions,
            'chunks_written': len(chunk_entities),
            'chunks_replaced': len(existing_chunk_ids),
        }

    def remove_doc_cleanup(self, doc_path: str) -> dict:
        """Delete the markdown_doc for `doc_path`, all its markdown_chunks,
        and clean up thematic entities so:
          - doc_path is removed from `source_doc_paths`
          - this doc's chunk_ids are removed from `mentioned_in_chunks`
          - entities whose source_doc_paths becomes empty are DETACH DELETE'd
        Returns counts + the lists of deleted/updated entity ids so the
        caller can refresh ChromaDB caches.
        """
        self.ensure_ready()
        project_id = self.project_id

        # 1. Resolve the doc id + collect its chunk ids by traversing
        #    chunked_into from the doc node (avoids relying on the
        #    markdown_chunk type index, which can hold stale references
        #    after recent DETACH DELETE ops).
        doc_id = f'markdown_doc:{doc_path}'
        chunk_rows = self._c.query(
            '''MATCH (d:Entity {id: $doc_id})-[r:RELATES]->(c:Entity)
               WHERE r.type = "chunked_into"
               RETURN c.id AS id''',
            {'doc_id': doc_id},
        )
        chunk_ids = [r.get('id') for r in chunk_rows if r.get('id')]

        # 2. Find every thematic entity that references this doc (cheaper
        #    than scanning all thematic entities). properties_json CONTAINS
        #    is a substring filter; safe because doc paths are unique enough
        #    that false positives won't survive the in-memory check below.
        path_marker = f'"{doc_path}"'
        ent_rows = self._c.query(
            '''MATCH (n:Entity)
               WHERE $pid IN n.project_ids
                 AND n.type IN ["concept", "person", "organization", "term"]
                 AND n.properties_json CONTAINS $marker
               RETURN n.id AS id, n.type AS type, n.label AS label,
                      n.community_id AS community_id, n.rank AS rank,
                      n.properties_json AS props, n.tags_json AS tags''',
            {'pid': project_id, 'marker': path_marker},
        )

        deleted_ids: list[str] = []
        updated_rows: list[dict] = []
        chunk_id_set = set(chunk_ids)
        for row in ent_rows:
            props = _load_json_or_dict(row.get('props'))
            sp = props.get('source_doc_paths') or []
            if doc_path not in sp:
                continue  # false positive from CONTAINS
            sp = [p for p in sp if p != doc_path]
            mc = props.get('mentioned_in_chunks') or []
            mc = [c for c in mc if c not in chunk_id_set]
            if not sp:
                deleted_ids.append(row['id'])
                continue
            props['source_doc_paths'] = sp
            props['mentioned_in_chunks'] = mc
            # Strip hoisted columns from props before re-serializing.
            cid = row.get('community_id')
            if 'community_id' in props:
                cid = props.pop('community_id', cid)
            rank = row.get('rank')
            if 'rank' in props:
                rank = props.pop('rank', rank)
            updated_rows.append({
                'id': row['id'],
                'type': row['type'],
                'label': row['label'],
                'community_id': cid,
                'rank': rank,
                'properties_json': _safe_json(props),
                'tags_json': row.get('tags') or '[]',
            })

        # 3. Apply updates (re-serialize properties_json).
        for chunk in _chunks(updated_rows, _CHUNK_VERTICES):
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (n:Entity {id: row.id})
                   SET n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json,
                       n.tags_json = row.tags_json''',
                {'rows': chunk},
            )

        # 4. Delete entities whose source_doc_paths is now empty.
        if deleted_ids:
            for chunk in _chunks(deleted_ids, _CHUNK_VERTICES):
                self._c.command(
                    'MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n',
                    {'ids': chunk},
                )

        # 5. Delete chunks (DETACH DELETE drops mentions + chunked_into).
        if chunk_ids:
            for chunk in _chunks(chunk_ids, _CHUNK_VERTICES):
                self._c.command(
                    'MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n',
                    {'ids': chunk},
                )

        # 6. Delete the doc node itself. Check existence first (DETACH
        #    DELETE + RETURN may not be supported by ArcadeDB's Cypher
        #    subset; simpler to query then delete).
        check = self._c.query(
            'MATCH (d:Entity {id: $doc_id}) RETURN d.id AS id LIMIT 1',
            {'doc_id': doc_id},
        )
        doc_deleted = bool(check)
        if doc_deleted:
            self._c.command(
                'MATCH (d:Entity {id: $doc_id}) DETACH DELETE d',
                {'doc_id': doc_id},
            )

        return {
            'doc_deleted': doc_deleted,
            'chunks_deleted': len(chunk_ids),
            'deleted_entity_ids': deleted_ids,
            'updated_entity_ids': [r['id'] for r in updated_rows],
        }

    # ── Recluster (analytics-only) primitives ────────────────────────
    def load_thematic_entities(
        self, ids: list[str] | None = None,
    ) -> list[Entity]:
        """Load every (or a specified subset of) thematic entity in the
        project as in-memory Entity objects. properties hot columns
        (community_id, rank) are promoted into the properties dict so the
        builder's analytics pipeline sees the same shape it produces."""
        self.ensure_ready()
        project_id = self.project_id
        if ids is not None and not ids:
            return []
        if ids is None:
            rows = self._c.query(
                '''MATCH (n:Entity)
                   WHERE $pid IN n.project_ids
                     AND n.type IN ["concept", "person", "organization", "term"]
                   RETURN n.id AS id, n.type AS type, n.label AS label,
                          n.community_id AS community_id, n.rank AS rank,
                          n.properties_json AS props, n.tags_json AS tags''',
                {'pid': project_id},
            )
        else:
            rows = self._c.query(
                '''MATCH (n:Entity)
                   WHERE $pid IN n.project_ids AND n.id IN $ids
                   RETURN n.id AS id, n.type AS type, n.label AS label,
                          n.community_id AS community_id, n.rank AS rank,
                          n.properties_json AS props, n.tags_json AS tags''',
                {'pid': project_id, 'ids': ids},
            )
        out: list[Entity] = []
        for r in rows:
            props = _load_json_or_dict(r.get('props'))
            if r.get('community_id') is not None and 'community_id' not in props:
                props['community_id'] = r.get('community_id')
            if r.get('rank') is not None and 'rank' not in props:
                props['rank'] = r.get('rank')
            out.append(Entity(
                id=r.get('id'),
                type=r.get('type'),
                label=r.get('label'),
                properties=props,
                tags=_load_json_or_list(r.get('tags')),
            ))
        return out

    def load_md_layer(
        self,
    ) -> tuple[list[Entity], list[Relationship], list[Relationship]]:
        """Load markdown_doc + markdown_chunk entities and their
        chunked_into + mentions edges. Used by recluster to rebuild the
        analytics subgraph without re-scanning disk."""
        self.ensure_ready()
        project_id = self.project_id
        node_rows = self._c.query(
            '''MATCH (n:Entity)
               WHERE $pid IN n.project_ids
                 AND n.type IN ["markdown_doc", "markdown_chunk"]
               RETURN n.id AS id, n.type AS type, n.label AS label,
                      n.properties_json AS props''',
            {'pid': project_id},
        )
        md_entities = [
            Entity(
                id=r.get('id'),
                type=r.get('type'),
                label=r.get('label'),
                properties=_load_json_or_dict(r.get('props')),
            )
            for r in node_rows
        ]
        edge_rows = self._c.query(
            '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
               WHERE $pid IN a.project_ids AND $pid IN b.project_ids
                 AND r.type IN ["chunked_into", "mentions"]
               RETURN a.id AS source, b.id AS target, r.type AS type,
                      r.properties_json AS props''',
            {'pid': project_id},
        )
        mentions: list[Relationship] = []
        chunked: list[Relationship] = []
        for r in edge_rows:
            rel = Relationship(
                source=r.get('source'),
                target=r.get('target'),
                type=r.get('type'),
                properties=_load_json_or_dict(r.get('props')),
            )
            if rel.type == 'mentions':
                mentions.append(rel)
            else:
                chunked.append(rel)
        return md_entities, mentions, chunked

    def replace_analytics_layer(
        self,
        thematic_entities: list[Entity],
        community_entities: list[Entity],
        member_of_rels: list[Relationship],
        summary_entities: list[Entity],
        summary_rels: list[Relationship],
        sameas_rels: list[Relationship],
        similar_rels: list[Relationship],
        progress_cb=None,
    ) -> dict[str, int]:
        """Atomically refresh the analytics layer.

        Drops old community + community_summary entities (and their
        member_of / summarizes / sameAs / similar_to edges via DETACH DELETE
        on the endpoints), then writes new ones. Updates rank + community_id
        + properties_json on existing thematic entities (where the analytics
        pass mutated them in place).

        `progress_cb(sub_phase, done, total)` is called from each chunked
        UNWIND loop so the orchestrator (research_builder.recluster) can
        promote sub-phase fields up to `self.progress`. Without it, the
        UI shows `phase: writing` for ~80 minutes with no movement during
        the analytics-edge insert loop."""
        self.ensure_ready()
        project_id = self.project_id

        def _report(sub_phase, done, total):
            if progress_cb:
                try:
                    progress_cb(sub_phase, done, total)
                except Exception:
                    pass

        # Per-step timing so a writing-phase hang shows the exact culprit
        # in the noted-graph logs (instead of a 30+ min silence after the
        # `summarizing -> writing` line). Each `step start` MUST be paired
        # with a `step end`; if start appears without end, that's the hang.
        phase_t0 = time.perf_counter()
        logger.info('writing.replace_analytics_layer: start (thematic=%d, communities=%d, summaries=%d, member_of=%d, summary_rels=%d, sameas=%d, similar=%d)',
                    len(thematic_entities), len(community_entities), len(summary_entities),
                    len(member_of_rels), len(summary_rels), len(sameas_rels), len(similar_rels))

        # Phase 0 instrumentation: per-step durations collected here, emitted
        # as one summary line at the end and returned to the caller so
        # research_builder can stash them on self.progress for /status.
        step_t: dict[str, float] = {}

        # 1. Drop old communities + community_summary nodes (DETACH DELETE
        #    removes member_of / summarizes edges automatically). sameAs +
        #    similar_to edges connect thematic entities directly so we drop
        #    those by edge type.
        t0 = time.perf_counter()
        logger.info('writing.step1a: drop old community/community_summary nodes — start')
        self._c.command(
            '''MATCH (n:Entity)
               WHERE $pid IN n.project_ids
                 AND n.type IN ["community", "community_summary"]
               DETACH DELETE n''',
            {'pid': project_id},
        )
        step_t['step1a_drop_communities'] = time.perf_counter() - t0
        logger.info('writing.step1a: end (%.2fs)', step_t['step1a_drop_communities'])

        # step1b: instead of unconditionally dropping ALL sameAs/similar_to
        # edges (the historical behavior — wasteful when most edges are
        # stable across reclusters), DIFF the existing edge set against
        # the freshly-computed one and only DELETE removals + CREATE
        # additions (Phase 5 of the scalability refactor, 2026-05-13).
        #
        # Property drift (e.g. cosine recomputed slightly differently for
        # the same pair) is handled correctly: a pair that appears in
        # both old and new with the *same* (source, target, type) key
        # keeps its existing edge — properties don't get updated. This
        # is acceptable because sameAs ratio + similar_to cosine depend
        # only on entity names/descriptions, which are stable across
        # reclusters of the same corpus. If entity descriptions DO
        # change, the next Full Rebuild propagates fresh properties.
        t0 = time.perf_counter()
        new_keys: set[tuple[str, str, str]] = {
            (r.source, r.target, r.type)
            for r in sameas_rels + similar_rels
        }
        logger.info(
            'writing.step1b: edge-set diff — start (new analytics edges to consider: %d unique keys)',
            len(new_keys),
        )
        # Read existing analytics-edge keys for this project.
        existing_rows = self._c.query(
            '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
               WHERE $pid IN a.project_ids
                 AND $pid IN b.project_ids
                 AND r.type IN ["sameAs", "similar_to"]
               RETURN a.id AS source, b.id AS target, r.type AS type''',
            {'pid': project_id},
        ) or []
        existing_keys: set[tuple[str, str, str]] = {
            (row['source'], row['target'], row['type'])
            for row in existing_rows
        }
        keys_to_delete = existing_keys - new_keys
        keys_to_create_set = new_keys - existing_keys
        logger.info(
            'writing.step1b: diff: %d existing, %d new, %d to delete, %d to create',
            len(existing_keys), len(new_keys), len(keys_to_delete),
            len(keys_to_create_set),
        )
        # Delete only the removed analytics edges. Chunked UNWIND keeps
        # ArcadeDB transactions bounded.
        if keys_to_delete:
            del_rows = [{'source': s, 'target': t, 'type': ty}
                        for (s, t, ty) in keys_to_delete]
            n_chunks_del = (len(del_rows) + _CHUNK_EDGES - 1) // _CHUNK_EDGES
            for ci, chunk in enumerate(_chunks(del_rows, _CHUNK_EDGES), 1):
                ct0 = time.perf_counter()
                self._c.command(
                    '''UNWIND $rows AS row
                       MATCH (a:Entity {id: row.source})-[r:RELATES {type: row.type}]->(b:Entity {id: row.target})
                       DELETE r''',
                    {'rows': chunk},
                )
                logger.info('writing.step1b.delete: chunk %d/%d (%d rows) %.2fs',
                            ci, n_chunks_del, len(chunk), time.perf_counter() - ct0)
        step_t['step1b_drop_analytics_edges'] = time.perf_counter() - t0
        logger.info('writing.step1b: end (%.2fs)', step_t['step1b_drop_analytics_edges'])
        # Cache the create-set so step4 knows which sameAs+similar edges to skip.
        self._sameas_similar_to_skip_keys = existing_keys & new_keys

        # 2. Update thematic entities with refreshed rank + community_id.
        rows = []
        for e in thematic_entities:
            props = dict(e.properties)
            cid = props.pop('community_id', None)
            rank = props.pop('rank', None)
            rows.append({
                'id': e.id,
                'community_id': cid,
                'rank': rank,
                'properties_json': _safe_json(props),
            })
        t0 = time.perf_counter()
        n_chunks_2 = (len(rows) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
        logger.info('writing.step2: update %d thematic entities in %d chunks — start', len(rows), n_chunks_2)
        for ci, chunk in enumerate(_chunks(rows, _CHUNK_VERTICES), 1):
            ct0 = time.perf_counter()
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (n:Entity {id: row.id})
                   SET n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json''',
                {'rows': chunk},
            )
            _report('writing.thematic_update', ci, n_chunks_2)
            logger.info('writing.step2: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_2, len(chunk), time.perf_counter() - ct0)
        step_t['step2_thematic_update'] = time.perf_counter() - t0
        logger.info('writing.step2: end (%.2fs)', step_t['step2_thematic_update'])

        # 3. Insert new community + community_summary nodes.
        new_nodes = list(community_entities) + list(summary_entities)
        t0 = time.perf_counter()
        n_chunks_3 = (len(new_nodes) + _CHUNK_VERTICES - 1) // _CHUNK_VERTICES
        logger.info('writing.step3: insert %d community/summary nodes in %d chunks — start',
                    len(new_nodes), n_chunks_3)
        for ci, chunk in enumerate(_chunks(new_nodes, _CHUNK_VERTICES), 1):
            ct0 = time.perf_counter()
            node_rows = []
            for e in chunk:
                props = dict(e.properties)
                cid = props.pop('community_id', None)
                rank = props.pop('rank', None)
                node_rows.append({
                    'id': e.id,
                    'type': e.type,
                    'label': e.label,
                    'community_id': cid,
                    'rank': rank,
                    'properties_json': _safe_json(props),
                    'tags_json': _safe_json(e.tags),
                })
            self._c.command(
                '''UNWIND $rows AS row
                   MERGE (n:Entity {id: row.id})
                   SET n.type = row.type,
                       n.label = row.label,
                       n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json,
                       n.tags_json = row.tags_json,
                       n.project_ids = CASE
                         WHEN n.project_ids IS NULL THEN [$pid]
                         WHEN $pid IN n.project_ids THEN n.project_ids
                         ELSE n.project_ids + $pid
                       END''',
                {'rows': node_rows, 'pid': project_id},
            )
            _report('writing.community_nodes', ci, n_chunks_3)
            logger.info('writing.step3: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_3, len(chunk), time.perf_counter() - ct0)
        step_t['step3_community_nodes'] = time.perf_counter() - t0
        logger.info('writing.step3: end (%.2fs)', step_t['step3_community_nodes'])

        # 4. Insert new edges (member_of, summarizes, sameAs, similar_to).
        # Phase 5 (edge-set diff): sameAs + similar_to edges whose
        # (source, target, type) already exists in the graph (from step1b's
        # diff) are skipped here. member_of + summary edges are always
        # written because their endpoint nodes were just (re-)inserted
        # in step3 by way of the community wipe in step1a.
        skip = getattr(self, '_sameas_similar_to_skip_keys', set()) or set()
        kept_sameas = [r for r in sameas_rels if (r.source, r.target, r.type) not in skip]
        kept_similar = [r for r in similar_rels if (r.source, r.target, r.type) not in skip]
        if skip:
            logger.info(
                'writing.step4: edge-set diff kept %d/%d sameAs + %d/%d similar_to '
                '(skipped %d already-present)',
                len(kept_sameas), len(sameas_rels),
                len(kept_similar), len(similar_rels),
                len(sameas_rels) + len(similar_rels) - len(kept_sameas) - len(kept_similar),
            )
        all_new_edges = (
            list(member_of_rels) + list(summary_rels)
            + kept_sameas + kept_similar
        )
        n_edges = 0
        t0 = time.perf_counter()
        n_chunks_4 = (len(all_new_edges) + _CHUNK_EDGES - 1) // _CHUNK_EDGES
        logger.info('writing.step4: insert %d analytics edges in %d chunks — start',
                    len(all_new_edges), n_chunks_4)
        for ci, chunk in enumerate(_chunks(all_new_edges, _CHUNK_EDGES), 1):
            ct0 = time.perf_counter()
            edge_rows = [
                {'source': r.source, 'target': r.target, 'type': r.type,
                 'properties_json': _safe_json(r.properties)}
                for r in chunk
            ]
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (a:Entity {id: row.source})
                   MATCH (b:Entity {id: row.target})
                   CREATE (a)-[e:RELATES]->(b)
                   SET e.type = row.type, e.properties_json = row.properties_json''',
                {'rows': edge_rows},
            )
            n_edges += len(edge_rows)
            _report('writing.analytics_edges', ci, n_chunks_4)
            logger.info('writing.step4: chunk %d/%d (%d rows) %.2fs',
                        ci, n_chunks_4, len(chunk), time.perf_counter() - ct0)
        step_t['step4_analytics_edges'] = time.perf_counter() - t0
        logger.info('writing.step4: end (%.2fs)', step_t['step4_analytics_edges'])

        total = time.perf_counter() - phase_t0
        breakdown = ' '.join(f'{k}={v:.1f}s' for k, v in step_t.items())
        logger.info(
            'writing.replace_analytics_layer.timing: total=%.1fs (thematic=%d, communities=%d, summaries=%d, analytics_edges=%d) | %s',
            total, len(thematic_entities), len(community_entities),
            len(summary_entities), n_edges, breakdown,
        )

        return {
            'thematic_updated': len(thematic_entities),
            'community_entities_written': len(community_entities),
            'summary_entities_written': len(summary_entities),
            'analytics_edges_written': n_edges,
            'writing_timings_seconds': {k: round(v, 3) for k, v in step_t.items()},
            'writing_total_seconds': round(total, 3),
        }

    # ── Read helpers (used by later phases) ──────────────────────────
    def counts(self) -> dict[str, int]:
        """Return entity + relationship counts for the configured project."""
        self.ensure_ready()
        project_id = self.project_id

        def _count_entities() -> list[dict]:
            return self._c.query(
                'MATCH (n:Entity) WHERE $pid IN n.project_ids RETURN count(n) AS c',
                {'pid': project_id},
            )

        def _count_relationships() -> list[dict]:
            return self._c.query(
                '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
                   WHERE $pid IN a.project_ids AND $pid IN b.project_ids
                   RETURN count(r) AS c''',
                {'pid': project_id},
            )

        # Two independent count queries; the status endpoint is UI-polled,
        # so worth running them concurrently rather than serially.
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_e = ex.submit(_count_entities)
            f_r = ex.submit(_count_relationships)
            e_rows = f_e.result()
            r_rows = f_r.result()

        return {
            'entities': _first_count(e_rows),
            'relationships': _first_count(r_rows),
        }


# ── Helpers ──────────────────────────────────────────────────────────

def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _safe_json(obj) -> str:
    """JSON-encode a structure, replacing non-serializable values with str()."""
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)


def _load_json_or_dict(raw) -> dict:
    """Decode a properties_json column (str -> dict). Returns {} on
    falsy / malformed input. ArcadeDB returns the JSON column as a string
    even when it's empty."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except (TypeError, ValueError):
        return {}


def _load_json_or_list(raw) -> list:
    """Same as _load_json_or_dict but for the tags_json column."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except (TypeError, ValueError):
        return []


def _first_count(rows: list[dict]) -> int:
    if not rows:
        return 0
    row = rows[0]
    # ArcadeDB returns {"c": N} for aliased aggregates
    for v in row.values():
        if isinstance(v, (int, float)):
            return int(v)
    return 0

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
    ) -> dict[str, int]:
        """Atomically replace every vertex/edge for the configured project_id.

        Returns counts of what was written, so callers can log the outcome.
        """
        self.ensure_ready()
        project_id = self.project_id

        entities = list(entities)
        relationships = list(relationships)

        # 1. Remove this project's id from every entity that lists it.
        #    ArcadeDB Cypher does not support list comprehension syntax yet,
        #    so we use ArcadeDB SQL for the two-step cleanup.
        self._c.command_sql(
            "UPDATE Entity REMOVE project_ids = :pid WHERE project_ids CONTAINS :pid",
            {'pid': project_id},
        )
        # Delete entities whose project_ids list is now empty. DETACH DELETE
        # via Cypher drops incident edges in one shot.
        self._c.command(
            'MATCH (n:Entity) WHERE size(n.project_ids) = 0 DETACH DELETE n',
        )

        # 2. Bulk-upsert entities, chunked. Hot retrieval properties
        #    (community_id, rank) are promoted from the properties dict
        #    to top-level Entity columns so they can be indexed and queried
        #    without doing a substring match on the JSON blob.
        n_entities = 0
        for chunk in _chunks(entities, _CHUNK_VERTICES):
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

        # 3. Bulk-upsert relationships. Endpoints must already exist (they
        #    were just written). MERGE on the edge pattern avoids duplicates.
        n_rels = 0
        for chunk in _chunks(relationships, _CHUNK_EDGES):
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

        logger.info(
            'ArcadeDB replace_project_graph: project=%s wrote %d entities, %d rels',
            project_id, n_entities, n_rels,
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
        """
        self.ensure_ready()
        project_id = self.project_id

        # 1. Drop existing doc + its chunks for this path. Each chunk is
        #    DETACH DELETE'd so its incident mentions edges go too.
        #    We traverse from the doc via chunked_into rather than type-
        #    filtering markdown_chunk + CONTAINS-matching the path, because
        #    ArcadeDB's type index gets stale references after DETACH DELETE
        #    that surface as "Record not found" on subsequent queries.
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
        # Drop the doc node itself if present (re-add will recreate it).
        self._c.command(
            'MATCH (d:Entity {id: $doc_id}) DETACH DELETE d',
            {'doc_id': doc_entity.id},
        )

        # 2. Insert the new doc + chunks + chunked_into edges using the
        #    same UNWIND pattern as replace_project_graph (CREATE since we
        #    just deleted these ids).
        md_entities = [doc_entity] + list(chunk_entities)
        for chunk in _chunks(md_entities, _CHUNK_VERTICES):
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
        for chunk in _chunks(list(chunked_into_rels), _CHUNK_EDGES):
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

        # 3. Thematic entity merge: load existing, merge in Python, write
        #    back. Avoids fragile Cypher list ops.
        new_by_id = {e.id: e for e in thematic_new}
        if new_by_id:
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

            for chunk in _chunks(merged_rows, _CHUNK_VERTICES):
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

        # 4. CREATE mentions edges. Chunk endpoints are brand new (we just
        #    inserted them above) so duplicates aren't possible.
        n_mentions = 0
        for chunk in _chunks(list(mention_rels), _CHUNK_EDGES):
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
    ) -> dict[str, int]:
        """Atomically refresh the analytics layer.

        Drops old community + community_summary entities (and their
        member_of / summarizes / sameAs / similar_to edges via DETACH DELETE
        on the endpoints), then writes new ones. Updates rank + community_id
        + properties_json on existing thematic entities (where the analytics
        pass mutated them in place)."""
        self.ensure_ready()
        project_id = self.project_id

        # 1. Drop old communities + community_summary nodes (DETACH DELETE
        #    removes member_of / summarizes edges automatically). sameAs +
        #    similar_to edges connect thematic entities directly so we drop
        #    those by edge type.
        self._c.command(
            '''MATCH (n:Entity)
               WHERE $pid IN n.project_ids
                 AND n.type IN ["community", "community_summary"]
               DETACH DELETE n''',
            {'pid': project_id},
        )
        self._c.command(
            '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
               WHERE $pid IN a.project_ids
                 AND $pid IN b.project_ids
                 AND r.type IN ["sameAs", "similar_to"]
               DELETE r''',
            {'pid': project_id},
        )

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
        for chunk in _chunks(rows, _CHUNK_VERTICES):
            self._c.command(
                '''UNWIND $rows AS row
                   MATCH (n:Entity {id: row.id})
                   SET n.community_id = row.community_id,
                       n.rank = row.rank,
                       n.properties_json = row.properties_json''',
                {'rows': chunk},
            )

        # 3. Insert new community + community_summary nodes.
        new_nodes = list(community_entities) + list(summary_entities)
        for chunk in _chunks(new_nodes, _CHUNK_VERTICES):
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

        # 4. Insert new edges (member_of, summarizes, sameAs, similar_to).
        all_new_edges = (
            list(member_of_rels) + list(summary_rels)
            + list(sameas_rels) + list(similar_rels)
        )
        n_edges = 0
        for chunk in _chunks(all_new_edges, _CHUNK_EDGES):
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

        return {
            'thematic_updated': len(thematic_entities),
            'community_entities_written': len(community_entities),
            'summary_entities_written': len(summary_entities),
            'analytics_edges_written': n_edges,
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

"""GraphRAG global-layer builder.

Orchestrates Phase 1C pipeline for the cross-project thematic graph:
  1. md_scanner walks documents/** + data/documents/** -> markdown_doc
     entities + extraction-purpose markdown_chunk entities + chunked_into
     relationships.
  2. For each chunk, Gemma extracts entities (concept, person, organization,
     term). Entities above the confidence floor become nodes; each one
     gets a :mentions edge from the originating chunk.
  3. Results are atomically swapped into ArcadeDB under project_id='__global__'.

Phases 1D-1E will extend this orchestrator with sameAs, Leiden, PageRank,
and community summaries. The shape of this file will evolve.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app import state as domain_state
from app.analytics.graph_metrics import (
    apply_metrics_to_entities,
    build_community_entities,
    compute_pagerank_and_communities,
)
from app.analytics.sameas import compute_sameas_edges, compute_similar_to_edges
from app.arcadedb_client import ArcadeDBError
from app.config import GLOBAL_PROJECT_ID
from app.extractors.gemma_community_summarizer import summarize_communities
from app.extractors.gemma_entity_extractor import GemmaEntityExtractor
from app.graph_storage import GraphStorage
from app.models import Entity, Relationship
from app.rag_client import RagClient, RagClientError
from app.scanners.md_scanner import MdChunk, MdScanner, _process_file as _scan_one_file


# Cache collection names. retriever.py reads these.
ENTITY_CACHE_COLLECTION = 'gr_entities'
SUMMARY_CACHE_COLLECTION = 'gr_summaries'

logger = logging.getLogger(__name__)


@dataclass
class ResearchBuildStats:
    """Counts + timing for a single rebuild run."""
    started_at: str
    finished_at: str
    md_docs: int = 0
    extraction_chunks: int = 0
    extracted_entities: int = 0
    accepted_entities: int = 0
    below_floor: int = 0
    sameas_edges: int = 0
    similar_to_edges: int = 0
    communities: int = 0
    community_summaries: int = 0
    entities_written: int = 0
    relationships_written: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class ResearchBuilder:
    """Builds the GraphRAG thematic layer for one KB.

    P3.2: parameterized at construction with a per-KB context (kb_id +
    project_id + collection names). One ResearchBuilder per KB, held by
    the matching KBContext. Multiple KBs run independently (each has its
    own builder, its own progress dict, its own GraphStorage instance).
    """

    def __init__(
        self,
        kb_id: str | None = None,
        project_id: str | None = None,
        arcadedb_database: str | None = None,
        corpus_collection: str | None = None,
        entity_cache_collection: str | None = None,
        summary_cache_collection: str | None = None,
        scanner: MdScanner | None = None,
        extractor: GemmaEntityExtractor | None = None,
        storage: GraphStorage | None = None,
        rag_client: RagClient | None = None,
    ):
        # Per-Domain config. The ArcadeDB database for this Domain lives
        # inside the shared noted-arcadedb container; `project_id` is the
        # legacy alias and resolves to the same value.
        self.kb_id = kb_id or 'noted'
        db = arcadedb_database or project_id or GLOBAL_PROJECT_ID
        self.arcadedb_database = db
        self.project_id = db  # back-compat alias
        self.corpus_collection = corpus_collection or f'{self.kb_id}__corpus'
        self.entity_cache_collection = entity_cache_collection or ENTITY_CACHE_COLLECTION
        self.summary_cache_collection = summary_cache_collection or SUMMARY_CACHE_COLLECTION

        self._scanner = scanner or MdScanner(kb_id=self.kb_id)
        self._extractor = extractor or GemmaEntityExtractor()
        self._storage = storage or GraphStorage(arcadedb_database=db)
        self._rag = rag_client or RagClient()
        # Live progress, mutated during build(). Single-writer single-reader
        # (rebuild is serialized by the caller's lock), no synchronization
        # needed. Eventual consistency is fine for progress reporting.
        self.progress: dict = {'phase': 'idle'}

    def _set_phase(self, phase: str, **extra):
        """Update the progress dict. Thread-safe enough (see __init__ note)."""
        old_phase = self.progress.get('phase')
        self.progress['phase'] = phase
        self.progress.update(extra)
        # Log every transition so a stuck-or-wrong Monitor reading can be
        # correlated against the source of the change in container logs.
        # Cheap (one log line per phase change, not per chunk), high value
        # for diagnosis.
        if old_phase != phase:
            extras_str = ''
            if extra:
                pairs = [f'{k}={v}' for k, v in extra.items() if k != 'started_at']
                if pairs:
                    extras_str = f' ({", ".join(pairs)})'
            logger.info(
                'phase[%s]: %s -> %s%s',
                self.kb_id, old_phase, phase, extras_str,
            )

    def build(
        self,
        dry_run: bool = False,
        limit_chunks: int | None = None,
        skip_analytics: bool = False,
        skip_community_summaries: bool = False,
    ) -> ResearchBuildStats:
        """Run the pipeline.

        dry_run: skip Gemma extraction entirely; commit doc + chunk nodes.
        limit_chunks: cap extraction to first N chunks.
        skip_analytics: skip sameAs + Leiden + PageRank (leaves graph as-is).
        skip_community_summaries: skip the Gemma community-summary pass
            (useful for fast incremental tests once analytics are stable).
        """
        started = datetime.now(timezone.utc)
        t0 = _now()
        self.progress = {
            'phase': 'starting',
            'started_at': started.isoformat(),
            'md_docs': 0,
            'extraction_chunks_total': 0,
            'extraction_chunks_done': 0,
            'entities_accepted': 0,
            'communities_total': 0,
            'communities_summarized': 0,
        }

        # 1. Scan markdown.
        self._set_phase('scanning')
        md_entities, md_rels, chunks = self._scanner.scan()
        md_docs = sum(1 for e in md_entities if e.type == 'markdown_doc')
        logger.info(
            'Research build: md_scanner produced %d entities, %d rels, %d chunks',
            len(md_entities), len(md_rels), len(chunks),
        )
        if limit_chunks is not None:
            chunks = chunks[:limit_chunks]
            logger.info('Limited extraction to first %d chunks', len(chunks))

        if dry_run:
            logger.info('Dry run: skipping Gemma extraction entirely.')
            chunks_to_process: list = []
        else:
            chunks_to_process = chunks

        # 2. Extract entities per chunk (shared helper - same loop as add_doc).
        extracted_nodes, mention_rels, extracted_count, accepted_count = (
            self._extract_from_chunks(chunks_to_process, md_docs=md_docs)
        )
        below_floor = self._extractor.drain_below_floor()
        logger.info(
            'Extraction: %d accepted, %d below floor, %d distinct entities',
            accepted_count, len(below_floor), len(extracted_nodes),
        )

        # 3. sameAs + identity-merge + similar_to + PageRank + Leiden + summaries.
        # `mention_rels` and `thematic_entities` are mutated in place by the
        # merge step so the persist payload below sees the redirected data.
        thematic_entities = list(extracted_nodes.values())
        sameas_rels, similar_rels, community_entities, community_member_rels, \
            summary_entities, summary_rels = self._run_analytics_and_summaries(
                thematic_entities,
                md_entities,
                mention_rels,
                md_rels,
                skip_analytics=skip_analytics,
                skip_community_summaries=skip_community_summaries,
            )

        # 4. Push caches.
        if not skip_analytics and thematic_entities:
            self._set_phase('caching')
            self._push_caches(thematic_entities, summary_entities, replace=True)

        # 4b. Push DOCLING-derived chunks (PDF/DOCX/PPTX/HTML) to noted-rag's
        # per-KB corpus collection. Without this, a fresh full rebuild leaves
        # `<kb>__corpus` empty for any non-MD doc - users would have to
        # re-upload through `add_doc_pdf` to repopulate. .md is skipped here
        # because noted-rag's own /ingest scanner handles it (and using both
        # paths would create duplicate chunks with different ids).
        if not dry_run:
            self._push_corpus_chunks_for_docling(chunks)

        # 5. Atomic swap into ArcadeDB under the __global__ project.
        self._set_phase('writing')
        all_entities = (
            md_entities
            + thematic_entities
            + community_entities
            + summary_entities
        )
        all_rels = (
            md_rels
            + mention_rels
            + sameas_rels
            + similar_rels
            + community_member_rels
            + summary_rels
        )
        self._storage.ensure_ready()
        counts = self._storage.replace_project_graph(all_entities, all_rels)

        finished = datetime.now(timezone.utc)
        stats = ResearchBuildStats(
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            md_docs=md_docs,
            extraction_chunks=len(chunks),
            extracted_entities=extracted_count,
            accepted_entities=accepted_count,
            below_floor=len(below_floor),
            sameas_edges=len(sameas_rels),
            similar_to_edges=len(similar_rels),
            communities=len(community_entities),
            community_summaries=len(summary_entities),
            entities_written=counts['entities'],
            relationships_written=counts['relationships'],
            duration_seconds=_now() - t0,
        )
        self._set_phase('done',
                        entities_written=counts['entities'],
                        relationships_written=counts['relationships'],
                        duration_seconds=stats.duration_seconds)
        logger.info('Research build complete: %s', stats.to_dict())
        return stats

    # ── Shared extraction loop (used by build + add_doc) ──────────────

    def _extract_from_chunks(
        self,
        chunks: list,
        md_docs: int = 0,
    ) -> tuple[dict[str, Entity], list[Relationship], int, int]:
        """Run Gemma extraction over `chunks`, build merged entity nodes
        with mention strength sorting. Returns
        (extracted_nodes, mention_rels, extracted_count, accepted_count).
        """
        extracted_nodes: dict[str, Entity] = {}
        mention_rels: list[Relationship] = []
        extracted_count = 0
        accepted_count = 0
        # Per-mention strength scores so the retriever can pick chunks where
        # the entity is the topic, not just incidentally named. Keyed by
        # entity_id -> chunk_id -> score. Score = case-insensitive occurrence
        # count of the canonical name in the chunk text + a +5 bonus when
        # the name appears in the chunk's section_path.
        mention_strength: dict[str, dict[str, int]] = {}

        n_total = len(chunks)
        n_done = 0
        _PROGRESS_EVERY = 25
        self._set_phase('extracting',
                        md_docs=md_docs,
                        extraction_chunks_total=n_total,
                        extraction_chunks_done=0,
                        entities_accepted=0)
        if n_total:
            logger.info('Extraction starting: %d chunks to process', n_total)

        for chunk in chunks:
            chunk_id = _chunk_id_for(chunk)
            self.progress['current_doc'] = chunk.doc_path
            self.progress['current_chunk_in_doc'] = chunk.chunk_index
            extracted = self._extractor.extract(chunk.text)
            extracted_count += len(extracted)
            chunk_text_lower = (chunk.text or '').lower()
            section_path_lower = (chunk.section_path or '').lower()
            for item in extracted:
                key = _canonical_key(item['type'], item['name'])
                entity_id = f'{item["type"]}:{key}'
                name_lower = (item['name'] or '').lower()
                if name_lower:
                    freq = chunk_text_lower.count(name_lower)
                    header_bonus = 5 if name_lower in section_path_lower else 0
                    score = freq + header_bonus
                else:
                    score = 0
                mention_strength.setdefault(entity_id, {})[chunk_id] = max(
                    score, mention_strength.get(entity_id, {}).get(chunk_id, 0)
                )
                existing = extracted_nodes.get(entity_id)
                if existing is None:
                    extracted_nodes[entity_id] = Entity(
                        id=entity_id,
                        type=item['type'],
                        label=item['name'],
                        properties={
                            'canonical_name': item['name'],
                            'description': item['description'],
                            'extraction_confidence': item['confidence'],
                            'aliases': [],
                            'mention_count': 1,
                            'mentioned_in_chunks': [chunk_id],
                            'source_doc_paths': [chunk.doc_path],
                        },
                    )
                else:
                    existing.properties['mention_count'] = (
                        int(existing.properties.get('mention_count', 1)) + 1
                    )
                    if item['confidence'] > existing.properties.get('extraction_confidence', 0):
                        existing.properties['extraction_confidence'] = item['confidence']
                        if item['description']:
                            existing.properties['description'] = item['description']
                    mc = existing.properties.setdefault('mentioned_in_chunks', [])
                    if chunk_id not in mc and len(mc) < 50:
                        mc.append(chunk_id)
                    sp = existing.properties.setdefault('source_doc_paths', [])
                    if chunk.doc_path not in sp and len(sp) < 20:
                        sp.append(chunk.doc_path)
                mention_rels.append(Relationship(
                    source=chunk_id,
                    target=entity_id,
                    type='mentions',
                    properties={'confidence': item['confidence']},
                ))
                accepted_count += 1
            n_done += 1
            self.progress['extraction_chunks_done'] = n_done
            self.progress['entities_accepted'] = accepted_count
            if n_done % _PROGRESS_EVERY == 0 or n_done == n_total:
                pct = (n_done / n_total) * 100 if n_total else 100.0
                logger.info(
                    'Extraction progress: %d/%d chunks (%.1f%%), %d entities accepted so far',
                    n_done, n_total, pct, accepted_count,
                )

        # Sort each entity's mentioned_in_chunks by descending strength so
        # the retriever's top-N pick is the strongest evidence first.
        for ent_id, ent in extracted_nodes.items():
            chunk_ids = ent.properties.get('mentioned_in_chunks') or []
            scores = mention_strength.get(ent_id, {})
            ent.properties['mentioned_in_chunks'] = sorted(
                chunk_ids, key=lambda cid: scores.get(cid, 0), reverse=True,
            )

        return extracted_nodes, mention_rels, extracted_count, accepted_count

    # ── Shared analytics + summaries (used by build + recluster) ──────

    def _run_analytics_and_summaries(
        self,
        thematic_entities: list[Entity],
        md_entities: list[Entity],
        mention_rels: list[Relationship],
        other_rels: list[Relationship],
        skip_analytics: bool = False,
        skip_community_summaries: bool = False,
        merge_sameas_identity: bool = True,
    ) -> tuple[
        list[Relationship], list[Relationship],
        list[Entity], list[Relationship],
        list[Entity], list[Relationship],
    ]:
        """Run sameAs + (optional merge) + similar_to + PageRank + Leiden +
        community summaries.

        Mutates the passed lists in place:
          - `thematic_entities`: rank/community_id added; absorbed nodes
            removed when `merge_sameas_identity` is True.
          - `mention_rels`: chunk -> absorbed edges redirected to canonical
            when `merge_sameas_identity` is True.

        Returns (sameas_rels, similar_rels, community_entities,
        community_member_rels, summary_entities, summary_rels).
        sameas_rels is empty after the merge step (every pair was absorbed
        into a single canonical node).

        `merge_sameas_identity=False` skips the merge — used by recluster
        to preserve existing-graph entities until users do a Full Rebuild.
        """
        sameas_rels: list[Relationship] = []
        similar_rels: list[Relationship] = []
        community_entities: list[Entity] = []
        community_member_rels: list[Relationship] = []
        summary_entities: list[Entity] = []
        summary_rels: list[Relationship] = []

        if skip_analytics or not thematic_entities:
            return (sameas_rels, similar_rels, community_entities,
                    community_member_rels, summary_entities, summary_rels)

        self._set_phase('sameas')
        sameas_rels = compute_sameas_edges(thematic_entities)

        # Collapse sameAs equivalence classes BEFORE PageRank/Leiden so the
        # rank score for "AI agent" / "AI agents" lands on a single node
        # rather than being split across two. Mutates thematic_entities and
        # mention_rels in place via clear+extend so the caller's references
        # see the redirected data when assembling the persist payload.
        if merge_sameas_identity:
            self._set_phase('merge_identity')
            survivors, sameas_rels, redirected_mentions = (
                _merge_sameas_identity_classes(
                    thematic_entities, sameas_rels, mention_rels,
                )
            )
            n_absorbed = len(thematic_entities) - len(survivors)
            n_mention_drops = len(mention_rels) - len(redirected_mentions)
            thematic_entities.clear()
            thematic_entities.extend(survivors)
            mention_rels.clear()
            mention_rels.extend(redirected_mentions)
            logger.info(
                'sameAs merge: absorbed %d entities into canonicals, redirected mention edges (%d duplicates dropped)',
                n_absorbed, n_mention_drops,
            )

        self._set_phase('similar_to')
        sameas_pairs = [(r.source, r.target) for r in sameas_rels]
        similar_rels = compute_similar_to_edges(thematic_entities, sameas_pairs=sameas_pairs)

        self._set_phase('analytics')
        chunk_and_doc_entities = [
            e for e in md_entities if e.type in ('markdown_chunk', 'markdown_doc')
        ]
        working_rels = mention_rels + other_rels + sameas_rels + similar_rels
        ranks, communities_dict = compute_pagerank_and_communities(
            thematic_entities,
            working_rels,
            bridge_entities=chunk_and_doc_entities,
        )
        apply_metrics_to_entities(thematic_entities, ranks, communities_dict)

        entity_by_id = {e.id: e for e in thematic_entities}
        community_entities, community_member_rels = build_community_entities(
            communities_dict, entity_by_id,
        )
        self.progress['communities_total'] = len(community_entities)

        if not skip_community_summaries:
            self._set_phase('summarizing')
            summary_entities, summary_rels = summarize_communities(
                community_entities, communities_dict, entity_by_id,
            )
            self.progress['communities_summarized'] = len(summary_entities)

        return (sameas_rels, similar_rels, community_entities,
                community_member_rels, summary_entities, summary_rels)

    # ── ChromaDB cache push (used by build + recluster + add_doc) ─────

    def _push_caches(
        self,
        thematic_entities: list[Entity],
        summary_entities: list[Entity],
        replace: bool = True,
    ) -> None:
        """Push entity-name and community-summary embeddings to noted-rag's
        ChromaDB caches. Failures are logged but not raised - queries fall
        back to per-call embed if the cache is stale."""
        try:
            ent_ids = [e.id for e in thematic_entities]
            ent_texts = [
                f"{(e.properties.get('canonical_name') or e.label)}. "
                f"{e.properties.get('description') or ''}".strip()
                for e in thematic_entities
            ]
            if ent_ids:
                self._rag.cache_upsert(self.entity_cache_collection, ent_ids, ent_texts, replace=replace)
            if summary_entities:
                sum_ids = [s.id for s in summary_entities]
                sum_texts = [s.properties.get('text', '') for s in summary_entities]
                self._rag.cache_upsert(self.summary_cache_collection, sum_ids, sum_texts, replace=replace)
            logger.info('Cache push: %d entities, %d summaries (replace=%s)',
                        len(ent_ids), len(summary_entities), replace)
        except RagClientError as e:
            logger.warning('Cache push failed (queries will fall back to per-call embed): %s', e)

    def _push_corpus_chunks_for_docling(self, chunks: list[MdChunk]) -> None:
        """Group Docling-derived chunks (PDF / DOCX / PPTX / HTML) by
        source path, push each doc's chunks to noted-rag's `/upsert_chunks`
        for the per-KB corpus collection. .md chunks are skipped (handled
        by noted-rag's own /ingest path).

        Best-effort: failures logged, never raised. The graph side already
        committed by the time this runs, so a noted-rag failure shouldn't
        roll back the rebuild."""
        _PDF_LIKE = {'.pdf', '.docx', '.pptx', '.html', '.htm'}

        # Group chunks by doc_path, keep only Docling-derived.
        by_doc: dict[str, list[MdChunk]] = {}
        for c in chunks:
            ext = os.path.splitext(c.doc_path or '')[1].lower()
            if ext not in _PDF_LIKE:
                continue
            by_doc.setdefault(c.doc_path, []).append(c)

        if not by_doc:
            return

        from app import corpus
        sources_root = corpus.sources_dir(self.kb_id)
        n_docs = 0
        n_indexed = 0
        n_skipped = 0
        for doc_path, doc_chunks in by_doc.items():
            abs_path = os.path.join(sources_root, doc_path)
            try:
                stat = os.stat(abs_path)
                mtime = stat.st_mtime
            except OSError:
                mtime = 0
            last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            fmt = os.path.splitext(doc_path)[1].lower().lstrip('.') or 'pdf'
            rag_chunks = [{
                'chunk_index': c.chunk_index,
                'section_path': c.section_path,
                'text': c.text,
                'page_no': c.page_no,
                'bbox': c.bbox,
                'section_level': c.section_level,
            } for c in doc_chunks]
            try:
                result = self._rag.upsert_chunks(
                    source_path=doc_path,
                    tags=[self.kb_id],
                    last_modified=last_modified,
                    chunks=rag_chunks,
                    format=fmt,
                    collection=self.corpus_collection,
                )
                n_docs += 1
                n_indexed += result.get('indexed', 0)
                n_skipped += result.get('skipped_unchanged', 0)
            except RagClientError as e:
                logger.warning(
                    'rebuild: upsert_chunks failed for %s (%s): %s',
                    doc_path, fmt, e,
                )
        logger.info(
            'Rebuild corpus push: %d Docling docs, %d new chunks indexed, %d unchanged',
            n_docs, n_indexed, n_skipped,
        )

    # ── Per-doc incremental ops (P2) ──────────────────────────────────

    def add_doc(self, rel_path: str) -> dict:
        """Markdown per-doc add. Scans the file (md_scanner) then routes
        through the shared `_add_doc_from_chunks` pipeline.

        rel_path is relative to data/domains/<kb_id>/sources/.
        doc_entity.id ends up as `markdown_doc:<rel_path>`, consistent
        with what the full scanner produces.
        """
        from app import corpus
        sources_root = corpus.sources_dir(self.kb_id)
        self._set_phase('adding_doc', current_doc=rel_path)
        abs_path = os.path.join(sources_root, rel_path)
        try:
            doc_entity, chunks = _scan_one_file(abs_path, sources_root)
        except FileNotFoundError:
            self._set_phase('idle')
            raise
        except Exception as e:
            self._set_phase('idle')
            logger.exception('add_doc: scanning %s failed', rel_path)
            raise RuntimeError(f'scan failed: {type(e).__name__}: {e}')
        return self._add_doc_from_chunks(rel_path, doc_entity, chunks)

    def add_doc_pdf(self, rel_path: str) -> dict:
        """Per-doc add for non-markdown formats (PDF / DOCX / PPTX / HTML).

        Parses the source via Docling (`pdf_scanner.scan_pdf`), runs the
        same shared pipeline as `add_doc`, then ships the chunks to
        noted-rag's `/upsert_chunks` so the vector DB picks them up.
        Plan B: noted-graph is the only Docling-equipped container.

        Vector upsert is best-effort: a noted-rag failure logs + records
        the error in the response but does not roll back the graph side
        (entity extraction already committed; Recluster will reflect it).
        """
        from app import corpus
        from app.scanners.pdf_scanner import scan_pdf

        sources_root = corpus.sources_dir(self.kb_id)
        self._set_phase('adding_doc', current_doc=rel_path)
        abs_path = os.path.join(sources_root, rel_path)
        if not os.path.isfile(abs_path):
            self._set_phase('idle')
            raise FileNotFoundError(abs_path)

        try:
            chunks = scan_pdf(abs_path, repo_root=sources_root)
        except Exception as e:
            self._set_phase('idle')
            logger.exception('add_doc_pdf: scanning %s failed', rel_path)
            raise RuntimeError(f'pdf scan failed: {type(e).__name__}: {e}')

        # Mirror md_scanner._process_file's doc_entity shape so downstream
        # code (storage, retriever, UI) treats PDF docs identically.
        try:
            stat = os.stat(abs_path)
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            mtime = 0
            size = 0
        doc_entity = Entity(
            id=f'markdown_doc:{rel_path}',
            type='markdown_doc',
            label=rel_path,
            properties={
                'path': rel_path,
                'last_modified': mtime,
                'size': size,
                'chunk_count': len(chunks),
            },
        )

        out = self._add_doc_from_chunks(rel_path, doc_entity, chunks)

        # Ship the same chunks to noted-rag for embedding + ChromaDB upsert.
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        fmt = os.path.splitext(rel_path)[1].lower().lstrip('.') or 'pdf'
        rag_chunks = [{
            'chunk_index': c.chunk_index,
            'section_path': c.section_path,
            'text': c.text,
            'page_no': c.page_no,
            'bbox': c.bbox,
            'section_level': c.section_level,
        } for c in chunks]
        try:
            result = self._rag.upsert_chunks(
                source_path=rel_path,
                tags=[self.kb_id],  # P3.2: KB id as the default tag.
                last_modified=last_modified,
                chunks=rag_chunks,
                format=fmt,
                collection=self.corpus_collection,
            )
            out['rag'] = {
                'indexed': result.get('indexed', 0),
                'skipped_unchanged': result.get('skipped_unchanged', 0),
                'deleted_stale': result.get('deleted_stale', 0),
            }
        except RagClientError as e:
            logger.warning('add_doc_pdf: rag upsert_chunks failed: %s', e)
            out['rag'] = {'error': str(e)}
        return out

    def _add_doc_from_chunks(
        self, rel_path: str, doc_entity: Entity, chunks: list[MdChunk],
    ) -> dict:
        """Shared pipeline used by both `add_doc` (markdown) and
        `add_doc_pdf` (Docling). Takes pre-built doc_entity + chunks,
        runs entity extraction + ArcadeDB merge + cache refresh + sets
        the noted KB's pending_recluster marker.
        """
        started = datetime.now(timezone.utc)
        t0 = _now()
        # Reset the progress dict so the Monitor's elapsed timer starts
        # from this op (not whatever stale started_at remained from the
        # previous build/recluster).
        self.progress = {'phase': 'starting', 'started_at': started.isoformat()}

        # Build chunk_entities + chunked_into edges (same shape md_scanner
        # would produce for a full scan).
        chunk_entities: list[Entity] = []
        chunked_into_rels: list[Relationship] = []
        for c in chunks:
            chunk_id = _chunk_id_for(c)
            chunk_entities.append(Entity(
                id=chunk_id,
                type='markdown_chunk',
                label=f'{c.doc_path}#{c.chunk_index}',
                properties={
                    'doc_path': c.doc_path,
                    'chunk_index': c.chunk_index,
                    'section_path': c.section_path,
                    'text': c.text,
                    'token_count': c.token_count,
                    'page_no': c.page_no,
                    'bbox': c.bbox,
                    'regions': c.regions,
                    'section_level': c.section_level,
                    'purpose': 'extraction',
                    'parent_embedding_chunk_id': None,
                    'embedding_id': None,
                },
            ))
            chunked_into_rels.append(Relationship(
                source=doc_entity.id,
                target=chunk_id,
                type='chunked_into',
            ))

        # Run extraction over just these chunks.
        extracted_nodes, mention_rels, extracted_count, accepted_count = (
            self._extract_from_chunks(chunks, md_docs=1)
        )
        self._extractor.drain_below_floor()
        thematic_new = list(extracted_nodes.values())

        # Merge into ArcadeDB.
        self._set_phase('writing', current_doc=rel_path)
        self._storage.ensure_ready()
        merge_stats = self._storage.add_doc_merge(
            doc_entity, chunk_entities, chunked_into_rels,
            thematic_new, mention_rels,
        )

        # Cache update: upsert (don't replace) so other entities stay.
        if thematic_new:
            self._set_phase('caching', current_doc=rel_path)
            # Pull the merged versions back from storage so the cache
            # reflects what's now in the graph (description / source_doc_paths
            # may differ from what extraction alone produced).
            try:
                merged = self._storage.load_thematic_entities(
                    ids=[e.id for e in thematic_new],
                )
                self._push_caches(merged, summary_entities=[], replace=False)
            except ArcadeDBError as e:
                logger.warning('add_doc: cache refresh skipped: %s', e)

        domain_state.set_recluster_pending(self.kb_id, reason=f'doc add: {rel_path}')
        finished = datetime.now(timezone.utc)
        out = {
            'doc_path': rel_path,
            'chunks': len(chunk_entities),
            'extracted': extracted_count,
            'accepted': accepted_count,
            'distinct_entities': len(thematic_new),
            'entities_written': merge_stats.get('entities_upserted', 0),
            'mentions_written': merge_stats.get('mentions_written', 0),
            'duration_seconds': _now() - t0,
            'started_at': started.isoformat(),
            'finished_at': finished.isoformat(),
            'pending_recluster': True,
        }
        self._set_phase('done', **{k: v for k, v in out.items() if k != 'started_at'})
        logger.info('add_doc complete: %s', out)
        return out

    def remove_doc(self, rel_path: str) -> dict:
        """Remove a doc from the graph: delete the markdown_doc + its
        chunks (and mentions edges via DETACH DELETE), subtract the doc's
        path + chunk_ids from every thematic entity's source_doc_paths /
        mentioned_in_chunks, and delete entities whose source_doc_paths
        becomes empty. Sets pending_recluster.
        """
        started = datetime.now(timezone.utc)
        t0 = _now()
        self.progress = {'phase': 'starting', 'started_at': started.isoformat()}
        self._set_phase('removing_doc', current_doc=rel_path)
        self._storage.ensure_ready()
        result = self._storage.remove_doc_cleanup(rel_path)

        # Cache cleanup: drop the deleted entities + refresh the surviving
        # ones whose properties changed.
        deleted_ids = result.get('deleted_entity_ids') or []
        changed_ids = result.get('updated_entity_ids') or []
        if deleted_ids or changed_ids:
            self._set_phase('caching', current_doc=rel_path)
            try:
                # noted-rag's /cache/upsert with the same ids overwrites
                # them. There's no per-id /cache/delete today; deleted
                # entity ids will linger in the gr_entities collection
                # until the next full /recluster (which uses replace=True).
                # For per-doc remove this is fine - vector search of stale
                # ids ranks them low because their text is unchanged but
                # the entity itself no longer exists in ArcadeDB and gets
                # filtered out at retrieval time.
                if changed_ids:
                    refreshed = self._storage.load_thematic_entities(ids=changed_ids)
                    self._push_caches(refreshed, summary_entities=[], replace=False)
            except ArcadeDBError as e:
                logger.warning('remove_doc: cache refresh skipped: %s', e)

        domain_state.set_recluster_pending(self.kb_id, reason=f'doc remove: {rel_path}')

        finished = datetime.now(timezone.utc)
        out = {
            'doc_path': rel_path,
            'doc_deleted': result.get('doc_deleted', False),
            'chunks_deleted': result.get('chunks_deleted', 0),
            'entities_deleted': len(deleted_ids),
            'entities_updated': len(changed_ids),
            'duration_seconds': _now() - t0,
            'started_at': started.isoformat(),
            'finished_at': finished.isoformat(),
            'pending_recluster': True,
        }

        # Symmetric vector cleanup: add_doc_pdf ships chunks to noted-rag,
        # so remove_doc must drop them. Idempotent on noted-rag side, so
        # safe for any format (markdown chunks land here too — kb.py used
        # to do this separately; redundant call is a no-op).
        try:
            rag_result = self._rag.delete_source(rel_path, collection=self.corpus_collection)
            out['rag'] = {'deleted_chunks': rag_result.get('deleted_chunks', 0)}
        except RagClientError as e:
            logger.warning('remove_doc: rag delete failed: %s', e)
            out['rag'] = {'error': str(e)}

        self._set_phase('done', **{k: v for k, v in out.items() if k != 'started_at'})
        logger.info('remove_doc complete: %s', out)
        return out

    def recluster(self) -> dict:
        """Re-run analytics (sameAs + similar_to + PageRank + Leiden) and
        community summaries over the CURRENT graph state. Drops old
        community / community_summary nodes + member_of / summarizes /
        sameAs / similar_to edges and writes new ones. Updates rank +
        community_id on existing thematic entities. Clears the
        pending_recluster marker on success.
        """
        started = datetime.now(timezone.utc)
        t0 = _now()
        self.progress = {'phase': 'starting', 'started_at': started.isoformat()}
        self._set_phase('recluster_loading')
        self._storage.ensure_ready()

        thematic_entities = self._storage.load_thematic_entities()
        md_entities, mention_rels, chunked_into_rels = (
            self._storage.load_md_layer()
        )
        logger.info(
            'Recluster: loaded %d thematic entities, %d md entities, %d mention edges, %d chunked_into edges',
            len(thematic_entities), len(md_entities),
            len(mention_rels), len(chunked_into_rels),
        )

        # Recluster runs over already-persisted entities; the sameAs merge
        # step would need a graph_storage primitive to absorb-and-delete
        # entities in ArcadeDB (out of scope for the build-path fix).
        # Existing graphs pick up the merge on the next Full Rebuild.
        sameas_rels, similar_rels, community_entities, community_member_rels, \
            summary_entities, summary_rels = self._run_analytics_and_summaries(
                thematic_entities,
                md_entities,
                mention_rels,
                chunked_into_rels,
                skip_analytics=False,
                skip_community_summaries=False,
                merge_sameas_identity=False,
            )

        self._set_phase('writing')
        write_counts = self._storage.replace_analytics_layer(
            thematic_entities,
            community_entities,
            community_member_rels,
            summary_entities,
            summary_rels,
            sameas_rels,
            similar_rels,
        )

        if thematic_entities:
            self._set_phase('caching')
            self._push_caches(thematic_entities, summary_entities, replace=True)

        domain_state.clear_recluster_pending(self.kb_id)

        finished = datetime.now(timezone.utc)
        out = {
            'thematic_entities': len(thematic_entities),
            'sameas_edges': len(sameas_rels),
            'similar_to_edges': len(similar_rels),
            'communities': len(community_entities),
            'community_summaries': len(summary_entities),
            'duration_seconds': _now() - t0,
            'started_at': started.isoformat(),
            'finished_at': finished.isoformat(),
            **write_counts,
            'pending_recluster': False,
        }
        self._set_phase('done', **{k: v for k, v in out.items() if k != 'started_at'})
        logger.info('Recluster complete: %s', out)
        return out


def _canonical_key(type_: str, name: str) -> str:
    """Normalize for dedup inside a single build.

    Phase 1D's sameAs pass handles semantic equivalence across spellings;
    here we just collapse case + whitespace variants per type so we don't
    mint `concept:Knowledge Graph` and `concept:knowledge graph` as two
    nodes from the same build.
    """
    return ' '.join(name.lower().split())


def _merge_sameas_identity_classes(
    thematic_entities: list[Entity],
    sameas_rels: list[Relationship],
    mention_rels: list[Relationship],
) -> tuple[list[Entity], list[Relationship], list[Relationship]]:
    """Collapse sameAs equivalence classes into a single canonical entity each.

    For every connected component in the sameAs graph, pick a canonical
    entity and absorb the others into it. Side effects per absorbed
    entity:
      - Its label + canonical_name + existing aliases append to the
        canonical's `properties['aliases']`.
      - Its `mentioned_in_chunks`, `source_doc_paths` union into the
        canonical's lists (capped at the same limits as extraction).
      - Its `mention_count` is summed onto the canonical's count.
      - Description: keep the longer non-empty form.
      - extraction_confidence: keep the higher value.

    Mention edges from chunks to absorbed entities are redirected to the
    canonical entity, deduplicated by `(source, type, target)`.

    Returns (surviving_entities, dropped_sameas_rels, redirected_mention_rels).
    `dropped_sameas_rels` is the empty list on the assumption that any pair
    sameAs flagged at all is identity enough to merge — keeping the edge
    after merging would point a node to itself. If you want to keep some
    pairs as edges (e.g. only merge above a threshold), tighten the input
    list before calling.
    """
    if not sameas_rels:
        return thematic_entities, sameas_rels, mention_rels

    by_id = {e.id: e for e in thematic_entities}

    # Union-find over sameAs pairs.
    parent: dict[str, str] = {}

    def _find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    # Digit-guard against template-shaped false matches.
    # Levenshtein over labels like "Directive 2014/90/EU" vs
    # "Directive 2013/32/EU" returns ~0.92+ because the "Directive YYYY/NN/EU"
    # template dominates the character distance — but those references are
    # SEMANTICALLY DIFFERENT documents. Same shape applies to "Article 5" /
    # "Article 6", "MLflow 2.0" / "MLflow 2.1", "Type 1 diabetes" /
    # "Type 2 diabetes", etc. Pure morphological merges (singular/plural,
    # hyphen/space, casing) never have digits in the label.
    # Rule: when either label contains a digit, require score >= 0.99
    # (essentially identical strings) to merge. Pure-text concepts use the
    # existing sameAs threshold (0.92).
    DIGIT_LABEL_THRESHOLD = 0.99

    def _label_has_digits(label: str) -> bool:
        return any(c.isdigit() for c in (label or ''))

    skipped_id_like = 0
    for r in sameas_rels:
        if r.source not in by_id or r.target not in by_id:
            continue
        src_e = by_id[r.source]
        tgt_e = by_id[r.target]
        score = float((r.properties or {}).get('score', 0.0))
        if (_label_has_digits(src_e.label) or _label_has_digits(tgt_e.label)):
            if score < DIGIT_LABEL_THRESHOLD:
                skipped_id_like += 1
                continue
        _union(r.source, r.target)

    if skipped_id_like:
        logger.info(
            'sameAs merge: skipped %d digit-label pairs below 0.99 (template-shape protection)',
            skipped_id_like,
        )

    # Group entities by their root.
    classes: dict[str, list[Entity]] = {}
    for e in thematic_entities:
        root = _find(e.id) if e.id in parent else e.id
        classes.setdefault(root, []).append(e)

    absorbed_to_canonical: dict[str, str] = {}
    surviving: list[Entity] = []

    for members in classes.values():
        if len(members) == 1:
            surviving.append(members[0])
            continue
        canonical = _pick_canonical_label(members)
        for m in members:
            if m.id == canonical.id:
                continue
            _absorb_into(canonical, m)
            absorbed_to_canonical[m.id] = canonical.id
        surviving.append(canonical)

    # Redirect mention edges to the canonical, dedup by (source, type, target).
    seen: set[tuple[str, str, str]] = set()
    redirected: list[Relationship] = []
    for r in mention_rels:
        target = absorbed_to_canonical.get(r.target, r.target)
        key = (r.source, r.type, target)
        if key in seen:
            continue
        seen.add(key)
        if target == r.target:
            redirected.append(r)
        else:
            redirected.append(Relationship(
                source=r.source, target=target, type=r.type,
                properties=r.properties,
            ))

    # Keep only sameAs edges whose endpoints didn't get merged. Pairs that
    # were skipped by the digit-guard remain as edges (the LLM still gets
    # a hint that two regulatory references are string-similar) but their
    # endpoints stay as distinct entities. Re-resolve through union-find:
    # if both endpoints map to the same canonical, the edge is redundant.
    surviving_ids = {e.id for e in surviving}
    kept_sameas: list[Relationship] = []
    for r in sameas_rels:
        if r.source not in by_id or r.target not in by_id:
            continue
        canon_s = absorbed_to_canonical.get(r.source, r.source)
        canon_t = absorbed_to_canonical.get(r.target, r.target)
        if canon_s == canon_t:
            continue  # both ends merged into the same node — edge redundant
        if canon_s in surviving_ids and canon_t in surviving_ids:
            kept_sameas.append(r)

    return surviving, kept_sameas, redirected


def _pick_canonical_label(members: list[Entity]) -> Entity:
    """Choose the canonical entity for a sameAs equivalence class.

    Selection rules in order of priority:
      1. Higher `mention_count` (most frequent form in the corpus).
      2. Fewer uppercase characters in label (prefer naturally-lowercase).
      3. Singular over plural — when this label is exactly `other_label + s`
         or `other_label + es` of another member, prefer the other.
      4. Shorter label.
      5. Alphabetical id (deterministic tiebreaker).

    All other labels get added as aliases on the canonical so source
    fidelity is preserved.
    """
    member_labels_lower = {(m.label or '').lower() for m in members}

    def _score(e: Entity) -> tuple:
        label = e.label or ''
        lower = label.lower()
        upper_count = sum(1 for c in label if c.isupper())
        mention_count = int((e.properties or {}).get('mention_count', 1))
        is_plural_of_another = False
        if lower.endswith('s') and len(lower) > 3:
            stem = lower[:-1]
            if stem in member_labels_lower:
                is_plural_of_another = True
            elif lower.endswith('es') and len(lower) > 4:
                stem2 = lower[:-2]
                if stem2 in member_labels_lower:
                    is_plural_of_another = True
        return (
            -mention_count,
            upper_count,
            1 if is_plural_of_another else 0,
            len(label),
            e.id,
        )

    return min(members, key=_score)


def _absorb_into(canonical: Entity, absorbed: Entity) -> None:
    """Merge `absorbed` into `canonical` by mutating canonical's properties.

    Caller is responsible for redirecting edges and dropping `absorbed`
    from the entity list afterwards.
    """
    can_props = canonical.properties
    abs_props = absorbed.properties or {}

    # mentioned_in_chunks: union, preserve canonical's existing order,
    # append absorbed's new entries. Cap matches extraction-time cap (50).
    can_chunks = can_props.get('mentioned_in_chunks') or []
    seen = set(can_chunks)
    for cid in (abs_props.get('mentioned_in_chunks') or []):
        if cid not in seen:
            can_chunks.append(cid)
            seen.add(cid)
    can_props['mentioned_in_chunks'] = can_chunks[:50]

    # source_doc_paths: union (cap 20).
    can_paths = can_props.get('source_doc_paths') or []
    seen_p = set(can_paths)
    for p in (abs_props.get('source_doc_paths') or []):
        if p not in seen_p:
            can_paths.append(p)
            seen_p.add(p)
    can_props['source_doc_paths'] = can_paths[:20]

    # mention_count: sum.
    can_props['mention_count'] = (
        int(can_props.get('mention_count', 1))
        + int(abs_props.get('mention_count', 1))
    )

    # aliases: collect absorbed's label + canonical_name + its own aliases.
    aliases = can_props.setdefault('aliases', [])
    for candidate in (
        absorbed.label,
        abs_props.get('canonical_name'),
        *(abs_props.get('aliases') or []),
    ):
        if candidate and candidate != canonical.label and candidate not in aliases:
            aliases.append(candidate)

    # Description: keep the longer non-empty.
    can_desc = can_props.get('description') or ''
    abs_desc = abs_props.get('description') or ''
    if len(abs_desc) > len(can_desc):
        can_props['description'] = abs_desc

    # extraction_confidence: keep the higher.
    if float(abs_props.get('extraction_confidence', 0.0)) > float(can_props.get('extraction_confidence', 0.0)):
        can_props['extraction_confidence'] = abs_props['extraction_confidence']


def _chunk_id_for(chunk: MdChunk) -> str:
    # Mirror md_scanner._chunk_id() logic without importing private helper.
    import hashlib
    h = hashlib.sha1(
        f'{chunk.doc_path}#{chunk.chunk_index}'.encode()
    ).hexdigest()[:12]
    return f'markdown_chunk:{h}'


def _now() -> float:
    import time
    return time.monotonic()

# GraphRAG Open Questions

Snapshot as of 2026-04-23. Everything below is to be answered before implementation starts OR explicitly deferred with a reason.

## Resolved so far

| # | Question | Decision |
|---|---|---|
| 1 | Graph store? | **ArcadeDB** (Apache 2.0, Cypher primary, new container). |
| 2 | Phase 1 scope: embeddings in graph? | **No.** ChromaDB keeps vectors; ArcadeDB graph-only. Permanent — no consolidation planned. |
| 3 | Concurrency for extraction? | **Shared Gemma pool, 1 instance, 30-min rebuild budget.** Acceptable in dev. Revisit at real-user load. |
| 4 | Builder library? | **Microsoft graphrag** with ArcadeDB adapter. |
| 5 | Gemma model? | **Same E4B UD-Q4_K_XL** used for chat (401/402 test pass). Skills + test YAMLs also become entity sources (see taxonomy). |
| 6 | Ingestion atomicity? | **Atomic**: staging prefix in ArcadeDB + new ChromaDB collection, swap on success. No partial graphs. |
| 7 | Output envelope for `research_topic`? | `{answer (markdown), citations, subgraph, mode, communities_used, graph_built_at}`. Text view AND 3D view share one response. |
| 8 | Skill routing rubric? | **Draft in [skill_proposal.md](skill_proposal.md)**. Ships with the tools; iterate from test-harness results. |
| 9 | Architecture diagram? | **[phase1_architecture.drawio](phase1_architecture.drawio)**. |
| 10 | Evaluation approach? | **Extend the existing 402-scenario harness** with new `research_topic.yaml` scenarios. Same LLM-judge workflow. |
| 11 | Corpus-size / indexing-time targets? | **Deferred**. Measure after first working build; set targets based on observed baselines. |
| 12 | Does noted-graph already exist? | **YES** — already implemented with scanners for MLflow/DVC/Hydra/Airflow/filesystem. GraphRAG EXTENDS it (adds persistence + new scanners + markdown layer), does not replace. |
| 13 | Synonym resolution strategy (was Q A) | **`sameAs` edge, not destructive merge.** Non-destructive: both nodes keep their provenance. Three confidence bands on bge-m3 cosine: `high` (≥0.90, always expand), `medium` (0.80-0.90, 'broad' mode only), `low` (0.70-0.80, review candidate). Preconditions: same type, normalize first, short-name threshold bump. Added to [taxonomy.yaml](taxonomy.yaml). |
| 14 | Leiden community sizing (was Q B) | **Default 50, configurable.** Expose `community_target_size` in noted-graph service config (passes through to Microsoft graphrag). Tune after first bench run; no pre-optimization. |
| 15 | Markdown chunk size + overlap (was Q C) | **Two chunk populations.** Embedding chunks = noted-rag's existing `ChunkRecord` untouched (MAX=1000/MIN=150/TARGET=700, heading-aware level ≥2). Extraction chunks = new `md_scanner` output (MAX=800/MIN=200/TARGET=600, heading-aware level ≥3). Cross-referenced via `parent_embedding_chunk_id`. |
| 16 | Retrieval strategy (global/local + Leiden/PageRank) | **Global mode:** vector-search community summaries (bge-m3, not keyword match) → top-K → per-community top-N entities by PageRank → prompt with summaries + entities + relationships + chunk excerpts. **Local mode:** vector-search entity names → N-hop Cypher traversal with rank floor → subgraph + chunk excerpts. Both expand `sameAs` (confidence≥0.85). `mode: auto` runs both in parallel. All params configurable. Full spec in [graph_rag_notes.md](graph_rag_notes.md#53-data-flow). |
| 17 | Entity extraction confidence floor (was Q D) | **0.6 starting value, configurable** as `entity_confidence_floor`. Below-threshold extractions logged to a file (not stored in graph) for review. Tune after first bench run shows the distribution. |
| 18 | ArcadeDB deployment (was Q E) | **E1 Ports:** host-side HTTP 2480, Gremlin 8182 (no collision with existing noted port map). Container-side confirmed at image pull. **E2 Volume:** bind-mount `./data/arcadedb/` so data survives container restarts. **E3 Backup:** deferred to [noted_backlog.md](../noted_backlog.md) — pre-rebuild dump + last-3 retention + auto-restore. Not blocking Phase 1. |
| 19 | Corpus inventory + initial file count (was Q F) | **~65-75 prose md files** for md_scanner extraction. Three-tier taxonomy of sources: **structured** (hydra/skills/tests YAMLs — dedicated scanners, no Gemma), **prose** (documents/**, data/documents/** — md_scanner + Gemma), **noise** (data/testing/reports/, data/environments/, data/projects/, data/.renv-cache/, node_modules/, .git/ — excluded). Expected ~300-500 extraction calls per full rebuild, comfortably within 30 min budget. |
| 20 | Taxonomy review gate (was Q G) | **Proceed without formal review.** Taxonomy has been through enough passes (Gemma review, Q A `sameAs`, Q C chunk fields). Gaps found mid-implementation cost one back-patch each, scaling linearly. Extend-as-we-go. |
| 21 | Phase 1 test scenarios (was Q H) | **Deferred to post-implementation.** Scenarios written once the tool's real behavior is observable. Target ~20 scenarios in `testing/assistant/tools/research_topic.yaml` iterated from failure patterns. 8 drafts in [skill_proposal.md §4](skill_proposal.md) are a sketch, not a commitment. |
| 22 | Rebuild trigger audience (was Q I) | **User-triggered, visible to all.** Dev-only platform, no multi-user concern. Add role check if/when auth roles land. |
| 23 | Rebuild-in-progress indicator (was Q J) | **Deferred to enhancements.** Envelope keeps the `rebuild_in_progress: bool` field (cheap, forward-compatible) but the UI banner is not wired in Phase 1. Implement when the feature demands it. |

## Still open — need decisions before code starts

*(all design-gate questions resolved 2026-04-23. Phase 1.5 design bundle below is not blocking Phase 1.)*

## Non-questions (explicitly NOT deciding now)

- Phase 3 incremental indexing.
- Whether to expose the graph as a `/mcp` resource to external agents.
- Whether to offer per-project graphs (vs one global graph).

These are deliberately deferred until Phase 1 is in production and usage patterns emerge.

## Phase 1.5 design detail: per-source auto-update (FR-9)

Goal: save/edit of a single `.md`, `SKILL.md`, or test YAML triggers a ~30-120 sec targeted re-index instead of a 15-30 min full rebuild.

Mechanics:
1. Hook the save path for markdown/skills/tests — emit `doc_ingested` event with `{source_type, path, operation: added|updated|deleted}`.
2. `noted-graph` subscribes → runs just the relevant scanner on that path → Gemma extracts new entities/edges → upsert to ArcadeDB.
3. For every entity whose community membership changed (added, moved, removed), mark the touched communities dirty.
4. Re-run the community-summary step only for dirty communities (one Gemma call per dirty community ≈ 2-5 sec).
5. Atomic swap of the affected subgraph and summaries.

What stays OUT of auto-update scope:
- Cross-doc relationship discovery via embedding similarity (requires a pass over all chunks; too expensive per-save).
- Re-clustering (Leiden over the whole graph) — only runs on full rebuilds. Communities stay stable between full rebuilds; new entities get member_of edges to existing communities via their dominant neighbors.

Open design points for Phase 1.5 kickoff:
- **Debounce window**: if the user saves 5 times in 10 seconds, coalesce into one re-index run. Default: 2-sec debounce, cap 1 run per source path per 10 sec.
- **Failure semantics**: same as full rebuild — staging prefix, swap on success, previous graph remains visible during the window.
- **User feedback**: freshness pill (FR-7) distinguishes "last full rebuild: Xh ago" vs "auto-updated from save: Ys ago". Two-line state.
- **Emergency flag**: a "pause auto-update" toggle for when the user is doing bulk edits and doesn't want 50 re-indexes fired.

## Later opportunity: self-improving graph

Once Phase 1 is running, the graph can critique its own schema via Cypher
analytics. Examples:
- Rare entity types → taxonomy too granular OR extractor weak.
- Dead relationship types → prune from schema.
- High-mention terms without synonym edges → review candidates.
- Overlapping community summaries → Leiden parameter tuning.
- Fragmented shortest-path distribution → community sizing wrong.

A scheduled job runs these weekly, drops a markdown report into the KB,
and the next ingestion ingests that report. Result: meta-introspection
loop — the graph tells us what to fix in itself. Defer to post-Phase-1.

## Gemma review log

- 2026-04-23: asked Gemma (via noted chat + `search_docs`) to flag missing
  entities/relationships. It proposed 4 + 4. Accepted: `metric`,
  `data_schema` entities; `measures`, `is_derived_from`, `is_governed_by`
  relationships. Deferred: `Deployment_Target` (speculative while single
  serving container). Skipped: `Pipeline_Step` (redundant with dag_task),
  `is_prerequisite_for` (redundant with depends_on). Noteworthy meta: Gemma
  could not see the EXISTING taxonomy in detail (only what we pasted), so
  some suggestions collided with what we already had. Exactly the gap
  GraphRAG's relational layer would close.

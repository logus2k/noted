# Vision and Scope: GraphRAG Integration

## 1. Business Opportunity
The current RAG stack (ChromaDB + `bge-m3` + reranker, served by `noted-rag`) is strong for specific-fact retrieval but cannot synthesize themes across the Markdown corpus, nor trace relationships between entities that appear in disparate files. GraphRAG addresses this by adding an entity/relationship layer alongside the existing vector layer.

## 2. Vision
Evolve the local AI assistant from a "document searcher" into a "knowledge analyst" by adding a hierarchical Knowledge Graph over the Markdown corpus AND over the structured entities noted already surfaces (MLflow runs, DVC data versions, Hydra configs, Airflow DAGs, etc.). Gives users thematic and relational queries without giving up privacy — everything runs locally on the RTX 4090 / Gemma 4 E4B.

## 3. Key Reframe (after code spelunking on 2026-04-23)

**noted already has a knowledge-graph service.** `graph/` ships as container `noted-graph` with:
- Pydantic models (`Entity`, `Relationship`, `Graph`, `Neighborhood`, `ViewDefinition`, `SearchResult`)
- Scanners for MLflow / DVC / Hydra / Airflow / Filesystem
- Search, views, tags, graph routers
- Three.js 3D viewer in the frontend (`knowledge-graph/`)

**GraphRAG is NOT a greenfield project — it's an extension:**
- Add ArcadeDB as the persistence layer (noted-graph currently rebuilds in memory via `graph_cache.py`)
- Add new scanners for markdown/skills/tools/tests/git (see [taxonomy.yaml](taxonomy.yaml))
- Add a Gemma-powered extractor for thematic entities (`concept`, `person`, `term`)
- Add Leiden community detection + community summaries
- Expose a new `/research` endpoint that the assistant's `research_topic` tool calls
- The existing 3D viewer consumes the new entity/edge types with zero frontend changes (data-driven)

## 4. Scope

### 4.1 In-Scope (Phase 1)
- ArcadeDB container (NEW) as the graph persistence store
- Extended `noted-graph` service with new scanners (markdown, skills, tools, test scenarios, git) and ArcadeDB adapter
- Gemma-powered entity extraction from markdown chunks
- Leiden community detection + per-community summaries (via Microsoft graphrag library)
- New assistant tool: `research_topic` (and `rebuild_knowledge_graph`)
- Updated `docs-rag` skill routing rule: `search_docs` (facts) vs `research_topic` (themes / relations)
- Manual ingestion trigger (batch)
- Full local execution (no external network calls)

### 4.2 Out-of-Scope (Phase 1)
- Real-time / incremental indexing (manual rebuild only)
- ChromaDB stays as the vector store. No migration planned.
- Web-based interactive graph editor (3D viewer already exists for read-only exploration)

## 5. Technical Architecture

See [phase1_architecture.drawio](phase1_architecture.drawio) for the diagram. Text summary below.

### 5.1 Graph Store: ArcadeDB
- **License:** Apache 2.0. Aligns with noted's zero-vendor-lock-in philosophy.
- **Query language:** Cypher (openCypher standard). Same dialect as Neo4j / Memgraph / Kùzu. Queries are portable; if ArcadeDB is ever retired, migration is a compose-file change, not a query rewrite.
- **Escape hatches:** SQL (ops / debug), Gremlin (complex traversals).
- **Deployment:** NEW Docker container in the noted compose stack. Single JAR, no hidden dependencies.
- **Scope in Phase 1:** entities, relationships, community summaries. NOT embeddings — those stay in ChromaDB.

### 5.2 Components

| Component | Role | Status |
|---|---|---|
| `noted-rag` sidecar | Chunk embeddings + vector retrieval via bge-m3 + reranker | Existing |
| ChromaDB (inside noted-rag) | Embedding store — remains authoritative for vector similarity | Existing |
| `noted-graph` service | Entity/relationship scanners + graph builder + Three.js backend | Existing, EXTENDED |
| **ArcadeDB** | Graph persistence (entities, edges, communities, summaries) | **NEW container** |
| `agent_server` / Gemma 4 E4B UD-Q4_K_XL | Entity extraction, community summarization, final answer synthesis | Existing (shared pool) |
| New scanners: `md_scanner`, `skill_scanner`, `tool_scanner`, `test_scenarios_scanner`, `git_scanner` | Per [taxonomy.yaml](taxonomy.yaml) | **NEW** in `graph/app/scanners/` |

### 5.3 Data Flow

**Ingestion (manual trigger):**
1. User clicks "Rebuild Knowledge Graph" in the UI (or chat calls `rebuild_knowledge_graph` tool).
2. `noted-graph` runs all scanners → emits Entities + Relationships.
3. `md_scanner` produces TWO chunk populations (resolved Q C): embedding chunks via noted-rag's existing `ChunkRecord` (MAX=1000/MIN=150/TARGET=700, heading-aware level ≥2) AND extraction chunks at MAX=800/MIN=200/TARGET=600, heading-aware level ≥3. Each extraction chunk carries `parent_embedding_chunk_id`.
4. Gemma extracts entities from each extraction chunk → Entities + Relationships (`:mentions`, `:defines`, etc.).
5. `sameAs` edge pass (resolved Q A): normalize + embed entity name/description, emit `sameAs` edges with confidence bands (high ≥0.90, medium 0.80-0.90, low 0.70-0.80).
6. Leiden clustering over the assembled graph → `community` nodes + `community_id` on every entity. `community_target_size` configurable (default 50).
7. PageRank over the assembled graph → `rank` property on every entity.
8. Gemma summarizes each community → `community_summary` nodes.
9. Atomic write to ArcadeDB (staging prefix → swap on success).
10. Same ingestion run updates ChromaDB with new embedding chunks (FR-6 — dual write in one transaction).

**Query (`research_topic`) — mode classification:**

The `research_topic` tool accepts `mode: "global" | "local" | "auto"`. Default `auto`: both paths run in parallel; Gemma merges. If latency becomes painful post-bench, switch to a single Gemma-classify call upfront.

**Query — Global mode (FR-1, thematic questions):**
1. Embed the user's question with bge-m3 (the same endpoint noted-rag uses).
2. Vector-search against `community_summary.text` embeddings. Take top-K (default K=3, configurable as `global_top_communities`).
3. For each selected community, one Cypher call pulls the top-N entities by rank AND their primary edges:
   ```cypher
   MATCH (e)-[:member_of]->(:community {community_id: $cid})
   WITH e ORDER BY e.rank DESC LIMIT $top_entities_n
   OPTIONAL MATCH (e)-[r]-(n) WHERE id(e) <> id(n)
   OPTIONAL MATCH (c:markdown_chunk {purpose: 'extraction'})-[:mentions]->(e)
   RETURN e, collect(DISTINCT [type(r), n.id, n.label]) AS edges,
          collect(DISTINCT c.id) AS supporting_chunks
   ```
   `top_entities_n` configurable (default 10).
4. Expand `sameAs` edges of confidence≥0.85 when building the entity set.
5. Fetch supporting `markdown_chunk.text` excerpts via `parent_embedding_chunk_id` for citation grounding.
6. Build prompt: community summaries + entity lists + key edges + chunk excerpts.
7. Gemma synthesizes. Envelope returns `mode: "global"`.

**Query — Local mode (FR-2, relational questions):**
1. Embed the question.
2. Vector-search against **entity** `name + description` embeddings (not community summaries) — find entry entities.
3. From each entry entity, Cypher N-hop traversal (default N=3, configurable as `local_traversal_hops`), following all edge types but filtering on rank to prevent subgraph explosion:
   ```cypher
   MATCH (entry) WHERE entry.id IN $entry_ids
   CALL { WITH entry
       MATCH p = (entry)-[*1..$hops]-(related)
       WHERE related.rank >= $rank_floor
       RETURN p, related LIMIT $subgraph_cap
   }
   RETURN p, related,
          [(c:markdown_chunk {purpose: 'extraction'})-[:mentions]->(related) | c.id] AS supporting_chunks
   ```
   `subgraph_cap` configurable (default 50 relationships).
4. Expand `sameAs` edges in traversal (the traversal naturally crosses them; no special code needed).
5. Fetch supporting chunk excerpts the same way as global mode.
6. Build prompt: described subgraph (paths as sentences) + chunk excerpts.
7. Gemma synthesizes. Envelope returns `mode: "local"`.

**Algorithm roles (resolved with your note):**

|  | Leiden | PageRank |
|---|---|---|
| Global mode | **Primary** — communities ARE the retrieval unit | **Secondary** — within-community top-N filter |
| Local mode | Optional boundary constraint | **Useful** — trims exploded subgraphs |

**Envelope:**
```json
{
  "answer": "<markdown>",
  "citations": ["<chunk_id>", ...],
  "subgraph": {"nodes": [...], "edges": [...]},
  "mode": "global" | "local" | "auto",
  "communities_used": [<community_id>, ...],
  "graph_built_at": "<iso-8601>",
  "rebuild_in_progress": false
}
```

UI renders `answer` as text AND passes `subgraph` to the 3D viewer — same response drives both views.

**Configurable retrieval params (one noted-graph config file):**
- `community_target_size` (default 50) — passes to Microsoft graphrag's Leiden
- `global_top_communities` (default 3)
- `top_entities_n` (default 10)
- `local_traversal_hops` (default 3)
- `subgraph_cap` (default 50 relationships)
- `rank_floor` (default 0.0, so no filter until tuned)
- `sameAs_expand_confidence` (default 0.85)
- `entity_confidence_floor` (default 0.6) — Gemma extractions below this are logged but not stored

## 6. Functional Requirements

| ID | Feature | Description |
|---|---|---|
| FR-1 | Global search | Answer thematic questions ("what are the core risks?") via community summaries. |
| FR-2 | Local search | Answer relational questions ("how is A linked to B?") via Cypher traversal. |
| FR-3 | Skill routing | `docs-rag` skill directs the model between `search_docs` (facts) and `research_topic` (synthesis). Rubric in [skill_proposal.md](skill_proposal.md). |
| FR-4 | Local embedding | Reuse the existing `bge-m3` endpoint; no new embedding service. |
| FR-5 | Standard query language | All graph queries use Cypher. No ArcadeDB-specific SQL in application code. Portable to Neo4j / Memgraph / Kùzu. |
| FR-6 | Ingestion coherence | When markdown is ingested or removed, ChromaDB chunks AND ArcadeDB entities are rebuilt in the same ingestion run. Atomic dual-write; no partial graphs. |
| FR-7 | Graph freshness indicator | UI surfaces graph last-built timestamp + entity counts so users can see if the graph is stale before asking `research_topic`. |
| FR-8 | Unified output envelope | `research_topic` returns `{answer, citations, subgraph, mode, communities_used}`. Text view and 3D view consume the same response. |
| FR-9 | Per-source auto-update (opt-in) | Each scanner has an `auto_update` flag. When true AND the source mutates (markdown saved, SKILL.md edited, test YAML added), the scanner re-processes just that source, upserts entities/edges, marks touched communities dirty, and re-summarizes only dirty communities. Defaults: OFF in Phase 1; targeted ON for markdown/skills/tests in Phase 1.5. Structured scanners (mlflow/airflow/dvc) stay batch because their changes have wider cross-entity effects that need full recomputation. |

## 7. Success Criteria
1. **Thematic accuracy:** answer-correctness on a theme/relation bench set (see §9 Evaluation).
2. **Fact regression guard:** unchanged accuracy on existing specific-fact queries.
3. **Privacy:** zero external network calls during ingest or query.
4. **Atomic ingestion:** partial graph never visible to queries; staging-swap verified.

Concrete numeric thresholds (corpus size target, indexing time, pass rates) deferred until the first working end-to-end build exposes realistic baselines.

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Gemma 4 E4B struggles with structured JSON extraction for entities. | Tight extraction schemas (`required`, `minItems` honored per session-2026-04-22 findings). Smaller chunks (~600 tokens). Dedicated prompts in `prompts/`. |
| Community summarization exceeds model context window. | Map-reduce summarization from the graphrag library. agent_server already runs n_ctx=131k, ample headroom. |
| `research_topic` vs `search_docs` routing ambiguous. | Explicit rubric in the `docs-rag` skill; validated against the bench set before ship (see [skill_proposal.md](skill_proposal.md)). |
| Graph staleness surfaces as silent wrong answers. | FR-7 freshness indicator + every `research_topic` answer stamps `graph_built_at` in citations. |
| Extraction blocks chat (shared Gemma pool). | Acceptable in dev (user decision): 1 instance, 30-min rebuild budget. Revisit when we approach real-user load. |
| ArcadeDB project stalls. | All queries are Cypher (openCypher). Migration target: Neo4j / Memgraph / Kùzu with no query rewrites. Exports: GraphML / JSON. |
| Vector-store drift between ChromaDB and ArcadeDB. | FR-6: single ingestion run writes both; failure on either fails the whole run. No partial commits. |

## 9. Evaluation Approach

Deferred until implementation is working, then materialized as **additional scenarios in the existing 402-scenario assistant harness** (same format, same LLM judge, same `testing/assistant/tools/*.yaml` layout).

Planned scenario splits:
- **Theme / relation queries** → `research_topic` expected.
- **Specific-fact queries** → `search_docs` expected (regression guard).
- **Routing ambiguity** → harness checks the chosen tool against `expected_tools_called`.

Draft scenario file path: `testing/assistant/tools/research_topic.yaml` (new). Judge evaluation identical to existing pattern.

## 10. Entity + Relationship Taxonomy

Full taxonomy in [taxonomy.yaml](taxonomy.yaml) — 50+ entity types across 14 domains, 30+ relationship types. Existing scanners already cover structured entities (MLflow, DVC, Hydra, Airflow, filesystem); new scanners added in Phase 1 for markdown content, skills, tools, test scenarios, git. The thematic GraphRAG layer (concept, person, term, community, community_summary) comes from Gemma extraction and Leiden clustering over the assembled graph.

## 11. Phase Boundaries

| Phase | Scope | Gate to proceed |
|---|---|---|
| **Phase 1** | Graph-only ArcadeDB. ChromaDB keeps vectors. `research_topic` tool + `rebuild_knowledge_graph` tool. Manual full-rebuild trigger only. New scanners + Gemma extraction + community summaries. | Evaluation scenarios green per §9. |
| **Phase 1.5** | Opt-in per-source auto-update (FR-9) for markdown, skills, tests. Per-doc upsert flow + dirty-community re-summarization. Structured scanners (mlflow/airflow/dvc) remain full-rebuild. | Phase 1 stable ≥2 weeks + ingestion coherence proven under auto-update load. |
| **Phase 2** (deferred) | Cross-source change-detected reindexing (structured scanners also auto-update). | Only after Phase 1.5 is stable and structured-source staleness is a real user pain. |

## 12. Related files in this directory

| File | Purpose |
|---|---|
| [graph_rag_notes.md](graph_rag_notes.md) | This document — vision, scope, architecture. |
| [taxonomy.yaml](taxonomy.yaml) | Full entity + relationship schema. Loaded by scanners at boot; defines the Cypher graph schema. |
| [phase1_architecture.drawio](phase1_architecture.drawio) | Draw.io diagram of Phase 1 topology (5 lanes, ingestion + query paths). |
| [skill_proposal.md](skill_proposal.md) | Concrete skill text changes + new tool definitions for `research_topic` and `rebuild_knowledge_graph`. |
| [open_questions.md](open_questions.md) | Remaining decisions before implementation starts. |

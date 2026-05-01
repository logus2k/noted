# GraphRAG Phase 1 Implementation Plan

Phases 1A-1F were implemented on 2026-04-23. This doc now serves as the shipped-state record. Design decisions live in [graph_rag_notes.md](graph_rag_notes.md), [taxonomy.yaml](taxonomy.yaml), and [open_questions.md](open_questions.md).

## Phase 1A — ArcadeDB service ✅

| Deliverable | File | Status |
|---|---|---|
| ArcadeDB service entry | `services/docker-compose.yml` | Shipped. Image pinned to `arcadedata/arcadedb:26.3.2` (stable; `:latest` points at SNAPSHOT nightly). Ports 2480 (HTTP) + 8182 (Gremlin). Root password set via `JAVA_OPTS` with ZGC flags preserved. |
| Bind-mounted data dir | `data/arcadedb/` | Shipped. Database auto-created via `defaultDatabases=noted[root]`. |

Verification: `curl -u root:noted-dev http://localhost:2480/api/v1/databases` returns `["noted"]`.

## Phase 1B — ArcadeDB adapter in noted-graph ✅

| Deliverable | File | Status |
|---|---|---|
| ArcadeDB HTTP client | `graph/app/arcadedb_client.py` | Shipped. Cypher + SQL endpoints, `ensure_schema()` bootstrap. |
| Persistence wrapper | `graph/app/graph_storage.py` | Shipped. `replace_project_graph()` does SQL-REMOVE / Cypher-DETACH-DELETE cleanup then bulk UNWIND MERGE entities + UNWIND MATCH+CREATE edges. `project_ids[]` list-valued so shared entities persist across projects. |
| Config + env wiring | `graph/app/config.py`, `services/docker-compose.yml` | Shipped. |

Verification: rebuilding `noted-testing` + `Examples` projects shows correct counts in `/graph/_arcadedb/status` (53/54 each, 72 total entities, 70 total edges due to shared MLflow entities).

**Design notes found during implementation:**
- ArcadeDB Cypher does NOT support list comprehensions. Array ops done via ArcadeDB SQL (`UPDATE ... REMOVE ... WHERE ... CONTAINS ...`).
- `MERGE` on edges was 30× slower than `MATCH + CREATE` (timing out at 30s per 200-row batch). Switched to CREATE since the prior `DETACH DELETE` guarantees no conflicts. 1208 edges now commit in <1s.
- Single `:Entity` vertex label, `:RELATES` edge label. `type` carried as a property. Simpler schema, no ArcadeDB type-registration churn.

## Phase 1C — md_scanner + Gemma extractor ✅

| Deliverable | File | Status |
|---|---|---|
| Markdown scanner | `graph/app/scanners/md_scanner.py` | Shipped. Walks `documents/**` + `data/documents/**`, ignores `data/testing/`, `data/environments/`, `data/projects/`, `node_modules/`, `.git/`. Heading-aware (level ≥3). TARGET=600 / MIN=200 / MAX=800 tokens. 100 docs → 1208 extraction chunks observed. |
| LLM client | `graph/app/llm_client.py` | Shipped. agent_server OpenAI-compatible. Model id: `gemma-4-e4b-it-q4-kxl-gguf` (direct, not a preset). `response_format={"type":"json_object"}` + balanced-brace fallback. |
| Gemma extractor | `graph/app/extractors/gemma_entity_extractor.py` | Shipped. Four types: concept / person / organization / term. Confidence floor 0.6 (configurable). Below-floor entries logged, not stored. |

Verification: 3-chunk sanity run produced 22 entities (e.g. "Model Serving Refactor", "NDJSON", "DeployEventStream", "MLflow") with reasonable types.

## Phase 1D — sameAs + PageRank + Leiden + community summaries ✅

| Deliverable | File | Status |
|---|---|---|
| sameAs edge pass | `graph/app/analytics/sameas.py` | Shipped. bge-m3 cosine on `name + description`. Three bands: high ≥0.90, medium 0.80-0.90, low 0.70-0.80. Preconditions: same type, normalize first, +0.05 bump for short-name/no-description. |
| PageRank + Leiden | `graph/app/analytics/graph_metrics.py` | Shipped. networkx 3.6.1 + igraph 1.0.0 + leidenalg 0.11.0. Thematic edges only (mentions / defines / documents / similar_to / sameAs / chunked_into). sameAs weighted into the partition (high=1.5, medium=1.0, low=0.3). |
| Community summarizer | `graph/app/extractors/gemma_community_summarizer.py` | Shipped. One Gemma call per community with ≥2 thematic members, caps prompt at 60 members for large communities. |
| /embed endpoint in noted-rag | `noted-rag/app/main.py` | Shipped. 1024-dim, normalized. Used by sameAs and retrieval. |

Note: Microsoft `graphrag` package NOT used — its transitive deps were too heavy for `python:3.12-slim`. We implemented sameAs / PageRank / Leiden directly. `graph/Dockerfile` switched from alpine to slim to get manylinux wheels.

## Phase 1E — Retrieval endpoint + MCP tool ✅

| Deliverable | File | Status |
|---|---|---|
| `/research/query` + retriever | `graph/app/retrieval/retriever.py`, `graph/app/routers/research.py` | Shipped. Global (community routing) + local (N-hop traversal) + auto (both, return higher-citation-count). |
| GraphRAG manager | `backend/app/managers/graphrag_manager.py` | Shipped. async httpx, graceful degradation. |
| `research_topic` MCP tool | `backend/app/mcp/tools.py`, `backend/app/managers/llm_tools.py` | Shipped. Read-only, fast. |
| `docs-rag` skill routing rubric | `data/skills/docs-rag/SKILL.md` | Shipped. Updated to route search_docs (facts) vs research_topic (themes). |

**Reversed mid-implementation:** `rebuild_knowledge_graph` was initially exposed as a chat write-tool with the approval panel. Framing was wrong — rebuild is an admin operation, not a user flow. **Removed from MCP.** Kept the backend plumbing (`GraphRagManager.rebuild()`, `/research/rebuild`). Future placement: context menu on Explorer Graph node with noted-password gate (mirroring KB Import).

Verification: 4 queries via `/research/query` returned cited, grounded answers in 5-7s each. Auto mode correctly selected local for specific-entity questions.

## Phase 1F — Manual validation + iteration (in progress)

| Deliverable | Status |
|---|---|
| Progress-monitoring web page | Shipped. `frontend/graph_rebuild_progress.html`. Polls `/research/status` every 2s. Serve via `npx serve -p 4005` from `frontend/`. |
| First full rebuild over the corpus | Running 2026-04-23 — 1208 chunks, ETA ~40 min at 30 chunks/min observed. |
| Ad-hoc query session + param retune | After rebuild finishes. |
| `research_topic.yaml` harness scenarios | After manual validation is done (per Q 21 deferral). |

Full rebuild is kicked off via CLI only:
```
curl -s -X POST http://localhost:5523/research/rebuild -m 14400 > /tmp/rebuild_stats.json
```

## Out of scope for Phase 1 (tracked elsewhere)

- ArcadeDB pre-rebuild backup + auto-restore ([noted_backlog.md](../noted_backlog.md))
- Per-source auto-update (FR-9 / Phase 1.5)
- Admin UI for rebuild (context menu on Explorer Graph node + noted-password gate)
- `research_topic.yaml` harness scenarios (post-manual-validation)

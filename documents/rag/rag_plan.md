# noted RAG Plan

## 1. Goal

Make noted's documentation searchable from the Assistant. User asks a conceptual / procedural / troubleshooting question whose answer lives in the user manual, architecture doc, developer manual, design docs, or skill references - the Assistant retrieves the relevant chunks and grounds its reply in them.

## 2. Non-goals

- Not a replacement for skills or tools. Live state stays with tools; curated skill content stays with the skill system.
- Not a general web search. Corpus is only noted's shipped documentation.
- Not a reindex-on-every-change watcher. Ingest is an explicit step (manual or via a simple endpoint).

## 3. Hard constraint: zero regression risk to noted

The feature must not be able to break any existing noted capability, even if it fails catastrophically. This dictates the architecture.

| Guarantee | How it's enforced |
|---|---|
| RAG dependency failure cannot crash noted | Runs in a **separate container** (`noted-rag`) with its own Python env, its own image |
| RAG resource use cannot pressure noted | Separate process, separate GPU handle, separate memory |
| RAG being down cannot block a chat turn | Assistant tool call degrades gracefully (returns `status=unavailable` + empty chunks) |
| Zero change in existing noted code paths | All noted-side edits are **additive** (new manager, new tool entry, new router line, new skill file). No modification to existing routers, tools, or skills. |
| Kill switch | Remove `noted-rag` from compose; noted behaves as before RAG existed |

## 4. Architecture

```
user ─► noted (backend)                           mlflow / airflow / evidently / minio / ...
          │                                              │
          │   search_docs tool                           │
          │        │                                     │
          │        ▼                                     │
          │   RagManager (httpx) ─► POST /search ─────►  noted-rag container
          │                                              │   FastAPI +
          │                                              │   bge-m3 (GPU)
          │                                              │   bge-reranker-v2-m3 (GPU)
          │                                              │   chromadb (PersistentClient)
          │                                              │
          │                                              ▼
          │                                         data/chroma/ (bind mount)
          │                                         data/rag_models/ (named volume)
          ▼
      docs-rag skill (priority 1, trigger: workspace_active)
```

### Components

| Component | Role | Where it lives |
|---|---|---|
| `noted-rag` container | Hosts the embedder, reranker, ChromaDB client; exposes `/search`, `/ingest`, `/health` over HTTP | New subdir `noted-rag/` at repo root |
| `RagManager` | Thin async httpx client in noted; graceful degrade on error | `backend/app/managers/rag_manager.py` |
| `search_docs` MCP tool | How the Assistant reaches RAG | `backend/app/mcp/tools.py` + dispatch in `backend/app/managers/llm_tools.py` |
| `docs-rag` skill | Tells the model **when** to call `search_docs` and when not to | `data/skills/docs-rag/SKILL.md` |

## 5. Models

| Layer | Model | Dims / context | License |
|---|---|---|---|
| Dense embedder | `BAAI/bge-m3` | 1024, 8k tokens | MIT |
| Reranker | `BAAI/bge-reranker-v2-m3` | cross-encoder | MIT |

Both run on GPU when available (env `DEVICE=cuda`), fall back to CPU (`DEVICE=cpu`) if not. Models download on first use and cache under `/data/rag_models/` (container path; named volume `rag-models` on host side).

## 6. Collections

Four collections, keyed by audience, all in the same ChromaDB instance at `data/chroma/`.

| Collection | Contents | Primary consumer |
|---|---|---|
| `user_docs` | User manual pages (`documents/user-manual/*.md`) | End user via Assistant |
| `developer_docs` | `documents/architecture/`, `documents/hydra/`, `documents/dap/`, `documents/evidently/`, `documents/explorer/`, `documents/developer/`, design docs, etc. | Developer via Assistant |
| `skills_library` | `data/skills/*/SKILL.md` + `data/skills/*/references/*.md` | Assistant internal grounding |
| `testing` | `testing/assistant/architecture/*.md` | Test engineers |

Four collections over one-shared-collection-with-filter because:
- Prevents cross-audience leakage at retrieval time (user chat never surfaces internal design docs).
- Cleaner filtering semantics (no complex `where` clauses).
- Storage cost is identical.

## 7. Record schema

```python
{
  "id":        "<source_path>#<section_path_slug>",
  "document":  "<raw markdown chunk>",
  "embedding": <list[float] of 1024>,
  "metadata": {
    "source_path":    "documents/architecture/noted_technical_architecture.md",
    "section_path":   "Service integrations > MLflow",
    "title":          "MLflow",
    "audience":       "developer",
    "doc_type":       "architecture",
    "domain":         "mlflow",
    "tags":           "comma,separated,strings",
    "content_hash":   "a1b2c3d4e5f6",
    "last_modified":  "2026-04-21T14:32:00Z"
  }
}
```

### Enum ranges

- `audience`: `user`, `developer`, `assistant`, `testing`
- `doc_type`: `manual`, `architecture`, `design`, `skill`, `reference`, `troubleshooting`, `test`
- `domain`: `platform`, `notebook`, `mlflow`, `hydra`, `dvc`, `airflow`, `evidently`, `minio`, `serving`, `assistant`, `knowledge_graph`, `none`

### ID scheme

`<source_path>#<slug(section_path)>` - stable, idempotent for upsert. Examples:

- `documents/architecture/noted_technical_architecture.md#service-integrations-mlflow`
- `data/skills/airflow-dag-creation/SKILL.md#root` (whole-file record for skills)
- `data/skills/airflow-dag-creation/references/complete_example.md#imports`

### content_hash

MD5 (first 12 chars) of the chunk text. Used during re-ingest to skip unchanged chunks (no re-embed, no upsert).

## 8. Chunking rules

Priority order:

1. **Skills (`SKILL.md`)**: one record per file. Never split. They're already ~400 tokens capped and authored as atomic injections.
2. **Default**: split on `##` headings. Each section becomes one chunk. Heading path carried in `section_path`.
3. **Oversized (>1000 tokens)**: split at `###` if present. If no `###`, fall back to sliding window (800 tokens, 80-token overlap).
4. **Tiny (<150 tokens)**: merge forward into next chunk of the same file.
5. **Code blocks**: never split mid-block. Fences kept with their explanation.

Sizes in approximate tokens (1 token ~= 4 chars):

| Param | Value |
|---|---|
| Target | 700 |
| Max | 1000 |
| Min | 150 |
| Overlap | 80 (sliding window only) |

## 9. Ingest pipeline

Owner: **noted-rag** (noted backend never imports chromadb or sentence-transformers).

### Trigger

Three ways, all idempotent:

| Trigger | How |
|---|---|
| Manual CLI | `python3 noted-rag/scripts/ingest.py` (runs inside or against the container) |
| HTTP | `POST http://noted-rag:8200/ingest` returns job_id, run in background task |
| Startup | **None** - ingest is never automatic on container start. Keeps cold-boot fast. |

### Flow

```
1. Walk sources          docroot glob -> files
2. Chunk                 per rules in section 8
3. Derive metadata       from file path + section context
4. content_hash          per chunk
5. Diff vs existing      pull existing (id, content_hash) from each collection
6. Embed changed         batch through bge-m3 (batch_size=32)
7. Upsert                chroma.upsert(ids=, documents=, embeddings=, metadatas=)
8. Cleanup               delete ids that existed before but weren't produced this run
9. Return summary        {indexed, skipped_unchanged, deleted_stale, collections}
```

### Sources

| Path glob | Audience | doc_type | Collection |
|---|---|---|---|
| `documents/user-manual/*.md` | user | manual | `user_docs` |
| `documents/architecture/*.md` | developer | architecture | `developer_docs` |
| `documents/hydra/*.md` | developer | design | `developer_docs` |
| `documents/dap/*.md` | developer | design | `developer_docs` |
| `documents/evidently/*.md` | developer | design | `developer_docs` |
| `documents/explorer/*.md` | developer | design | `developer_docs` |
| `documents/developer/*.md` | developer | manual | `developer_docs` |
| `documents/serving_worker/*.md` | developer | design | `developer_docs` |
| `documents/rag/*.md` | developer | design | `developer_docs` |
| `data/skills/*/SKILL.md` | assistant | skill | `skills_library` |
| `data/skills/*/references/*.md` | assistant | reference | `skills_library` |
| `testing/assistant/architecture/*.md` | developer | test | `testing` |

## 10. Query path

```
client POST /search {query, audience, top_k=5}
   │
   ▼
embed(query) -> 1024-dim vector
   │
   ▼
collection.query(query_embeddings=[q], n_results=20)  ← cheap recall
   │
   ▼
reranker.predict([(query, doc) for doc in 20])        ← expensive precision
   │
   ▼
sort by score desc, take top_k=5
   │
   ▼
return [{id, source_path, section_path, title, score, text}, ...]
```

Latency budget:
- Embed query: ~20 ms (GPU) / ~80 ms (CPU)
- Chroma query: ~5 ms
- Rerank 20 candidates: ~50 ms (GPU) / ~400 ms (CPU)
- Total P50 target: <100 ms on GPU, <500 ms on CPU.

## 11. Failure contract

Every failure mode degrades gracefully to "RAG unavailable, Assistant continues without it".

| Failure | Behaviour |
|---|---|
| noted-rag container down | `RagManager.search` catches `httpx.HTTPError` -> returns `{status: "unavailable", chunks: []}` |
| noted-rag timeout (>8s) | Same - caught by httpx.TimeoutException inside httpx.HTTPError |
| Bad query / 500 in service | Same |
| Empty collection (not yet ingested) | Service returns `{status: "ok", chunks: []}` - tool result says "no docs indexed yet" |

Tool result when unavailable:

```
"Documentation search is currently unavailable. Answer from existing
context, active skills, or the conversation so far; or ask the user
to retry later."
```

The Assistant sees this exactly like any other tool-returned string and plans the next step.

## 12. Kill switch

`docker compose stop noted-rag` (or removing the service block from the compose file) leaves noted fully functional. The `search_docs` tool will return `unavailable` on every call; the Assistant handles that per section 11. No other feature is impacted.

## 13. File changes

### New files

| Path | Role |
|---|---|
| `noted-rag/Dockerfile` | python:3.12-slim base, installs torch+cuda wheels, chromadb, sentence-transformers, FastAPI |
| `noted-rag/requirements.txt` | Pinned deps |
| `noted-rag/app/main.py` | FastAPI app, endpoints `/health`, `/search`, `/ingest`, `/ingest/status/:id`, `/collections` |
| `noted-rag/app/rag_service.py` | RagService (lazy-load models + chroma client, embed, search, rerank) |
| `noted-rag/app/ingest.py` | Walk sources, chunk, embed, upsert, cleanup |
| `noted-rag/app/config.py` | Env-driven config |
| `noted-rag/scripts/ingest.py` | CLI wrapper |
| `backend/app/managers/rag_manager.py` | Async httpx client, graceful degradation |
| `data/skills/docs-rag/SKILL.md` | Priority 1, trigger `workspace_active`, instructs when to call `search_docs` |
| `documents/rag/rag_plan.md` | This document |

### Modified files (additive only)

| Path | Change |
|---|---|
| `backend/app/mcp/tools.py` | Add one `types.Tool(name="search_docs", ...)` entry |
| `backend/app/managers/llm_tools.py` | Add one dispatch branch calling `RagManager.search(...)` |
| `backend/app/routers/llm.py` | Instantiate `RagManager` and put it in `_managers["rag"]` (one import, one line) |
| `services/docker-compose.yml` | Add `noted-rag` service block |
| `services/docker-compose.gpu.yml` | Add GPU device reservation for `noted-rag` |

### Unmodified

Every existing router, manager, skill, scenario, and frontend module is untouched.

## 14. Skill body

`data/skills/docs-rag/SKILL.md`:

```markdown
---
name: docs-rag
description: When the user asks a conceptual, procedural, or troubleshooting
  question whose answer lives in noted's documentation, call search_docs and
  ground the reply in the returned chunks.
triggers: [workspace_active]
priority: 1
max_tokens: 200
---
When the user asks a conceptual, procedural, or troubleshooting question
about noted (user manual content, architecture, design rationale,
troubleshooting), call:

  search_docs(query, audience="user"|"developer")

Use audience="developer" when the user asks about internals, code paths,
design decisions, or how a service is wired. Use audience="user" for
everything else.

Cite the source in your reply using the returned section_path.

DO NOT call search_docs for:
  - Live state (use get_run_details, get_dag_status, list_dags, etc.)
  - The user's own notebook cells or source files
    (use get_notebook_cells, get_file_contents, get_hydra_config)
  - Topics already covered by an active skill - its curated content wins
```

## 15. Rollout steps

1. Scaffold `noted-rag/` (Dockerfile, requirements, app/*) - zero impact on noted.
2. Add compose entry for `noted-rag` in `services/docker-compose.yml` + GPU override.
3. Build + start `noted-rag`: `docker compose up -d --build noted-rag`. Verify `/health`.
4. First ingest: `curl -X POST http://noted-rag:8200/ingest` (from inside compose network) or via the CLI script. Verify chunk counts per collection via `/collections`.
5. Manual search test: `curl -X POST http://noted-rag:8200/search -d '{"query":"how do I deploy a model","audience":"user","top_k":5}'`.
6. In noted: add `managers/rag_manager.py`, register in `_managers`, add `search_docs` tool + dispatch, add `docs-rag` skill.
7. Rebuild noted: `docker compose up -d --build noted`.
8. End-to-end test via Assistant chat: ask a manual-shaped question; verify `search_docs` fires, chunks are returned, answer cites section_path.
9. Kill-switch test: `docker compose stop noted-rag`; ask the same question; verify Assistant handles `unavailable` gracefully.

## 16. Verification checklist

- [ ] `noted-rag/` image builds without noted dependencies.
- [ ] `noted-rag` `/health` returns `{status: ok}` on startup (no ingest required).
- [ ] `/ingest` completes, `/collections` shows non-zero counts per expected collection.
- [ ] `/search` returns ranked chunks with plausible section_paths.
- [ ] `RagManager.search` returns `status=unavailable` when `noted-rag` is stopped - no exception escapes.
- [ ] `search_docs` tool appears in the Assistant's tool list and fires on appropriate queries.
- [ ] `docs-rag` skill is auto-injected (visible in `skills` SSE event).
- [ ] Assistant gracefully handles `unavailable` (no crash, no error to the user).
- [ ] Pre-existing test harness (`testing/assistant/*`) still passes.

## 17. Out of scope / future

- Incremental re-ingest on file save (watcher). Manual/endpoint-triggered for now.
- Hybrid retrieval (dense + BM25 / sparse). bge-m3 can output sparse vectors; easy to add later.
- Frontend panel for browsing collections / inspecting chunks. Not required for Assistant integration.
- Multilingual corpus. Corpus is English today; bge-m3 supports it for free when needed.
- Skill body -> skill references migration. Keep skills as-is; add references retrieval later if token budget gets tight.

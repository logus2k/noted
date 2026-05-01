# RAG Status and Evolution

## Document Information

| Field | Value |
|-------|-------|
| Scope | Current state of noted's RAG layer and the evolutions discussed but not yet built |
| Companion doc | [rag_plan.md](rag_plan.md) (original design) |
| Layers covered | `noted-rag` sidecar, `RagManager`, `/api/rag` proxy, `search_docs` tool, `docs-rag` skill, `Assistant/Embeddings` Explorer node |

---

## 1. What is shipped

### 1.1 Runtime components

| Component | Location | Role |
|-----------|----------|------|
| `noted-rag` container | `noted-rag/app/` | FastAPI sidecar. Dense retrieval (bge-m3) + cross-encoder rerank (bge-reranker-v2-m3), both on CUDA. Owns its own Python env; failure is isolated from noted. |
| ChromaDB store | Docker volume `rag-chroma` mounted at `/data/chroma` | Persistent vector store, single collection `noted_corpus`. |
| Model cache | Docker volume `rag-models` mounted at `/data/rag_models` | HuggingFace hub cache for bge-m3 (~1.5 GB) and bge-reranker-v2-m3 (~1.2 GB). |
| `RagManager` | `backend/app/managers/rag_manager.py` | Async httpx client. Graceful unavailable on any transport error so a missing sidecar cannot break a chat turn. |
| `/api/rag` proxy | `backend/app/routers/rag.py` | Forwards a minimal read-only surface from the browser through noted to `noted-rag`. |
| `search_docs` tool | `backend/app/mcp/tools.py`, `backend/app/managers/llm_tools.py` | MCP tool the Assistant calls to retrieve grounded chunks. |
| `docs-rag` skill | `data/skills/docs-rag/SKILL.md` | Priority 1, trigger `workspace_active`. Tells the model when to call `search_docs` and when not to (active skills on the topic win over retrieval). |
| `Assistant/Embeddings` tree | `frontend/js/panels/ExplorerPanel.js` | User-visible view of the index. Lazy tree: documents at level 1, chunks at level 2, full chunk text on click. |

### 1.2 Corpus stats at current ingest

| Metric | Value |
|--------|-------|
| Sources | 9 markdown files |
| Total chunks | 407 |
| Chunking | Split at level-2 headings, sliding-window fallback for oversized sections, minimum-size merge |
| Per-chunk metadata | `source_path`, `section_path`, `title`, `doc_type`, `content_hash`, `last_modified` |
| Tag dimensions today | `doc_type` (single-valued) |
| Rerank score threshold | `RERANK_MIN_SCORE` on top-1; falling below returns an empty set (the tool surfaces "no strong match" so the model does not hallucinate from noise) |

### 1.3 Endpoints

**`noted-rag` (internal, not browser-reachable):**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness (no model load required) |
| POST | `/search` | Dense + rerank retrieval (used by `search_docs` tool) |
| POST | `/ingest` | Kicks off a background re-ingest, returns `job_id` |
| GET | `/ingest/status/{job_id}` | Polls an ingest job |
| GET | `/collections` | Collection names + counts |
| GET | `/index/sources` | Explorer tree level 1 (distinct source files + chunk counts) |
| GET | `/index/sources/{source_b64}/chunks` | Explorer tree level 2 (chunks for one source) |
| GET | `/index/chunks/{chunk_b64}` | Click-through: full text + metadata for one chunk |

**noted-side proxy (browser-reachable):**

| Method | Path | Proxies |
|--------|------|---------|
| GET | `/api/rag/health` | `noted-rag /health` |
| GET | `/api/rag/index/sources` | `noted-rag /index/sources` |
| GET | `/api/rag/index/sources/{source_b64}/chunks` | `noted-rag /index/sources/{source_b64}/chunks` |
| GET | `/api/rag/index/chunks/{chunk_b64}` | `noted-rag /index/chunks/{chunk_b64}` |

Base64-urlsafe encoding on source paths and chunk ids keeps `/` and `#` out of URL path segments.

### 1.4 End-to-end flow verified

- Question whose topic is covered by an active skill (e.g. "how do I deploy a registered model?") - model answers from the skill, does not call `search_docs`. This matches the `docs-rag` rule "skip retrieval if a curated skill already covers the topic".
- Question whose answer lives only in documentation (e.g. "what do the coloured dots on the baseline badge mean?") - model calls `search_docs`, receives the matching user-manual chunk at a high rerank score, answer is grounded in the chunk text.

---

## 2. Design decisions and their trade-offs

### 2.1 Single collection, not audience-split

Earlier drafts explored four collections (`user_docs`, `developer_docs`, `skills_library`, `testing`). We collapsed to one `noted_corpus` collection.

| Benefit | Cost |
|---------|------|
| Cross-audience search (one query hits both user manual and developer manual when the topic spans both) | Loses a cheap hard filter; narrowing must go through metadata tags rather than collection choice |
| Simpler ingest, one upsert path | Tag quality becomes more load-bearing |

### 2.2 Skills are NOT indexed as RAG chunks

Skills live under `Assistant/Skills` with their own loader and detail view. The index intentionally omits skill files.

| Reason | Consequence |
|--------|-------------|
| Avoid double representation in Explorer | Skill content stays source-of-truth in one place |
| `docs-rag` skill explicitly says "active skills win over retrieved chunks" | Retrieval over skill text would produce content the skill rule tells the model to ignore |

If in the future we want skill chunks reachable for inspection, each skill node could expose its own `chunks` view via a different endpoint without changing the `Embeddings` tree shape.

### 2.3 Explorer tree shape: `Embeddings -> document -> chunks`

Two levels only. No collection layer, no `By doc_type` facet, no `By domain` facet.

| Alternative considered | Why deferred |
|------------------------|--------------|
| `Embeddings -> collection -> document -> chunks` | Index has a single collection today; the layer would be a noop |
| `Embeddings -> doc_type group -> document -> chunks` | Would fight the document-name-first mental model; doc_type belongs as a chip/filter, not a hierarchy |
| Filter bar above the tree (multi-select `doc_type` + `domain`) | Real value, but requires multi-valued tag support per chunk before it earns its weight |

### 2.4 Three endpoints, lazy per level

| Alternative | Rejected because |
|-------------|------------------|
| One endpoint returning the whole tree with per-chunk metadata | Couples tree fetch to per-chunk fetch; chunk text is the heaviest payload and most rarely needed |
| Two endpoints (tree + detail) | Acceptable, but one more round trip only when a source is actually expanded is cheaper than an always-paid source-enumeration cost inside the tree response |

### 2.5 Graceful-unavailable everywhere the path crosses the sidecar

`RagManager` returns structured `{"status": "unavailable", ...}` on any transport error rather than raising. `search_docs` turns that into "Documentation search is currently unavailable" in the tool result; the skill instructs the model to proceed with what it has rather than surface the outage.

---

## 3. Discussed evolutions (not yet built)

### 3.1 Multi-valued tags per chunk

Current ingest stores one `doc_type` per chunk (single value). The position we agreed on:

- Chunks should be able to carry several tag values across several dimensions.
- Doc types and domains are two dimensions we will revisit; more may surface.
- Filter semantics become "any-of within dimension, all-of across dimensions" once cardinality > 1.

**Touchpoints to revisit when enabling:** `ingest._SOURCES` (shape change from tuple to dict), `_build_records` (attach a list instead of a single string), `rag_service._parse_tags_to_where` (Chroma `where` filters on list-valued metadata use a different operator), `search_docs` tool description (the `tags` arg semantics), the Explorer chip rendering, and any filter bar.

### 3.2 Filter bar above the `Embeddings` tree

A two-part picker at the top of the panel, matching the same taxonomy the model uses in `search_docs(tags=[...])`. Narrowing the tree via the same filter shape the model applies is a testing and trust-building tool, not just a UX nicety.

**Endpoint change:** new `GET /index/taxonomy` returns `{doc_types: [{name, count}], domains: [{name, count}]}`. Existing `/index/sources` and `/index/sources/{b64}/chunks` accept optional `?doc_type=...&domain=...` query params and reflect the filter in returned counts so the aggregate totals stay honest.

### 3.3 Tag chips as leaf decorations

Small tag pills on each source (or each chunk) row inside the tree. Pure decoration; does not filter. Works alongside or without the filter bar.

### 3.4 Document-order ordinal per chunk

Ingest does not currently stamp an ordinal, so chunks under a source are returned in alphabetical order of `section_path`. Adding `ord: int` to the metadata during chunking gives true document order without changing the response shape of the Explorer endpoints.

**Caveat:** existing chunks keep their old metadata because the ingest idempotency check only re-embeds on changed `content_hash`. Enabling `ord` cleanly would need either a one-time forced re-embed or a metadata-only upsert pass.

### 3.5 Skill chunks reachable from `Assistant/Skills`

Out of scope for the `Embeddings` tree. If we later want chunks of a specific skill visible from inside that skill's node, each skill in the `Assistant/Skills` tree could gain its own expandable `Chunks` child populated via a separate endpoint. This would not touch the `Embeddings` tree.

### 3.6 Token counts stored at ingest time

Today `token_count` is computed on the fly as `len(text) // 4`. Cheap, and good enough for a display hint. If we start showing aggregate token counts at the source or tree level, stamp the count at ingest time and let the endpoint sum them instead of fetching chunk bodies.

### 3.7 Basename disambiguation for same-named files

No collisions in the current corpus (the 9 basenames are unique) so the default "show basename in the tree" is unambiguous. If the corpus ever grows to include two files that share a basename, append a dirname hint to disambiguate in-place; do not expose full paths in the tree.

---

## 4. Known caveats

| Caveat | Mitigation |
|--------|------------|
| `last_modified` is the source file's mtime at ingest, not the ingest timestamp itself | Source mtime is the freshness signal users actually want (when did the content change). If ingest time is also needed, add a separate `ingested_utc` field. |
| Deleting a source file does not remove its chunks until a re-ingest runs | The ingest cleanup pass deletes stale ids; no auto-watcher today. |
| Re-embedding skips unchanged content via `content_hash` | Metadata-only changes (like adding a new tag dimension) will not propagate without a forced re-embed. |
| Chunks under a source are alphabetical by section path | Approximates document order for hierarchical documents; see 3.4. |
| Single-rerank threshold for every query | Works well for the current corpus; queries with very short keyword inputs can sometimes fall below threshold even when a relevant chunk exists. A per-query adaptive threshold is a follow-up if this becomes an observed problem. |

---

## 5. Glossary

| Term | Meaning |
|------|---------|
| Source | A single document indexed in the corpus (a markdown file listed in `_SOURCES`) |
| Chunk | One retrieval unit: a section or sliding-window slice of a source, with its own metadata and embedding |
| `section_path` | ` > `-joined heading trail that locates a chunk inside its source |
| `doc_type` | Tag dimension identifying the document family (`user-manual`, `architecture`, `developer-manual`, etc.) |
| `content_hash` | 12-char MD5 of chunk text, used to short-circuit re-embedding of unchanged chunks |

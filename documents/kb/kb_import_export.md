# KB Ingestion Performance + Document Import/Export — Integrated Plan

## 1. Outcome the work targets

| Workflow | Today | After this plan |
|---|---|---|
| Add a fresh PDF to a domain | 30-45 min | **4-6 min** |
| Re-add a previously-exported document (`.notedoc`) | not possible | **1-2 min** |
| Recluster a domain | 1h 42m | **15-25 min** |
| Share a curated document with another instance | full re-ingestion on the receiving side | **1-2 min import on receiver** |
| User-visible progress during long phases | extraction-only | **every phase, sub-step granularity** |

The two pain points being solved: ingestion is slow and ingestion is opaque. After the plan, both are addressed and a third capability appears (portable, shareable doc archives).

## 2. Why ingestion is slow today (verified pipeline trace)

For a 735-chunk PDF the steady-state is ~30-45 min, dominated by two stages:

| Stage | What happens | Wall time | Cause |
|---|---|---|---|
| **LLM entity extraction** | `_extract_from_chunks` does a serial `for chunk in chunks: chat_json(...)` | 12-24 min | llama-server has 4 slots; serial loop uses 1 |
| **ArcadeDB edge merge** | `add_doc_merge` step 4 inserts mention edges via `UNWIND + MATCH + MATCH + CREATE` | ~12 min for 5000 edges | 2 index lookups per edge × 5000 edges = 10000 probes |
| Docling parse | `scan_pdf` produces chunks | 30-90s | inherent to PDF parsing |
| bge-m3 embedding compute | one batched call | 10-30s | already efficient |
| ChromaDB upsert | one batched call | 10-30s | already efficient |

The other phases (sameAs, similar_to, leiden, community detection) are minor.

## 3. Verification probes that informed the plan

Run against ArcadeDB v26.3.2 with the `ml` database during plan design. Results recorded for repeatability.

| Probe | Result | Implication |
|---|---|---|
| `Entity[id]` UNIQUE index exists? | ✅ Yes (`Entity[id]: unique=True`) | Missing index is NOT the cause. Cost is genuinely the UNWIND+MATCH pattern. |
| `POST /api/v1/batch/<db>` HTTP endpoint in v26.3.2? | ✅ Yes — accepts NDJSON, returns `{verticesCreated, edgesCreated, elapsedMs, idMapping}` | The fast path (GraphBatch) is reachable from Python over HTTP. |
| GraphBatch with property edges (`lightEdges=false`) | ✅ Works | Our mention edges (with `confidence` + `properties_json`) are supported. |
| Realistic-size benchmark (200 vertices + 1000 edges) | **61ms wall, 44ms server** | vs ~140s for the same volume on the current path. ~2300× raw throughput. |
| MERGE on duplicate `@id` (re-send) | ❌ Throws `DuplicatedKeyException` | GraphBatch is **CREATE-only**. Need pre-fetch + Python-side merge for entity overlap. |
| `@from`/`@to` referencing pre-existing vertex by `@id` (across batches) | ❌ "Unknown temporary ID — vertices must appear before edges that reference them" | Cross-batch `@id` resolution doesn't work. |
| `@from`/`@to` as RID string (`"#1:967834"`) for pre-existing vertex | ✅ Works | This unblocks the hybrid: pre-fetch RIDs of existing entities, use RID strings in edge payload. |

**Net**: GraphBatch HTTP is real, fast, accessible from Python, and supports the hybrid pattern needed for our merge semantics.

## 4. Phases

### Phase 0a — Preflight scan (fail-fast before long ingestion)

Today an ingestion failure can cost 30-60 minutes before the actual error surfaces (corrupt PDF, LLM regression, ArcadeDB schema drift, embedding service down, doc already exists). Most of those problems are detectable in **5-15 seconds** of cheap checks before any expensive work begins.

**New endpoint**: `POST /api/domains/{id}/documents/preflight?path=<file>` (or `?archive=<filename>` for `.notedoc` imports).

Runs in this order, stops at the first hard-fail:

| Check | Typical cost | Catches |
|---|---|---|
| Docling probe — parse first page only (`scan_pdf(page_range=[0,1])`) | 3-5s | Corrupt / encrypted / unsupported PDFs |
| Gemma `chat_json` smoke — single tiny prompt, validate response is clean JSON with `entities` field, refuse if `<think>` text present | 1-2s | Chat-template-swap-style regressions; agent_server preset misconfiguration; cold-start failures |
| ArcadeDB write probe — `INSERT 10 vertices + 20 edges, DELETE` against the target domain's DB | 0.5-1s | Server reachable, auth correct, edge-creation works, no rebuild lock held by something else |
| Schema + index sanity — verify `Entity[id]` UNIQUE + `RELATES[type]` indexes exist | 0.2s | Schema drift after a manual op; bootstrap incomplete |
| noted-rag embedding probe — embed a 100-token sample, verify dim matches expected | 1-2s | Embedding model loaded, GPU available, no CUDA OOM, model name agrees with `producer.embedding_model` for `.notedoc` imports |
| Manifest collision check | <0.1s | Doc already exists in domain → user picks Replace / Skip / Cancel **before** committing |
| Disk space + size estimate | <0.1s | Refuse if estimated chunks/entities × bytes-per-row exceeds free space; warn if estimate is way over typical |
| For `.notedoc` only: schema_rev + producer.embedding_model + checksum | <0.5s | Reject incompatible archives upfront (vs midway through import) |

**Output** — structured report consumed by the UI:

```json
{
  "ok": true,
  "checks": [
    {"name": "docling.first_page", "status": "ok", "elapsed_ms": 3120, "detail": "3 tables, 12 figures"},
    {"name": "gemma.json", "status": "ok", "elapsed_ms": 1850},
    {"name": "arcadedb.write_probe", "status": "ok", "elapsed_ms": 18},
    {"name": "schema.indexes", "status": "ok"},
    {"name": "noted_rag.embed", "status": "ok", "elapsed_ms": 1100, "detail": "bge-m3-q8 1024-dim"},
    {"name": "manifest.collision", "status": "warn", "detail": "Doc exists in this domain", "user_decision": ["replace", "skip", "cancel"]},
    {"name": "estimate", "status": "ok", "detail": "~750 chunks, ~2500 entities"}
  ],
  "estimate": {"chunks": 750, "entities": 2500, "wall_seconds_minutes": "4-6"}
}
```

**Always run automatically** as the first step of `add_doc_pdf` / `.notedoc` import. Surfaces in the UI as a small banner during the 5-15 seconds before the actual ingestion progress kicks in. If any check is `error`, ingestion aborts with the report. If any check is `warn`, user sees the report and can confirm or cancel.

**UX**: The Explorer right-click "Import .notedoc" or "Add document" flow shows the preflight report in the same modal as the existing pre-import summary (Phase 4.2). For import via API/curl, the report is the response body.

**Files**:
- `noted/graph/app/preflight.py` (new) — orchestrator + check implementations
- `noted/graph/app/routers/research.py` — new route
- `noted/backend/app/routers/kb.py` — proxy route
- `noted/frontend/js/...` — banner component in import modal

**Effort**: ~250 LOC + tests. **~4-5 hours** focused work.

**Risk**: low — all checks are read-only or write-then-delete cleanup. If the orchestrator itself fails, fall through to running the import anyway with a "preflight unavailable" warning.

### Phase 0b — Progress visibility (cheapest UX win)

Today only the LLM extraction stage reports usable progress (`chunks_done/total`). All other long phases (writing 12-15 min, recluster's analytics layer 80 min, caching 30s+) appear as a phase-name label with no movement, indistinguishable from a hang. The instrumentation already added to `add_doc_merge`, `replace_analytics_layer`, `replace_project_graph`, and `_push_caches` logs every step's timing — but those values are not promoted to `self.progress`, so the UI never sees them.

**Implementation** (light-touch, ~150 LOC backend + 80 LOC frontend):

Each long-running loop writes sub-progress fields into `self.progress`:

```python
self.progress.update({
    'sub_phase': 'writing.mention_edges',
    'sub_done': ci,
    'sub_total': n_chunks_4,
    'sub_eta_seconds': int(eta_per_chunk * (n_chunks_4 - ci)),
})
```

Same pattern in:
- `_extract_from_chunks` — keep existing `extraction_chunks_done/total` fields
- `add_doc_merge` — sub-phase per step (`inserting_chunks`, `merging_entities`, `mention_edges`)
- `replace_analytics_layer` — sub-phase per step1a/1b/2/3/4
- `replace_project_graph` — sub-phase per step
- `_push_caches` — sub-phase per cache push (`entities`, `summaries`)
- `upsert_chunks` — sub-phase per vector batch

**Frontend** (KB Monitor):

```
Phase: writing
Sub: inserting mention edges  [████████░░░░] 47/141  ~6m 30s remaining
```

Conditional rendering — falls back gracefully when older noted-graph code (without sub-phase fields) is still running.

**Why polling, not SSE**: KB Monitor already polls `/api/domains/{id}/status` every 2s. Per-chunk granularity is ~28s, so 2s polling visually keeps up. Memory `feedback_progress_streaming.md` mandates SSE for "long operations needing progress" — that rule applies to **user-initiated** explicit operations (e.g. `.notedoc` import — see Phase 3, which uses SSE). For ambient KB-rebuild telemetry, polling-enrichment is the lower-cost path and is good enough.

**Effort**: ~1 day. **Risk**: low. **Deploy**: `noted-graph` rebuild + frontend in `noted` rebuild.

### Phase 1 — Parallel LLM entity extraction

**Problem**: serial `for chunk in chunks: chat_json(...)` loop wastes 3 of 4 llama-server slots.

**Fix**: bounded `ThreadPoolExecutor` matching slot count. Threading is the right primitive here because the existing `LLMClient` uses sync `requests.post` and the GIL releases on I/O. No async refactor needed.

**Code shape** (`research_builder.py`):

```python
def _extract_one(chunk):
    return chunk, self._extractor.extract(chunk.text or '')

with ThreadPoolExecutor(
    max_workers=ENTITY_EXTRACT_PARALLELISM,
    thread_name_prefix='gemma-extract',
) as pool:
    extraction_iter = pool.map(_extract_one, chunks)
    for chunk, extracted in extraction_iter:
        # ... aggregation loop stays serial (mutates shared dicts) ...
```

The aggregation loop stays serial because `extracted_nodes`, `mention_strength`, `mention_rels` are mutated. Aggregation is fast (Python-side dict updates); only the LLM call is the bottleneck.

**Thread safety in extractor**: `_below_floor_log` mutation needs `threading.Lock`. Other state (`self._llm`, `self._floor`) is read-only.

**Config**: `ENTITY_EXTRACT_PARALLELISM` env var, default 4. Set to 1 to disable concurrency (revert path).

**Effort**: ~30 LOC. **Expected**: 12-24 min → 3-6 min on Stage 1. **Risk**: low.

### Phase 2 — GraphBatch HTTP for `add_doc_merge`

**Problem**: `MATCH+MATCH+CREATE` per edge → 28s/200 edges → 12 min for 5000 mention edges.

**Fix**: use `POST /api/v1/batch/<db>?lightEdges=false` (GraphBatch) for chunk + new-entity + edge inserts. Stay on the existing UNWIND path for property-merge UPDATE on already-existing entities.

**Algorithm**:

1. **Pre-fetch RIDs** of thematic entities that already exist in this domain:
   ```sql
   SELECT id, @rid FROM Entity WHERE id IN [...candidate ids...]
   ```
   One round-trip; uses the unique `Entity[id]` index. Returns `{id → "#1:967834"}` for entities present in the graph.

2. **Partition** the thematic entities Python-side:
   - `new_entities` — not in pre-fetch result → send via GraphBatch CREATE
   - `existing_entities` — in pre-fetch result → keep their RID; build property-merge UPDATE separately

3. **Build NDJSON payload** (one HTTP call):
   - All chunks (always new — `add_doc_merge` step 1 DETACH DELETE'd the old ones)
   - All `new_entities`
   - All `chunked_into` edges (both endpoints in batch by `@id`)
   - All mention edges:
     - `@from` = chunk_id (always in batch)
     - `@to` = entity_id (if new in this batch) OR RID string from pre-fetch map (if pre-existing)

4. **POST** `/api/v1/batch/<db>?lightEdges=false` with `Content-Type: application/x-ndjson`

5. **Property-merge for `existing_entities`** in a separate small UNWIND UPDATE batch:
   ```cypher
   UNWIND $rows AS row
   MATCH (n:Entity {id: row.id})
   SET n.properties_json = row.merged_props_json,
       n.label = row.label
   ```
   Python computes the merged property dict (same logic as today's `add_doc_merge` step 3 thematic merge).

**Why this hybrid is correct for our pipeline**:

- All edges are always new in scope: chunks just got DETACH DELETE'd, so all incident mention edges went with them. New chunks → new mention edges.
- The only "MERGE" complexity is property-update on existing thematic entities — and that's UNWIND UPDATE on a small set, not edge deduplication.
- A consultant LLM (sixth answer in the design discussion) advised "GraphBatch is more trouble than it's worth for incremental ingestion" — they assumed re-ingestion creates duplicate edges. For our DETACH-DELETE-then-insert flow, that's not true.

**Files**:
- `noted/graph/app/graph_storage.py` — new method `add_doc_merge_v2` (NDJSON builder + POST)
- `noted/graph/app/research_builder.py` — call site behind feature flag `USE_GRAPHBATCH_V2`
- `noted/graph/app/config.py` — flag default `false` initially

**Rollout safety**: flag-gated. Old `add_doc_merge` stays in place. Round-trip test in a clone domain (not live `ml`) before flipping the flag on.

**Effort**: ~250 LOC + tests. ~1-2 days. **Expected**: Stage 2 12-15 min → **<1 min** (GraphBatch portion ~30s for 5000 edges per probe; property-merge UPDATE ~30s).

### Phase 3 — `.notedoc` (per-document) + `.noteddomain` (whole-domain) archive formats

Two archive formats, layered: `.noteddomain` is a tarball of N × `.notedoc` files plus the domain's manifest. Implementing the per-document path first, then composing the domain wrapper on top.

#### `.notedoc` archive layout

```
notedoc.json              # manifest
source/<filename>         # original file bytes (PDF / DOCX / MD / etc.)
graph/
  doc_node.json           # markdown_doc Entity dict
  chunks.json             # markdown_chunk Entity list
  chunked_into.json       # doc → chunks edges
  thematic.json           # thematic entities mentioned in this doc
  mentions.json           # entity → chunk mention edges with strength scores
vectors/
  corpus_chunks.jsonl     # one ChromaDB record per line: {id, embedding[1024], metadata, document}
```

Single tarball, `.notedoc` extension.

#### Manifest schema

```json
{
  "schema_rev": 1,
  "doc_id": "markdown_doc:optimization_for_machine_learning.pdf",
  "filename": "optimization_for_machine_learning.pdf",
  "source_domain": "ml",
  "exported_at": "2026-05-04T22:30:00Z",
  "checksum_sha256": "<over the bundle>",
  "producer": {
    "platform_version": "<noted git tag at export time>",
    "embedding_model": "bge-m3-q8",
    "extraction_model": "gemma-4-E4B-it-UD-Q4_K_XL"
  },
  "counts": {"chunks": 735, "entities": 2657, "mentions": 5102}
}
```

#### Validation rules on import

| Field | Rule | Why |
|---|---|---|
| `schema_rev` | importer's `>=` archive's | Forward-compat: an older importer rejects a v2 archive cleanly |
| `producer.embedding_model` | **must equal** target's embedding model | Vectors aren't transferable across embedding spaces. Silent garbage retrieval otherwise. |
| `producer.extraction_model` | **warn-only** if different | Entity quality may differ but graph is still valid |
| `checksum_sha256` | must match recomputed checksum of bundle | Catch corruption / tampering |

**Do NOT** disable database constraint checks during import (some optimization sources suggest this for bulk loads). Our `Entity[id]` unique index is what we rely on for entity identity. Disabling it lets duplicates slip in and corrupts later merges.

#### `.noteddomain` archive layout

```
noteddomain.json          # domain manifest (schema_rev, producer, included_files list, counts)
sources/
  <filename1>.notedoc     # one notedoc archive per included read_store file
  <filename2>.notedoc
  ...
domain_manifest.json      # the source domain's manifest.json (categories, modes, etc.)
```

`noteddomain.json` mirrors `notedoc.json`'s schema but at the domain level: `schema_rev`, `domain_id`, `exported_at`, `producer.{platform_version,embedding_model,extraction_model}`, and a `documents` array enumerating the included `.notedoc` filenames + their per-doc counts.

Importer iterates `documents`, runs the same `.notedoc` import pipeline for each, and at the end merges the domain manifest's metadata into the target's manifest (categories, modes — preserved per-doc).

#### Endpoints

Per-document:
- **Export**: `GET /api/domains/{id}/documents/export?path=<file>` — streams the `.notedoc` tarball with `Content-Disposition: attachment`.
- **Import**: `POST /api/domains/{id}/documents/import` (multipart upload of a `.notedoc`). Returns SSE stream of progress events (`unpacking`, `validating`, `prefetching_rids`, `graph_upsert`, `vector_upsert`, `complete`).

Whole-domain:
- **Export**: `GET /api/domains/{id}/export` — streams the `.noteddomain` tarball (manifest + every read_store doc as `.notedoc`).
- **Import**: `POST /api/domains/import` (multipart upload of a `.noteddomain`; target domain id taken from the archive's manifest). Returns SSE stream emitting per-doc progress events plus a final `domain_complete`.

#### Implementation reuses Phase 2

Import builds an NDJSON GraphBatch payload from the archive's `graph/*.json` + `vectors/*.jsonl` and POSTs to the same `/api/v1/batch/<db>` endpoint Phase 2 introduced. Property-merge for existing entities uses the same UNWIND UPDATE.

**Files**:
- `noted/graph/app/notedoc/exporter.py` (new) — walks the graph from `markdown_doc:<path>`, collects chunks via `chunked_into`, collects thematic entities via `mentions`; gets vector chunks from `<id>__corpus` filtered by `source_path`; tars all + manifest
- `noted/graph/app/notedoc/importer.py` (new) — unpacks, validates manifest, runs the GraphBatch hybrid import, pushes vectors via existing `rag.upsert_chunks`, sets `pending_recluster`
- `noted/graph/app/routers/research.py` — two new routes
- `noted/backend/app/routers/kb.py` — proxy routes on the noted backend so the UI doesn't need a different base URL

**Effort**: ~500 LOC + tests. ~2-3 days.

### Phase 4 — UX integration

Three touch-points; all extend existing patterns. No new panels.

#### 4.1 Export — Explorer document context menu

**Where**: existing right-click menu on a document in the Explorer panel.

**New item**: `Export as .notedoc`

**Flow**:
1. User right-clicks a `.pdf` (or `.md`, `.docx`, etc.) in their domain
2. Click triggers `GET /api/domains/{id}/documents/export?path=<file>`
3. Browser handles the download via `Content-Disposition: attachment`
4. Toast on completion: `Exported optimization_for_machine_learning.notedoc (15.2 MB)`

**Effort**: ~30 LOC in the Explorer context-menu module.

#### 4.2 Import — Domain context menu + drag-drop

**Where 1**: existing right-click menu on a **domain** node in the Explorer panel.

**New item**: `Import .notedoc archive…`

**Flow**:
1. User right-clicks a domain node
2. Click → file picker opens with `accept=".notedoc,.tar,.tar.gz"`
3. After selection → modal shows pre-import summary (parsed from archive's `notedoc.json`):
   - Filename, source domain, exported timestamp
   - Counts: 735 chunks, 2657 entities, 5102 mentions
   - Producer info: platform version, embedding model, extraction model
   - Compatibility check: ✅ embedding model match / ❌ would refuse import / ⚠️ extraction model differs
4. User confirms → upload begins
5. **Conflict resolution**: if a doc with the same path already exists in target, modal asks **Replace / Skip / Cancel**
6. SSE progress stream renders in modal:
   ```
   unpacking…
   validating manifest…
   prefetching existing entity RIDs…
   graph upsert…  (5102/5102 edges, 30s)
   vector upsert…  (735/735 chunks, 12s)
   complete (1m 24s)
   ```
7. On success → modal auto-closes, KB Monitor refreshes, toast: `Imported optimization_for_machine_learning.pdf (1m 24s) — 2657 entities merged, 5102 mention edges`

**Where 2**: drag-drop a `.notedoc` file onto a domain in the Explorer triggers the same modal flow.

**Effort**: ~150 LOC frontend (modal + SSE consumer + drag-drop wiring) + ~50 LOC backend (SSE event stream from import endpoint).

#### 4.3 KB Monitor provenance badge

Imported documents get a small `📦 imported` badge next to their filename in KB Monitor. Hover shows `producer.platform_version`, `exported_at`, source domain. Helps distinguish freshly-ingested docs from imported ones (relevant when troubleshooting "why does this doc have different entity quality").

**Effort**: ~20 LOC.

#### 4.4 Deliberately NOT in this round

- No standalone "KB Module Catalog" panel — premature; build only if users accumulate many archives.
- No CLI tooling — the API endpoints are scriptable via `curl` already.
- No schema-rev migration tooling — v1 importer rejects mismatched schemas with a clear error; migration logic deferred until a v2 ships.

### Phase 5 — Apply GraphBatch to recluster's `replace_analytics_layer`

`replace_analytics_layer.step4` has the same `MATCH+MATCH+CREATE` shape for ~28k analytics edges (sameAs + similar_to + member_of + summarizes). Mechanically identical refactor to Phase 2.

**Effort**: ~150 LOC, mostly mechanical given Phase 2's helpers.

**Expected**: recluster 1h 42m → **15-25 min**.

## 5. Deployment plan

| Phase | Containers to rebuild | Migration / data cost | Rollback |
|---|---|---|---|
| 0a | `noted-graph` + `noted` (proxy + frontend) | none | endpoint can be hidden; preflight failure falls through to legacy ingest with a warning |
| 0b | `noted-graph` + `noted` (frontend) | none | revert; UI gracefully handles missing sub-phase fields |
| 1 | `noted-graph` only | none | `ENTITY_EXTRACT_PARALLELISM=1` env var |
| 2 | `noted-graph` only | none (feature flag) | `USE_GRAPHBATCH_V2=false` env var |
| 3 | `noted-graph` + `noted` | none | new endpoints; can hide via nginx if misbehaving |
| 4 | `noted` only (frontend) | none | revert |
| 5 | `noted-graph` only | none (feature flag) | same `USE_GRAPHBATCH_V2` flag |

### Suggested order of landing (~1.5-2 weeks focused work)

| Day | Task |
|---|---|
| 1 | Deploy Phase 0b + Phase 1. Bench against a fresh PDF re-add. Confirm 4× win on Stage 1 + sub-phase progress visible. |
| 2-3 | Build Phase 2. Test with feature flag against a clone domain (NOT the live `ml`). When stable, flip flag on for live use. |
| 4-5 | Build Phase 3 export. Wire UI export item. Round-trip test: export → import to a different domain → verify entity counts + sample query works. |
| Week 2 day 1-2 | Build Phase 3 import + Phase 4 UX. SSE progress stream. Conflict modal. |
| Week 2 day 3-4 | Phase 5 (recluster GraphBatch). |
| Week 2 day 5 | End-to-end test of share-with-colleague workflow (export from one instance, import on another, query both). |

Each phase ships independently. If Phase 2 takes longer than expected, Phase 1 + Phase 0b alone are still meaningful wins.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| GraphBatch v2 path has subtle bug on edge cases (specific entity types, very large docs) | Feature flag + parallel old path retained. Round-trip tests in clone domain first. |
| Concurrent extraction overwhelms llama-server's 4 slots if user starts two doc imports at once | Bounded thread pool per `add_doc_pdf` call; outer queue at the `domain_registry.py` worker thread already serializes per-domain |
| `.notedoc` schema evolves and breaks existing archives | `schema_rev` field + strict reject if mismatched. Migration tooling deferred to v2. |
| Imported `.notedoc` from a different `embedding_model` produces silent garbage retrieval | Strict reject on `producer.embedding_model` mismatch — the only field where we MUST refuse |
| Large `.notedoc` archive (e.g. 100 MB PDF + 10000 chunks) blows browser memory on upload | Multipart upload streams from disk; backend writes to temp file, never holds whole archive in memory |
| Conflict-resolution UX confuses users (Replace/Skip/Cancel granularity) | v1: per-archive choice (one global Replace / Skip / Cancel decision). Per-doc granularity is a v2 concern. |
| Recluster + import racing | Existing rebuild-lock in `domain_registry.py` already serializes; import joins the same queue |
| Sub-progress fields polluting the status JSON for clients that don't care | Fields are namespaced (`sub_phase`, `sub_done`, `sub_total`, `sub_eta_seconds`) — clients that don't read them ignore them; small payload addition |

## 7. Outside scope (acknowledge but defer)

- **Domain-level export/import** — composes from `.notedoc` (export each `included_files` entry, tar with the manifest). ~50 LOC on top of Phase 3. Add when there's real demand.
- **Native ArcadeDB BACKUP/RESTORE for whole-domain clones** — separate feature for "drag this whole domain to a fresh instance" use case (different audience: ops, not end users).
- **Phase 2 chat-context summarization** (large file → chunked summary in chat for the Assistant `+` menu File option) — separate feature, separate scope.
- **Public catalog of `.notedoc` modules** — only if user demand emerges.
- **gRPC streaming endpoint** instead of HTTP NDJSON — also exposes GraphBatch in v26.3.2; ~10-20% additional throughput at the cost of integration complexity. Not worth it unless we hit ingestion volumes that make 1-2 min noticeable.

## 8. Verification reference

Probe commands used during plan design (re-runnable for sanity checks):

```bash
# 1. Verify Entity[id] unique index exists
curl -s -u root:noted-dev -X POST http://localhost:2480/api/v1/query/<db> \
  -H 'Content-Type: application/json' \
  -d '{"language":"sql","command":"SELECT FROM schema:indexes"}' | jq '.result[] | select(.typeName=="Entity")'

# 2. Verify GraphBatch HTTP endpoint accepts NDJSON
curl -s -u root:noted-dev -X POST "http://localhost:2480/api/v1/batch/<db>?lightEdges=false" \
  -H 'Content-Type: application/x-ndjson' \
  --data-binary $'{"@type":"vertex","@class":"Entity","@id":"__test__:a","id":"__test__:a","type":"concept","label":"a"}\n{"@type":"vertex","@class":"Entity","@id":"__test__:b","id":"__test__:b","type":"concept","label":"b"}\n{"@type":"edge","@class":"RELATES","@from":"__test__:a","@to":"__test__:b","type":"probe"}'

# 3. Cleanup test data
curl -s -u root:noted-dev -X POST http://localhost:2480/api/v1/command/<db> \
  -H 'Content-Type: application/json' \
  -d '{"language":"sql","command":"DELETE FROM Entity WHERE id LIKE \"__test__%\""}'
```

# Session Handoff — KB Ingestion Optimization Work

**Status as of writing**: PDF import for `optimization_for_machine_learning.pdf` is running end-to-end with the new code path. Phase 1 (parallel extraction) and the retry-with-backoff are deployed and active. Phase 0a (preflight) and Phase 2 (GraphBatch v2) are coded and staged but **not yet deployed** — they need a `noted-graph` rebuild AFTER the current import finishes.

## What's running RIGHT NOW

| Component | State |
|---|---|
| `ml` domain doc add | `extracting`, ~88/735 chunks at last check, ~2.2s/chunk wall = ~24 min remaining for extraction |
| Code path | `add_doc_merge` (legacy) — `USE_GRAPHBATCH_V2=false` for safety on this first run |
| Parallel LLM extraction | active (`ENTITY_EXTRACT_PARALLELISM=4`, `ThreadPoolExecutor`) |
| Retry-with-backoff | active (`ARCADEDB_MAX_RETRIES=5`, jittered exp backoff) |
| Throughput observed | ~1.4-1.6× speedup vs serial baseline. Limited by GPU compute sharing across the 4 llama-server slots; the dramatic 4× would need wider llama-server tuning. Phase 2 (GraphBatch) addresses the writing-phase bottleneck where the bigger win lives. |

## Files changed in this session (all on disk; some deployed, some staged)

### Deployed in `noted-graph`

- `noted/graph/app/config.py` — added `ENTITY_EXTRACT_PARALLELISM` (default 4) and `USE_GRAPHBATCH_V2` (default false) env vars.
- `noted/graph/app/extractors/gemma_entity_extractor.py` — `_below_floor_lock` for thread-safe append; `extend()` with lock instead of per-item `append`.
- `noted/graph/app/research_builder.py` — `ThreadPoolExecutor(max_workers=ENTITY_EXTRACT_PARALLELISM)` wrapping the extraction loop; aggregation stays serial. Imports for `ENTITY_EXTRACT_PARALLELISM` and `USE_GRAPHBATCH_V2`. Branch in `_add_doc_from_chunks` to call `add_doc_merge_v2` when the flag is on.
- `noted/graph/app/arcadedb_client.py` — retry-with-backoff for `ConcurrentModificationException` (up to 5 retries, jittered exp backoff, configurable via `ARCADEDB_MAX_RETRIES` and `ARCADEDB_RETRY_BACKOFF_BASE`); new `graphbatch_post(ndjson_lines, light_edges)` method for `POST /api/v1/batch/<db>`.

### Staged on disk, NOT yet in container (need `noted-graph` rebuild)

- `noted/graph/app/graph_storage.py` — new `add_doc_merge_v2()` method implementing the GraphBatch hybrid (CREATE for new vertices/edges; small UNWIND UPDATE for property merge on existing thematic entities). Behind `USE_GRAPHBATCH_V2` feature flag.
- `noted/graph/app/preflight.py` — new file. Phase 0a preflight orchestrator + check implementations (Docling first-page parse, Gemma JSON smoke, ArcadeDB write probe via GraphBatch, schema-index sanity, noted-rag embedding probe, manifest collision, disk-space estimate). Two entry points: `run_preflight_for_doc()` and `run_preflight_for_notedoc()`.
- `noted/graph/app/routers/research.py` — new route `POST /{domain_id}/preflight` calling the orchestrator.
- `noted/backend/app/routers/kb.py` — new proxy `POST /api/domains/{id}/preflight` to the noted-graph endpoint.

### Deploy commands when ready

```bash
# After current import finishes (status shows phase=done):
cd ~/env/assets/noted/services
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f ../data/docker-compose.mounts.yml \
    up -d --build --no-deps noted-graph
# noted backend rebuild (for the proxy route):
bash run.sh
```

## Smoke tests to run after deploy

### Preflight (read-only — safe)

```bash
# Re-add the optimization PDF as the test target (file already in sources/)
curl -s -X POST "http://localhost:8123/api/domains/ml/preflight?path=optimization_for_machine_learning.pdf" \
  | python3 -m json.tool
```

Expected: structured report with checks for `arcadedb.schema_indexes`, `arcadedb.write_probe`, `noted_rag.embedding`, `gemma.json_smoke`, `disk.space`, `manifest.collision`, `docling.first_page`. `ok: true` if all pass; collision will show as `warn` (already in domain).

### GraphBatch v2 (small risk — only enable on a test doc)

To test GraphBatch v2 on the next ingestion:

```bash
# Set the env var on the noted-graph compose service (or set it in compose.yml):
docker compose -f ... up -d -e USE_GRAPHBATCH_V2=true --no-deps noted-graph
```

Then re-import a small test doc (or the optimization PDF after deletion). Watch logs for `writing.add_doc_merge_v2:` lines. Expected: writing phase completes in <1 min vs the 12-15 min legacy path.

**Rollback**: set `USE_GRAPHBATCH_V2=false` and recreate the container.

## Plan & memory

- Full integrated plan: `documents/kb/kb_import_export.md` (Phases 0a → 5)
- Memory pointer: `MEMORY.md` → `project_kb_ingestion_perf_and_notedoc.md`

## What's NOT done in this session

| Phase | Status | Notes |
|---|---|---|
| Phase 0b (progress visibility — sub-phase fields in `self.progress`) | **not coded** | ~150 LOC backend + 80 LOC frontend; high-UX-value cheap win |
| Phase 0a frontend (UI banner with preflight report) | **not coded** | Backend endpoint is ready; needs frontend consumer |
| Phase 3 (`.notedoc` archive export + import) | **not coded** | Biggest remaining feature; ~500 LOC + tests |
| Phase 4 (UX in Explorer — context-menu items, drag-drop) | **not coded** | Needs Phase 3 first |
| Phase 5 (GraphBatch for `replace_analytics_layer` recluster path) | **not coded** | Mechanical port from Phase 2 once that's validated |

Realistic remaining effort: **~1 week** of focused work to land Phases 0b, 3, 4, 5. The user's "2 hours" target landed Phase 1 (deployed) + Phase 0a code + Phase 2 code (both staged behind safety guards). That's the high-ROI subset; everything else needs a separate session.

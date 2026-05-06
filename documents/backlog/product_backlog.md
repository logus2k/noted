# Product Backlog

Living list of pending and deferred work across the noted stack. Organized by area; within each area items roughly sorted by user-visible value × effort. Cross-references the integrated plan in `documents/kb/kb_import_export.md` where relevant.

Last updated: 2026-05-05

---

## 1. KB ingestion performance + archive formats

| ID | Item | Effort | Notes |
|---|---|---|---|
| **KB-1** | **Phase 5 — GraphBatch in `replace_analytics_layer` (recluster perf)** | ~150 LOC | Mechanical port of Phase 2's hybrid pattern to the recluster path. Behind same `USE_GRAPHBATCH_V2` flag. Expected: recluster ~80 min → ~15-25 min. |
| **KB-2** | **Phase 3a — `.notedoc` per-document archive (export + import)** | ~500 LOC + tests | New `notedoc/exporter.py` + `notedoc/importer.py` + two routes in `routers/research.py` + proxy in noted backend `kb.py`. Skips re-extraction on import (15-20 min total instead of 30-45 min). Plan: `documents/kb/kb_import_export.md` Phase 3. |
| **KB-3** | **Phase 3b — `.noteddomain` whole-domain archive (export + import)** | ~150 LOC on top of KB-2 | Tarball of N × `.notedoc` files + domain manifest. Importer iterates the per-doc pipeline. |
| **KB-4** | **Phase 4 — Explorer right-click Export / Import context-menu items** | ~200 LOC frontend + SSE progress modal | Document context menu: "Export as .notedoc". Domain context menu: "Import .notedoc archive…" with conflict modal (Replace/Skip/Cancel) + drag-drop. |
| **KB-5** | **Synthetic round-trip test of GraphBatch v2** | ~80 LOC | Flip `USE_GRAPHBATCH_V2=true`, ingest a small stub doc, verify graph counts/relationships match the legacy path's output. Validation gate before the flag becomes the default. |
| **KB-6** | KB Monitor provenance badge for imported docs | ~20 LOC frontend | Small `📦 imported` badge with hover-detail of `producer.platform_version` + `exported_at` + source domain. |
| **KB-7** | Phase 0b polish — ETA calculation per sub-phase | small | Running average of last N chunks → `sub_eta_seconds` field surfaced in KB Monitor. |
| **KB-8** | Phase 0b — surface sub-phases for `replace_project_graph` (full-rebuild path) | ~30 LOC | Currently only `add_doc_merge` + `replace_analytics_layer` report sub-phase. Full-rebuild path goes silent. |
| **KB-9** | Cypher → SQL hot-path migration for hot retrieval queries | medium | Per `feedback_arcadedb_cypher_to_sql_hot_path.md`, Cypher is 25-49× slower on hot paths. Several retrieval queries still use Cypher. |
| **KB-10** | Docling per-page progress callback | small-medium | Today the `adding_doc` phase shows an indeterminate spinner. Newer Docling versions expose `progress_callback`. Upgrade + wire. |

---

## 2. Chat artifacts (open in mid panel + save)

| ID | Item | Effort | Notes |
|---|---|---|---|
| **CHAT-1** | **Part A — double-click chat image/file → open in mid panel** | ~150 LOC | Building NOW. Reuses `_openMediaTab` pattern with new `chat-img:` / `chat-file:` keys; content carried in-memory. Covers user uploads (image + file) + assistant-rendered `<img>` in markdown. |
| **CHAT-2** | **Part B — Save icon in viewer title bar** | ~250 LOC + backend route | New action in the panel top bar for `chat-img:` / `chat-file:` tabs. Modal: project picker → folder tree picker → filename (pre-filled). Backend `POST /api/projects/{id}/save-from-chat` writes bytes/text. |
| **CHAT-3** | **Part C — Coverage for external-URL images in assistant bubbles** | small | Images fetched from external URLs need server-side download (CORS) before save. Small backend URL-to-bytes proxy. |
| **CHAT-4** | Phase 2 chat-context summarization (large file → chunked summary) | medium-large | Current text-attach truncates at `NOTED_CHAT_CONTEXT_MAX_CHARS`. Phase 2 plan: chunked LLM-summarize for files larger than the cap, then attach the condensed version. Needs a new `noted_context_summarizer` agent_server preset (`succint` is NOT a summarizer). Plan ref: `project_chat_context_attach.md`. |
| **CHAT-5** | PDF / DOCX support in chat-context attach | medium | Today only `text/*` + curated code extensions. Add a PDF/DOCX strategy (probably calls Docling parse-only). |

---

## 3. UX polish

| ID | Item | Effort | Notes |
|---|---|---|---|
| **UX-1** | "Reconnecting…" state during transient backend unreachability | small | KB Monitor jumps straight to "Unreachable" on the first failed `/status` poll during a `noted` rebuild. After N consecutive failures fall to "Unreachable"; before that, show "Reconnecting…" with a spinner. |
| **UX-2** | Replace "~25 minutes" stale wording in pending-recluster banner | trivial | Banner says "full re-extraction, ~25 minutes" — predates Phase 1 + 2. Either drop the time estimate or make it dynamic. |
| **UX-3** | Phase 0a — wire preflight as a step inside the doc-add UI flow | small | Today preflight is a manual button in KB Manager. Hooking into the upload modal so it fires automatically, with results visible before the long ingestion commits. |

---

## 4. Charts in chat (ECharts-backed)

| ID | Item | Effort | Notes |
|---|---|---|---|
| **CHART-1** | New `chart_designer` agent_server preset + system prompt + GBNF grammar | ½ day | Specialized LLM role for chart-intent generation. `chat_template_kwargs:{enable_thinking:false}`, `memory_policy:none`. Grammar-constrained JSON output — biggest reliability win, eliminates LLM-emits-broken-spec failure mode. |
| **CHART-2** | Backend `render_chart` tool + per-type ECharts option builders (bar, pie, scatter, heatmap, line, area, histogram, box) | 2-3 days | One builder per chart type. Server validates + binds data; LLM never sees the raw values. Returns ECharts `option` dict via SSE `data.chart` event. |
| **CHART-3** | Data-source resolver (3 shapes: inline / project_file / prior_result) | 1 day | `inline` for chat-typed numbers; `project_file` for CSV/Parquet/JSON in noted projects; `prior_result` for chaining off another tool's output (server caches recent tool results by id). Auto-samples >1k rows. |
| **CHART-4** | `inspect_dataset(path)` companion tool | small | LLM calls this first to learn column names/types before emitting a render_chart that references them. Eliminates column-name hallucination. |
| **CHART-5** | Frontend ECharts inline render in assistant bubble | 1 day | ChatService catches `data.chart`, ChatPanel inserts `<div class="chat-message-chart">` and runs `echarts.init` + `setOption`. echarts.min.js is already loaded. |
| **CHART-6** | Chart artifact opens in floating viewer (Part A reuse) + Save as PNG/SVG (CHAT-2 reuse) | small | Reuses `_openChatArtifact` with new `kind:'chart'`. Save uses `chart.getDataURL()` for PNG export, drops cleanly into the project-folder Save modal. |
| **CHART-7** | Tests + edge cases (huge dataset, missing columns, ambiguous chart-type request) | 1 day | Validation layer + retry-on-error feedback to the LLM. |
| **CHART-8** | Rendering / instruction reliability — observed failure modes 2026-05-05 | 1-2 days | Open issues seen in chat: (a) categorical-x scatter request → blank canvas before fix, now returns "switch to bar" error but assistant doesn't auto-retry; (b) ambiguous prompts ("Component A (X-axis) vs Component B (Y-axis)" + "(35,45) for Component A") → chart_designer can't tell whether A is an axis or a data point, often emits empty values; (c) "distinctly coloured" requests not honored — single-series scatter renders one colour; (d) lossy roundtrip — inline data goes assistant → prose → chart_designer parses prose back to numbers, every step bleeds info. Likely fix is structural, not prompt-tuning: split tool into structured `chart` (assistant ships markdown table or CSV + chart_type + column mapping, no second LLM) and `chart_from_file` (description path, chart_designer earns its keep with file inspection). See chat 2026-05-05 for the design discussion. |

Total estimate: **~5-7 focused days** for a robust v1. Realistic reliability: ~85-95% on typical requests, degrading to user-nudge rather than crash.

## 5. Tools available to the Assistant

| ID | Item | Effort | Notes |
|---|---|---|---|
| **TOOL-1** | **`open_file` tool — open notebook / source / document / media in noted from the Assistant** | done (staged) | Backend tool + handler done; frontend ChatService callback + app.js dispatcher done. Needs `noted` + `noted-graph` rebuilds to deploy. |
| **TOOL-2** | KB document lookup helper for `_openDocumentTab` from the LLM path | small | `_handleAssistantOpenFile` for `kind === 'document'` synthesises a doc object from the path. A real manifest lookup (read `included_files` to get category/mode) would produce a richer doc object. |

---

## 6. Validation / observability

| ID | Item | Effort | Notes |
|---|---|---|---|
| **OBS-1** | Diagnostics modal on close — already fixed (jsPanel backdrop cleanup) | done | |
| **OBS-2** | py-spy in noted-graph image (live stack inspection if a hang recurs) | trivial | Mentioned in `project_clean_reimport_plan.md`. Phase 0b's per-step timing logs cover most of the observable layer; py-spy is fallback. |
| **OBS-3** | Container restart UX — friendlier error during transient API gaps | see UX-1 | |

---

## 7. Multi-agent / agent_server work

| ID | Item | Effort | Notes |
|---|---|---|---|
| **AS-1** | Multi-agents dropdown — design notes only, not implemented | medium | Per `project_multi_agents_dropdown.md`. agent_server already supports per-turn dynamic via `model` field; gotchas: tools (noted-side), memory ((project_id, client_id)-scoped), voice contract (in prompts). |
| **AS-2** | Phase 2 voice-injection (parallel/early injection from reasoning context) | medium | Per `project_voice_injection_fallback.md`. Phase 1 shipped; Phase 2 is the parallel injection user originally asked for. Single-file change to `_LlamaServerProxy._stream_iter`. |

---

## 8. Architectural considerations (deferred)

| ID | Item | Effort | Notes |
|---|---|---|---|
| **ARCH-1** | Two `llama-server` instances (split chat vs embedders) | medium | Could let gemma-4 chat traffic and bge-m3 embedding bursts not contend on the same GPU compute scheduler. VRAM penalty: each llama-server has ~500MB-1GB CUDA context overhead. Worth it if extraction + embedding throughput is genuinely the next bottleneck after KB-2 lands. |
| **ARCH-2** | Native ArcadeDB BACKUP/RESTORE for whole-domain clones | medium | Different shape than KB-2/KB-3 — file-level instant snapshot, but whole-domain scope only and overwrites target on restore. Use case: "drag this whole domain to a fresh instance, target empty". Different audience (ops, not end users). |
| **ARCH-3** | Public catalog of `.notedoc` modules | speculative | Build only if user demand emerges after KB-2/KB-3 ship. |
| **ARCH-4** | gRPC streaming endpoint to ArcadeDB GraphBatch | small (10-20% throughput gain) | Available in v26.3.2. Not worth integration cost yet; HTTP NDJSON is fast enough for our scale. |

---

## 9. STT pipeline (stt_server)

| ID | Item | Effort | Notes |
|---|---|---|---|
| **STT-1** | Chunked Whisper decoding for utterances > 30s | ~½ day | Whisper-large-v3-turbo's encoder is capped at ~30s natively. Today's `_transcribe_sync` calls `model.generate(input_features)` directly so any audio segment longer than 30s gets truncated by the processor. Fix is `pipeline(... chunk_length_s=30)` or manual split-and-stitch with overlap windows. The 60s buffer fix (2026-05-05) raised the segment ceiling to Whisper's native limit; this item raises the ceiling beyond 30s. Validation: a 45-60s captured utterance round-trips to a complete transcript. |
| **STT-2** | `/stt_server/data/captures/` is `:ro` bind-mount, every diagnostic capture write fails with `[Errno 30] Read-only file system` and a `Wave_write.__del__` AttributeError traceback in stt_server logs | trivial (~10 min) | Either flip the bind-mount to `:rw` in the stt_server compose entry (`~/env/assets/stt_server/data:/stt_server/data:rw`) so the diagnostic capture path actually works, OR guard the `wave.open` call with a write-permission probe and skip silently. The traceback is benign (capture is wrapped in try/except) but pollutes the logs and obscures real errors. |

---

## 10. Notes / Known wrinkles

- **Off-limits containers**: `femulator`, `scipredictor`, `gan_game` — never stop, restart, modify, or rebuild without explicit user authorization (per session rule).
- **Restart safety**: `git`-related destructive ops, container restarts, force-pushes, and history-rewriting commands always require explicit user authorization.
- **noted-graph rebuilds**: code is COPY'd into the image. Per memory `feedback_runtime_json_bind_mounted.md`: deploy needs `up -d --build --no-deps noted-graph`, NOT `--force-recreate` alone.
- **VRAM baseline**: with `llama-vision` + `tts_server` + `stt_server` running, expect ~17-22 GB on the 4090 in steady state. Driver upgrades + WSL2 cold-starts can reduce this temporarily.

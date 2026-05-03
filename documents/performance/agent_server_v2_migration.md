# agent_server_v2 migration plan

## Goal

Replace agent_server's in-process llama-cpp-python with HTTP forwarding
to a `llama-server` sidecar. Same APIs and clients, ~10× generation
throughput, vision support included.

## Current state (PoC validated)

| Layer | Now (PoC) |
|---|---|
| LLM host | `llama-vision` container (ghcr.io/ggml-org/llama.cpp:server-cuda), port 8500, `-c 131072 --parallel 1`, mmproj loaded |
| API gateway | `agent_server_v2` container, port 7701, `LLAMA_SERVER_URL=http://llama-vision:8500`, `pool_size=20` |
| Bridge | `LlamaServerEngine` + `_LlamaServerProxy` + `_ThinkingSplice` (translates `reasoning_content` → `<think>...</think>` so noted's existing UI parser keeps working) |
| Clients | noted backend, Socket.IO, REST — unchanged |

Generation rate measured: ~150 t/s per request (vs ~14 t/s in-process).
Vision works end-to-end through `/v1/chat/completions` multimodal
content blocks. Tool calls / citations / graph all working.

## Phases

| # | Phase | Scope | Deliverable | Blocker |
|---|---|---|---|---|
| 1 | Slim Dockerfile.v2 | Drop CUDA toolchain + llama-cpp-python source build from agent_server image; switch base to `python:3.12-slim`; install httpx/fastapi/uvicorn/etc. only | Image 8.5 GB → ~500 MB. Build 3 min → 30 s | none |
| 2 | Verify lean stack | Recreate via compose; smoke-test from noted (text, tool, citations, graph) | Confirmation nothing regressed | none |
| 3 | Code cleanup | Add deprecation comments to `app/chat_handlers/gemma4_vision.py`, `mmproj_path` field, `_ThinkingSplice` | TODOs visible to future readers; no deletions yet | none |
| 4 | Memory + plan-of-record | Update `MEMORY.md`; this document | Findings preserved across compaction | none |
| 5 | Cutover rename | `agent_server_v2` → `agent_server`, retire v1 image, swap docker-compose paths | Single canonical service | user call |
| 6 | noted UI: render `reasoning_content` natively | Update noted's `ChatPanel.js` / `ChatService.js` to handle the field directly; remove `_ThinkingSplice` translator from agent_server | Cleaner architecture, smaller forwarding code | Launchpad recovery (noted backend rebuild) |
| 7 | noted UI: image attachment | Add paste/drop image in chat input; backend forwards multimodal content blocks; agent_server forwards as-is to llama-vision | Vision in chat, end-user usable | Launchpad recovery |
| 8 | **PoC: llama-server router mode with mixed model types** | Spin up a single `llama-server` instance with `--models-preset config.ini` declaring three models with their specific flags: `gemma-4-E4B` with `--mmproj`, `bge-m3` with `--embeddings --pooling cls`, `bge-reranker-v2-m3` with `--reranking`. Verify all three load + serve simultaneously with per-request `model` selection. If feasible, also bench: embedding throughput, reranking throughput, chat throughput — confirm no regression vs single-model llama-vision. | Go/no-go on the 1-container architecture (Phase 9b vs 9a). If router supports mixed types → Phase 9b; otherwise → fall back to Phase 9a (3 sidecars). | none (independent of agent_server cutover) |
| 9 | noted-rag forwarding refactor (architecture decided in Phase 8) | Replace noted-rag's in-process `Llama(embedding=True, ...)` and reranker with HTTP forwarding to either: **(9a)** dedicated `llama-embed` + `llama-rerank` sidecars, or **(9b)** the same `llama-router` instance also serving the chat model. Slim noted-rag's Dockerfile (drop CUDA + llama-cpp-python source build) | noted-rag becomes a thin orchestrator; full GPU compute consolidated in C++ daemons | Phase 8 result |
| 10 | Cutover noted-rag | Rename / retire old image; one canonical noted-rag (forwarding) | Single canonical service per role | user call after Phase 9 stabilises |
| 11 | **Future: noted ↔ llama-server via Anthropic `/v1/messages` API** | llama.cpp has added `/v1/messages` (Anthropic Messages API). noted already uses Anthropic API for Claude backends. Unifying both paths to Anthropic format would: (a) let noted use a single LLM client for local + remote, (b) make extended thinking native on local (no more `_ThinkingSplice` translator), (c) make Phase 6 (noted UI render `reasoning_content`) moot — Claude-path UI already handles Anthropic thinking blocks natively. Significant rework — defer for separate design discussion. | Decision document, possibly a v3 architecture proposal | further discussion |
| 12 | **LAST stage: user-facing model CRUD on top of always-loaded baseline** | **Baseline stays always-loaded** (gemma-4 chat+vision, bge-m3 embed, bge-reranker — the planned set). Pin them in the INI with `load-on-startup = true`. No automatic eviction of baseline models — users never wait for cold-start latency on normal operations. Phase 12 then adds a CRUD UI for **additional** models that users can opt-in to load (Claude-picker style, but only for extras): a coding-tuned model when working on code, a translation model on demand, etc. When they unload, baseline remains. Architectural choice: noted talks directly to llama-server's `/models/*` endpoints (cleaner — agent_server stays focused on agent orchestration, llama-server stays focused on model management). Worth noting: load/unload has measurable latency, so this is explicitly an opt-in user action, not auto-routing during chats. | New product capability layered on stable baseline; UI in noted; architecture decision (noted-direct vs. agent_server-proxied) | All other phases — this is intentionally the LAST stage of the agent_server journey |

Phases 1-4: agent_server work only, no Launchpad dep, can land
immediately.

Phases 5-7: deferred until Launchpad recovers (PPA blocked) and user
gives the rename go.

Phases 8-10 (noted-rag migration): independent of Launchpad and of
agent_server cutover. Can run in parallel once Phase 4 lands. Phase 8
is **PoC-only** (no production change) so it's safe to do early — and
its outcome determines whether Phase 9 takes the 3-sidecar (9a) or
1-router (9b) shape.

Phase 11: deferred to a future design discussion. Significant noted
rework. Not on the path for the current migration.

Phase 12: explicitly the LAST stage of the agent_server journey. The
always-loaded baseline (chat + embed + rerank) stays as planned with
no eviction; CRUD is purely additive for opt-in extras the user
loads/unloads themselves (with the understood load latency cost).

## Open items

- `LlamaCppEngine` stays in `app/llm_engine.py` as the rollback
  path. Active engine selected by env var `LLAMA_SERVER_URL` (set
  → forwarding; unset → in-process).
- `gemma4_vision.py` chat handler subclass (PoC artefact for the
  in-process vision attempt, before pivot to llama-server) becomes
  dead code after Phase 1 but is kept for reference until Phase 6.
- The `_ThinkingSplice` translator is a PoC convenience to keep
  noted's existing UI working without a noted backend rebuild.
  Removed in Phase 6 once noted UI handles `reasoning_content`.
- noted-rag still uses in-process llama-cpp-python with the per-input
  loop workaround (per session memory `feedback_llama_cpp_python_multi_seq_decode_broken`).
  Per-input loop means each text pays full Python per-call overhead;
  per-call overhead is the dominant cost for embedding/rerank (no
  per-token amortisation since they're single-forward-pass ops). Gap
  vs llama-server likely larger than chat's ~10× — to be measured in
  Phase 8.
- **Known visual artifact (Phase 6 candidate)**: citations in markdown
  link-ref form `[markdown_chunk:hex]:` (with trailing colon) appearing
  inside the live thinking body don't render as clickable badges —
  they show as raw text. Root cause is in noted's `ChatPanel.js`:
  `_normalizeRefDefs` runs only on the answer body, not on the live
  thinking body, so the link-ref form (`[xxx]:`) reaches the thinking
  renderer in a shape `_renderCitations` doesn't catch (`_renderCitations`
  matches bare `[xxx]` without the colon). Newly visible with v2
  forwarding because llama-server's peg-gemma4 template makes Gemma
  produce more elaborate, structured thinking with markdown-list
  citation references. Two fix options: (a) extend `_normalizeRefDefs`
  to also run on `_liveThinkingBody` in noted's UI (proper fix, needs
  noted backend rebuild), (b) add link-ref normalisation to agent_server's
  `_ThinkingSplice` so the form is converted before noted sees it
  (tactical, no noted rebuild needed). Deferred to Phase 6.

## Embedding / reranker migration architecture (Phase 8-10)

Same pattern as agent_server → llama-vision, applied to noted-rag.

**Two candidate architectures to evaluate in Phase 8:**

### (a) 3-sidecar architecture (safe, originally planned)

```
Today:    noted -> noted-rag -> in-process llama-cpp-python (bge-m3 + reranker) -> GPU
Phase 9a: noted -> noted-rag -> HTTP -> llama-embed     -> GPU
                              -> HTTP -> llama-rerank   -> GPU
agent_server -> HTTP -> llama-vision (chat + vision)    -> GPU
```

3 separate llama-server processes, one per model. Each independently
configured with its own flags. Battle-tested.

### (b) 1-router architecture (cleaner if it works)

llama.cpp added Router Mode (~Dec 2025): a single `llama-server` can
host multiple models, selected per-request via the standard OpenAI
`model` field. Per-model config via `--models-preset config.ini`.

```
Phase 9b: noted -> noted-rag -> HTTP -> llama-router (gemma + bge-m3 + bge-rerank) -> GPU
agent_server -> HTTP -> llama-router (model=gemma-4-...)                            -> GPU
```

1 container, 3 models loaded, all request-routed. Architecture much
simpler.

**Critical unknown** that Phase 8 must answer empirically: can a single
llama-server router instance host **mixed model TYPES** simultaneously
when each needs different flags (`--mmproj`, `--embeddings`,
`--reranking`)? The blog post focuses on swapping between chat models
of different sizes/quantisations, doesn't explicitly cover mixed types.
Per-model INI overrides may handle it; needs verification.

If router mode supports mixed types → Phase 9b. Otherwise → Phase 9a.

**Strategic upside of (b) even beyond saving 2 containers**: future
model additions (a small router model for cheap routing decisions, a
coding-specific model, a translation model, etc.) become a line in
the INI rather than a new sidecar. Long-term, the platform is set up
for easy multi-model serving.

**VRAM math** (Q8 quants, both architectures equivalent):
- bge-m3 (~600 MB on disk) → ~1 GB GPU
- bge-reranker-v2-m3 (~600 MB on disk) → ~1 GB GPU
- Plus compute buffers per process (~200-500 MB each, fewer in router mode)
- Total new GPU: ~2-3 GB on top of current llama-vision footprint
- Headroom check: currently ~9 GB free of 24 GB → fits comfortably either way

## Rollback

Setting `LLAMA_SERVER_URL` to empty (or unsetting it) reverts the
engine factory to `LlamaCppEngine`. Container restart picks up the
change. No code change required.

The current Dockerfile.v2 still builds llama-cpp-python (carries the
in-process binary in the image). After Phase 1 (slim image), rollback
to in-process mode would require rebuilding with the old Dockerfile.v2
— or keeping the previous image tag around as `agent_server_v2:1.0-fat`.

## Files affected (v2 branch)

```
app/llm_engine_server.py        NEW — forwarding engine + thinking splice
app/main.py                     MOD — env-var-gated engine factory
app/openai_compat.py            MOD — multimodal content blocks accepted
app/chat_handlers/__init__.py   NEW — package init (will be removed in Phase 6)
app/chat_handlers/gemma4_vision.py  NEW — in-process vision handler (dead in forwarding mode)
agent_config.json               MOD — pool_size=20, mmproj_path on active model entry
Dockerfile.v2                   NEW (slimmed in Phase 1)
docker-compose.v2.yml           NEW — both services (llama-vision + agent_server_v2)
_vision_test/                   NEW — Dockerfile, test scripts, concurrent_load.py
```

## Performance expectations after migration

| Workload | v1 (in-process) | v2 (forwarding) |
|---|---|---|
| Text gen rate | ~14 t/s | ~150 t/s |
| Image work (encode + decode) | ~3.6 s | ~91 ms |
| Vision-augmented chat turn | 7-10 s typical | 2-4 s typical |
| Concurrent requests | model-bound, serialised | continuous batching at llama-server |
| agent_server image size | 8.5 GB | 500 MB |
| agent_server build time | ~3 min | ~30 s |
| GPU memory baseline | ~5 GB (Gemma in agent_server) | ~5 GB (Gemma in llama-vision) — same |
| Adding extra agent_server pool worker | +5 GB GPU | +5 MB Python heap |

## 2026-05-03: completion status

All migration phases are in production except the Launchpad-blocked items.

| Phase | Description | Status |
|---|---|---|
| 1-5 | Slim image, cleanup, cutover | DONE |
| 6 | noted UI renders `reasoning_content` natively | PENDING (Launchpad-blocked) |
| 7 | Image attach in chat (vision via paste/drop) | PENDING (Launchpad-blocked) |
| 8 | Router-mode PoC for embed/rerank | DONE |
| 9 | Production llama-vision in router mode + noted-rag forwarding | DONE |
| 10 | noted-rag cutover | DONE (collapsed into Phase 9) |
| 11 | Anthropic `/v1/messages` API unification | future |
| 12 | User-facing model CRUD on baseline | LAST stage, future |

### What landed this session (2026-05-03)

**noted-rag refactor (Phase 9 noted-rag side)**:
- `noted-rag/app/rag_service.py`: `embed()` + `_rerank()` now POST to
  `llama-vision:8500/v1/embeddings` and `/v1/rerank` (batched, no
  per-input loops). The in-process `Llama()` instances and the
  `_GgufReranker` class are gone.
- `noted-rag/Dockerfile`: `python:3.12-slim` base, no CUDA, no
  llama-cpp-python. **Image: 6 GB → 432 MB. RAM: GBs → 131 MB.**
- `noted/services/docker-compose.yml`: noted-rag block reduced to
  `LLAMA_SERVER_URL=http://llama-vision:8500`. GPU stanza removed
  from `docker-compose.gpu.yml`.

**Required INI tweak on bge models**:
- bumped `batch-size = 8192` and `ubatch-size = 8192` on bge-m3 and
  bge-reranker. Pooling-mode embedders need the WHOLE sequence in one
  physical batch (no chunked prefill), and noted-rag's chunker
  produces 700-1000 token chunks. The default ubatch=512 was failing
  on real workloads.

**Gemma 4 chat template fix**:
- `[gemma-4]` section in `llama-router-models.ini` now has
  `jinja = true` AND `reasoning = on`. This activates the GGUF's
  official Gemma 4 Jinja template (instead of llama-server's
  hardcoded `peg-gemma4` compatibility shim) and turns on thinking
  mode by injecting `<|think|>` into the system block. Verified by
  `init: chat template, thinking = 1` and `example_format:
  '<|turn>system'` at startup.
- The `--chat-template-kwargs '{"enable_thinking":true}'` form is
  deprecated in favor of `--reasoning on`. Use the latter.
- Sampling defaults from Unsloth's Gemma 4 docs: `temperature=1.0
  top_p=0.95 top_k=64`. CUDA 12.8 (in our llama.cpp:server-cuda
  image) is safe; Unsloth warns specifically against 13.2.

**Tool-call leak fix (the "JSON-as-text in answer" bug)**:
- Root cause: noted's `backend/app/managers/llm_tools.py` injects a
  legacy `<tool_call>{"name":..., "args":...}</tool_call>` template
  into the system prompt. With native tool calling now ALSO active,
  Gemma sees two conflicting tool-format specs and stochastically
  emits the JSON literal as plain text in `content`. Self-reinforcing
  cascade: the fake tool call gets stored in history → next turn sees
  it → model imitates again.
- Two helpers in `app/llm_engine_server.py` mitigate this until noted
  can be rebuilt:
  - `_strip_history_thinking(messages)` — removes `<think>...</think>`
    AND any leftover JSON-as-text tool calls from prior assistant
    messages. Preserves current-turn tool sequences.
  - `_scrub_legacy_tool_template(content)` — removes noted's literal
    text-format tool-call template from any message before forwarding.
  Both called in `_LlamaServerProxy.create_chat_completion`.
- Validation: `noted/tests/leak_probe.py` is a Playwright probe in
  the `noted-test` container that drives noted's Assistant panel via
  `button[data-key="assistant"]` and runs a 12-turn
  multi-turn-with-tool conversation. **12/12 turns clean post-fix**,
  including the previously-failing "compare those two" follow-up.

### Permanent fix (deferred until Launchpad recovers)

The proper fix lives in noted, not agent_server: drop the
`TOOL_DESCRIPTIONS` injection in
`noted/backend/app/managers/llm_tools.py` (or gate it on backend
type — Anthropic still benefits from text-format instructions).
The agent_server scrub is a workaround, not the proper fix. Open a
noted-side PR for this once `apt-get update` against Launchpad is
reliable again.

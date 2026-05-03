# Phase 12 — User-facing model CRUD plan

Status: planning, not started. Last stage of the agent_server v2
migration. Depends on the rest being stable in production.

## Requirements (from user)

1. Switch the active model **mid-session** without restarting noted.
2. UI exposes selection for **three slot types**: active chat LLM,
   active embedding model, active reranker.
3. Selecting/unselecting a model **loads / unloads it from VRAM**.
4. **No add/remove** of models in the UI — that stays administrative
   (INI changes + container recreate).
5. UI shows useful per-model metadata: parameter count, context size,
   quantization, current state, VRAM impact.
6. User can give each model a **friendly name** (default = file name).

## Constraints we already know

- llama-server router exposes the operations we need:
  `GET /models`, `POST /models/{id}/load`, `POST /models/{id}/unload`,
  with model states `unloaded | loading | loaded | sleeping | failed`.
- Baseline models stay `load-on-startup = true` in
  `agent_server/llama-router-models.ini` and are NOT unloadable from
  the UI: gemma-4 (chat+vision), bge-m3 (embed), bge-reranker (rerank).
  Treat them as "active by default, slot occupied".
- Router-mode requires the `model:` field on each request to route to
  the right loaded instance. agent_server's `LlamaServerEngine`
  already does this for chat (sends `model: "gemma-4"` via
  `_llama_server_model`); embed and rerank in noted-rag do too
  (`config.EMBED_MODEL_NAME`, `config.RERANK_MODEL_NAME`).
- VRAM is finite (~24 GB on the RTX 4090). Total of all loaded
  models must fit. Need server-side guard against OOM.
- Per `feedback_check_active_model_first.md`: noted already has
  `/api/llm/health` with an `active_model` field. We extend that
  surface, not replace it.

## Architecture sketch

```
                                    ┌─────────────────────────┐
   User ──── select model ──────────►   noted frontend:        │
                                    │   Model Manager panel    │
                                    └─────────────┬────────────┘
                                                  │ HTTPS /api/models/*
                                                  ▼
                                    ┌─────────────────────────┐
                                    │   noted backend:         │
                                    │   model_manager service  │
                                    │   - registry + aliases   │
                                    │   - active-slot state    │
                                    │   - call llama-server    │
                                    │   - call noted-rag       │
                                    └─────┬─────────────┬──────┘
                                          │             │
                                          │             │ embed/rerank model_id
                                          │             ▼
                                          │       ┌──────────────┐
                                          │       │  noted-rag   │ (uses
                                          │       │  forwards    │  model_id
                                          │       │  to llama-vis│  per req)
                                          │       └──────┬───────┘
                                          │              │
                          chat model_id   │              │
                                          ▼              ▼
                                    ┌──────────────────────────┐
                                    │  llama-vision (router):  │
                                    │  /v1/models, /models/load│
                                    │  /models/unload, etc.    │
                                    └──────────────────────────┘
```

Active-slot state lives in **noted backend** (single source of truth).
agent_server and noted-rag pass the chosen model id per request — they
don't carry slot state themselves. This keeps switching atomic from
the user's perspective: change in UI → next request uses new model.

## Data model

### Persistent

`~/env/assets/noted/data/model_registry.json` (bind-mounted, survives
container rebuilds):

```json
{
  "active": {
    "chat": "gemma-4",
    "embed": "bge-m3",
    "rerank": "bge-reranker"
  },
  "aliases": {
    "gemma-4": "Gemma 4 (E4B Q4)",
    "bge-m3": "BGE-M3 embeddings",
    "bge-reranker": "BGE reranker v2"
  }
}
```

Just two top-level keys: current active per slot, and friendly-name
aliases. Models are NOT defined here — they're defined in
`llama-router-models.ini` (admin-only). This file only carries what
the user can change.

### Runtime (computed from llama-server's /v1/models)

Per-model object surfaced to the UI:

| Field | Source |
|---|---|
| `id` | INI section name (e.g. `gemma-4`, `bge-m3`) |
| `friendly_name` | aliases.json entry, fallback to `id` |
| `slot_type` | inferred from preset flags: `embedding=true` + `pooling=cls` → embed; `pooling=rank` → rerank; otherwise chat |
| `model_path` | INI `model =` field |
| `n_params` | parsed from GGUF metadata (use `gguf` python package, cache) |
| `n_ctx` | INI `c =` (or `ctx-size =`) field |
| `quantization` | parsed from filename or GGUF metadata |
| `mmproj_path` | INI `mmproj =` field (chat models with vision) |
| `state` | from `/v1/models[].status.value` (loaded / unloaded / sleeping / loading / failed) |
| `is_baseline` | INI `load-on-startup = true` |
| `vram_estimate_mb` | rough: file_size_bytes × 1.1 (overhead) |

## API surface (noted backend)

All under `/api/models/*`. Same authentication as the rest of noted.

### GET /api/models
Returns the full picture for the UI:
```json
{
  "models": [ {<per-model object>}, ... ],
  "active": { "chat": "gemma-4", "embed": "bge-m3", "rerank": "bge-reranker" },
  "vram": { "total_mb": 24563, "used_mb": 15800, "loaded_models_mb": 9800 }
}
```

### POST /api/models/{id}/load
Tells the router to load the model. Returns 202 + `state: "loading"`,
or 200 + `state: "loaded"` if already loaded. Refuses with 409 if
predicted VRAM after load would exceed total.

### POST /api/models/{id}/unload
Tells the router to unload. Refuses with 409 if `is_baseline=true` or
if `id` is currently the active model for any slot (force the user
to pick another active first).

### POST /api/models/active
```json
{ "slot": "chat" | "embed" | "rerank", "model_id": "..." }
```
Validates that `model_id` belongs to the right slot type and is loaded
(auto-load if not, returning the new state). Updates registry,
returns the new active mapping.

### PUT /api/models/{id}/name
```json
{ "friendly_name": "..." }
```
Updates `aliases.json`. Empty / null clears the alias (UI falls back
to `id`). 200 on success.

### GET /api/models/health
Lightweight: just the active mapping + baseline status. Fast for the
status bar / always-on indicators.

## Engine wiring

### chat (agent_server)
`LlamaServerEngine._llama_server_model` is currently a constructor
constant (`gemma-4`). Change to read the active chat model from
**each request's payload** (noted sends it as the `model` field on
`/v1/chat/completions`). agent_server already supports this via
`payload.setdefault("model", self._default_model)` — make
`_default_model` a fallback only, prefer caller-supplied value.

### embed + rerank (noted-rag)
`config.EMBED_MODEL_NAME` and `config.RERANK_MODEL_NAME` are read
once at startup. Refactor to read per request: noted-rag's `embed`
and `_rerank` accept an optional `model` parameter (default to env
var). noted backend's calls to noted-rag pass the active model id.

### Auto-load on use
When a request comes in for a model that's `unloaded` or `sleeping`,
agent_server / noted-rag should:
1. Call `/models/{id}/load` synchronously (block the request).
2. Poll until `loaded` (with a reasonable timeout, e.g. 60 s).
3. Forward the original request.
4. Surface "Loading model..." to the UI via the existing streaming
   protocol so the user knows why the first request after a switch
   is slow.

This keeps Phase 12 "no surprises" — selecting a model just means it's
the next request's target; if it isn't in VRAM yet, the request
itself triggers the load.

## UI sketch

New panel reachable from the existing icon-bar (suggest: under
Settings or as its own icon).

```
┌─ Models ──────────────────────────────────────────────────────┐
│ VRAM: 9.8 / 24.6 GB   [████████░░░░░░░░░░░░░░]                │
│                                                                │
│ ┌─ Chat ─────────────────────────────────────────────────────┐ │
│ │ ● Gemma 4 (E4B Q4)              4B params   131072 ctx  ★ │ │
│ │ ○ Mistral 7B Instruct Q4        7B params    32768 ctx    │ │
│ │ ○ Qwen 2.5 Coder 14B Q5         14B params   32768 ctx    │ │
│ │   [ Edit name ] [ Load / Unload ]                          │ │
│ └────────────────────────────────────────────────────────────┘ │
│                                                                │
│ ┌─ Embedding ────────────────────────────────────────────────┐ │
│ │ ● BGE-M3 embeddings             0.6B   8192 ctx   ★        │ │
│ │ ○ Other embedding model          ...                        │ │
│ └────────────────────────────────────────────────────────────┘ │
│                                                                │
│ ┌─ Reranker ─────────────────────────────────────────────────┐ │
│ │ ● BGE reranker v2                0.6B   8192 ctx   ★        │ │
│ └────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

- ★ = baseline (always loaded, can't unload).
- Radio per slot section = active.
- Click a row to expand: friendly-name input, full file path, full
  metadata, individual Load/Unload button (disabled for baseline +
  for the currently-active model).
- "VRAM" bar at the top updates live after each load/unload.
- Switching active immediately writes to `model_registry.json`; next
  request to that slot type uses the new model.

## Implementation phases

| # | Step | Output |
|---|---|---|
| 12.1 | Probe llama-server's model lifecycle endpoints + measure load/unload latency for our 3 baseline models. Document what `/v1/models` returns vs what we need to compute ourselves (n_params from GGUF). | Latency table + metadata-source matrix |
| 12.2 | Build `model_manager` service in noted backend with registry + aliases persistence. Read-only first: GET /api/models works, no mutation yet. | Read-only API live |
| 12.3 | Add load/unload + set-active mutations. Wire VRAM accounting + baseline guards. | Full API live |
| 12.4 | Refactor `LlamaServerEngine` and noted-rag to honour per-request model id (with auto-load on miss). | Engine wiring done |
| 12.5 | Build the Models UI panel. | UI shipped |
| 12.6 | Validation: switch chat model mid-conversation, verify embed switch reindexes correctly (or doc that it doesn't and why), verify rerank switch picks up new scores, verify VRAM accounting matches `nvidia-smi`. | Test report |

## Open design questions

- **Embedding switch implications**: switching embedding models at
  runtime invalidates all stored vectors in ChromaDB (different
  embedding spaces). UX choice: refuse switch unless re-index is run,
  OR allow switch with a "search disabled until reindex" warning.
  Suggest: refuse with a clear modal + "Reindex now" button that
  triggers per-Domain reingest.
- **Rerank switch**: scores recalibrate but stored vectors stay valid;
  switching is safe but threshold (`RERANK_MIN_SCORE`) may need tuning
  per model. Surface as a per-model config field if needed later.
- **Concurrent load/unload**: noted is mostly single-user; a simple
  RLock around model_manager mutations is enough. If we ever go
  multi-user, revisit.
- **Failure mode**: what if `/models/load` fails (corrupt file, OOM)?
  noted needs to keep the previous active model and surface the
  error in the UI. Don't silently degrade.
- **Sleep vs unload**: llama-server has `--sleep-idle-seconds N` for
  auto-sleep (frees VRAM but keeps state for fast wake). Worth
  exposing as a per-model config field, defaulting off. Sleeping
  models still count as loaded for UI but show a `sleeping` chip.
- **Model registry file ownership**: bind-mounted under noted's data/.
  Use the same RLock as DomainContext to avoid races during writes.

## Definition of done

- User can pick a non-baseline chat model from the UI; next chat turn
  uses it; the prior baseline model unloads if not in use elsewhere.
- User can rename any model; rename persists across container
  restarts.
- VRAM bar in the UI matches `nvidia-smi --query-gpu=memory.used`
  within ~500 MB.
- Switching embed model triggers a clear "must reindex" UX, not a
  silent broken-search state.
- Baseline models can't be unloaded; UI clearly indicates that.
- All operations work without restarting any container.

## 12.1 results (probe, 2026-05-03)

llama-server's lifecycle endpoints behave as expected, with one
async-state caveat to handle in client code.

**Endpoints (confirmed)**:
- `GET /v1/models` and `GET /models` — same payload (`id`, `aliases`,
  `tags`, `object`, `owned_by`, `created`, `status` with nested
  `value` and full `args` array). Note: `value` reflects current
  state (`loaded` / `unloaded` / `loading` / `sleeping` / `failed`).
- `POST /models/load` body `{"model": "<id>"}` — returns
  `{"success":true}` if accepted; returns `400 model is already
  running` if the target is loaded. URL `/v1/models/load` returns 404
  (it's `/models/load`, no `/v1`).
- `POST /models/unload` body `{"model": "<id>"}` — same shape.
- **Async semantics**: both load + unload return success in ~5 ms but
  the actual VRAM op completes later. Caller MUST poll
  `GET /v1/models[].status.value` until it reaches the target state.
  Unload finishes in ~70 ms, load takes seconds.

**Latencies measured (RTX 4090, baseline models)**:

| Model | File size | Load (full) | Unload (full) | API call returns |
|---|---|---|---|---|
| bge-reranker-v2-m3 (Q8) | 606 MB | 2.4 s | 70 ms | <10 ms |
| bge-m3 (Q8) | 605 MB | 2.2 s | ~70 ms | <10 ms |
| gemma-4-E4B-it (Q4_K_XL) + mmproj | 4865 + 945 MB | not measured (extrapolated ~20-25 s based on file size ratio) | n/a | <10 ms |

**UI implication**: a switch from one chat model to another with
auto-load on miss adds ~20-25 s of "Loading model..." for first-use
of any chat model that wasn't already loaded. Embed/rerank switches
are ~2-3 s. If we want snappier UX, we can allow the user to
pre-load multiple models (within VRAM budget) so the switch is just
an active-slot rewrite.

**Metadata limitations**: `/v1/models[].status` exposes the FULL
command-line args + INI preset string. From those we can extract
model_path, ctx-size, mmproj presence, embedding/pooling flags, etc.
What we DO NOT get from the endpoint:
- `n_params` — must read from GGUF metadata (use the inline mmap
  parser we already wrote during the chat-template extraction work,
  or add the `gguf` python package; total weight count is at
  `<arch>.block_count` × `<arch>.embedding_length` × derived factors).
- `n_ctx` (the trained ctx, vs the runtime ctx-size override) — also
  in GGUF metadata at `<arch>.context_length`.
- File size — `os.stat` on the model_path.
- Quantization scheme — parse from filename (`Q4_K_XL`, `Q8_0`, etc.)
  or read GGUF `general.file_type`.

**Implication for the backend service**: cache GGUF metadata reads on
first probe per model, since we never need them to change without an
admin-driven INI swap (which requires container recreate).

**Friendly-name persistence target file**:
`~/env/assets/noted/data/model_registry.json` — bind-mounted under
noted's data/ (already mounted). Single JSON with `active` (per slot)
and `aliases` (id → friendly name). Models themselves never declared
here, only annotations.

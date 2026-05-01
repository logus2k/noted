# Serving Worker Subprocess Architecture - Implementation Plan

**Status**: Designed, not started. Targets the window between 2026-04-16 (report delivery) and 2026-04-21 (live demo). Identified as the required fix for the cold-deploy Protobuf/TF version mismatch discovered 2026-04-14 during Phase 0 verification.

## Problem Being Solved

During Phase 0 verification of the serving refactor, the `Deploy v7` test after a `noted-serving` container restart produced this error:

```
VersionError: Detected incompatible Protobuf Gencode/Runtime versions when
loading tensorflow/core/framework/attr_value.proto: gencode 6.31.1
runtime 5.29.6. Runtime version cannot be older than the linked gencode
version.
```

Forensic investigation showed the timeline:
- Container started at T0 with `protobuf 5.29.6` and a matching older `tensorflow` (baseline from unpinned `client/requirements.txt`).
- uvicorn PID 1 (noted-serving control process) imported `google.protobuf 5.29.6` and `tensorflow` at startup - both loaded into memory.
- Model deploy at T0+36s ran `uv pip install -r model_reqs.txt` which wrote `protobuf 6.33.6` and `tensorflow==2.21.0` to disk.
- When `mlflow.pyfunc.load_model()` then ran inside the same uvicorn process, TF's C extensions (compiled against protobuf gencode 6.31.1) tried to use the **already-imported runtime protobuf 5.29.6** and crashed.

The fundamental problem: **you cannot hot-swap Python C extension modules in a running interpreter**. Once `google.protobuf` (or `tensorflow._pywrap_*`) is imported into a Python process, that version is locked in memory until the process restarts. `uv pip install` at runtime only rewrites disk - it has no effect on the running process.

This means the runtime-install-then-load approach in `ModelLoader._install_model_deps` + `_load_inner` is **fundamentally broken for any model whose pinned versions differ from the image baseline**. It only appears to work when the pins happen to match, or when the changes don't affect already-imported packages.

Three realistic fixes considered:

1. **Pin the image exactly to the model's versions** - makes runtime install a no-op but couples the image to one specific model.
2. **Subprocess-per-deploy architecture** - each Deploy spawns a fresh Python interpreter that does install + import + load from scratch. Clean imports by construction. *This plan.*
3. **Hot process restart** - `os.execv` the uvicorn process after install, reload pending model on startup. Drastic, hard to get right.

Option 2 is the only option that is both correct for all models AND decoupled from specific pinned versions, at the cost of ~3-5s spawn latency per Deploy.

## Goal

Replace the in-process `ModelLoader` with a **per-model worker subprocess** architecture. The long-running control-plane process never imports tensorflow/mlflow/numpy, so its imports never go stale. Each Deploy spawns a fresh Python interpreter that does install + import + load with a clean slate.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ noted-serving container                             │
│                                                     │
│  ┌────────────────────────────────────────────┐    │
│  │ Control plane (uvicorn PID 1)              │    │
│  │ main.py - thin FastAPI app                 │    │
│  │                                            │    │
│  │ Imports: fastapi, uvicorn, httpx,          │    │
│  │          pydantic, asyncio, subprocess,    │    │
│  │          json, logging                     │    │
│  │ DOES NOT IMPORT: mlflow, tensorflow,       │    │
│  │   numpy, pandas, torch, jax, etc.          │    │
│  │                                            │    │
│  │ WorkerManager:                             │    │
│  │   - current: {proc, port, info} | None     │    │
│  │   - start(model, version, alias) → stream  │    │
│  │   - kill() / predict() / schema()          │    │
│  └─────────┬──────────────────────────────────┘    │
│            │ asyncio.create_subprocess_exec        │
│            │ stdout=PIPE, stderr=STDOUT            │
│            ▼                                        │
│  ┌────────────────────────────────────────────┐    │
│  │ Worker subprocess (spawned per Deploy)     │    │
│  │ app/worker.py                              │    │
│  │                                            │    │
│  │ Fresh Python interpreter - no stale imports│    │
│  │ Steps:                                     │    │
│  │  1. Download model artifacts from MLflow   │    │
│  │  2. uv pip install -r model_reqs.txt       │    │
│  │     (runs in THIS process, which hasn't    │    │
│  │     imported ML libs yet, so stale-import  │    │
│  │     problem is impossible)                 │    │
│  │  3. Import mlflow, load model via pyfunc   │    │
│  │  4. Start mini-uvicorn on localhost:{port} │    │
│  │  5. Emit "ready" event to stdout           │    │
│  │  6. Serve /predict, /schema, /internal     │    │
│  │     requests from the control plane        │    │
│  │                                            │    │
│  │ Emits NDJSON to stdout throughout:         │    │
│  │  {phase: resolving, detail: ""}            │    │
│  │  {phase: downloading, detail: "v7"}        │    │
│  │  {phase: installing_deps, detail: "..."}   │    │
│  │  {phase: loading_model, detail: ""}        │    │
│  │  {phase: ready, port: 5523, health: {...}} │    │
│  │  # control plane now routes requests here  │    │
│  │                                            │    │
│  │ Dies on SIGTERM (Unload) or new Deploy     │    │
│  └────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

**Communication:**
- **Load progress**: worker → stdout NDJSON → control plane → HTTP streaming response (same contract as Phase 0a, no frontend changes).
- **Schema / predict**: control plane → `httpx.AsyncClient` → `http://localhost:{worker_port}/...` → worker FastAPI → response.
- **Lifecycle**: control plane keeps `asyncio.subprocess.Process` handle, kills via SIGTERM then SIGKILL.

## What stays the same

- **Frontend** (`ModelDeployer.js`, `ExplorerRegistryViews.js`, `ExplorerServingViews.js`): zero changes. The streaming NDJSON contract is preserved byte-for-byte.
- **Noted backend proxy** (`backend/app/routers/serving.py`): zero changes. Still streams NDJSON from noted-serving.
- **nginx config**: zero changes.
- **Memory rules**: streaming, no polling, no setTimeout, encapsulated classes.
- **MLflow client usage** inside the worker is the same code we have today - it just runs in a fresh process instead of the long-running one.

## What changes

### New files

- **`client/app/worker.py`** (new) - standalone script invoked as `python -m app.worker --model-name X --version Y [--alias Z]`. Contains most of the logic currently in `model_loader.py`:
  - Download artifacts from MLflow Registry
  - Run `uv pip install -r model_reqs.txt` if needed (but now with a fresh Python process that doesn't have stale imports)
  - Import mlflow + framework, load pyfunc model
  - Extract signature, flavors, framework, param count, artifact size
  - Start a small FastAPI app on a chosen localhost port (say 5523, or dynamically allocated via `bind to :0`)
  - Emits NDJSON progress events to stdout throughout
  - Emits terminal `{"phase": "ready", "port": 5523, "health": {...}}` when the uvicorn is bound and serving
  - Emits `{"phase": "error", "error": "..."}` on any failure and exits non-zero
  - Handles SIGTERM gracefully (shuts down the inner uvicorn, exits 0)

- **`client/app/worker_manager.py`** (new) - replaces `ModelLoader`. `WorkerManager` class:
  - `async start(model_name, version, alias) -> AsyncIterator[bytes]` - spawns the worker, yields NDJSON events as they arrive on stdout. Resolves internal state when a `ready` event is seen.
  - `async kill(timeout=10)` - SIGTERM, wait with timeout, then SIGKILL. Clears state.
  - `async predict(input_data) -> dict` - httpx.AsyncClient POST to worker's `/predict`. Returns the worker's response. 503 if no worker.
  - `async schema() -> dict` - httpx GET to worker's `/schema`.
  - `health() -> dict` - control-plane view: which model/version is currently deployed, worker PID, uptime, framework, params (cached from the `ready` event's health payload).
  - `asyncio.Lock` serializing `start` / `kill` so concurrent deploys queue cleanly.

### Modified files

- **`client/app/main.py`**:
  - Remove `ModelLoader`, `build_schema`, `run_prediction` imports at the top (they stay in `worker.py`).
  - Import `WorkerManager` instead. Single global instance.
  - `/health` - returns `worker_manager.health()`. Small, fast, no ML imports.
  - `/load` - creates a `DeployEventStream(worker_manager)`. Stream now bridges the worker's stdout NDJSON to the HTTP response.
  - `/unload` - `await worker_manager.kill()`. No more try-acquire semantics needed because we don't touch an in-process model - we signal the subprocess.
  - `/schema` - forwards to worker.
  - `/predict` - forwards to worker.

- **`client/app/deploy_stream.py`**: `DeployEventStream` now wraps `WorkerManager.start()` (which yields NDJSON bytes) instead of running `ModelLoader.load()` in a threadpool. Simpler - no more asyncio queue + executor juggling, no more phase_callback hack. The worker's stdout IS the event stream.

- **`client/app/model_loader.py`**: **retired**. Content moves to `worker.py`. File deleted.

- **`client/app/predict.py`**, **`client/app/schema_builder.py`**: unchanged; imported by `worker.py` instead of `main.py`.

- **`client/Dockerfile`**: unchanged. Same deps, same base image. Both control plane and worker share the same site-packages.

## Task breakdown

### Phase A - Worker script (~3h)

- **T-S.A.1** Create `client/app/worker.py` as a minimal standalone script that can be run as `python -m app.worker --model-name X --version Y`. Parses argparse args, prints a `resolving` NDJSON event, exits cleanly.
- **T-S.A.2** Port the MLflow artifact download logic from `model_loader.py._load_inner()` into `worker.py`. Emit `downloading` and `installing_deps` NDJSON events as it progresses.
- **T-S.A.3** Port `_install_model_deps()` logic. Running inside the worker means the first-time uv install is fresh (no stale imports to conflict with) so this finally works correctly even across TF major versions.
- **T-S.A.4** Port model loading + signature/framework/params extraction. Import `mlflow`, call `mlflow.pyfunc.load_model()`, unwrap for framework detection.
- **T-S.A.5** Start an inner FastAPI app on a dynamically-chosen free localhost port (bind to `127.0.0.1:0`, let OS pick, read back the bound port). Emit `ready` event with the chosen port + full health payload to stdout.
- **T-S.A.6** Implement `/predict`, `/schema`, `/internal-health` inside the worker FastAPI app. Logic is the same as today's `main.py` handlers but running in this fresh process.
- **T-S.A.7** Handle SIGTERM: catch signal, shutdown the inner uvicorn gracefully, exit 0. Docker SIGKILL timeout is 10s so graceful shutdown must complete inside that window.

### Phase B - WorkerManager (~2h)

- **T-S.B.1** Create `client/app/worker_manager.py` with `WorkerManager` class. Fields: `_proc`, `_port`, `_info`, `_lock`, `_http_client`.
- **T-S.B.2** `async start(model_name, version, alias)` - uses `asyncio.create_subprocess_exec(sys.executable, '-m', 'app.worker', ...)` with `stdout=PIPE, stderr=STDOUT`. Returns an async generator that reads the worker's stdout line by line, parses NDJSON, yields events. Stores the `port` from the `ready` event. Lock-protected.
- **T-S.B.3** `async kill(timeout=10)` - `self._proc.terminate()`, then wait with timeout, then `self._proc.kill()`. Clears state. Lock-protected.
- **T-S.B.4** `async predict(input_data)` / `async schema()` - httpx.AsyncClient against `http://127.0.0.1:{self._port}/`. Returns the worker's JSON response.
- **T-S.B.5** `health()` - synchronous read of current state. Returns the same shape the old `ModelLoader.get_health` did.
- **T-S.B.6** Replace Deploy during active Deploy: `start()` under lock first calls `kill()` if there's an existing worker.
- **T-S.B.7** Dead-worker detection: `predict` / `schema` catch httpx errors, return 503, set state to idle (so next `/health` reflects the dead state).

### Phase C - Control plane rewiring (~1.5h)

- **T-S.C.1** Update `main.py` to import `WorkerManager` instead of `ModelLoader`. Global `worker_manager = WorkerManager()`.
- **T-S.C.2** Rewrite `DeployEventStream.run()` to wrap `worker_manager.start(...)` - which already yields NDJSON. Much simpler than today's queue+executor bridge.
- **T-S.C.3** `/health` returns `worker_manager.health()`.
- **T-S.C.4** `/unload` becomes `await worker_manager.kill()`.
- **T-S.C.5** `/predict` and `/schema` become thin proxies to `worker_manager.predict(...)` / `worker_manager.schema()`.
- **T-S.C.6** Startup hook: register `atexit` / FastAPI `shutdown` event to kill any worker on container shutdown (prevent orphans).

### Phase D - Retire in-process loader (~30 min)

- **T-S.D.1** Delete `client/app/model_loader.py`.
- **T-S.D.2** Delete `client/app/deploy_stream.py`'s now-unused asyncio queue / phase-callback plumbing; the class becomes a thin wrapper around `worker_manager.start()`.
- **T-S.D.3** Remove `set_phase_callback` hooks from anywhere that still references them (nothing should, after A-C).
- **T-S.D.4** Delete the `_installed_reqs_hashes` cache - no longer needed because the worker process is already fresh, and uv's on-disk cache handles repeat downloads.

### Phase E - Verification (~1.5h)

- **T-S.E.1** Rebuild `noted-serving` image. Confirm control plane starts without importing tensorflow (check startup log - should be fast, ~1s instead of ~5s today).
- **T-S.E.2** Test 1: cold container, Deploy v7. Expected: worker spawns, runs uv install (if needed), loads TF 2.21 fresh, serves. Verify `nvidia-smi` shows the GPU used by the worker subprocess, not the control plane.
- **T-S.E.3** Test 2: with v7 deployed, Deploy v7 again. Expected: WorkerManager kills the existing worker and spawns a new one. Total time bounded by TF import (~3-5s) since uv cache is warm.
- **T-S.E.4** Test 3: Try It after Deploy. Verify `/predict` round-trips through the worker correctly.
- **T-S.E.5** Test 4: Unload. Worker dies, VRAM released (subprocess exit is the cleanest possible release - no `tf.keras.backend.clear_session()` hacks needed).
- **T-S.E.6** Test 5: Deploy v7 → Deploy v6 (hypothetically different pins, or same). Second deploy spawns fresh worker. Verify no stale-import crash.
- **T-S.E.7** Test 6: Simulate container restart then immediately Deploy. Cold uv cache → slow install (~50s), but it works end-to-end (the fresh worker subprocess picks up the fresh install correctly).
- **T-S.E.8** Test 7: socket.io Assistant connection stays up during long Deploy (the control plane has no heavy work, event loop is always free).

### Phase F - Memory updates (~30 min)

- **T-S.F.1** Update `project_serving_refactor.md` with the new architecture diagram, decisions, and phase status. Rename "Phase 0" section to "Phase 0a" and this work to "Phase 0b - Worker subprocess architecture".
- **T-S.F.2** Update MEMORY.md index entry to reflect "Phase 0a shipped, 0b in progress/shipped".

## Effort estimate

| Phase | Hours |
|-------|-------|
| A - Worker script | 3 |
| B - WorkerManager | 2 |
| C - Control plane rewiring | 1.5 |
| D - Retire in-process loader | 0.5 |
| E - Verification | 1.5 |
| F - Memory updates | 0.5 |
| **Total** | **9 hours** |

## Key design decisions

1. **Per-Deploy spawn, not a persistent sidecar.** When the user Deploys a different model, the old worker dies and a fresh one replaces it. This guarantees clean imports. Trade-off: ~3-5s spawn latency per Deploy, but this is bounded and predictable.

2. **HTTP-over-localhost instead of stdin/stdout pipes for runtime requests.** stdin/stdout is used only for the initial load streaming. Once ready, predict/schema go over HTTP to a localhost port. Cleaner, async-friendly, easier to debug with curl from inside the container.

3. **Dynamic port allocation** (bind to `:0`, read back the assigned port). Avoids port collision if we ever run multiple workers. Control plane reads the port from the worker's `ready` NDJSON event.

4. **Graceful shutdown via SIGTERM with 10s grace + SIGKILL fallback.** Matches Docker's stop behavior.

5. **Control plane is intentionally naive about models.** It never imports mlflow/TF/etc. If a future refactor wants to add multi-worker support or worker pooling, the control plane is already the right shape for it.

6. **MLflow client lives in the worker.** This means the worker runs two imports of mlflow (once for download, once for `pyfunc.load`). Both are fresh in the worker's Python, so no conflict. The control plane doesn't need mlflow at all.

7. **Same shared site-packages for control plane and worker.** Avoids per-worker venvs. The control plane happens to not import any of the heavy packages, so it's insulated from disk changes.

## Risks / open questions

1. **Startup latency per Deploy.** Spawning a Python subprocess that imports tensorflow takes ~3-5s even warm. Cold (uv cache empty) can take minutes. This is the same cost we have today, just paid on every Deploy instead of once per container. Users trade "first Deploy is slow, rest are fast" for "every Deploy has a floor of 3-5s but they all work consistently". Worth it given the current implementation is actually broken.

2. **GPU contention during Deploy replace.** When Deploy replaces an active worker, there's a brief window where the old worker holds VRAM while the new one tries to allocate. We kill the old one first, `await` it, then spawn the new. Sequential. Safe.

3. **MLflow client version in the control plane vs worker.** If the worker's uv install changes mlflow for the container, the control plane sees the new version on next restart but not immediately. Control plane doesn't import mlflow so this is fine.

4. **Existing uv hash cache.** Not needed anymore. The worker's install happens in a fresh process, and uv's on-disk cache handles repeat downloads. Can delete `_installed_reqs_hashes`.

5. **Non-goals for this phase**: multi-worker support, model warmup, pre-spawned worker pools, health check endpoints on the worker for liveness, load balancing, blue-green deploys. Keep it simple.

## Expected Deploy latency profile

With the worker architecture alone (no extra caching layers):

| Scenario | Time | Why |
|----------|------|-----|
| Deploy #1 after fresh container, cold uv cache | ~50-60s | uv downloads TF wheel (546 MB), installs, worker imports everything fresh |
| Deploy #2 same model | ~3-5s | uv cache warm, "no changes" install, worker fresh-imports with warm FS cache |
| Deploy of different model with same-major TF | ~5-10s | small delta install from uv's wheel cache |
| Deploy of different model needing a different major TF | ~50-60s | one-off cold path again for the new wheels |
| Unload → Deploy same model | ~3-5s | same as Deploy #2 |
| Container restart → Deploy of previously-deployed model | ~50-60s | uv cache is inside the container, lost on restart (unless Layer 2 below is added) |

## Why this architecture is also the right VRAM story

A side benefit of the per-Deploy subprocess design: **GPU memory release is guaranteed**, not best-effort.

When a Linux process exits, the kernel reclaims all its resources: host RAM, CUDA context, VRAM allocations held under that context, any retained framework pools, compile caches, graph state. Process death = clean slate on the GPU.

Contrast with the Phase 0a in-process cleanup code (`tf.keras.backend.clear_session()`, `torch.cuda.empty_cache()`, `gc.collect()`):

- Those calls ask the framework *nicely* to release resources.
- Frameworks retain internal pools that may not return to the driver.
- The CUDA driver keeps a process-level memory context "just in case" until the process exits.
- `nvidia-smi` would often still show allocation after the cleanup ran.

With Phase 0b:

```python
worker.terminate()           # SIGTERM
await worker.wait(timeout=10) # process exits → CUDA context destroyed
# VRAM returned to device by the driver, no framework cooperation needed
```

After a clean Unload, `nvidia-smi` shows the worker's PID has vanished from the GPU process list and the associated VRAM row is gone. The control plane never imports CUDA-bound libraries so it holds no GPU memory of its own.

This is why Phase 0b is the right architecture not only for correctness (stale C-extension imports) but also for GPU memory hygiene. Both wins come from the same mechanism.

Framework-specific `clear_session` / `empty_cache` hacks from Phase 0a can be removed - they're unnecessary now and misleading about what they actually guarantee.

## Optional cache persistence layers (recommended)

Three optional optimizations beyond the core worker architecture. Each can be layered on top independently without changing the worker design. Layers 2 and 3 depend on the uv cache from Layer 1 being present.

### Layer 1: uv download cache volume

**What**: named Docker volume on `/root/.cache/uv` in the `noted-serving` container.

**docker-compose.yml change**:
```yaml
services:
  noted-serving:
    volumes:
      - noted-serving-uv-cache:/root/.cache/uv
volumes:
  noted-serving-uv-cache:
```

**Effect**: uv's downloaded wheels survive container restarts and image rebuilds (the volume lives outside the image layers). Cold installs drop from "~50s (download + resolve + install)" to "~5-10s (resolve + install from cache)" because downloads are skipped.

**Safety**: 100% safe. The uv cache is just wheel files - can be cleaned/rebuilt at any time, no drift with the image baseline.

**Effort**: ~15 minutes (docker-compose edit + restart).

### Layer 2: per-model venv on host

**What**: each unique model `requirements.txt` (keyed by SHA-256 hash) gets its own Python venv under a host-mounted directory.

**Directory layout**:
```
/var/lib/noted-serving/venvs/{reqs_hash}/
├── bin/python
├── lib/python3.12/site-packages/
│   ├── mlflow/
│   ├── tensorflow/
│   └── ...
└── ...
```

**Worker startup flow**:
1. Download model's `requirements.txt` via MLflow artifact API.
2. Compute `hash = sha256(requirements.txt)`.
3. If `/var/lib/noted-serving/venvs/{hash}/` exists, skip install entirely. Launch worker subprocess using `./venvs/{hash}/bin/python -m app.worker ...`.
4. Otherwise, create the venv with `uv venv --python 3.12 ./venvs/{hash}/`, activate it, `uv pip install -r requirements.txt`, then spawn worker against it.

**docker-compose.yml change**:
```yaml
services:
  noted-serving:
    volumes:
      - noted-serving-uv-cache:/root/.cache/uv
      - noted-serving-venvs:/var/lib/noted-serving/venvs
volumes:
  noted-serving-uv-cache:
  noted-serving-venvs:
```

**Effect**: after the first deploy of any model, all subsequent deploys of the same model (across container restarts, rebuilds, everything) are ~3-5s because the exact venv already exists on host. The "which model is deployed" decision becomes "which venv to spawn from" - the slow path is only hit the first time a new `requirements.txt` is seen.

**Safety**: venvs are isolated per-hash. Image rebuilds don't affect them because they're in a host-mounted volume, not in the image. If the venv ever corrupts, delete `/var/lib/noted-serving/venvs/{hash}/` and it'll be recreated on next Deploy.

**Relationship to MLflow conventions**: this is exactly what `mlflow models serve -m models:/X/Y` does internally - it creates a per-model conda env / venv. We're just doing the same thing with uv and managing the cache ourselves.

**Effort**: ~2 additional hours. Worker startup logic, venv creation path, hash-based cache lookup.

### Layer 3: worker pool with hash-based routing

**What**: keep multiple worker subprocesses alive simultaneously, keyed by `requirements.txt` hash. Reuse workers when redeploying the same model or a same-hash different model.

**Why**: eliminates the "kill old worker, spawn new one" cost for common demo scenarios where the user alternates between models (e.g. comparing v6 and v7 of the same registered model, or comparing two models that share the same TF version).

**Data structures**:

```python
class WorkerSlot:
    proc: asyncio.subprocess.Process
    port: int
    req_hash: str                          # SHA-256[:12] of this worker's requirements.txt
    venv_path: str                         # /var/lib/noted-serving/venvs/{req_hash}
    loaded_model: tuple[str, str]          # (name, version) currently inside this worker
    last_used: float                       # monotonic timestamp for LRU

class WorkerPool:
    _workers: dict[str, WorkerSlot]        # keyed by req_hash
    _current: str | None                   # which req_hash serves /predict
    _max_workers: int = 3                  # memory budget
    _lock: asyncio.Lock
```

**Deploy flow with pool**:

1. Download the model's `requirements.txt` via MLflow artifact API (lightweight, one small file).
2. `req_hash = sha256(requirements.txt).hexdigest()[:12]`.
3. `async with pool._lock:`
   - **Case A - same model, same hash**: `pool._workers[req_hash]` exists AND its `loaded_model == (name, version)`. Just set `pool._current = req_hash`, touch `last_used`, return current health. **~200 ms** - no spawn, no load, just a bookkeeping update.
   - **Case B - same hash, different model version**: `pool._workers[req_hash]` exists but `loaded_model != (name, version)`. POST `/internal/switch {model_name, version}` to the worker. Worker calls `mlflow.pyfunc.load_model(...)` in-place inside its existing Python process, clearing the previous model via `clear_session()` + `gc.collect()`. **~1-3 s** - no spawn, no TF reimport, just a model weight swap.
   - **Case C - new hash, pool has room**: `len(pool._workers) < max_workers`. Spawn a new worker via the Layer 2 venv. Add to pool, set `_current`. **~3-5 s** (warm venv) or **~50-60 s** (cold venv).
   - **Case D - new hash, pool is full**: evict the LRU worker first (SIGTERM, wait, remove from dict, **keep** its venv on disk). Then spawn a new worker as in Case C.

**Key detail - Case B safety**: when the requirements hash is identical, the C extensions (tensorflow, protobuf, etc.) are byte-identical in the venv. The stale-import bug that Phase 0b solves for cross-version Deploy cannot happen for same-hash Deploy because nothing changes on disk. In-place model swap via `mlflow.pyfunc.load_model(...)` is safe.

**Unload semantics with pool + Layer 2**:

Per user direction, the user-facing Unload button has clear "purge everything for this model" semantics:

- Kill the current worker subprocess (guaranteed VRAM release via process exit).
- `shutil.rmtree` the venv directory that worker was using.
- Remove the pool entry for that `req_hash`.
- Set `pool._current = None`.

**Automatic LRU eviction**, by contrast, only kills the process and removes the pool entry. It keeps the venv on disk so future Deploys of any same-hash model are still fast.

This gives users two different freeing mechanisms:

| Mechanism | Trigger | Frees RAM | Frees VRAM | Frees disk | Fast redeploy after? |
|-----------|---------|-----------|-----------|-----------|----------------------|
| LRU eviction (automatic) | Pool full, new Deploy | ✓ | ✓ | ✗ (venv stays) | Yes (~3-5 s, reuse venv) |
| Unload button (explicit) | User clicks Unload | ✓ | ✓ | ✓ (rmtree venv) | No (~50-60 s, cold install) |

Users who want to reclaim memory don't need to do anything - the pool handles it silently. Users who want to fully purge a model (demo reset, disk cleanup) click Unload.

**UI is unchanged** from the current design: Deploy / Unload / Try It per version row, Unload visible only when this version is currently deployed. Users never see "which worker", "which venv", or "which hash" - those are implementation details under the hood.

**Additional tasks on top of Phase 0b core**:

- **T-S.A.8** Worker exposes `POST /internal/switch {model_name, version}` that:
  1. Acquires the worker's internal lock.
  2. Clears the previous model: `self._model = None`, framework-specific cleanup, `gc.collect()`.
  3. Calls `mlflow.pyfunc.load_model("models:/{name}/{version}")`.
  4. Updates `self._loaded_model` state.
  5. Returns the new health payload.
  6. Emits nothing to stdout (this is an HTTP call, not a spawn-streaming call).
- **T-S.B.8** `WorkerPool` replaces the single-slot field in `WorkerManager`. Exposes `start()` / `switch_or_spawn()` / `unload_current()` / `evict_lru()`.
- **T-S.B.9** Deploy logic distinguishes Cases A/B/C/D per above. Same-hash-same-model is near-instant; same-hash-different-model is an HTTP switch call; new-hash is a spawn.
- **T-S.B.10** Pool cleanup on control plane shutdown - kill all workers, do NOT delete venvs (so next container start can reuse them via Layer 2).
- **T-S.B.11** Unload implementation: kill current worker, `shutil.rmtree` its venv, remove from pool.
- **T-S.E.9** Verification test: Deploy v6 → Deploy v7 (same requirements hash) → measure. Expected **~1-3 s** for the second Deploy.
- **T-S.E.10** Verification test: Deploy v6 → Deploy v7 → Deploy v6 → measure each. Third Deploy expected **<200 ms** because v6 is still in the pool from the first Deploy.
- **T-S.E.11** Verification test: explicit Unload on v7. `nvidia-smi` shows the worker's PID gone, VRAM reclaimed, venv directory removed from `/var/lib/noted-serving/venvs/`.

**Effort**: ~3 additional hours on top of Phase 0b core + Layer 2.

### Recommended adoption order

1. **Phase 0b core**: worker subprocess architecture. Solves the stale-import crash. (9 h)
2. **Layer 1 (uv cache volume)**: trivial, ships with Phase 0b. (15 min)
3. **Layer 2 (per-model venvs)**: persist venvs across restarts/rebuilds. (2 h)
4. **Layer 3 (worker pool + in-place switch + Unload-deletes-venv)**: near-instant same-hash switching, clean freeing semantics. (3 h)

Total if all four layers ship together: **~14-15 hours**.

For the Apr 21 demo, all four layers are worth shipping - the demo likely alternates between model versions, and Layer 3 makes that interaction feel instant.

## What this plan does NOT fix

- **First-ever cold install of a new model requirements.txt**. The FIRST time any new set of requirements is seen on a host, wheels have to be downloaded + installed. Layer 1 reduces subsequent cold starts; Layer 2 eliminates them entirely for already-seen requirements. But the first-time cost is unavoidable.
- **VRAM fragmentation across Deploy cycles**. Each new worker process gets a fresh CUDA context, but the driver may retain some memory between processes. Not a blocker.
- **Multi-client coordination** (parked in the project doc under Known Limitations). The per-Deploy subprocess model is orthogonal to "two users deploying different models at the same time" - it's still a single-slot serving container from the user's perspective.

## Rollback plan

If the worker architecture introduces regressions before the Apr 21 demo:

- The current Phase 0a code (in-process ModelLoader with the streaming /load proxy) still exists in git history.
- Revert path: git revert the Phase 0b commits, rebuild `noted-serving`. The control plane goes back to its current buggy-but-known state.
- Mitigation for the revert state: users instructed to restart the serving container between Deploys of models with different pinned versions.

## Connection to the longer-term venv-based serving plan

This plan (Phase 0b) and the earlier "venv-based prediction via KernelManager" (Phase 1+) are not alternatives - they're layers on the same idea:

- Phase 0b: prediction runs in a subprocess spawned by `noted-serving`. Simple, self-contained.
- Phase 1+: prediction runs in the project's training venv via `noted`'s existing kernel infrastructure. Eliminates the separate `noted-serving` container for noted-native models. Falls back to Phase 0b's subprocess approach for foreign models.

The worker subprocess mechanism built in Phase 0b is directly reusable when we build Phase 1+ - the "worker" just becomes "the kernel in the training venv" instead of "a subprocess spawned by noted-serving". Same NDJSON contract, same lifecycle, different source of truth for the environment.

## Revisit triggers for extensions

Reopen this plan if:

- Users ask for simultaneous serving of multiple models (→ worker pooling).
- The ~3-5s per-Deploy subprocess spawn becomes a user-facing complaint (→ pre-warmed worker pool).
- A non-Python model framework (TensorFlow Serving, Triton) needs to be integrated as a worker type (→ generalize the worker protocol).
- Remote workers (e.g. on a separate GPU node) become a requirement (→ the localhost HTTP protocol generalizes to remote HTTP naturally).

Until then, single-worker subprocess is enough.

# Multi-Runtime Environment Architecture

## Overview

Design and implementation plan for supporting multiple Python versions (3.10-3.14 + free-threading) in the notebook application, with an architecture that allows adding new languages (C#, Java, R) by only updating the Dockerfile and a metadata file — zero code changes.

## Design Decisions

1. **Convention-based discovery**: Available runtimes are discovered from a well-structured directory layout (`data/runtimes/{language}/{version}/runtime.json`), not hardcoded
2. **Templated commands**: All language-specific behavior (env creation, kernel launch, package management) is defined in `runtime.json` descriptors using placeholder tokens
3. **Single Docker image with GPU**: Base image `nvidia/cuda:12.x-runtime-ubuntu24.04` includes CUDA libraries; GPU is auto-detected when available, CPU fallback is transparent
4. **Ubuntu + deadsnakes PPA**: Instead of Debian slim, use Ubuntu 24.04 with deadsnakes PPA so `apt-get install python3.X` always gets the latest patch version
5. **Phased implementation**: Backend first (preserving old API), then kernel generalization, then frontend, then Dockerfile — each phase keeps the app working

## Directory Layout

```
data/
  runtimes/                              # Read-only, created by Dockerfile
    python/
      3.10/runtime.json
      3.11/runtime.json
      3.12/runtime.json
      3.13/runtime.json
      3.13t/runtime.json                 # free-threaded
      3.14/runtime.json
      3.14t/runtime.json                 # free-threaded
    r/                                   # future
      4.4/runtime.json
    csharp/                              # future
      9.0/runtime.json
  environments/                          # User-created, read-write
    python/
      3.12/
        taap_mp3/                        # migrated from old flat layout
        test_env/
      3.13/
        data_science/
      3.14t/
        experiments/
```

**Runtime ID** = `{language}/{version}` (e.g. `python/3.12`, `r/4.4`)

## runtime.json Schema

Each runtime directory contains a `runtime.json` placed by the Dockerfile. Placeholders `{executable}`, `{env_path}`, `{connection_file}` are resolved at runtime by the backend.

### Python example

```json
{
  "language": "python",
  "version": "3.12",
  "display_name": "Python 3.12",
  "executable": "/usr/bin/python3.12",
  "env_create_cmd": ["{executable}", "-m", "venv", "{env_path}"],
  "env_post_create_cmds": [
    ["{env_path}/bin/pip", "install", "ipykernel"]
  ],
  "kernel_cmd": ["{env_path}/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
  "kernel_language": "python",
  "package_manager": {
    "list_cmd": ["{env_path}/bin/pip", "list", "--format=json"],
    "install_cmd": ["{env_path}/bin/pip", "install"],
    "remove_cmd": ["{env_path}/bin/pip", "uninstall", "-y"]
  }
}
```

### Free-threading example (Python 3.13t)

```json
{
  "language": "python",
  "version": "3.13t",
  "display_name": "Python 3.13 (free-threaded)",
  "executable": "/usr/bin/python3.13-nogil",
  "env_create_cmd": ["{executable}", "-m", "venv", "{env_path}"],
  "env_post_create_cmds": [
    ["{env_path}/bin/pip", "install", "ipykernel"]
  ],
  "kernel_cmd": ["{env_path}/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
  "kernel_language": "python",
  "package_manager": {
    "list_cmd": ["{env_path}/bin/pip", "list", "--format=json"],
    "install_cmd": ["{env_path}/bin/pip", "install"],
    "remove_cmd": ["{env_path}/bin/pip", "uninstall", "-y"]
  }
}
```

### Future R example

```json
{
  "language": "r",
  "version": "4.4",
  "display_name": "R 4.4",
  "executable": "/usr/bin/R",
  "env_create_cmd": ["/usr/bin/Rscript", "--vanilla", "-e", "renv::init(project='{env_path}')"],
  "env_post_create_cmds": [
    ["/usr/bin/Rscript", "--vanilla", "-e", "IRkernel::installspec(user=FALSE, prefix='{env_path}')"]
  ],
  "kernel_cmd": ["/usr/bin/R", "--slave", "-e", "IRkernel::main()", "--args", "{connection_file}"],
  "kernel_language": "r",
  "package_manager": {
    "list_cmd": ["/usr/bin/Rscript", "--vanilla", "-e", "cat(jsonlite::toJSON(as.data.frame(installed.packages()[,c('Package','Version')])))"],
    "install_cmd": ["/usr/bin/Rscript", "--vanilla", "-e", "install.packages(commandArgs(TRUE), repos='https://cran.r-project.org')"],
    "remove_cmd": ["/usr/bin/Rscript", "--vanilla", "-e", "remove.packages(commandArgs(TRUE))"]
  }
}
```

## Backend Architecture

### New classes (in `backend/app/managers/env_manager.py`)

**`RuntimeRegistry`** — Discovers and caches available runtimes:
- `__init__(runtimes_dir)`: path to `data/runtimes/`
- `list_runtimes() -> list[dict]`: returns `[{language, version, display_name, runtime_id}]`
- `get_runtime(runtime_id) -> dict`: returns full runtime.json spec
- `resolve_template(template, **kwargs) -> list[str]`: replaces `{placeholder}` tokens in command lists

**`EnvironmentManager`** — Language-agnostic environment management:
- `__init__(environments_dir, registry)`: auto-migrates old flat envs on first run
- `list_envs() -> list[dict]`: walks `environments/{lang}/{ver}/*`, returns `[{name, runtime_id, language, version, display_name}]`
- `create_env(runtime_id, name, requirements?) -> dict`: creates env using runtime's `env_create_cmd`, runs `env_post_create_cmds`, optionally installs requirements
- `delete_env(runtime_id, name) -> dict`: removes env directory
- `get_kernel_cmd(runtime_id, name) -> (list[str], str)`: returns `(kernel_cmd, kernel_language)` for kernel manager
- `list_packages(runtime_id, name) -> list[dict]`: runs runtime's `package_manager.list_cmd`
- `install_packages(runtime_id, name, packages) -> dict`: runs `package_manager.install_cmd`
- `remove_packages(runtime_id, name, packages) -> dict`: runs `package_manager.remove_cmd`

### Kernel manager changes (`backend/app/managers/kernel_manager.py`)

`KernelSession` dataclass fields change:
- Remove: `python_path`, `venv_path`
- Add: `runtime_id`, `env_name`, `kernel_cmd`, `kernel_language`

`start_kernel()` signature:
```python
async def start_kernel(self, session_id, kernel_cmd, kernel_language,
                       display_name, project_id, notebook_path, client_sid)
```

No more hardcoded `python3` kernel name or `ipykernel_launcher`. The `kernel_cmd` and `kernel_language` come from the runtime spec via `EnvironmentManager.get_kernel_cmd()`.

### API changes (`backend/app/routers/venvs.py`)

New endpoints:
```
GET    /api/runtimes                                -> list available runtimes + GPU info
GET    /api/envs                                     -> list all environments
POST   /api/envs                                     -> create env {runtime_id, name, requirements?}
DELETE /api/envs/{runtime_id:path}/{name}             -> delete env
GET    /api/envs/{runtime_id:path}/{name}/packages    -> list packages
POST   /api/envs/{runtime_id:path}/{name}/packages    -> install packages
DELETE /api/envs/{runtime_id:path}/{name}/packages    -> remove packages
```

The `runtime_id` (e.g. `python/3.12`) contains a slash, so FastAPI uses `:path` parameter type.

Old `/api/venvs` endpoints kept as compatibility wrappers during migration.

### Socket.IO changes (`backend/app/main.py`)

`kernel:start` event payload changes from `{venv_name}` to `{runtime_id, env_name}`. Backward compatibility: if old `venv_name` is sent, scan environments for matching name.

## Frontend Architecture

### Explorer tree structure

Three-level hierarchy under Environments:
```
Environments
  Python 3.10
    my_env_1
  Python 3.12
    taap_mp3
    test_env
  Python 3.13 (free-threaded)
    experiments
```

Tree node keys:
- Runtime nodes: `runtime:{runtime_id}` (e.g. `runtime:python/3.12`)
- Environment nodes: `env:{runtime_id}:{name}` (e.g. `env:python/3.12:taap_mp3`)

### Create form

- Clicking a runtime node → create form pre-filled with that runtime
- Clicking Environments root → create form with runtime dropdown selector
- Fields: Runtime selector, Environment name, Requirements (optional)

### app.js state changes

`_activeVenv` shape: `{name, runtimeId, displayName}` (was `{name, pythonVersion}`)

localStorage format: `runtimeId|name` (e.g. `python/3.12|taap_mp3`) — use `|` separator since `runtime_id` contains `/`

`startKernel(runtimeId, envName)` instead of `startKernel(venvName)`

### InfoBar changes

`setVenv(name, displayName)` — shows `envName (displayName)` (e.g. `taap_mp3 (Python 3.12)`)

## Dockerfile Strategy

**Single image with GPU support**:

```dockerfile
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04

# deadsnakes PPA for multiple Python versions
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && apt-get update

# Each install auto-resolves to latest patch. Rebuild image to update.
RUN apt-get install -y python3.10 python3.10-venv python3.10-dev \
                       python3.11 python3.11-venv python3.11-dev \
                       python3.12 python3.12-venv python3.12-dev \
                       python3.13 python3.13-venv python3.13-dev \
                       python3.13-nogil \
                       python3.14 python3.14-venv python3.14-dev \
                       python3.14-nogil

# System deps for pyzmq and pip
RUN apt-get install -y gcc libzmq3-dev python3-pip && rm -rf /var/lib/apt/lists/*
```

- GPU: Run with `docker run --gpus all` on GPU hosts; works on CPU-only hosts without `--gpus`
- Free-threading: `python3.X-nogil` packages from deadsnakes
- Auto-update: Rebuilding image (`docker build --no-cache`) gets latest patch versions
- GPU detection: Backend runs `nvidia-smi` at startup, exposes via `GET /api/runtimes` response

### Runtime config generation

A `scripts/create_runtime_configs.sh` script runs during Docker build to auto-generate `runtime.json` for each installed Python by detecting executables.

## Migration Plan

### Existing environments (data/environments/)

Auto-detected at startup: if `bin/python` exists directly under `data/environments/{name}`, it's an old flat env. Moved to `data/environments/python/3.12/{name}` (3.12 was the original Dockerfile base).

### localStorage

Old format `name:pythonVersion` detected by absence of the new separator. Cleared on mismatch — falls back to "Select kernel" (already implemented).

### Socket.IO

`kernel:start` accepts both old `{venv_name}` and new `{runtime_id, env_name}` during transition.

## Implementation Phases

### Phase 1: Backend Foundation (no frontend breakage)
1. Add `RUNTIMES_DIR` to `config.py`
2. Create initial `data/runtimes/python/3.12/runtime.json` for current system Python
3. Create `env_manager.py` with `RuntimeRegistry` + `EnvironmentManager`
4. Keep old `venv_manager.py` as compatibility wrapper
5. Add new API endpoints, keep old `/api/venvs` working

**Checkpoint**: Old frontend works. Existing envs migrated.

### Phase 2: Kernel Manager Generalization
6. Update `KernelSession` and `start_kernel()` to be language-agnostic
7. Update `kernel:start` Socket.IO handler with backward compat

**Checkpoint**: Backend fully generalized. Old frontend still works.

### Phase 3: Frontend Updates
8. Update `KernelClient.js` `startKernel()` signature
9. Update `app.js` state shape and localStorage format
10. Rebuild `ExplorerPanel.js` tree structure and create form
11. Update `InfoBar.js` to use `displayName`

**Checkpoint**: Full end-to-end working.

### Phase 4: Dockerfile & Cleanup
12. Update Dockerfile to Ubuntu + CUDA + deadsnakes + multi-Python
13. Add `scripts/create_runtime_configs.sh`
14. Remove old compatibility endpoints and `SYSTEM_PYTHON`

## Files Summary

| File | Action |
|------|--------|
| `backend/app/config.py` | Add `RUNTIMES_DIR` |
| `backend/app/managers/env_manager.py` | **New** — `RuntimeRegistry` + `EnvironmentManager` |
| `backend/app/managers/venv_manager.py` | Keep as compat wrapper, then remove in Phase 4 |
| `backend/app/managers/kernel_manager.py` | Generalize `KernelSession` + `start_kernel()` |
| `backend/app/routers/venvs.py` | Add new endpoints alongside old ones |
| `backend/app/main.py` | Update `kernel:start` handler + manager instantiation |
| `frontend/js/KernelClient.js` | Update `startKernel()` signature |
| `frontend/js/app.js` | Update `_activeVenv` shape, localStorage, all kernel calls |
| `frontend/js/panels/ExplorerPanel.js` | Three-level tree, runtime selector, new API calls |
| `frontend/js/InfoBar.js` | Use `displayName` instead of `pythonVersion` |
| `Dockerfile` | Ubuntu + CUDA + deadsnakes + multi-Python |
| `scripts/create_runtime_configs.sh` | **New** — auto-generate runtime.json files |
| `data/runtimes/python/*/runtime.json` | **New** — generated by build script |

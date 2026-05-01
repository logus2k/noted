# noted -- Project Status Report

> Last updated: 2026-03-18

## Overview

**noted** is a collaborative Jupyter-compatible notebook platform with real-time multi-user editing, multi-runtime kernel execution, and environment management. It runs as a single Docker container serving a vanilla ES6 frontend over a FastAPI + Socket.IO backend.

---

## Currently Supported Capabilities

### Notebook Editing

- Full `.ipynb` (nbformat 4) read/write compatibility with Jupyter
- Code cells with streaming execution output via Jupyter kernel protocol
- Markdown cells with live preview, LaTeX math rendering (KaTeX), and syntax highlighting
- Cell operations: add, delete, move (drag-and-drop and keyboard), copy/cut/paste
- Multi-cell selection with Shift+Arrow and bulk operations
- Undo/redo stack for cell-level changes
- CodeMirror 6 editor with 7 themes (Default, Ayu Light, Clouds, Espresso, Smoothy, Tomorrow, One Dark)
- Notebook import/export (standard `.ipynb` format)

### Real-Time Collaboration

- Multiple users can edit the same notebook simultaneously
- Cell-level locking with TTL (60s, renewed via heartbeat)
- Live synchronization of cell edits, additions, deletions, and moves via Socket.IO
- User presence indicators (connected users shown in toolbar)
- Reconnection handling with 15-second grace period (kernel session transfer on reconnect)

### Multi-Runtime Kernel Execution

- Python 3.10, 3.11, 3.12, 3.13, 3.14
- Free-threaded (nogil) variants for Python 3.13t and 3.14t
- Runtime auto-detection at build time via `create_runtime_configs.sh`
- One kernel per client session with idle timeout (600s)
- Kernel lifecycle: start, stop, restart, interrupt
- GPU acceleration: CUDA runtime included, `LD_LIBRARY_PATH` injection for PyTorch/TensorFlow

### Environment Management

- Create isolated virtual environments per runtime version
- Install/uninstall packages from the UI with real-time terminal feedback (PTY streaming)
- Cancel in-progress installations
- Package list inspection per environment
- Persistent terminals per environment (xterm.js with 10+ color themes)
- Environments persist across container restarts via volume mount

### Project Organization

- Hierarchical project/notebook structure
- Create, rename, delete projects and notebooks
- Welcome project with example notebook created on first launch
- File explorer with Wunderbaum tree view (split pane: tree + detail)

### External Projects

- Link existing notebook directories from the host machine via `data/projects.txt`
- INI-style config: `[Project Name]` sections with container-internal paths
- Recursive scanning with `/*` suffix
- Symlink-based: works on all host OSes (Linux, macOS, Windows)
- Notebook creation in external projects: user chooses internal (noted storage) or external (host directory)
- Stale symlink cleanup on each container startup

### Display & Theming

- Configurable cell width (350px to full width)
- Toggle visibility: cell titles, borders, backgrounds, line numbers, output, table stripes
- Terminal color themes: Adventure (default), Dracula, Nord, One Dark, Tokyo Night, Gruvbox Dark, Monokai, Solarized Dark, Default Dark
- Settings persist to localStorage

### Deployment

- Single Docker image for both GPU and CPU hosts (GPU auto-detected at runtime)
- Two Docker Compose files: `docker-compose.yml` (GPU, default), `docker-compose.cpu.yml` (CPU-only)
- Data persistence via volume mount (`/app/data`)
- Base image: `nvidia/cuda:13.1.1-runtime-ubuntu24.04`

---

## Integration Endpoints

### REST API

#### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List all projects (includes `external` flag and `external_paths` for linked projects) |
| POST | `/api/projects` | Create a new project |
| DELETE | `/api/projects/{project_id}` | Delete a project and all its notebooks |
| PUT | `/api/projects/{project_id}/rename` | Rename a project |

#### Notebooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/{project_id}/notebooks` | List notebooks in a project |
| GET | `/api/projects/{project_id}/notebooks/{name}` | Get full notebook content |
| GET | `/api/projects/{project_id}/notebooks/{name}/summary` | Get notebook metadata (cell counts, description, kernel info) |
| POST | `/api/projects/{project_id}/notebooks` | Create notebook (supports `external_path` for linked projects) |
| PUT | `/api/projects/{project_id}/notebooks/{name}` | Update notebook content |
| PUT | `/api/projects/{project_id}/notebooks/{name}/rename` | Rename a notebook |
| DELETE | `/api/projects/{project_id}/notebooks/{name}` | Delete a notebook |
| GET | `/api/projects/{project_id}/files/{path}` | Serve embedded files (images, etc.) from a project |

#### Runtimes & Environments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/runtimes` | List all available runtimes |
| GET | `/api/envs` | List all environments across all runtimes |
| POST | `/api/envs` | Create environment (streaming PTY response) |
| DELETE | `/api/envs/{runtime_id}/{name}` | Delete an environment |
| GET | `/api/envs/{runtime_id}/{name}/packages` | List installed packages |
| POST | `/api/envs/{runtime_id}/{name}/packages` | Install packages (streaming PTY response) |
| POST | `/api/envs/{runtime_id}/{name}/packages/cancel` | Cancel active installation |
| DELETE | `/api/envs/{runtime_id}/{name}/packages` | Remove packages |

#### MLflow

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mlflow/experiments` | List active experiments |
| GET | `/api/mlflow/experiments/{id}/runs` | List runs for experiment |
| GET | `/api/mlflow/runs/{id}` | Get full run details |
| GET | `/api/mlflow/runs/{id}/artifacts` | List classified artifacts (models/images/charts/files) |
| GET | `/api/mlflow/runs/{id}/artifacts?path=x` | List artifacts in subdirectory |
| GET | `/api/mlflow/runs/{id}/artifacts/download?path=x` | Download artifact file |
| GET | `/api/mlflow/runs/{id}/metrics/{key}` | Get metric history (all steps) |
| POST | `/api/mlflow/runs/{id}/stop` | Stop a running run |
| DELETE | `/api/mlflow/runs/{id}` | Delete (archive) a run |
| DELETE | `/api/mlflow/experiments/{id}` | Delete (archive) an experiment |

### Socket.IO Events

#### Client to Server

| Event | Data | Description |
|-------|------|-------------|
| `notebook:open` | `project_id`, `notebook_path`, `user_name` | Join a notebook editing session |
| `notebook:close` | `project_id`, `notebook_path` | Leave a notebook session |
| `notebook:save` | `content` | Save notebook to disk |
| `cell:lock` | `cell_index` | Acquire editing lock on a cell |
| `cell:unlock` | `cell_index` | Release cell lock |
| `cell:update` | `cell_index`, `source` | Broadcast source change to other users |
| `cell:add` | `cell_index`, `cell_type`, `cell_id` | Add a new cell |
| `cell:delete` | `cell_index` | Delete a cell |
| `cell:move` | `from_index`, `to_index` | Move a cell |
| `cell:execute` | `cell_index`, `code` | Execute cell code on the kernel |
| `kernel:start` | `runtime_id`, `env_name` | Start a kernel with a specific environment |
| `kernel:stop` | -- | Stop the active kernel |
| `kernel:restart` | -- | Restart the kernel |
| `kernel:interrupt` | -- | Interrupt running execution |
| `run:execute` | `cells`, `run_name`, `datasets`, `notebook_key` | Execute Run Manager run |
| `heartbeat` | -- | Keep-alive (renews locks, prevents idle timeout) |

#### Server to Client

| Event | Data | Description |
|-------|------|-------------|
| `notebook:state` | `notebook`, `locks`, `connected_users` | Full state on notebook open |
| `notebook:saved` | `success`, `error` | Save confirmation |
| `cell:updated` | `cell_index`, `source`, `by_sid` | Another user edited a cell |
| `cell:added` | `cell_index`, `cell_type`, `cell_id`, `by_sid` | Another user added a cell |
| `cell:deleted` | `cell_index`, `by_sid` | Another user deleted a cell |
| `cell:moved` | `from_index`, `to_index`, `by_sid` | Another user moved a cell |
| `cell:output` | `cell_index`, `output` | Streaming execution output |
| `cell:execute_complete` | `cell_index`, `execution_count` | Execution finished |
| `cell:lock_changed` | `cell_index`, `owner`, `locked` | Lock state broadcast |
| `kernel:status` | `status` | Kernel state change (`idle`, `busy`, `starting`, `dead`) |
| `user:joined` | `sid`, `name` | User joined the notebook |
| `user:left` | `sid`, `name` | User left the notebook |
| `metrics:update` | `cell_index`, `notebook_key`, `metric` | Live metric data point from mlflow.log_metric() |
| `run:started` | `run_name`, `notebook_key` | Run Manager execution started |
| `run:complete` | `run_name`, `notebook_key`, `errored` | Run Manager execution completed |
| `error` | `message`, `code` | Error notification |

---

## Architecture Summary

| Layer | Technology |
|-------|-----------|
| Server | FastAPI, python-socketio, Uvicorn |
| Kernel | jupyter_client, ipykernel, pyzmq |
| Frontend | Vanilla ES6 modules, CodeMirror 6 |
| Real-time | Socket.IO |
| UI Panels | jsPanel, Wunderbaum, Split.js, Apache ECharts |
| Terminal | xterm.js (DOM renderer) |
| Icons | Font Awesome |
| Markdown | Marked, Highlight.js, KaTeX |
| Container | Docker, NVIDIA CUDA 13.1 runtime |

### Backend Managers

| Manager | Responsibility |
|---------|---------------|
| `NotebookManager` | CRUD for projects and `.ipynb` files |
| `KernelManagerService` | Jupyter kernel lifecycle, idle cleanup |
| `ExecutionBridge` | Socket.IO <-> Jupyter ZMQ message bridge, live metrics intercept |
| `AutoInstrumentation` | MLflow silent code injection, metrics hook monkey-patch |
| `CollaborationManager` | Rooms, cell locks, presence, broadcast |
| `EnvironmentManager` | Runtime-aware venv creation, package ops |
| `MlflowManager` | MLflow SDK wrapper (experiments, runs, metric history, artifacts) |
| `ExternalProjectsConfig` | Singleton; parses `projects.txt` at startup |

---

## Extensibility Opportunities

### Short-Term

- **Visual indicator for linked projects** -- Add a link icon or badge in the explorer tree to distinguish external projects from native ones
- **Delete/rename guards for linked notebooks** -- Warn or prevent deletion of symlinked notebooks (which would affect host files)
- **Filename collision handling** -- Detect and resolve conflicts when multiple source paths in the same project contain notebooks with the same name
- **Hot-reload of `projects.txt`** -- Re-parse the config file without restarting the container (e.g., via an API endpoint or file watcher)
- **Wire up pending callbacks** -- `onProjectDeleted`, `onNotebookDeleted`, `onProjectRenamed`, `onNotebookRenamed` in `app.js` need full integration
- **Cancel active installs before environment deletion** -- Prevent orphan processes when deleting an environment with a running installation

### Medium-Term

- **Authentication & authorization** -- User accounts, per-project permissions, session tokens (currently open access)
- **Notebook versioning** -- Git-backed or snapshot-based version history for notebooks
- **File upload/download** -- Upload datasets, images, and supporting files into project directories from the UI
- **Search across notebooks** -- Full-text search across all notebooks in a project or globally
- **Cell output persistence** -- Currently outputs are lost on page reload unless the notebook is saved; could auto-persist execution state
- **R / Julia runtime support** -- The runtime registry is language-agnostic (`runtime.json` descriptors); adding new languages requires a kernel implementation and runtime config
- **Markdown-only mode** -- A lightweight editing mode for documentation notebooks without kernel overhead
- **Notebook viewer sharing** -- The `/viewer` endpoint exists; could be extended with public sharing links

### Long-Term

- **Multi-tenant deployment (k3s)** -- Nginx ingress, per-user containers or namespaces, persistent volume claims
- **OCI image per environment** -- Snapshot environments as container images for reproducibility
- **Plugin system** -- Allow custom cell types, output renderers, or toolbar actions via a plugin API
- **JupyterHub compatibility** -- Implement the Jupyter Server API surface to allow JupyterHub to proxy to noted instances
- **Collaborative cursors** -- Show other users' cursor positions within a cell (requires OT/CRDT for sub-cell edits)
- **DAG execution** -- Define cell dependencies and execute notebooks as directed acyclic graphs rather than linearly
- **REST API for headless execution** -- Run notebooks programmatically via API (CI/CD pipelines, scheduled jobs)
- **WebSocket-based file sync** -- Replace restart-dependent symlink refresh with live file watching for external projects

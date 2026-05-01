# noted - Project Status

## Document Information

| Field | Value |
|-------|-------|
| Last Updated | 2026-03-13 |
| Current Phase | Phase 1B (in progress) |
| Phase 0 | COMPLETED 2026-03-10 |
| Phase 1A | COMPLETED 2026-03-11 |
| Phase 1A+ | COMPLETED 2026-03-13 |

---

## What Is Working (as of 2026-03-13)

### Infrastructure

- Docker stack: `noted`, `noted-mlflow`, `noted-airflow-apiserver`, `noted-minio`, `noted-postgres`, `noted-redis`, `noted-nginx`
- Compose files: `services/docker-compose.yml` (base), `docker-compose.gpu.yml` (GPU override), `docker-compose.local.yml` (nginx standalone)
- Service URLs: `/mlflow`, `/airflow`, `/minio` (nginx routing, same for local and production)
- GPU passthrough via `deploy.resources.reservations.devices` in compose
- `uv` installed in Docker image for fast package installs

### UI Layout (VS Code-like 4-column)

- **Icon Bar** (`frontend/js/IconBar.js`, `frontend/css/icon-bar.css`): dark `#181818` vertical bar, logo at top (`noted_logo_small.png`), icons for Projects, TOC, Git, AI Assistant, LLM Prompts (top group), Airflow/MLflow/MinIO service images + Settings (bottom group)
- **Sidebar** (`frontend/js/SidebarPanel.js`, `frontend/css/sidebar.css`): collapsible panel, 280px default (160–500px range), named views registered via `registerView()`, toggled from icon bar. Active tab shown in tab strip; clicking tab switches (not closes); closing via icon bar only.
- **Center pane** (`frontend/js/TabBar.js`): tabbed, supports notebooks, file editor, media viewer, service iframes (MLflow/Airflow/MinIO), document viewer, git commit viewer. Tabs show filename only with full-path hover tooltips. Preview (transient) tabs on single-click, pinned on double-click or edit. Service iframes are persistent DOM wrappers (not removed on close).
- **Right panel** (`frontend/js/RightPanel.js`): Chat assistant with status LED + label in title bar.
- **Info bar** (`frontend/js/InfoBar.js`): decorative only.
- **Notebook bars**: two sticky bars inside `.notebook` wrapper:
  - Top bar (`#notebook-top-bar`): bg `#ffe39eed`, breadcrumb left
  - Second bar (`#notebook-second-bar`): bg `#fff2bcd9`, Save + PostIt left, kernel controls center, kernel selector right. Labels hide at `@container (max-width: 580px)`.

### Workspace Tree (Wunderbaum)

Sections:
- **Projects**: full directory tree with lazy loading, notebooks, all file types. Create/import notebooks, create/delete/rename projects. Context menus for file/folder CRUD (new file, new folder, rename, delete).
- **Mounts**: host directory mounts configured via `NOTED.md`. Same file tree browsing, context menus, and editing as projects.
- **Environments**: project-scoped and shared venvs, package install/uninstall with terminal (xterm.js PTY streaming). uv or pip selector.
- **Knowledge Base** (formerly Documents): markdown (marked.js) and PDF (pdf.js ESM, lazy render) viewer. Two-level category/document organization via `documents.json`. Context menus for open/rename/delete documents.
- **Storage**: MinIO bucket browser (placeholder).
- **Pipelines**: DVC pipeline stages + Airflow DAGs (placeholder).
- **Models**: MLflow model registry (placeholder).
- **APIs**: serving endpoints (placeholder).

Git status decorations:
- `DecorationService` (`frontend/js/services/DecorationService.js`) provides VS Code-style colored dots on tree nodes with git changes
- Colors: amber (modified/changed), green (added/untracked), red (deleted), purple (renamed)
- Ancestor bubbling: directory and project/mount root nodes show the highest-priority child status
- Per-repo key tracking for efficient cleanup on refresh
- Extensible `source` field designed for future DVC decoration integration

Wunderbaum quirks:
- `folder` property stripped on lazyLoad — must set `node.folder = true` programmatically.
- `return false` in click handler prevents default expand — must explicitly list expandable node types.
- `wb-row` is `position: absolute` (virtual scrolling) — child elements must not add `position: relative`.

### Notebooks

- CodeMirror 6 editor per cell (Python, oneDark theme)
- Markdown cells (edit/preview toggle)
- Cell execution (Shift+Enter / Ctrl+Enter / Run button), Run All, Interrupt
- Streamed output rendering: stdout, stderr, execute_result, display_data, errors, images
- Cell sidebar: drag handle, execution count (absolute `left: -36px`), type indicator
- Drag-and-drop cell reordering (midpoint detection, wrapper offset by 2 for top/second bars)
- Cell add (code/markdown), delete
- TOC (table of contents) panel with 30px scroll offset for sticky bar
- Post-it notes panel
- Save (Ctrl+S), export (.ipynb download), import (.ipynb upload)
- URL-based auto-open (project + notebook params)
- Execution counts: always visible, Jupyter-standard numbering

### File Editing

- Generic file editor (`FileEditor.js`) opens any text file (`.py`, `.md`, `.yaml`, `.gitignore`, etc.) via `api/files/{root_type}/{root_name}/read|write`
- CodeMirror 6 editor in center pane with theme support, edit + save (Ctrl+S)
- Tab shows filename only; hover tooltip shows full physical path
- Dirty indicator (`filename *`) in tab label; preview tabs auto-pin on edit
- Markdown files support in-place preview toggle (Play button)
- `PYTHONPATH` injected into kernel — notebooks can `import` from project `src/`

### MLflow Integration (Phase 1A — T-1A.6)

- `MLFLOW_TRACKING_URI=http://mlflow:5000` and `MLFLOW_EXPERIMENT_NAME={project_id}` injected into every kernel
- `mlflow` auto-installed in new venvs via `runtime.json` post-create commands (via `uv`)
- Notebooks can `import mlflow` and auto-connect without configuration
- Experiment name = project name; runs visible in MLflow UI at `/mlflow`
- MLflow tab as persistent iframe in center pane
- `mlflow.autolog()` captures sklearn/pytorch/keras params+metrics automatically
- Service health check with Notyf toast on connect/disconnect

### Kernel & Environment Management

- jupyter_client kernel lifecycle (start, stop, restart, interrupt)
- ZMQ → Socket.IO execution bridge with streamed output
- Kernel env: `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`, `PYTHONPATH`, `LD_LIBRARY_PATH` (WSL/CUDA)
- PTY-based terminal install: 24×120, `TERM=xterm-256color`, clean env (strips `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`)
- Cancel active install: `_install_procs` dict, SIGTERM + 5s timeout + SIGKILL
- Terminal theme: `TerminalThemes.js` with listener pattern, default "Adventure"
- Panel title: `"Terminal - {envName} installation"`

### Git Panel (Source Control sidebar view)

- Sections: Author · Repositories · Changes · History
- Branch selector + new branch form, Font Awesome `fa-code-branch` icon
- Commit textarea + full-width "Commit" button with checkmark SVG
- Changed files list with file type icons and status badges (M/A/D/R/?)
- Project rows show SVG change badge (8px amber circle) when repo has uncommitted changes
- Commit history list with short hash, message, relative date
- Expandable commit items with diff viewer (CodeMirror read-only)
- Git commit viewer in center pane tab for detailed commit diffs
- Remote section: push/pull with ahead/behind indicators, remote URL config
- GitHub credentials management (PAT-based, stored per-repo)
- Refresh button in CHANGES section header (right-aligned, `e.stopPropagation()`)
- Section headers: styled with `#ffa11124` background, `#e1ca8ee3` border, orange hover
- `_onStatusRefreshed` callback feeds git status to `DecorationService` for explorer tree decorations

### Notifications

- Notyf library (`frontend/vendor/notyf.min.js/css`), singleton `frontend/js/Notify.js`, bottom-right
- Kernel toasts: `venvName (displayName) started/failed`
- Assistant toasts: connect/disconnect
- Service toasts: MLflow/Airflow/MinIO health checks

### Chat Assistant

- ChatPanel + ChatService + AgentClient
- Connects to external LLM at `logus2k.com/llm`, agent `"docbro"`
- Status LED in RightPanel title bar
- Visible by default, auto-sends "Hello!" on connect

### MLOps Vision Documents (in `documents/`)

Full use-case specs for Phase 1B–4 integrations:
- `noted_mlflow.md`: 9 use cases (run logging, live metrics, artifact management, model registry, serving, hygiene)
- `noted_dvc.md`: 7 use cases (dataset versioning, MinIO remote, lineage, DVC pipelines)
- `noted_hydra.md`: 6 use cases (config management, sweeps, MLflow auto-log)
- `noted_airflow.md`: 8 use cases (DAG authoring, trigger, monitoring, inline logs, scheduling)

---

## What Is Next (Phase 1B)

### DVC Integration (Phase 1B — first priority)

1. DVC init + remote config: auto-init in new projects, auto-configure MinIO remote
2. Workspace tree badges: DVC-tracked file indicators
3. Source Control panel extension: DVC push/pull buttons alongside Git
4. Context menu: "Track with DVC" on files
5. Pipeline tree: list DVC stages from `dvc.yaml`
6. Reproduce from MLflow run: "Restore environment" action

### MLflow Experiments Panel (Phase 1B)

1. Experiments section in workspace tree: run list per project
2. Run detail panel: metrics, params, artifacts inline
3. Live metric streaming during active runs (poll every few seconds)
4. Run compare panel: side-by-side metrics + param diff

---

## Recent Changes (Phase 1A+ — 2026-03-13)

- **Git status decorations**: VS Code-style colored dots in explorer tree for files/folders with git changes, with ancestor bubbling to parent directories and project roots
- **DecorationService**: decoupled service (`frontend/js/services/DecorationService.js`) with extensible `source` field for future DVC integration
- **File editor modernized**: reads/writes via generic `api/files/` endpoints (not legacy `api/projects/.../src/`); opens any text file including dotfiles (`.gitignore`, etc.)
- **Tab improvements**: filename-only labels (no path prefixes), full physical path in hover tooltip, notebook tab name fix
- **Icon bar reorganized**: service icons (Airflow, MLflow, MinIO) moved to bottom group above Settings; settings icon outline matches folder icon
- **Git panel polish**: SVG change badges on project rows, Font Awesome branch icons, connection status styling
- **Knowledge Base context menus**: Open, Rename, Delete on document nodes; Upload on category nodes
- **Highlight.js languages**: added PowerShell and Dockerfile modules (v11.9.0) for proper syntax highlighting
- **Git commit viewer fix**: corrected property name mismatch (`projectId` → `repoPath`) causing 422 errors on re-show
- **Markdown Play button**: 14×14px SVG with `#333333` stroke

---

## Known Pending Issues

- Cancel active install before deleting an environment
- External projects feature designed but not implemented (see `documents/external-projects.md`)
- Multi-notebook support deferred (one notebook tab at a time)
- ExplorerPanel.js is 3200+ lines — candidate for modular refactoring (13+ extractable modules identified)

---

## Key File Map

### Backend

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI + Socket.IO app, event handlers |
| `backend/app/managers/kernel_manager.py` | Kernel lifecycle + env injection |
| `backend/app/managers/env_manager.py` | Venv lifecycle, PTY install stream |
| `backend/app/managers/notebook_manager.py` | Notebook file CRUD |
| `backend/app/managers/document_manager.py` | Document file CRUD |
| `backend/app/managers/source_file_manager.py` | Legacy Python src/ file CRUD (being replaced by file_manager) |
| `backend/app/managers/file_manager.py` | Generic file CRUD for projects and mounts |
| `backend/app/routers/venvs.py` | REST: venv endpoints |
| `backend/app/routers/documents.py` | REST: document endpoints (list, upload, rename, delete) |
| `backend/app/routers/files.py` | REST: generic file browsing, read, write, create, delete, rename |
| `backend/app/routers/git.py` | REST: git status/commit/branch/log/push/pull/show |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/js/app.js` | Bootstrap, wiring, tab management, breadcrumbs |
| `frontend/js/IconBar.js` | Icon bar with view toggles |
| `frontend/js/SidebarPanel.js` | Sidebar with registered views, tab strip |
| `frontend/js/RightPanel.js` | Chat/right panel with status LED |
| `frontend/js/panels/ExplorerPanel.js` | Workspace tree (Wunderbaum), detail panes |
| `frontend/js/NotebookEditor.js` | Cell array, remote sync, top/second bars |
| `frontend/js/CellEditor.js` | CodeMirror per cell, lock/focus/run |
| `frontend/js/CellOutput.js` | Output renderer |
| `frontend/js/NotebookToolbar.js` | Toolbar (spacer + connected users) |
| `frontend/js/panels/DocumentViewer.js` | Markdown + PDF document renderer |
| `frontend/js/FileEditor.js` | CodeMirror file editor (all text file types) |
| `frontend/js/MediaViewer.js` | Image/audio/video/PDF/markdown viewer |
| `frontend/js/GitPanel.js` | Source Control sidebar view |
| `frontend/js/GitCommitViewer.js` | Center pane commit diff viewer |
| `frontend/js/services/DecorationService.js` | Git status decorations for explorer tree |
| `frontend/js/ChatPanel.js` | Chat UI |
| `frontend/js/ChatService.js` | LLM connection + status callbacks |
| `frontend/js/TabBar.js` | Center pane tab bar |
| `frontend/js/Notify.js` | Notyf singleton wrapper |
| `frontend/js/TerminalThemes.js` | xterm.js theme registry |

### CSS

| File | Purpose |
|------|---------|
| `frontend/css/base.css` | CSS variables, reset, scrollbars, fonts |
| `frontend/css/icon-bar.css` | Icon bar |
| `frontend/css/sidebar.css` | Sidebar panel + tab strip |
| `frontend/css/tab-bar.css` | Center pane tab bar |
| `frontend/css/right-panel.css` | Right/chat panel |
| `frontend/css/explorer-panel.css` | Workspace tree + detail pane |
| `frontend/css/document-viewer.css` | Markdown + PDF viewer |
| `frontend/css/file-editor.css` | File editor |
| `frontend/css/git-panel.css` | Git/Source Control panel |
| `frontend/css/cell.css` | Cell styling, CodeMirror overrides |
| `frontend/css/output.css` | Output rendering |
| `frontend/css/venv-panel.css` | Environment panel |

---

## Architecture Notes

- **No frontend framework**: vanilla JS classes, no React/Vue/Angular
- **jsPanel**: floating/draggable panels (not currently in active use for main layout)
- **Wunderbaum**: workspace tree (lazy-load, virtual scroll)
- **CodeMirror 6**: all code/text editing (cells, Python files, git diff, YAML)
- **xterm.js**: UMD build, DOM renderer (not WebGL), `MesloLGS NF` font, 24×120 cols
- **Socket.IO**: kernel execution bridge, collaboration
- **highlight.js 11.9.0**: syntax highlighting (Python, PowerShell, Dockerfile + bundled languages)
- **marked v15.0.12**: GFM markdown rendering (tables, code blocks)
- **pdf.js ESM**: lazy page rendering with IntersectionObserver
- **Notyf**: toast notifications
- **Split.js**: explorer left/right pane split

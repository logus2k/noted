# noted - Project Status

## Document Information

| Field | Value |
|-------|-------|
| Last Updated | 2026-04-06 |
| Current Phase | Phase 4 (complete), Demo Pipeline (complete) |
| Phase 0 | COMPLETED 2026-03-10 |
| Phase 1A | COMPLETED 2026-03-11 |
| Phase 1B | COMPLETED 2026-03-20 |
| Phase 2 | COMPLETED 2026-03-20 |
| Phase 3 | COMPLETED 2026-03-21 |
| Phase 4 | COMPLETED 2026-03-23 |
| Phase 1A+ | COMPLETED 2026-03-13 |
| Demo Pipeline | COMPLETED 2026-03-27 |
| Next Deadline | Final Delivery 2026-04-12 |

---

## Current Focus: Tutorial 2 Movie Recording (as of 2026-03-27)

All noted platform phases (0-4) are complete with 129 automated tests, 100% pass rate. The **Jena Weather Forecasting pipeline** is complete and tested - all demo tasks done. Next step is recording the Tutorial 2 video.

### Demo Pipeline Status

| Task | Description | Status |
|---|---|---|
| T-DEMO.1 | Hydra config groups (model/gru.yaml, model/linear.yaml, data/default.yaml) | Done |
| T-DEMO.2 | Modular scripts (ingestion, preprocessing, training, evaluation) | Done |
| T-DEMO.3 | 4-stage Airflow DAG (ingest -> preprocess -> train -> evaluate) | Done |
| T-DEMO.4 | Demo notebook (`emi_tutorial2_demo.ipynb`) | Done |
| T-DEMO.5 | Pre-trained model registered in MLflow (JenaWeatherGRU v1) | Done |
| T-DEMO.6 | Requirements file update | Done |

### Infrastructure Updates (2026-03-27)

- Airflow worker Dockerfile: added mlflow, omegaconf, hydra-core, joblib, tensorflow[and-cuda], matplotlib
- GPU override (`docker-compose.gpu.yml`): added airflow-worker to GPU passthrough
- Evidently container added to `services/docker-compose.yml` (port 8009)
- Serving container: auto-installs model dependencies from MLflow artifact requirements on `/load`
- Serving container: 3D tensor prediction support (unwraps pyfunc via `get_raw_model()`)

### Remaining

- Record Tutorial 2 video (see `documents/tutorial2_movie_script.md`)
- Post-production + submission (2026-03-29)

See `documents/tutorial2_movie_script.md` for scene-by-scene recording script.

---

## What Is Working (as of 2026-03-23)

### Infrastructure

- Docker stack: `noted`, `noted-mlflow`, `noted-airflow-apiserver`, `noted-airflow-scheduler`, `noted-airflow-worker`, `noted-airflow-triggerer`, `noted-airflow-dag-processor`, `noted-minio`, `noted-postgres`, `noted-redis`, `noted-serving`, `noted-graph`, `noted-evidently`, `noted-nginx`
- Compose files: `services/docker-compose.yml` (base), `docker-compose.gpu.yml` (GPU override: noted, airflow-worker, serving), `docker-compose.local.yml` (nginx standalone), `../data/docker-compose.mounts.yml` (auto-generated mount volumes for noted + Airflow)
- Airflow worker: mlflow, omegaconf, hydra-core, joblib, tensorflow[and-cuda], matplotlib installed
- Service URLs: `/mlflow`, `/airflow`, `/minio` (nginx routing, same for local and production)
- GPU passthrough via `deploy.resources.reservations.devices` in compose
- `uv` installed in Docker image for fast package installs

### UI Layout (VS Code-like 4-column)

- **Icon Bar** (`frontend/js/IconBar.js`, `frontend/css/icon-bar.css`): dark `#181818` vertical bar, logo at top (`noted_logo_small.png`), icons for Projects, TOC, Git, AI Assistant, LLM Prompts (top group), Airflow/MLflow/MinIO service images + Settings (bottom group). Airflow icon 23px, MLflow 21px, MinIO 20px.
- **Sidebar** (`frontend/js/SidebarPanel.js`, `frontend/css/sidebar.css`): collapsible panel, 280px default (160-500px range), named views registered via `registerView()`, toggled from icon bar. Active tab shown in tab strip; clicking tab switches (not closes); closing via icon bar only. Settings panel opens as a sidebar view.
- **Center pane** (`frontend/js/TabBar.js`): tabbed, supports multiple simultaneous notebooks, file editor, media viewer, service iframes (MLflow/Airflow/MinIO), document viewer, git commit viewer. Tabs show filename only with full-path hover tooltips. VS Code-style preview/pin behavior: single-click opens a preview (transient) tab, double-click or editing pins it. Service iframes are persistent DOM wrappers (not removed on close).
- **Right panel** (`frontend/js/RightPanel.js`): Chat assistant with status LED + label in title bar.
- **Info bar** (`frontend/js/InfoBar.js`): decorative only. Status bar shows OS brand icons (fa-brands: fa-windows, fa-docker, fa-apple, fa-ubuntu, fa-debian, fa-fedora, fa-redhat, fa-linux) for host and container.
- **Notebook bars**: two sticky bars inside `.notebook` wrapper:
  - Top bar (`#notebook-top-bar`): bg `#ffe39e`, breadcrumb left
  - Second bar (`#notebook-second-bar`): bg `#fff9e3`, Save + PostIt left, kernel controls center, kernel selector right. Labels hide at `@container (max-width: 580px)`.

### Workspace Tree (Wunderbaum)

Sections:
- **Projects**: `fa-clipboard-list` icon (pastel green). Full directory tree with lazy loading, notebooks anywhere in project root (not restricted to `/notebooks` subfolder). Create/import notebooks, create/delete/rename projects. Context menus for file/folder CRUD.
- **Mounts**: `fa-hard-drive` icon (same for category and instances). Host directory mounts configured via `NOTED.md`. Same capabilities as projects — file/folder creation, notebook import, auto-tracking.
- **Environments**: `fa-layer-group` icon (category), with Python and JavaScript language sub-nodes using VS Code color SVG icons. `fa-cube` (individual envs). Project-scoped and shared venvs, package install/uninstall with terminal (xterm.js PTY streaming). uv or pip selector.
- **Knowledge Base**: markdown (marked.js) and PDF (pdf.js ESM, lazy render) viewer. Two-level category/document organization via `documents.json`.
- **Experiments**: `fa-flask-vial` icon (purple). MLflow experiment browser. Lazy-loaded experiments → runs. Run status icons (green check/spinner/red X). Detail panels show experiment run list, run metrics/params/tags, inline ECharts metric history charts (auto-loaded, 2-column grid). "View Charts" popout button opens MetricsPanel with full history. Breadcrumb trail in top bar for run detail (Experiments / experiment / run / run_id). Action icons (chart popout, delete) in second bar. Backend: `mlflow_manager.py` (SDK wrapper) + `mlflow.py` router (includes metric history endpoint).
- **Storage**: `fa-database` icon. MinIO bucket browser. Lazy-loaded bucket/folder/object tree via `minio_manager.py` + `minio.py` router. Card-based detail panels show object metadata.

Git/DVC status decorations:
- `DecorationService` (`frontend/js/services/DecorationService.js`) provides VS Code-style decorations on tree nodes
- **Colored dots**: amber (modified/changed), green (added/untracked), red (deleted), purple (renamed), teal (DVC tracked)
- **Status letter badges**: M (modified), A (added), U (untracked), D (deleted), R (renamed) for git; T (tracked), M (changed), N (new) for DVC
- **Source badges**: "GIT" (warm beige) and "DVC" (light teal) labels distinguish which system manages each file
- **Colored filenames**: file names colored to match their status (VS Code style)
- Ancestor bubbling: directory and project/mount root nodes show the highest-priority child status (dot only, no letter/color)

### Notebooks

- CodeMirror 6 editor per cell (Python, JavaScript, oneDark theme)
- Markdown cells (edit/preview toggle)
- Cell execution (Shift+Enter / Ctrl+Enter / Run button), Run All, Interrupt
- Streamed output rendering: stdout, stderr, execute_result, display_data, errors, images
- Cell sidebar: drag handle, execution count, type indicator
- Drag-and-drop cell reordering
- Cell add (code/markdown), delete
- TOC panel, Post-it notes panel
- Save (Ctrl+S), export (.ipynb download), import (.ipynb upload)
- URL-based auto-open (project + notebook params)
- Notebooks can live anywhere in the project directory tree (not restricted to `/notebooks`)

### MLflow Integration

**Phase 1A (completed):**
- `MLFLOW_TRACKING_URI=http://mlflow:5000` and `MLFLOW_EXPERIMENT_NAME={project_id}` injected into every kernel
- `mlflow` auto-installed in new venvs via `runtime.json` post-create commands
- MLflow tab as persistent iframe in center pane
- Service health check with toast notification

**Phase 1B (completed so far):**
- **Auto-instrumentation engine** (`auto_instrumentation.py`): silent pre/post code injection into kernel. PRE_CODE starts an MLflow run if none active. POST_CODE activates framework-specific autolog (sklearn, pytorch, tensorflow, xgboost, lightgbm) and ends the run. Back-off: skips injection if cell contains `mlflow.start_run`.
- **Execution bridge integration** (`execution_bridge.py`): `_execute_silent()` helper runs pre-code synchronously before user cell. Post-code is fire-and-forget. `auto_tracking` flag passed from frontend per cell execution.
- **Experiments section in workspace tree**: MLflow experiment/run browser. Backend `mlflow_manager.py` wraps `MlflowClient` SDK. Frontend lazy-loads experiments → runs with status icons and detail panels showing metrics, params, tags.
- **Project settings API** (`project_settings.py`, `projects.py` router): `.noted/settings.json` read/write for both projects and mounts. Currently unused by auto-tracking (moved to notebook metadata) but kept for future project-scope settings.

**Phase 1B (implemented):**
- **Run Manager** (`frontend/js/RunManagerPanel.js`, backend `execute_run()` in `execution_bridge.py`): visual tool to define named cell groups as MLflow run templates. Cell badges (colored squares with run number) on right side of each cell. Execute Run button runs all assigned cells sequentially wrapped in a single MLflow run (backend injects `mlflow.start_run`/`mlflow.end_run`). Cell click interception for run assignment. Badge click to remove cells. Runs button (microscope icon) in notebook second bar replaces auto-tracking checkbox.
- **Stop Run / Delete Run**: Context menu and detail pane actions. Stop marks run as KILLED (orange `fa-circle-stop` icon). Delete archives run via MLflow API.
- **Delete Experiment**: Context menu and detail pane action. Archives experiment via MLflow API.
- **Auto-instrumentation for Run Manager** (`auto_instrumentation.py`): `get_run_start_code(run_name)` and `get_run_end_code()` methods for Run Manager injection. Back-off if cell contains `mlflow.start_run`.
- **Live Metrics Streaming** (T-1B.6): `METRICS_HOOK_CODE` in `auto_instrumentation.py` monkey-patches `mlflow.log_metric()` and `mlflow.log_metrics()` to emit `display_data` with custom MIME type `application/x-noted-metric`. Injected on every cell execution (with or without auto-tracking). `execution_bridge.py` intercepts the custom MIME type, emits `metrics:update` Socket.IO event, suppresses from cell output. Frontend `MetricsPanel.js` renders real-time charts via Apache ECharts. Three view modes: Split (default, one chart per metric), Combined (all traces overlaid), Summary (table with Latest/Min/Max/Steps). Auto-opens on first metric, auto-clears on new run. Copy-to-clipboard on each chart (PNG) and table (TSV+HTML). Tooltip on hover with 6 decimal precision.
- **Metric History from Explorer**: `GET /api/mlflow/runs/{run_id}/metrics/{metric_key}` endpoint returns full metric history. Run detail page shows inline ECharts with tooltips. "View Charts" popout button fetches all metric histories and opens a MetricsPanel instance. Each popout creates a new panel (cascaded offset) for side-by-side run comparison. Panel header shows run name + short run ID for identification.
- **Kernel restart fix**: `restart_kernel()` in `kernel_manager.py` now preserves `room_key` in `_room_index` during restart to prevent `NO_KERNEL` errors. Frontend `app.js` tracks `_kernelStarting` state so `ensureKernel` waits for restart completion instead of starting a duplicate kernel.

### Kernel & Environment Management

- jupyter_client kernel lifecycle (start, stop, restart, interrupt)
- ZMQ → Socket.IO execution bridge with streamed output
- Kernel env: `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`, `PYTHONPATH`, `LD_LIBRARY_PATH` (WSL/CUDA)
- PTY-based terminal install: 24×120, `TERM=xterm-256color`, clean env
- Cancel active install: `_install_procs` dict, SIGTERM + 5s timeout + SIGKILL

### DVC Integration (Phase 1B — in progress)

**Backend** (`backend/app/managers/dvc_manager.py`, `backend/app/routers/dvc.py`):
- `DvcManager` class with subprocess pattern matching `GitManager`
- Lazy initialization: auto-inits DVC + MinIO remote on first track operation
- `track()`: runs `git rm --cached` before `dvc add` for Git-tracked files
- `status()`: parses `*.dvc` YAML files for tracked files, 5-second result cache
- `push()` / `pull()`: DVC push/pull with MinIO credentials injected
- `file_history()`: walks `git log` on `.dvc` pointer files
- `dvc install`: adds Git hooks for auto-checkout on branch switch

**Frontend — Source Control panel** (`frontend/js/GitPanel.js`):
- DVC section ("DATA - DVC"): tracked file list, push/pull buttons

**Frontend — Explorer tree**:
- "Track with DVC" context menu on data files
- `.dvc` file version history in detail pane

### Git Panel (Source Control sidebar view)

- Sections: Author · Remote · Branches · Tags · Changes · History
- Branch selector + new branch, tag create/delete
- Commit textarea + button, changed files with status badges
- Expandable commit items with diff viewer
- Remote push/pull with ahead/behind indicators
- GitHub credentials management (PAT-based)

---

## Phase 1B Progress Against Plan

### Completed

| Plan Task | Status | What Was Built |
|-----------|--------|----------------|
| T-1B.1: ProjectVersionControl Service | **PARTIAL** | `DvcManager` + `GitManager` cover init, track, push/pull, status, tags. Not unified. |
| T-1B.2: Data Upload and Tracking | **DONE** | "Track with DVC" context menu. Auth-gated file upload via Explorer, File menu, and context menu. |
| T-1B.3: Data Listing and Version History | **DONE** | DVC status + file history endpoints. Version history in detail pane. |
| T-1B.5: Auto-Instrumentation Engine | **DONE** | Silent pre/post code injection, autolog activation, back-off logic. Run Manager injection methods added. |
| T-1B.8: Storage Section | **DONE** | MinIO bucket browser in workspace tree with detail panels. |
| T-1B.9: Data Section in Workspace Tree | **DONE** | Dedicated "Data" section in Explorer tree. Aggregates DVC-tracked files across all projects/mounts. Collection nodes per project, file nodes with metadata card (size, hash, source, DVC file), version history with checkout. Backend `data_overview()` scans all repos. |
| T-1B.10: Run Manager UI | **DONE** | RunManagerPanel.js, cell badges, execute run, cell click interception, badge click removal. Backend execute_run() in execution_bridge.py. Stop/Delete Run, Delete Experiment. |
| (New) Experiments Section | **DONE** | MLflow experiment/run browser in workspace tree. |
| T-1B.6: Live Metrics Streaming | **DONE** | Monkey-patch intercept of `mlflow.log_metric()`, Socket.IO forwarding, ECharts real-time panel with Split/Combined/Summary views. |
| T-1B.7: Run Manager Dataset Selection | **DONE** | Dataset checkboxes in Experiments UI, DVC hash resolution on execute, auto-logs `dvc_data_hash` param + `dvc.data_hash`/`dvc.data_file` tags to MLflow. Tested and confirmed. |
| T-1B.12: Run Comparison View | **DONE** | Full comparison panel: metrics diff table (delta + percentage), parameters diff table, tags diff table, overlaid ECharts metric history charts. Diff rows highlighted amber. `modalSelect` picker for second run. Comparison opens as cascading jsPanel. Run details now open as proper undockable tabs (preview on single-click, pin on double-click). Second bar with compare/metrics/delete icons. |
| (New) Metric History Explorer | **DONE** | Inline ECharts in run detail, metric history API endpoint, "View Charts" popout, multi-panel comparison via cascading panels. |
| (New) Kernel Restart Fix | **DONE** | Backend preserves room_key during restart, frontend waits for restart completion. |
| (New) ECharts Migration | **DONE** | Replaced Plotly.js (4.3MB) with Apache ECharts (1MB) for all metric charts. |
| (New) MLflow Plotly Install | **DONE** | MLflow container command updated to install plotly for chart rendering in MLflow UI. |
| T-1B.13: Artifact Browser | **DONE** | Full artifact browsing in Explorer tree. Backend: `list_artifacts`, `list_artifacts_classified`, `download_artifact` endpoints. Frontend: run nodes expandable with 4 category folders (Models, Images, HTML Charts, Files). Auto-classification by extension and MLmodel detection. Inline viewers: images, sandboxed HTML iframes, syntax-highlighted text/YAML, model card (MLmodel content + file listing). Download via second bar icon. File sizes in tree nodes. Colored category icons (brain/image/chart/file). |
| T-1B.4: Data Version Switching | **DONE** | `checkout_version()` in `dvc_manager.py`: validates commit hash, `git checkout` on `.dvc` file, `dvc checkout`, auto-pulls from remote if cache miss. REST endpoint `POST /api/dvc/checkout`. Frontend: version rows in `.dvc` detail pane show teal "Current" badge (md5 match) or "Checkout" button with clock icon. Confirmation modal, loading state, auto-refresh on success. Test procedure at `testing/09_test-dvc-version-switching.md`. |
| T-1B.10: Terminal Escape Hatch | **DONE** | `ProjectTerminal.js`: reusable floating terminal (jsPanel + xterm.js + PTY). Opens via Version Control topbar icon or "Open Terminal" button in git/DVC error modals. Terminal reuse per project directory (Map registry), cascading offset for multiple terminals, PTY cleanup on close. `InteractiveTerminal.js`: Ctrl+C copies if selection else SIGINT, Ctrl+V paste, right-click paste. Terminal access key gate: `NOTED_TERMINAL_SECRET` env var, `terminal:auth` Socket.IO handshake, password prompt with sessionStorage caching. Backend `terminal:auth` event in `main.py`. Test procedure at `testing/08_test-terminal-escape-hatch.md`. |

### Additional Work Done (not in original plan)

| Feature | Description |
|---------|-------------|
| Workspace tree icons | Distinct icons per section: clipboard-list (projects), hard-drive (mounts), layer-group (environments), flask-vial (experiments). VS Code color SVG icons for Python/JavaScript language nodes. |
| Mount detail panel | File/folder creation + notebook import in mount details (parity with projects) |
| Notebooks anywhere | Notebooks resolved from project root (not /notebooks subfolder). Projects and mounts unified. |
| Git Tags | Full create/list/delete tag support |
| VS Code-style decorations | Status letters, colored filenames, source badges |
| DVC file icons | Custom DVC logo SVG for `.dvc` files |
| Multi-mode TOC | Notebook/markdown/PDF modes with PDF heading cache |
| Document tab switching | `_documentTabs` Map for correct re-rendering |
| ExplorerPanel refactoring | Refactored from monolithic 4000+ line file into 6 modules: `ExplorerPanel.js` (core), `ExplorerHelpers.js`, `ExplorerProjectViews.js`, `ExplorerEnvViews.js`, `ExplorerExternalViews.js`, `ExplorerContextMenu.js`. Factory + shared `ctx` pattern. |
| Multi-notebook tabs | Multiple notebooks open simultaneously in separate tabs. Each tab maintains its own kernel/editor state. |
| VS Code-style file preview | Single-click opens file/notebook as preview (transient) tab. Double-click or editing pins the tab. Detail panel no longer shown on file click. |
| Kernel picker improvements | Gold star on selected kernel, `#ffe39e` title background, wider panel (280-400px), "Select Environment Kernel" label |
| Wallpaper flash fix | Inline `<script>` in `<head>` restores wallpaper from localStorage before paint, preventing flash of default background |
| NotebookEditor listener cleanup | KernelClient listeners tracked in array and removed on tab close. `_savePending` flag prevents duplicate save toasts. |
| OS brand icons | Status bar shows FA brand icons for host OS (fa-windows, fa-apple, fa-ubuntu, etc.) and fa-docker for container |
| Settings sidebar | Settings panel moved from floating panel to left sidebar view, icon in bottom group after service icons |
| HTML notebook export | Added HTML export to File > Export menu alongside PDF, Markdown, Word |
| Git Pull dropdown | Split button with dropdown: Pull (ff-only), Pull --rebase, Pull --merge. Backend accepts strategy parameter. |
| Modal dialogs | Replaced all browser `alert()` with `modalError` (copyable text + copy button) and all `prompt()` with `modalPrompt` across entire frontend |
| Document mousedown fix | Fixed leaked `document` mousedown handler causing cursor loss on notebook close/reopen and across multi-notebook tabs |
| File save deduplication | Eliminated triple-save on Ctrl+S (removed duplicate keydown handler, unified through MenuBar) |
| Native copy/paste | Removed global Ctrl+C/X/V/Z shortcuts from MenuBar that blocked native clipboard and CodeMirror undo. Cell copy/cut/paste still works via NotebookSelection command mode. |
| Cell output text selection | Added `user-select: text` on `.cell-output` and `.cell-markdown-rendered` to enable text selection and copy |
| Folder click behavior | Folders no longer open detail panel or switch to workspace tab on click - only expand/collapse |
| Explorer folder refresh | Expanding a folder/project/mount reloads contents via `resetLazy()` instead of showing cached children |
| Kernel picker empty state | "Create Virtual Environment" button now shows when no environments exist (was blocked by early return) |
| Hydra in default venvs | `hydra-core` added to `create_runtime_configs.sh` post-create commands for all runtimes |
| CRLF Docker fix | Dockerfile now runs `sed -i 's/\r$//'` on shell scripts before `chmod +x`, fixing Windows CRLF issues |
| Airflow local config | Added `AIRFLOW__WEBSERVER__BASE_URL` to both base and local compose overrides |
| Tutorial #1 delivery | Report v2 (3 pages), notebook with Hydra+DVC+MLflow lineage, project structure, SETUP README, compose files. Submitted 2026-03-17. |
| Tutorial #2 test notebook | `emi_tutorial2.ipynb` - streamlined GRU training notebook with per-epoch `mlflow.log_metric()` calls via custom Keras callback for testing live metrics panel. |
| ECharts migration | Replaced Plotly.js (4.3MB) with Apache ECharts (1MB). All metric charts (live panel, run detail inline, popout panels) use ECharts. |
| Explorer detail scrollbar | Matched scrollbar styling to tree panel (blue thumb, 8px width, 10px top/bottom margin, 5px right margin). |
| Breadcrumb separator | Changed from `\|` to ` / ` across all breadcrumb trails in the application. |
| Output table header styling | `#bfdcff` background for `<th>` in notebook output HTML tables. |
| Run detail page improvements | Inline metric charts (auto-loaded, no layout shift), status icons colored to match tree, breadcrumbs in top bar, action icons in second bar, vertical scrolling. |
| Artifact browser | Full artifact tree with 4 categories (Models, Images, HTML Charts, Files). Model directory detail with MLmodel card. File sizes in tree. Colored icons. Download in second bar. MLmodel downloads as .yaml. |
| Run labels with dates | Run nodes in tree show `yyyy-MM-dd HH:mm - run_name` format. |
| Dynamic tab labels | Workspace tab label updates to match active section (Experiments, Storage, Projects, etc.). |
| Tutorial #2 model artifacts | Notebook saves Keras model with MLmodel metadata YAML via `model.save()` + `mlflow.log_artifacts()`. |
| Version Control topbar redesign | Removed git version label. Left side: terminal icon (`fa-window-maximize`, `#6fa374`) + refresh icon. Right side: LED dot (green connected / grey disconnected) + label (hostname or "No remote"). Consistent `#6fa374` color across all git branch icons. |
| Terminal access key | `NOTED_TERMINAL_SECRET` env var in `services/.env` (gitignored). Server-side `terminal:auth` Socket.IO handshake validates before PTY creation. Frontend password prompt with sessionStorage caching. Designed for online deployments; planned OAuth2 proxy replacement. |
| Terminal clipboard | Ctrl+C copies if text selected (else sends SIGINT), Ctrl+Shift+C always copies (with `preventDefault` to block DevTools), Ctrl+V pastes. Right-click paste. |
| Terminal theme consistency | All terminals (project, env install) use same Adventure theme background from `getTerminalTheme()`. Removed hardcoded `#1e1e20` backgrounds. |
| jsPanel header padding | Removed 2px padding from `.jsPanel .jsPanel-headerbar`. |
| Undock/dock panels | Notebooks, files, and service iframes can be undocked into floating jsPanel windows and re-docked. Undock icon in first bar (notebooks/files) or service top bar (iframes). Dock icon in jsPanel header controls next to close. Close X closes the tab, dock button re-docks. Notebooks preserve full functionality when undocked (save, run, kernel selector, cell hover titles). Wallpaper background on undocked notebooks. Service iframes preserve URL on undock/redock. Kernel picker z-index fixed for floating panels. |
| Explorer topbar context actions | Container nodes (Mounts, Projects, individual mount/project) no longer open detail pages. Actions moved to context-sensitive icons in Explorer sidebar title bar that change based on selected tree node. jsPanel modals for input (Create File, Create Folder, Import Notebook, Add Mount, Create Project). Close button on all sidebar title bars. |
| Sidebar active indicator | Vertical marker in icon bar now correctly tracks the active (visible) panel, not all open panels. |
| Splitter improvements | 4px thickness, `margin-top: var(--toolbar-height)`, hover background matches notebook resizer. Left panel max-width increased 50% (750px). |
| Panel close buttons | All sidebar panels (Explorer, Version Control, TOC, Chat, Prompts) have close button in title bar, 6px right margin consistent across all panels. |
| Version Control topbar icons | Unified hover styling (`#c8e6c0`) across all topbar action buttons (Explorer, Version Control, notebook bars). |
| Undocked file focus | Clicking a file in the Explorer tree that is already undocked brings the floating panel to front instead of re-opening a docked copy. |
| File upload | Auth-gated file upload (reuses terminal secret). Backend `POST /api/files/upload/{root_type}/{root_name}` with 500MB limit, path traversal protection. Upload icon in Explorer title bar for projects/mounts/folders. Upload in File menu (targets active tree node). Upload in context menu for projects, mounts, and folders. Multi-file support, tree auto-refresh after upload. |
| Venv persistence in notebook metadata | Kernel/venv association stored in `.ipynb` metadata (`metadata.noted.venv`) instead of localStorage. Validated against available envs on load; silently shows "No Kernel Selected" if env doesn't exist. |
| Live Metrics recovery | `last_run_id` stored in notebook metadata during training. On reopening Live Metrics with empty traces, fetches metric history from MLflow for that run. |
| Undocked notebook page effect | `.notebook-page` wrapper with `#fdfdfd` background and box-shadow creates a printable page look when cells are not hovered. Shadow hides on hover so individual cell styles take over. |
| Undocked status bar | Project, branch, and cursor info update in status bar when clicking undocked panels. Status bar preserved when all docked tabs close but undocked panels exist. |
| Sidebar/right panel tab close buttons | Close buttons (X on hover) on individual sidebar and right panel tabs, matching center pane tab style. Closes only that view, switches to next open view. |
| Explorer path in title bar | File path shown in Explorer sidebar title bar when a file is selected. |
| Default wallpaper | "Diagonal Lines" pattern applied by default when no wallpaper preference saved. |
| Delete re-activates parent | After deleting a file via context menu, parent folder becomes active node to prevent upload targeting wrong location. |
| Splitter independence | Left splitter compensates center column width when sidebar is closed. Both splitters disable each other during drag via `pointer-events: none`. |
| DVC-aware delete | Deleting a DVC-tracked file runs `dvc remove` + deletes data + stages git changes. Confirmation warns about DVC tracking. |
| DVC-aware rename | Renaming a DVC-tracked file runs `dvc remove` + rename + `dvc add` + stages git changes. Backend endpoints `POST /api/dvc/remove` and `POST /api/dvc/rename`. |
| Run/experiment detail tabs | Experiments and runs open as proper undockable tabs (preview on single-click, pin on double-click). Second bar with action icons (compare, metrics popout, delete). |
| Experiment detail redesign | Removed inline Delete button, moved to Explorer title bar icon. Run list uses FA status icons, hover highlights, date format matching tree labels. |
| Experiments root detail redesign | Clean layout with summary card and clickable experiment rows with vial icons. |
| Run detail grid layout | Metrics, parameters, and tags render in 2-column grids (when 4+ items) instead of single-column lists. Reduces vertical scrolling. |
| MLflow client warm-up | Pre-imports MLflow SDK on app startup, eliminating 2-3s delay on first Experiments tree expand. |
| Service iframe link interception | Links inside MLflow/Airflow/MinIO iframes that would open new tabs now navigate within the iframe. Handles both same-origin and internal container URLs. |
| Explorer tree reorder | Sections reordered: Projects, Mounts, Data, Experiments, Environments, Storage, Knowledge Base. |

---

## What Is Next

### Recommended next steps (target: Tutorial #2 deadline 2026-03-29)

**Phase 1B: COMPLETED** (all tasks done and tested as of 2026-03-20)

**Phase 2 - Must Have (Labs 3-4 coverage):**

| # | Task | Status | What Was Built |
|---|------|--------|----------------|
| 1 | T-2.1 + T-2.2: Hydra Config Endpoints | **DONE** | `hydra_manager.py`: config dir discovery, schema extraction, compose with overrides + group selections, SHA-256 hash. `hydra.py` router: `GET /api/hydra/schema/{id}`, `POST /api/hydra/compose`, `GET /api/hydra/group/{id}/{group}/{option}`. Supports flat configs and Hydra config groups. |
| 2 | T-2.11: Config Section in Explorer | **DONE** | "Configuration" node in project tree (auto-detected). Config groups as expandable folders, options as leaf nodes (star for defaults). Detail panels: config root (summary + parameter grid + compose button), group detail (options list), option detail (YAML preview). Compose panel (jsPanel): group dropdowns, override inputs per parameter, resolved YAML + hash output, copy button. |
| 3 | T-2.4: Config Hash Injection | **DONE** | On Experiments run start, backend composes Hydra config and injects `hydra_config_hash` param + `hydra.config_hash` tag into MLflow run. Silently skipped if no config exists. Same pattern as DVC data hashes. |
| 4 | T-2.5 + T-2.6: Airflow DAG Discovery + Trigger | **DONE** | `airflow_manager.py`: JWT token auth (auto-refresh, fallback to basic), DAG list/detail/tasks, trigger with conf params, run monitoring, task instances, task logs, pause/unpause. `airflow.py` router: 10 endpoints covering full DAG lifecycle. Airflow 3.0 compatible (v2 API, `/details` for params, JSON logs). |
| 5 | T-2.14: Pipeline Section in Explorer | **DONE** | "Pipelines" top-level section. DAGs as expandable nodes (paused/active icons). Runs as children with state icons + datetime. Tasks as leaf nodes sorted by execution order with timestamps and duration. Detail panels: pipelines root (health + DAG list), DAG detail (info + trigger/pause buttons + recent runs), run detail (state + config + task list), task log viewer (dark terminal). Trigger panel (jsPanel): typed param inputs (number/text/checkbox/dropdown from schema), additional JSON config, auto-tree-refresh. |
| 6 | T-2.7: Pipeline Monitor | **DONE** | Background polling after trigger (4s interval, 10min max). `pipeline:status` + `pipeline:task_status` Socket.IO events. Frontend auto-updates run AND task node icons/titles in real-time. Toast notifications on success/failure. Task-level tracking with start time and duration. |

**Phase 2 - Should Have (Tutorial #2 polish):**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 7 | T-2.12: YAML Preview | **DONE** | Included in config option detail and compose panel output. Syntax-highlighted `<pre>` with hash. |
| 8 | T-2.3: Config Templates | **DONE** | Templates CRUD: save/load/delete named config presets per project. Stored as YAML in `.noted/config_templates/`. Backend: `list_templates`, `save_template`, `get_template`, `delete_template` in `hydra_manager.py`. Router: `GET/POST/DELETE /api/hydra/templates/{id}`. Frontend: template dropdown with load/save/delete buttons in compose panel. |
| 9 | T-2.8 + T-2.15: Pipeline Run History | **DONE** | Full history table in DAG detail page with columns: state icon, started, duration, state, MLflow link. Clickable rows navigate to run detail. Duration calculated server-side. MLflow link navigates to Experiments tree when `conf.mlflow_run_id` is set. Up to 50 runs shown. |
| 10 | T-2.17: DAG Visualization | **DONE** | Read-only directed graph using dagre (layout) + SVG (rendering). Task nodes as rounded rectangles with name, operator label, and state indicator. Arrows show dependency direction. On DAG detail page: neutral/pending colors. On run detail page: nodes colored by task state (green/blue/red/orange/grey). `get_dag_structure()` backend endpoint. 30KB dagre.min.js vendor lib. |

**Phase 2 - Nice to Have (Final Delivery, Labs 5-6):**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 11 | T-2.9 + T-2.13: Sweep DAGs + UI | **DONE** | Parameter grid sweep: comma-separated multi-value inputs, live combination preview table, cartesian product generation, batch DAG triggering. Backend `sweep()` in `airflow_manager.py` triggers one run per combination with `_sweep_id`/`_sweep_index` tags. Frontend sweep panel (jsPanel) with real-time preview and per-run status reporting. Monitoring started for all sweep runs. |
| 12 | T-2.10: Pipeline Scheduling | **DONE** | Dynamic scheduling via Airflow Variables. DAGs use `Variable.get("{dag_id}_schedule")` pattern. Backend: `get_schedule()`, `set_schedule()` in `airflow_manager.py`. Frontend: cron input with Set/Clear buttons in DAG detail panel. Changes take effect on next DAG parse cycle (~30s). |
| 13 | T-2.16: Pipeline Status in Bottom Bar | **DONE** | Blue pill in status bar shows active DAG run name(s). Listens to `pipeline:status` Socket.IO events. Auto-shows on trigger, auto-hides on completion. Multi-run count display. |

**Phase 2 - Additional Work Done (not in original plan):**

| Feature | Description |
|---------|-------------|
| FontAwesome 7.2.0 upgrade | Upgraded from 6.4.2 to 7.2.0. Fixed webfont paths for vendor directory structure. |
| Service iframe navigation | Back/Forward/Refresh/Home buttons in service second bar. URL shown in top bar with real-time updates. |
| Service iframe link interception | Same-origin and container URL links stay in iframe. External links open in new tab. |
| Airflow JWT authentication | Auto-obtains JWT from `/airflow/auth/token`, caches with expiry, retries on 401, falls back to basic auth. |
| Jena training pipeline DAG | Demo DAG with 3 tasks (validate, train, evaluate) and 7 configurable params for testing the trigger UI. |
| Typed trigger form inputs | Number inputs for integers/floats, checkboxes for booleans, dropdowns for enums. Param descriptions shown. |
| DAG pause/unpause with tree update | Tree node icon updates immediately on pause/unpause without browser refresh. |
| Hydra config examples | Examples project with grouped config (model: linear/gru/lstm, data: default/full). |
| MinIO bucket auto-creation | `noted-dvc` bucket created on startup if not present. Prevents errors after fresh `docker compose down -v`. |
| DAG run naming | DAG runs labeled "DAG Run" (not "Run") to distinguish from MLflow experiment runs. |
| MLflow basic-auth exploration | Investigated `--app-name basic-auth`. Browser iframe requires `proxy_hide_header WWW-Authenticate` in nginx. Deferred to OAuth2 proxy for production auth. |
| FontAwesome 7.2.0 upgrade | Upgraded from 6.4.2 to 7.2.0. Fixed webfont paths (`../webfonts/` to `./webfonts/`). |
| ExplorerExternalViews refactoring | Split 2864-line monolith into 7 modules: DocsViews (282), MlflowViews (979), StorageViews (278), PipelineViews (815), HydraViews (416), DataViews (175), orchestrator (29). Factory+ctx pattern preserved. |
| Mounts compose auto-generation | `docker-compose.mounts.yml` auto-generated from `data/NOTED.md` frontmatter. Provides volume entries for both `noted` and all Airflow services. Projects' `dags/` folders visible to Airflow via `../data/projects:/opt/airflow/dags/_projects`. |
| DAG files in project directories | DAGs live in project `dags/` folders (version-controlled), not `services/airflow/dags/`. Airflow discovers them via auto-generated mount volumes. |
| Parallel pipeline DAG | Demo DAG (`parallel_pipeline_dag.py`) with fan-out/fan-in pattern for testing DAG visualization layout. |
| DAG graph interactivity | Click task node navigates to tree. Hover tooltip shows task metadata (state, operator, duration, trigger rule). Live state coloring during execution. |
| DAG detail as undockable tabs | DAGs, DAG runs, and DAG tasks open as proper undockable tabs (same pattern as experiment runs). |

**Phase 3 - Snapshots, Registry, and Serving (next):**

| # | Task | Status | Description |
|---|------|--------|-------------|
| T-3.0 | Snapshot Manager | **DONE** | `snapshot_manager.py`: create/restore/fork/list snapshots. Git branch creation (`snapshot/{experiment}_{version}`), auto-commit dirty state, DVC hash collection + push, MLflow run tagging (`noted.snapshot=true` + lineage metadata), Hydra config hash + YAML artifact, pip freeze artifact. Sequential versioning per experiment. Cleanup on failure (delete branch, return to original). |
| T-3.0b | Run Leaderboard Endpoint | **DONE** | `GET /api/mlflow/experiments/{id}/leaderboard` - all runs with metrics, params, snapshot status, lineage hashes. Sort/order/limit params. Returns metric_keys and param_keys for dynamic columns. |
| T-3.1 | Model Registration | **DONE** | `register_model()` in `mlflow_manager.py`. Creates registered model + version from run artifact URI. Tags with run_id, data hash, config hash. REST: `POST /api/registry/models/register`. Frontend: register panel (jsPanel) with model name input. |
| T-3.2 | Model Listing/Versions | **DONE** | `list_registered_models()`, `list_model_versions()`, `get_model_version()` in `mlflow_manager.py`. REST: `GET /api/registry/models`, `GET .../versions`. Frontend: "Models" section in Explorer tree with brain icon. Expandable model nodes with version children. Detail pages for root, model, and version. |
| T-3.3 | Alias Management | **DONE** | `set_model_alias()`, `delete_model_alias()` in `mlflow_manager.py`. REST: `PUT .../alias`, `DELETE .../aliases/{alias}`. Frontend: alias dropdown (champion/staging/archived) in version detail and version table. Alias badges in tree and detail views. Reassignment removes from previous holder. |
| T-3.4 | Model Lineage | **DONE** | `get_model_lineage()` in `mlflow_manager.py` resolves full chain: Data (DVC hash) -> Config (Hydra hash) -> Code (git commit + snapshot branch) -> Run (MLflow metrics/params) -> Model (Registry version + aliases). Includes Pipeline (Airflow) layer when present. REST: `GET /api/registry/models/{name}/versions/{v}/lineage`. Frontend: vertical chain of clickable nodes with colored icons, greyed out for untracked layers. |
| T-3.5 | Model Comparison | **DONE** | REST: `POST /api/registry/models/compare` returns metrics diff (with delta), params diff (changed only), lineage diff. Frontend: jsPanel with version selectors, metrics table with delta arrows (red up / green down), changed params table, lineage differences summary. |
| T-3.5b | Experiment Report Generation | **DONE** | `report_generator.py` (415 lines). Generates Markdown with: summary, ranked leaderboard, varying/constant params, snapshot details, lineage table. matplotlib charts: grouped bar chart (metrics comparison, best highlighted) + convergence line charts (per-metric history, top 5 runs overlaid). Feeds Markdown + PNGs to existing `DocumentConverter` -> Pandoc -> Word. |
| T-3.6 | Model Serving Container | **DONE** | `client/` folder: FastAPI + Uvicorn service. Endpoints: `/load` (any model by name+version or alias), `/unload`, `/predict`, `/health`, `/schema`. Schema builder extracts input/output metadata from MLflow signatures for dynamic UI. Predict handler supports DataFrame and tensor inputs, formats output as scalar/ndarray/dataframe/class_probabilities. Docker Compose: `noted-serving` service with CPU base + GPU override. |
| T-3.7 | Hot Model Reload | **DONE** | Via `/load` endpoint - frontend can swap models anytime. Thread-safe loader with status tracking (idle/loading/ready/error). No polling needed since user controls which model is loaded. |
| T-3.8 | Serving Proxy | **DONE** | `serving.py` (90 lines): proxies `/api/serving/{load,unload,predict,health,schema}` to serving container. Connection error handling returns 503. |
| T-3.10 | Snapshot UI | **DONE** | "Create Snapshot" button on finished run detail pages. jsPanel modal with capture info, run summary, name/description inputs. SNAPSHOT badge on snapshot runs. |
| T-3.10b | Restore/Fork UI | **DONE** | "Restore Snapshot" button (git checkout + dvc checkout, stash dirty changes). "New Experiment from Snapshot" button (restore + new branch + new MLflow experiment). Confirmation dialogs. Toast notifications. |
| T-3.10c | Run Leaderboard UI | **DONE** | Sortable table with click-to-sort columns (asc/desc arrows), best metric values highlighted bold green, snapshot star badges, metric columns (green headers), param columns (purple headers), alternating row colors, hover highlight, CSV export, click-to-navigate to run detail. Extracted into `ExplorerSnapshotViews.js` (485 lines). |
| T-3.11 | Models Section in Explorer | **DONE** | `ExplorerRegistryViews.js` (451 lines). Tree: models with version children, alias badges. Detail views: root (model list), model (version table with alias dropdowns), version (metadata + alias assignment + source run navigation). Register panel (jsPanel). Wired into orchestrator and ExplorerPanel. |
| T-3.12 | Lineage View | **DONE** | Visual lineage chain auto-loaded on version detail page. Five layers: Data, Config, Code, Run, Model (+ Pipeline when present). Clickable run node navigates to Experiments tree. Greyed out layers for untracked components. |
| T-3.14 | Try It Tab | **DONE** | `ExplorerServingViews.js` (413 lines). jsPanel with auto-load, dynamic input form (named fields for DataFrame, JSON for tensors), output rendering (scalar/line chart/bar chart/table/JSON), request history (last 5). "Try It" button on model version detail. |
| T-3.15 | Serving Status Bar | **DONE** | Green pill in bottom bar showing loaded model name + version. Polls `/api/serving/health` every 10s. Spinner during loading, hidden when idle. |
| T-3.16 | Report Export UI | **DONE** | "Export Word" and "Export Markdown" buttons on experiment detail page. `reports.py` router: `GET /api/reports/experiment/{id}` with format/sort_by/sort_order/top_n params. FileResponse with proper media types. |

**Phase 4 - Integration and Polish (in progress):**

| # | Task | Status | Description |
|---|------|--------|-------------|
| T-4.X | Knowledge Graph Service (Backend) | **DONE** | Separate container `graph/` (Alpine + Python, port 5523). 5 scanners: MLflow (experiments, runs, snapshots, models), DVC (tracked files, versions), Hydra (configs, groups, options), Airflow (DAGs, tasks, runs), Filesystem (projects, notebooks, files). Relationship resolver with 9 cross-entity edge types. In-memory graph cache with TTL. Full-text search index (text, prefix, metric threshold, tag queries). Tag CRUD with JSON storage in `.noted/tags/`. 6 built-in perspective views (Lineage, Performance, Versioning, Pipeline, Overview, Tags) + custom view storage. REST API: /graph, /neighborhood, /entity, /search, /tags, /views. noted backend proxy at `/api/graph/*`. |
| T-4.X-E | Knowledge Graph Frontend | **DONE** | `knowledge-graph/` folder: KnowledgeGraph3D.js (881 lines, Three.js scene, force-directed layout, 18 entity-type shapes/colors, node dragging with live physics simulation, neighbour highlighting, search with camera animation, draggable/resizable/pinnable detail panel on hover, "Open in Explorer" navigation), GraphPanel.js (235 lines, jsPanel with search bar + view selector + results dropdown), GraphNodeRenderer.js (44 lines, entity style definitions). Dynamic import (Three.js loads on first panel open). View > Knowledge Graph menu item. |
| T-4.R5 | Config as CLI Overrides | **DONE** | sys.argv injection for @hydra.main cells. Flattens resolved config to dot-notation overrides. |
| T-4.R6 | Config Search in Leaderboard | **DONE** | Filter bar in leaderboard with =, !=, >, >=, <, <= operators. Searches params and metrics. Debounced 300ms. |
| T-4.R7 | Config Template for Pipeline Runs | **DONE** | "Load Last Run Config" button in trigger panel. Fetches last successful run's conf and pre-fills inputs. |
| T-4.R8 | Run as Pipeline from Notebook | **DONE** | Rocket button in notebook second bar. Auto-discovers project DAGs by tag. Triggers with current Hydra config. Multi-DAG selection. |
| T-4.R9 | Copy Log Action | **DONE** | Copy button in task log viewer. Disabled until log loads, feedback "Copied" for 1.5s. |
| T-4.R10 | Retry Failed Task | **DONE** | Retry button for failed/upstream_failed tasks. Calls Airflow clearTaskInstances API to re-queue. |
| T-4.R11 | DVC Per-File Sync Icons | **DONE** | Green cloud = pushed, orange cloud-up = not pushed. Backend `dvc status --cloud` endpoint. |
| T-4.R12 | Post-Run Summary Toast | **DONE** | Toast shows run name + last metric values (up to 5, pipe-separated). |
| T-4.R13 | Pinned Metrics in Leaderboard | **DONE** | Columns button with checkbox dropdown for metrics + params. |
| T-4.R14 | Epoch Progress Bar | **DONE** | Progress bar in Live Metrics panel. Shows "Epoch X / Y" when total_epochs logged. |
| T-4.R16 | Predict Cell Template | **DONE** | "Insert Predict Cell" button on model version detail page. |
| T-4.R17 | APIs Section in Workspace | **DONE** | APIs section in Explorer tree with serving endpoint health/model info. |
| T-4.R18 | Bulk Run Management | **DONE** | Multi-select list + "Delete Selected" on experiment detail page. |
| T-4.R19 | Promote Best Config | **DONE** | "Promote Best" button in leaderboard saves best run's params as Hydra template. |
| T-4.R20 | Config Inheritance View | **DONE** | Source file annotations in compose panel (key <- file). |
| T-4.R21 | Dynamic Task Generation | **DONE** | Mapped tasks shown with [index] suffix in task tree. |
| T-4.R22 | Notebook-to-DAG Conversion | **DONE** | "Export as Pipeline Task" rocket button on code cells copies @task function. |
| T-4.R23 | DAG Validation | **DONE** | "Validate" button on DAG detail checks imports, syntax, common pitfalls. |
| T-4.R24 | Jump to Error in Logs | **DONE** | Error lines highlighted dark red, auto-scroll to first error in task log. |
| T-4.R25 | Visual Cron Builder | **DONE** | Preset cron buttons (@hourly, @daily, @weekly, Every 6h, Every 12h, Weekdays 9am). |
| T-4.R26 | Data-Aware Pipeline Triggering | **DONE** | DVC tracked files shown in trigger panel for the DAG's project. |
| T-4.R27 | Template Runs | **DONE** | Covered by Hydra templates + "Load Last Run Config" + "Promote Best". |
| T-4.R28 | Pipeline Health Indicators | **DONE** | Colored health dot on Pipelines root (green/red/blue). |
| T-4.Y | Automated Test Suite | **DONE** | 129 tests (15 kernel + 114 API/E2E), 0 failures, 0 skips - 100% pass rate. Test container (`noted-test`) with 3 suites: Socket.IO kernel execution (MLflow, Hydra injection, terminal), REST API (strengthened assertions verifying response values and behavior), Playwright E2E (headless Chromium, real tree navigation). Snapshot test verifies end-to-end: git branch, git commit SHA, DVC hashes, Hydra config hash, MLflow run reference, version numbering, and branch existence. All 31 testing documents covered. Two-phase pipeline (kernel first, restart, then API+E2E) via `run-all.sh`. Found and fixed 1 backend bug: Hydra config injection ignored list-style overrides from frontend selector. |
| T-4.RV | Run Python with Venv | **DONE** | Right-click `.py` file > "Run with venv" opens a terminal and auto-executes with the active venv's Python. Also available as a green play button in the file editor second bar. Uses active venv or falls back to system python3. Reuses existing ProjectTerminal infrastructure with new `initialCommand` option. |
| T-4.Z | Merge Projects into Mounts | Not started | Unify into single "Projects" section |
| T-4.WEB | HTML/CSS/JSON Language Support | **DONE** | Syntax highlighting, auto-completion, hover documentation, and linting/validation for HTML, CSS, and JSON files via vscode-langservers-extracted. Documentation panel shows hover docs. |
| T-4.ENV | Environments Rename + Language Grouping | **DONE** | "Virtual Environments" renamed to "Environments". Python and JavaScript shown as sub-nodes with VS Code color SVG icons (background-image technique). |
| T-4.ICONS | VS Code-Style SVG Icons | **DONE** | Folder icons, Python/JS language icons as color SVGs. VS Code-style SVG icons in autocomplete dropdown (method, property, variable, class, etc.). |
| T-4.IIFE | JS Notebook IIFE Wrapping | **DONE** | const/let re-declaration fix via IIFE wrapping with globalThis exports for JavaScript notebook cells. |
| T-4.EDITOR | File Editor Improvements | **DONE** | Tab inserts 4 spaces, Ctrl+Home/End navigate to start/end of file, hover documentation shown in Documentation panel only (not inline). |
| T-4.STARTUP | Clean Startup | **DONE** | Application starts with no panels open. |

**Phase 5 - Advanced Features and Production Readiness (planned after Phase 4):**

| # | Task | Effort | Status | Description |
|---|------|--------|--------|-------------|
| T-5.1 | Impact Analysis via Knowledge Graph | S-M | Not started | Right-click "What breaks if I change this?". Directed BFS on downstream edges. Highlight affected runs, pipelines, models in 3D graph. |
| T-5.2 | Automated Model Cards | S-M | Not started | Generate structured Model Card documents from lineage data (data hash + config + code + metrics). Uses existing DocumentConverter pipeline. "Generate Model Card" on model version detail. |
| T-5.3 | Project Templates | M | Not started | "New Project" wizard with pre-configured templates: LLM Fine-tuning, Time-series Forecasting, Computer Vision. Each has Hydra config, starter DAG, notebook, venv setup. |
| T-5.4 | Data Validation and Quality Gates | M | Not started | Integrate Pandera for DataFrame schema validation. `.schema.yaml` alongside `.dvc` files. "Data Health" badge in tree. Pre-pipeline validation checks. |
| T-5.5 | Post-Deployment Observability | L | Not started | Monitoring panel for noted-serving. Feature/prediction drift detection. Latency/throughput metrics. Production anomalies linked back to training data/config via Knowledge Graph. |
| T-5.6 | Hardware and Cost Profiling | M | Not started | GPU utilization monitoring via nvidia-smi during training. Logged as MLflow metrics. Displayed in Live Metrics panel alongside loss curves. |
| T-5.7 | Collaborative Feature Store | S | Not started | "Feature Catalog" view. Register DVC-tracked files as verified features with descriptions and tags. Reuses existing tags infrastructure. |

---

## Key Decision: Airflow over DVC Pipelines

Confirmed from teacher's lab notebooks (2026-03-17): the teacher uses **Airflow for orchestration** and DVC **only for data versioning** (`dvc add`/`dvc push`/`dvc pull`). He does NOT use `dvc.yaml` pipelines or `dvc repro`. This aligns with noted's architecture and scope document (F-DVC out-of-scope explicitly excludes `dvc repro` from UI). Phase 2 Airflow integration is the correct path.

---

## EMI Deadlines

| Delivery | Deadline | Weight | Status |
|----------|----------|--------|--------|
| Tutorial #1 | 2026-03-17 | 20% | SUBMITTED |
| Tutorial #2 | 2026-03-29 | 40% | Next (10 days) |
| Final Delivery | 2026-04-12 | 40% | Planned |
| Oral Discussion | 2026-04-21 | - | Planned |

---

## Known Pending Issues

- Cancel active install before deleting an environment
- `ProjectVersionControl` abstraction not implemented (two separate managers)
- Backend code baked into Docker image - must rebuild to deploy
- noted image now on Docker Hub (`logus2k/noted`) - compose `pull_policy` needs update for distribution

---

## Key File Map

### Backend

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI + Socket.IO app, event handlers |
| `backend/app/managers/kernel_manager.py` | Kernel lifecycle + env injection |
| `backend/app/managers/execution_bridge.py` | ZMQ→Socket.IO bridge, auto-instrumentation hooks |
| `backend/app/managers/auto_instrumentation.py` | MLflow silent code injection engine |
| `backend/app/managers/notebook_manager.py` | Notebook file CRUD (project root resolution) |
| `backend/app/managers/file_manager.py` | Generic file CRUD for projects and mounts |
| `backend/app/managers/git_manager.py` | Git operations |
| `backend/app/managers/dvc_manager.py` | DVC operations |
| `backend/app/managers/minio_manager.py` | MinIO S3 bucket/object browsing |
| `backend/app/managers/mlflow_manager.py` | MLflow SDK wrapper (experiments, runs) |
| `backend/app/managers/project_settings.py` | .noted/settings.json read/write |
| `backend/app/routers/mlflow.py` | REST: MLflow experiments/runs/run-detail/metric-history/artifacts |
| `backend/app/routers/minio.py` | REST: MinIO buckets/objects/metadata |
| `backend/app/routers/projects.py` | REST: project settings |
| `backend/app/managers/terminal_manager.py` | PTY-based terminal session lifecycle |
| `backend/app/routers/dvc.py` | REST: DVC status/track/push/pull/checkout |
| `backend/app/routers/git.py` | REST: git operations |
| `backend/app/routers/files.py` | REST: generic file browsing/read/write |
| `backend/app/managers/hydra_manager.py` | Hydra config schema, compose, templates CRUD |
| `backend/app/managers/airflow_manager.py` | Airflow DAG discovery, trigger, monitoring (JWT auth) |
| `backend/app/managers/config_manager.py` | Mount config (NOTED.md), compose mounts file generation |
| `backend/app/routers/hydra.py` | REST: Hydra config schema/compose/group/templates |
| `backend/app/routers/airflow.py` | REST: Airflow DAGs/runs/tasks/logs/trigger/structure |
| `backend/app/managers/snapshot_manager.py` | Experiment snapshots: create, restore, fork, list |
| `backend/app/routers/snapshots.py` | REST: Snapshot create/restore/fork/list |
| `backend/app/routers/registry.py` | REST: Model Registry models/versions/aliases |
| `frontend/js/panels/explorer/ExplorerRegistryViews.js` | Model Registry tree and detail views |
| `frontend/js/panels/explorer/ExplorerSnapshotViews.js` | Leaderboard table + Snapshot modal/restore/fork |
| `frontend/js/panels/explorer/ExplorerServingViews.js` | Try It panel, prediction rendering, model load |
| `backend/app/routers/serving.py` | REST: Serving proxy (load/unload/predict/health/schema) |
| `client/app/main.py` | Model serving FastAPI app |
| `client/app/model_loader.py` | MLflow model loading, thread-safe lifecycle |
| `client/app/schema_builder.py` | Input/output schema from MLflow signatures |
| `client/app/predict.py` | Input parsing, inference, output formatting |
| `backend/app/managers/report_generator.py` | Experiment report: Markdown + matplotlib charts -> Word via DocumentConverter |
| `backend/app/routers/reports.py` | REST: Experiment report generation |
| `graph/app/main.py` | Knowledge Graph FastAPI app |
| `graph/app/graph_builder.py` | Orchestrates 5 scanners + relationship resolution + tag loading |
| `graph/app/scanners/mlflow_scanner.py` | Scans experiments, runs, snapshots, models, versions |
| `graph/app/scanners/dvc_scanner.py` | Scans .dvc files, parses hashes, walks git history for versions |
| `graph/app/scanners/hydra_scanner.py` | Scans config dirs, groups, options, defaults |
| `graph/app/scanners/airflow_scanner.py` | Scans DAGs, tasks, runs via JWT-authenticated API |
| `graph/app/scanners/filesystem_scanner.py` | Scans projects, notebooks, DAG files, Python files |
| `graph/app/relationship_resolver.py` | 9 cross-entity edge resolvers (run->data, run->config, etc.) |
| `graph/app/search_index.py` | In-memory inverted index with text, metric, and tag search |
| `graph/app/views.py` | 6 built-in perspective views + custom view storage |
| `graph/app/routers/graph.py` | Full graph, neighborhood, entity, cache invalidation |
| `graph/app/routers/search.py` | Full-text search endpoint |
| `graph/app/routers/tags.py` | Tag CRUD (add/remove/list per entity) |
| `graph/app/routers/views.py` | List/get/save/delete perspective views |
| `backend/app/routers/graph_proxy.py` | Proxies /api/graph/* to graph service |
| `frontend/js/knowledge-graph/KnowledgeGraph3D.js` | Three.js 3D scene, force layout, interaction |
| `frontend/js/knowledge-graph/GraphPanel.js` | jsPanel with search, view selector, graph loading |
| `frontend/js/knowledge-graph/GraphNodeRenderer.js` | Entity-type shapes, colors, icons (18 types) |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/js/app.js` | Bootstrap, wiring, tab management |
| `frontend/js/IconBar.js` | Icon bar with view toggles |
| `frontend/js/panels/ExplorerPanel.js` | Workspace tree core, detail panes, experiments browser |
| `frontend/js/panels/explorer/ExplorerHelpers.js` | Shared utility functions for explorer modules |
| `frontend/js/panels/explorer/ExplorerProjectViews.js` | Project/mount detail views (file detail, folder detail) |
| `frontend/js/panels/explorer/ExplorerEnvViews.js` | Environment detail views (Python/JavaScript sub-nodes) |
| `frontend/js/panels/explorer/ExplorerExternalViews.js` | Orchestrator for all external view modules |
| `frontend/js/panels/explorer/ExplorerMlflowViews.js` | MLflow experiments, runs, artifacts, metrics |
| `frontend/js/panels/explorer/ExplorerPipelineViews.js` | Airflow DAGs, runs, tasks, trigger, DAG visualization |
| `frontend/js/panels/explorer/ExplorerHydraViews.js` | Hydra config groups, options, compose, templates |
| `frontend/js/panels/explorer/ExplorerStorageViews.js` | MinIO bucket/object browsing |
| `frontend/js/panels/explorer/ExplorerDataViews.js` | DVC data overview, version history |
| `frontend/js/panels/explorer/ExplorerContextMenu.js` | Wunderbaum context menu definitions |
| `frontend/js/NotebookEditor.js` | Cell array, remote sync, listener cleanup |
| `frontend/js/KernelClient.js` | Socket.IO kernel communication |
| `frontend/js/CellEditor.js` | CodeMirror per cell |
| `frontend/js/GitPanel.js` | Source Control sidebar (git + DVC + tags) |
| `frontend/js/TocPanel.js` | Table of Contents (notebook/markdown/PDF) |
| `frontend/js/MetricsPanel.js` | Live metrics + historical charts (ECharts, 3 views, multi-panel) |
| `frontend/js/ProjectTerminal.js` | Reusable floating terminal with access key auth |
| `frontend/js/InteractiveTerminal.js` | xterm.js bidirectional terminal connected to PTY via Socket.IO |
| `frontend/js/services/DecorationService.js` | Git/DVC tree decorations |

### Key Documents

| File | Purpose |
|------|---------|
| `documents/noted_mlflow.md` | MLflow integration design (v2.0) — includes Run Manager spec |
| `documents/noted_dvc.md` | DVC integration use cases |
| `documents/noted_architecture_principles.md` | Architecture design principles (v1.0) — zero lock-in, terminal escape hatch, decisions log |
| `documents/project-status.md` | This file |

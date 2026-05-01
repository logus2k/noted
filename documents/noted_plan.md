# noted - Integrated MLOps Platform Plan

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Development Plan                   |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 2.7                                |
| Date          | 2026-04-15                         |
| Status        | Draft                              |
| Related       | Vision Document v2.4, Scope Document v2.4, Knowledge Graph Design v1.0, Tutorial 2 Implementation Plan v1.0 |
| Changes       | See [Changelog](#changelog) below                                                |

---

## Changelog

### v2.7

Final delivery milestone (2026-04-14/15). **Model Serving Refactor - Phase 0a shipped 2026-04-14**: Deploy / Unload / Try It three-button UX aligned with MLflow terminology (replaces "Publish / Try It" wording); streaming NDJSON progress from `/load` endpoint with phases resolving -> downloading -> loading_model -> ready; `ModelLoader` correctness fixes (RLock full serialization of the load path, content-hash cache to skip re-install when same requirements.txt was already processed, early-return when same model+version already loaded, non-blocking `try_acquire` in unload so concurrent unload during load refuses cleanly); new `DeployEventStream` class bridging the sync loader's phase callbacks to an async NDJSON generator using `asyncio.wait(FIRST_COMPLETED)`; new `ModelDeployer` frontend class using fetch + `ReadableStream.getReader()` + line-based NDJSON parser (no `setTimeout` polling anywhere); framework-specific VRAM cleanup in unload (`tf.keras.backend.clear_session`, `torch.cuda.empty_cache` + `torch._dynamo.reset`, `jax.clear_caches`), all gated on `sys.modules` so frameworks not in use are never imported. **Model Serving Refactor - Step 1 unblock shipped 2026-04-15**: Phase 0a's runtime install (`_install_model_deps` calling `uv pip install --system`) was discovered to fail on cold deploys because Python cannot hot-swap C extension modules in a running interpreter (protobuf runtime/gencode mismatch crashes). Fix: dropped `protobuf>=4.0.0,<5.0.0` pin from `client/requirements.txt`, removed the `_install_model_deps` call from `_load_inner()`, removed the `_installed_reqs_hashes` cache, removed the `hashlib` import, and removed the entire `_install_model_deps` method. Baseline image now serves all registered model versions via MLflow's warning-mode loading (verified end-to-end against v1-v7 of Jena Weather Forecaster). Phase 0b worker-subprocess architecture designed in `documents/serving_worker/serving_worker_plan.md` (~9h core + ~5h optional layers for uv cache volume, per-model venvs, worker pool with in-place switching) but deferred to post-demo since step-1 unblock eliminates the immediate crash vector. **Logged Models UI shipped 2026-04-15**: new backend endpoints `GET /api/mlflow/runs/{run_id}/logged_models` and `GET /api/mlflow/logged_models/{experiment_id}/{model_id}/download?path=...` in `backend/app/routers/mlflow.py`; new `MlflowManager.list_logged_models_for_run()` scans `<exp_id>/models/` via MLflow's artifacts REST API and walks each matching model's tree (matches against run_id via MLmodel content); new `MlflowManager.download_logged_model_artifact()` streams via artifact proxy HTTP (not `mlflow.artifacts.download_artifacts`, to avoid the noted backend's SQLite tracking URI issue). Frontend: new `loadLoggedModelsCategory` / `loadLoggedModelSubdir` / `showLoggedModelsCategoryDetail` / `showLoggedModelDetail` in `ExplorerMlflowViews.js`; key-prefix dispatch for `mllm-cat:` / `mllm:` in `ExplorerPanel.js`; fa-brain icon in Files grey via inline `setProperty('color', '#b0bec5', 'important')` in `_recolorNode`; hljs-highlighted previews (language-yaml for MLmodel / conda.yaml / python_env.yaml, language-plaintext for requirements.txt). **jena_client Model Serving Client shipped 2026-04-15**: generic reference client at `iscte/jena_client/` with three-dropdown UI (Model / Version / Alias with `@champion` auto-selected); backend endpoints `/api/models` (merges `registered-models/get` for aliases with `model-versions/search` for versions) and `/api/models/{name}/versions` and `/api/run_params/{run_id}` and `/api/schema`; NDJSON streaming `load_model` socket handler consumes `resp.aiter_lines()` and forwards progress events as frontend status updates, emits `model_loaded` on the terminal `ready` event; inverse scaler transform via `target_mean` / `target_std` MLflow params (applied as `value * std + mean` before rendering); three-column results table (Hour / Temperature degC / Raw z-score) with scaler formula caption; noted-style scrollbars, hljs-matched monospace font, subtitle shows `{model_name} v{version}`. **Notebook fix 2026-04-15**: `emi_tutorial3_jena_weather.ipynb` cells 116 and 117 refactored to gate MLflow logging and `register_and_promote()` behind `if mlflow.active_run() is not None:` (Run All no longer creates orphan runs); added `target_mean` / `target_std` to `mlflow.log_params()` so serving clients can de-standardize. **Git tagging instrumentation shipped 2026-04-15**: `execution_bridge.py _log_hydra_bundle_for_run` git-tagging block rewritten with per-branch `logger.info` / `logger.warning` at every exit point (resolve project path, .git check, rev-parse success/failure, tag writes, caught exception with exc_info=True); no more silent fall-throughs. **User Manual 7 pages published 2026-04-15**: Pages 1-5 revised (UX-friction blockquotes and friction-summary tables stripped, content updated to reflect shipped state); Page 6 (Serving & Deploying Models) and Page 7 (noted Assistant) newly written; all 7 published to Knowledge Base under `data/documents/files/manual_0[1-7]_*.md` and indexed in `data/documents/documents.json`. **NOTED_SETUP.md** added at repo root as the reviewer-facing setup guide covering prerequisites, cloning noted + jena_weather + jena_client, configuring `data/NOTED.md` upfront mounts, `services/.env.example` -> `services/.env`, launch with GPU/CPU compose variants, first-run smoke test (Page 1 flow + train + Deploy + Try It + jena_client), troubleshooting, stop/cleanup; mentions `https://github.com/logus2k/noted` and live instance `https://logus2k.com/noted`. **Post-demo backlog** captured in `documents/noted_backlog.md`: Phase 0b worker-subprocess architecture, MLflow soft-delete foot-gun (remove `except: pass` in `RUN_START_CODE` + detect-and-offer-restore-or-purge modal), noted terminal child-process tracking (kill-on-close/rebuild prompt), generic output rendering for non-regression models in serving client, UI timestamp audit.

### v2.6

Explorer UX overhaul (root node detail pages removed, double-click expand, tree consolidation Models/Data, KB upload to context menu, KB document undocking, Knowledge Graph as KB tree child, R renv package manager fully implemented, renv cache persistence, skills as document tabs - shipped 2026-04-11). Hydra Unification + Time Machine: Configuration Composer with dual mode (Local Baseline / Experiment Run), per-run self-contained Hydra bundles archived to MLflow (hydra/ folder: config/ tree + selections.json + resolved.yaml), HydraSource abstraction (LocalSource/MlflowSource) + in-memory cache keyed by (notebook_uid, run_id), baseline badge (BASELINE/RUN xxxxxx + colored dot: green check / orange ! / red X), stale metadata validation, schema refresh on Apply, Composer Apply-before-run footgun fixed (M1-M6 all shipped 2026-04-12). Tutorial 3 jena_weather Level C: training config inlined into config.yaml (10 override inputs in Composer), second DVC-tracked dataset (jena_climate_2012.csv, 52704 rows), DAG Level C refactor with log_hydra_lineage task producing Hydra bundles for all DAG runs, Run Manager dataset row read-only for Hydra-using notebooks, DAG runs appear in Time Machine dropdown alongside Run Manager runs (shipped 2026-04-13). Evidently partial: evidently_quality (DataSummaryPreset) and evidently_drift (DataDriftPreset, run_id linkage) DAG tasks, Data Health dot, Evidently UI service tab (T-5.4/T-5.5 partial - quality gates and model drift badges still planned). Chat/Assistant fixes: Ask Assistant duplicate messages, panel focus on invoke, full run IDs, Gemma token regex (thought\n -> thought\s), pre-thinking preamble stripping, math rendering in chat via marked.js KaTeX extension. User Manual Pages 1-5 written and published to Knowledge Base.

### v2.5

R as third notebook language (T-5.R1 Phase 1 R kernel/execution DONE; T-5.R2 Phase 2 R LSP for modern R DONE; T-5.R3 Phase 2.1 IRkernel for legacy R DONE; T-5.R4 Phase 2.2 PPM-binary languageserver for legacy R DONE; T-5.R5 R Run from file editor PLANNED; T-5.R6 R debugger PLANNED Phase 3 deferred). Six R versions supported (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) - all 6 with full LSP. Two-kernel architecture (ark for modern, IRkernel for legacy because ark cannot drive R 3.x / R 4.0). Two languageserver install paths (latest CRAN for modern, era-matched PPM binary repos for legacy bypassing both source dep resolution and glibc 2.34 testthat compile failure). RENV_CONFIG_EXTERNAL_LIBRARIES injected for both LSP and kernel paths. libicu66 from focal archive installed alongside libicu74 to satisfy stringi runtime linking. End-to-end validated via the 9-test walkthrough at testing/34_test-r-lsp-phase2.md - ALL pass. Bonus fixes shipped alongside: 4 pre-existing main.py bugs, bridge `_latest_sources` cache for cross-cell completion, ERROR spam silence, R binary path substitution, Tab-to-accept via Prec.highest (required Prec re-export from CodeMirror bundle), MenuBar text-editing-shortcut focus check, NotebookEditor.undo() public method. Seven languages with full LSP: Python, JavaScript, R, HTML, CSS, JSON, YAML.

### v2.4

YAML language support via yaml-language-server (Red Hat).

### v2.3

Web language support added (T-5.WEB1 DONE). HTML/CSS/JSON syntax highlighting via @codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json. LSP for HTML/CSS/JSON via vscode-langservers-extracted (single-server mode). VS Code-style completion icons (SVG data URI). File editor improvements (Tab=4 spaces, Ctrl+Home/End, Documentation panel hover). "Virtual Environments" renamed to "Environments" with Python/JS language sub-nodes and VS Code color SVG icons. JS notebook IIFE wrapping for const/let re-declaration fix with globalThis exports. Clean startup (no panels, no auto-open). dynamicRegistration forced false for all LSP init. rootUri rewrite for virtual-to-real path mapping. Verified test matrix (testing/33_test-language-support-matrix.md).

### v2.2

JavaScript integration tasks added to Phase 5 (T-5.JS1 through T-5.JS5). Evidently tasks (T-5.4, T-5.5) updated with detailed plan references.

### v2.0

DAP Phase D4 tasks added to Phase 4 (T-4.DAP5 Run Menu and Debug UI, T-4.DAP6 Debug All Cells, T-4.DAP7 Debug Stop Cleanup - all done). Multi-language debug support added to Phase 5 (T-5.11). Default theme/wallpaper changes and scrollbar fix recorded.

### v1.9

LSP integration tasks added to Phase 4 (T-4.LSP1 through T-4.LSP5, all done). DAP integration tasks added to Phase 4 (T-4.DAP1 through T-4.DAP4, all done). app.js refactoring and Explorer improvements recorded. Curriculum alignment updated with LSP/DAP coverage.

### v1.8

Auto-tracking removed, Run Manager is the only managed tracking mode. AI Assistant consolidated as first-class feature (T-4.AI tasks). DAG trigger enhanced with Hydra dropdowns. Curriculum alignment section generalized.

### v1.7

All platform phases (0-4) completed. Jena Weather reference pipeline added. Phase 4 completed (129 automated tests, Knowledge Graph).

### v1.6

Phase 5 added - Advanced Features.

### v1.5

Phase 2 completed. Phase 3 redesigned with Snapshots.

### v1.4

Multi-notebook support, ExplorerPanel refactored.

### v1.3

Academic alignment requirements added.

### v1.2

Phase 0 completed, Phase 1 split into 1A/1B.

---

## 1. Purpose

This document defines the phased delivery plan for the noted MLOps platform. It sequences the work based on technical dependencies, incremental value delivery, and risk management. Each phase produces a working, demonstrable increment of the platform.

---

## 2. Phasing Strategy

### 2.1 Dependency Graph

The tools and features have hard technical dependencies that constrain sequencing:

```
MinIO (running)
    |
    +----> DVC (needs remote storage)
    |
    +----> MLflow Tracking (needs artifact store) (running)
               |
               +----> MLflow Registry (needs tracking data)
               |           |
               |           +----> Model Serving (needs registry)
               |
               +----> Hydra (config logged as MLflow artifact)
                          |
                          +----> Airflow (executes with Hydra configs) (running)
```

### 2.2 Value Delivery Principle

Each phase must be independently useful. A user should benefit from Phase 1 even if Phase 4 is never built. This means:

- Phase 1A delivers UI layout infrastructure and basic MLflow experiment tracking
- Phase 1B adds data versioning, Run Manager, and advanced tracking features
- Phase 2 adds configuration management and orchestration (production workflows)
- Phase 3 adds model governance and serving (deployment lifecycle)
- Phase 4 adds cross-cutting integration polish and the end-to-end experience

### 2.3 Phase Overview

| Phase | Name                              | Primary Tools                   | Key Deliverable                                          |
|-------|-----------------------------------|---------------------------------|----------------------------------------------------------|
| 0     | Infrastructure Verification       | MinIO, PostgreSQL, Docker       | All services verified connectable and interoperable      |
| 1A    | UI Layout and MLflow Integration  | MLflow Tracking, CodeMirror     | New layout (icon bar, sidebar, tabs) + MLflow tracking   |
| 1B    | Data Versioning and Advanced Tracking | DVC, Git, MLflow              | Versioned data, Run Manager, live metrics, comparison    |
| 2     | Configuration and Orchestration   | Hydra, Airflow                  | Config-driven pipeline execution from noted UI           |
| 3     | Registry and Serving              | MLflow Registry, FastAPI serving| Model promotion and live prediction from noted UI        |
| 4     | Integration and Polish            | All                             | Full lineage, collaboration events, end-to-end workflow  |
| 5     | Advanced Features and Production Readiness | Knowledge Graph, Evidently, nvidia-smi | Impact analysis, model cards, templates, data quality, drift monitoring |

---

## 3. Phase 0: Infrastructure Verification

**Goal:** Verify that all already-running backend services can communicate with the noted container and with each other as required.

**Rationale:** All core infrastructure is already deployed (MLflow, Airflow 3.0, MinIO, PostgreSQL, Redis). This phase confirms interoperability and creates the bucket/database structures needed by subsequent phases. No new services are deployed.

### 3.1 Tasks

**T-0.1: Docker Network Connectivity**
Verify that the noted container can reach all backend services on the Docker internal network:
- MLflow server (`mlflow:5000`)
- Airflow API Server (`airflow-apiserver:8080`)
- MinIO (`minio:9000`)
- PostgreSQL (`postgres:5432`)

Acceptance: HTTP health checks pass from within the noted container for each service.

**T-0.2: PostgreSQL Database Setup**
Create a dedicated `noted` database within the existing PostgreSQL instance (`postgres`) for noted application metadata. Confirm MLflow's database also exists and is accessible.

Acceptance: noted backend can connect to the `noted` database. MLflow backend store is confirmed operational.

**T-0.3: MinIO Bucket Structure**
Create the base bucket structure in the existing MinIO instance (`minio`):
- `noted-mlflow-artifacts` (MLflow artifact store)
- `noted-dvc` (DVC remote storage)

Acceptance: MLflow can write and read artifacts via S3 protocol to the new bucket. DVC can push and pull to the new bucket.

**T-0.4: MLflow Integration Verification**
Verify MLflow server from the noted container:
- Create an experiment via the MLflow API
- Start a run, log a metric, log a file artifact to MinIO
- Retrieve all via the MLflow API

Acceptance: Full round-trip (create experiment -> log data -> retrieve) succeeds from inside the noted container.

**T-0.5: Airflow API Verification**
Verify Airflow 3.0 API Server from the noted container:
- List existing DAGs via the REST API
- Place a test DAG file in the Airflow DAGs directory
- Trigger it via the API Server
- Confirm execution completes on the Celery worker

Acceptance: Test DAG triggered from noted container executes successfully on the Airflow worker.

**T-0.6: DVC + Git Verification**
Verify DVC with backend-managed Git within the noted container:
- `git` subprocess can initialize a bare repo
- `dvc init` succeeds within a test project directory
- `dvc add` on a test file creates a `.dvc` pointer file
- `dvc push` sends the file to MinIO (`noted-dvc` bucket)
- `dvc pull` in a clean directory retrieves the file from MinIO

Acceptance: Round-trip test (add -> push -> delete local -> pull -> verify content) passes.

**T-0.7: Airflow Worker Access to Project Data**
Resolve how the Airflow worker (`noted-airflow-worker`) accesses project files:
- Option A: Shared volume mount (same `/data/projects` volume mounted read-only on worker)
- Option B: Worker runs `dvc pull` at task start (requires DVC + MinIO access from worker)

Decision required before Phase 2 but the volume mount should be tested here.

Acceptance: Airflow worker can read a file from a noted project directory.

### 3.2 Decision Points

| Decision                                 | Options                          | Deadline       |
|------------------------------------------|----------------------------------|----------------|
| pygit2 vs git subprocess                 | pygit2 preferred, subprocess fallback | Before T-0.6 |
| Worker data access (volume vs DVC pull)  | Volume mount preferred           | Before T-0.7   |

### 3.3 Exit Criteria

All services are verified reachable from the noted container. Bucket structure exists. Test round-trips pass for MLflow, Airflow, and DVC. No user-facing changes.

### 3.4 Phase 0 Results

Phase 0 completed on 2026-03-10. All tasks passed:

| Task | Result | Notes |
|------|--------|-------|
| T-0.1: Docker network connectivity | PASS | All 4 services reachable from noted container |
| T-0.2: PostgreSQL `noted` database | PASS | Database created and accessible |
| T-0.3: MinIO bucket structure | PASS | `noted-mlflow-artifacts` and `noted-dvc` created |
| T-0.4: MLflow round-trip | PASS | Experiment, run, metric, param — full cycle |
| T-0.5: Airflow API | PASS | JWT auth, DAG deploy, trigger, execution on Celery worker |
| T-0.6: DVC + Git | PASS | git subprocess + dvc[s3], round-trip to MinIO |
| T-0.7: Worker data access | PASS | Shared volume mount at /opt/noted/projects:ro |

**Decisions resolved:**
- pygit2 vs git subprocess → **git subprocess** (installed in container, works reliably)
- Worker data access → **shared volume mount** (read-only, tested successfully)
- Airflow API auth → **JWT tokens** via `/auth/token` endpoint (Airflow 3.x), session backend for web UI
- Execution API URL → requires `/airflow` prefix to match `AIRFLOW__API__BASE_URL`

---

## 4. Phase 1A: UI Layout and MLflow Integration

**Goal:** Rebuild the UI layout to support the full MLOps lifecycle, migrate existing features into the new layout, and deliver MLflow experiment tracking as the first integration.

**Rationale:** The current UI (floating modal Explorer, single notebook view, toolbar-triggered service iframes) cannot support the density of features planned for Phases 1-4. Building the layout infrastructure first ensures all subsequent features have a consistent home. MLflow tracking is included because it delivers immediate user value and validates the new layout with real content.

### 4.1 Tasks

**T-1A.1: Icon Bar and Sidebar Shell**
Build the left icon bar and collapsible Workspace Explorer sidebar:
- Icon bar: narrow vertical strip, always visible, one icon per category
- Sidebar: slides in/out on icon click, resizable width via drag handle
- Initial categories: Projects, Environments (migrated from existing Explorer)
- State persistence: sidebar width, collapsed/expanded, active section (localStorage)
- CSS: new sidebar.css module

**T-1A.2: Tabbed Center Pane**
Replace the current fixed notebook container with a tabbed content area:
- Tab bar with close buttons, active tab indicator
- Tab types: notebook (existing editor), iframe (service UIs), placeholder for future types
- Tab lifecycle: create, focus, close, persist across page reload (localStorage)
- The existing notebook editor becomes the content of a notebook tab
- Notebook tab opens automatically when a notebook is selected in the Workspace tree
- TabManager class (frontend/js/TabManager.js) manages all tab operations

**T-1A.3: Workspace Explorer Migration**
Migrate the existing ExplorerPanel (floating jsPanel modal) into the new sidebar:
- Move Projects tree (Wunderbaum) into the sidebar under Projects section
- Move Environments management into the sidebar under Environments section
- Keep the existing tree data and detail pane behavior (split view within sidebar)
- Remove the floating Explorer jsPanel
- Toolbar "Browse" button now toggles the sidebar instead

**T-1A.4: Service UI Tabs**
Move MLflow, Airflow, and MinIO from toolbar-triggered floating panels to center pane tabs:
- Each opens as an iframe tab when clicked in toolbar or Workspace tree
- Singleton behavior: clicking again focuses existing tab
- Tab title shows service name with optional status indicator

**T-1A.5: Python File Tabs**
Support opening Python files from the Workspace tree as editor tabs:
- CodeMirror 6 editor instance per tab (Python mode, same themes as notebook)
- File content loaded via REST API, saved on Ctrl+S
- No execution UI — files share the notebook's kernel via import
- Backend endpoint: GET/PUT /api/projects/{id}/files/{path}

**T-1A.6: MLflow Integration in Kernel Startup**
(Previously T-1.5) Extend KernelManagerService to inject MLflow environment variables:
- `MLFLOW_TRACKING_URI` pointing to `mlflow:5000`
- `MLFLOW_EXPERIMENT_NAME` set from project metadata
- Existing `LD_LIBRARY_PATH` injection for CUDA preserved
- Ensure `mlflow` is installable via EnvironmentManager

**T-1A.7: Explicit MLflow Verification**
(Previously T-1.6) Verify standard MLflow code works in notebook cells.

**T-1A.8: Experiments API**
(Previously T-1.9) Implement REST endpoints proxying to MLflow:
- GET /api/projects/{id}/experiments/runs
- GET /api/projects/{id}/experiments/runs/{run_id}
- GET /api/projects/{id}/experiments/runs/{run_id}/artifacts

**T-1A.9: Experiments Section in Workspace Tree**
Add an Experiments category to the Workspace tree:
- Shows runs for the current project with status icons
- Click a run to open a detail tab in the center pane
- Basic run info: status, start time, key metrics
- Updates via polling initially (live streaming in Phase 1B)

### 4.2 Exit Criteria

- The new 4-column layout (icon bar, sidebar, tabs, chat) is functional
- Existing Projects and Environments work in the new sidebar
- Notebook opens as a tab, Python files open as editor tabs
- MLflow/Airflow/MinIO open as iframe tabs
- A user can run MLflow code in a notebook and see the run in the Workspace tree
- No regressions in existing notebook functionality

---

## 5. Phase 1B: Data Versioning and Advanced Tracking

**Goal:** Add DVC data versioning, Run Manager, live metrics streaming, and comparison views.

**Rationale:** With the layout infrastructure in place and basic MLflow tracking working, Phase 1B adds the deeper integrations that make noted's experiment tracking superior to using MLflow UI directly.

### 5.1 Tasks

**T-1B.1: ProjectVersionControl Service** (previously T-1.1)
Implement the `ProjectVersionControl` abstraction layer as a new backend manager:
- Interface defining: init, add_file, commit, tag, checkout, get_versions, get_current_hash
- Implementation using git subprocess + DVC CLI
- Project-level locking for Git operations (extending the existing CollaborationManager's lock pattern)
- Integrated into the existing NotebookManager's project creation flow: new project = new Git repo + DVC init + MinIO remote config

Scope reference: F-DVC-01, F-DVC-02, F-DVC-09

**T-1B.2: Data Upload and Tracking Endpoint** (previously T-1.2)
Implement `POST /api/projects/{id}/data/upload`:
- Accepts multipart file upload
- Writes to `data/raw/` in the project directory
- Calls ProjectVersionControl to add, push, commit, and tag
- Returns version info (version number, hash, size)

Scope reference: F-DVC-03

**T-1B.3: Data Listing and Version History Endpoints** (previously T-1.3)
Implement:
- `GET /api/projects/{id}/data` - list all tracked files with current version
- `GET /api/projects/{id}/data/{path}/versions` - version history for a file
- `GET /api/projects/{id}/data/{path}/download` - pre-signed URL from MinIO

Scope reference: F-DVC-04, F-MINIO-04

**T-1B.4: Data Version Switching Endpoint** (previously T-1.4)
Implement `POST /api/projects/{id}/data/checkout`:
- Accepts a version tag or hash
- Calls ProjectVersionControl to checkout + DVC checkout
- Notifies connected clients via Socket.io (`data:version_created`)

Scope reference: F-DVC-05

**T-1B.5: Run Manager with Framework Autologging** (previously Auto-Instrumentation Engine)
MLflow experiment tracking is managed exclusively through the Run Manager. Users explicitly define which cells to track:
- Run Manager UI: define named runs, assign cells via individual toggle or "Select All" button
- On Execute Run: backend wraps the cell sequence with `mlflow.start_run()`/`mlflow.end_run()`
- Post-execution: detect ML frameworks (PyTorch, scikit-learn, TensorFlow, XGBoost, LightGBM) and activate autologging
- Tag runs with `instrumentation: experiments`
- Individual cell execution (outside Run Manager) has no MLflow overhead - clean separation of exploration vs experimentation

Scope reference: F-MLF-05

**T-1B.6: Live Metrics Streaming** (previously T-1.8)
Implement real-time metric forwarding:
- Backend polls MLflow API for active runs in the project's experiment (configurable interval, default 1s)
- When new metric steps are detected, emit `metric:update` via Socket.io (through CollaborationManager's room broadcasting)
- Include run_id, metric_name, step, value, and timestamp in the event payload
- Polling starts when a kernel executes a cell and stops when no active runs remain

Alternative approach (evaluate during implementation): intercept `mlflow.log_metric()` calls at the kernel level via a custom MLflow plugin or monkey-patch, which would eliminate polling latency.

Scope reference: F-MLF-06

**T-1B.7: Run Manager Dataset Selection** (previously DVC Hash Injection)
Users select DVC-tracked datasets per run definition in the Run Manager UI. On Execute Run, the backend resolves DVC hashes and auto-logs them to MLflow:
- Tag keys: `dvc.data_hash`, `dvc.data_file`
- Parameter key: `dvc_data_hash` (enables filtering/searching runs by data version in the experiment table)
- Value: resolved from `.dvc` file hashes via `DvcManager.status()` at execution time
- Dataset selection stored in notebook metadata (`metadata.mlflow_runs[id].datasets`)
- Frontend: checkboxes in Run Manager panel per DVC-tracked file, `getDvcFiles` callback via DVC status API
- Backend: `main.py` resolves hashes, passes to `execution_bridge.execute_run()`, `auto_instrumentation.get_run_start_code()` generates logging code
- Detailed implementation plan exists (9 steps, 7 files modified)

Status: Plan complete, implementation pending.

Scope reference: F-DVC-07

**T-1B.8: Storage Section in Workspace Tree**
MinIO bucket browser as a tree category in the Workspace Explorer:
- Shows buckets and objects in a navigable tree
- Click an object to view metadata or download

**T-1B.9: Data Section in Workspace Tree**
DVC-tracked files per project as a tree category:
- Shows tracked files with version badges
- Version history expandable per file
- Upload action (drag-and-drop or file picker) that calls the upload endpoint
- Version selector that triggers checkout

**T-1B.10: Git/DVC Terminal Escape Hatch**
When `ProjectVersionControl`, `GitManager`, or `DvcManager` operations fail with non-standard errors:
- Catch the error and classify it (merge conflict, lock contention, cache corruption, unknown)
- Display a toast notification with a clear error description and an **"Open Terminal"** action button
- The action opens the built-in xterm.js terminal pre-navigated to the project directory (`cd /path/to/project`)
- No attempt to build UI for merge conflict resolution, lock management, or other complex Git/DVC failure modes

See Architecture Principles document, P6: The Terminal Is an Escape Hatch.

**T-1B.11: Run Manager UI**
Implement the visual run definition and execution tool (design in `noted_mlflow.md` section 3.10):
- Run Manager panel (jsPanel-based, similar to PostItIndexPanel pattern)
- Run definitions stored in notebook metadata (`metadata.mlflow_runs`)
- Cell membership stored in cell metadata (`cell.metadata.mlflow_runs`)
- Cell badges showing run number with run color on right side of each cell
- Cell click interception when Run Manager has an active run (toggle membership)
- Execute Run: sequential cell execution wrapped in MLflow start/end injection via backend `execute_run()`
- Badge click to remove cell from a run without needing the panel open
- Runs button in notebook second bar
- "Select All" button to add all code cells to a run in one click

Scope reference: noted_mlflow.md Section 3.10

**T-1B.12: Run Comparison View** (previously T-1.13)
Opens as a center tab:
- Checkbox selection on runs (2-5 runs)
- Overlaid metric charts (shared axes, one color per run)
- Parameter diff table (highlight cells that differ)
- Data version column showing DVC hash per run

**T-1B.13: Artifact Browser** (previously T-1.14)
Within run detail tab:
- Tree view of artifacts from MLflow artifact store (MinIO)
- Image artifacts render inline (PNG, JPEG, SVG — plots, charts, confusion matrices)
- HTML artifacts render in a sandboxed iframe (Plotly interactive forecast plots)
- Text artifacts render in a code viewer
- YAML artifacts render as formatted, syntax-highlighted YAML (Hydra config snapshots)
- Model directories show model card with framework info (PyTorch `.pt2`, Prophet, sklearn)
- All artifacts show download link (pre-signed URL)

### 5.2 Exit Criteria

- A user can upload a dataset, see it versioned in the Workspace tree, switch between versions
- Auto-tracking works: metrics logged without explicit MLflow code
- Run Manager: user can define named cell groups, assign cells via click, execute a run that creates a single MLflow run
- Live metrics update in the Experiments detail tab within 2 seconds
- Run comparison opens as a center tab with overlaid charts and param diffs
- Every run has a `dvc.data_hash` tag and `dvc_data_hash` parameter
- Artifact browser renders images inline, HTML artifacts in iframe, and model cards
- MinIO buckets are browsable in the Workspace tree

---

## 6. Phase 2: Configuration and Orchestration

**Goal:** Users can manage Hydra configurations through the UI and submit pipeline runs to Airflow.

**Rationale:** Once users can track experiments (Phase 1), the natural next step is parameterizing them (Hydra) and running them at scale (Airflow). This phase transitions noted from an interactive tool to a production pipeline manager.

### 6.1 Backend Tasks

**T-2.1: Hydra Config Schema Endpoint**
Implement `GET /api/projects/{id}/config/schema`:
- Reads the project's `config/` directory structure
- Parses `config.yaml` defaults list to identify config groups
- For each config group directory, lists available options (YAML files)
- If Structured Configs (dataclasses) exist in `src/`, extracts field types and constraints
- Returns a JSON schema suitable for dynamic form generation

**T-2.2: Hydra Config Composition Endpoint**
Implement `POST /api/projects/{id}/config/compose`:
- Accepts a set of Hydra overrides (e.g., `{"model": "transformer", "model.n_heads": 8}`)
- Uses `hydra.compose()` to assemble the complete configuration
- Validates against Structured Configs if available
- Returns the composed config as YAML and a deterministic hash
- Returns validation errors if type constraints are violated

**T-2.3: Config Templates**
Implement:
- `GET /api/projects/{id}/config/templates` - list saved templates
- `POST /api/projects/{id}/config/templates` - save current config as named template
- Templates stored in `config/templates/{name}.yaml` within the project directory
- Templates committed to the backend Git repo via ProjectVersionControl

Scope reference: F-HYD-06

**T-2.4: Config Hash Injection into MLflow**
When a run starts with a Hydra config:
- Compute the config hash from the composed YAML
- Inject as MLflow run tag: `hydra.config_hash`
- Log the composed YAML as an MLflow artifact: `hydra_config.yaml`

Scope reference: F-HYD-05

**T-2.5: Airflow DAG Management**
Support both generated and user-authored DAGs:

*DAG Generator module:*
- Input: project metadata (ID, entry point path, environment info)
- Output: a valid Airflow DAG Python file written to `pipelines/dag_{project_id}.py`
- DAG structure:
  1. `pull_data` task: runs `dvc pull` in the project directory
  2. `validate_config` task: runs `hydra.compose()` with provided overrides and validates
  3. `train` task: executes `python src/train.py` with Hydra CLI overrides
  4. Tasks are connected: pull_data >> validate_config >> train
- The DAG file is parameterized: reads overrides from `dag_run.conf`

*User-authored DAG support:*
- Scan project's `dags/` and `pipelines/` directories for `.py` DAG files
- Sync all discovered DAG files to the Airflow DAGs directory (accessible by `noted-airflow-dag-processor`)
- Support multiple DAGs per project (e.g., separate ingestion, training, evaluation DAGs)
- DAG files editable in the center pane Python editor (T-1A.5)
- Backend watches for DAG file changes and re-syncs to Airflow

Scope reference: F-AIR-02

**T-2.6: Pipeline Trigger Endpoint**
Implement `POST /api/projects/{id}/pipelines/{dag_id}/trigger`:
- Lists available DAGs for the project via `GET /api/projects/{id}/pipelines`
- For generated DAGs: accepts Hydra config overrides, optional data version tag; validates config; ensures DAG file exists
- For user-authored parameterized DAGs: reads DAG `params` schema from Airflow API to render trigger form fields (text, date, dropdown - supports Airflow `Param` and `ParamsDict`)
- Calls Airflow API Server (`airflow-apiserver`): trigger DAG run with `conf` (for generated) or `params` (for user-authored) payload
- Returns the Airflow DAG run ID
- Emits `pipeline:task_status` via Socket.io with initial "queued" state

Scope reference: F-AIR-03

**T-2.7: Pipeline Status Polling and Streaming**
Implement a PipelineMonitor backend module:
- Polls Airflow API Server for active pipeline run task instances
- Detects state transitions and emits `pipeline:task_status` events via Socket.io (through CollaborationManager rooms)
- For running tasks, fetches logs via Airflow API and emits `pipeline:task_log` events
- Polling interval: 2 seconds for active runs, stops when run completes

Scope reference: F-AIR-04, F-AIR-05

**T-2.8: Pipeline History Endpoint**
Implement `GET /api/projects/{id}/pipelines/runs`:
- Lists all DAG runs for the project from Airflow API Server
- Enriches with: trigger time, duration, final status, config overrides used
- Includes correlation to MLflow runs (matched by config hash and timestamp)

Scope reference: F-AIR-07

**T-2.9: Sweep DAG Generation**
Extend the DAGGenerator for Hydra multirun sweeps:
- When sweep parameters are specified, generate a DAG with Airflow dynamic task mapping
- Each parameter combination becomes a mapped task instance of the `train` task
- The `pull_data` and `validate_config` tasks run once; `train` fans out
- Parallelism controlled by Airflow worker concurrency settings

Scope reference: F-AIR-06, F-HYD-07

**T-2.10: Pipeline Scheduling Endpoints**
Implement:
- `POST /api/projects/{id}/pipelines/schedule` - create or update schedule (cron or interval)
- `DELETE /api/projects/{id}/pipelines/schedule` - remove schedule
- These modify the DAG file's `schedule` parameter and update Airflow via API Server

Scope reference: F-AIR-08

### 6.2 Frontend Tasks

**T-2.11: Config Section in Workspace Tree**
Implement the Config section as a Workspace tree category with detail tabs in the center pane:
- Config tree shows config groups and available options from the schema endpoint
- Click a config group to open a detail tab with a dynamic form
- Type-appropriate input controls (number, text, select, boolean toggle)
- Validation feedback inline (red borders, error messages)
- "Compose" button that calls the composition endpoint and shows the full YAML preview
- Config hash displayed for reference
- Template selector dropdown and "Save as Template" button

**T-2.12: YAML Preview Panel**
Within the Config detail tab, a collapsible section showing:
- The composed YAML (read-only, syntax-highlighted)
- Diff view when comparing against a previous config or template

**T-2.13: Sweep Configuration UI**
Extension to the Config detail tab:
- "Sweep" toggle that switches a field from single-value to multi-value input
- Multi-value inputs accept comma-separated values or range syntax (start:stop:step)
- Combination count displayed (e.g., "24 configurations")
- "Submit Sweep" button that triggers pipeline with sweep parameters

**T-2.14: Pipeline Tab**
Implement a Pipeline view as a center pane tab that opens when a pipeline is triggered or selected from the Workspace tree:
- DAG list: shows all DAGs for the project (generated and user-authored) with trigger buttons
- DAG node graph visualization showing task names and dependencies
- Color-coded task nodes: grey (queued), blue (running), green (success), red (failed), orange (skipped — e.g., model-selective tasks using exit 99)
- Real-time updates from `pipeline:task_status` Socket.io events
- Parameterized trigger dialog: renders form fields from DAG `params` schema (date pickers, dropdowns, text inputs)
- Click a task node to expand and see its streaming logs
- Log output area that receives `pipeline:task_log` events

**T-2.15: Pipeline History View**
Within the Pipeline tab:
- List of past pipeline runs with status, duration, config summary
- Click a run to replay its node graph state
- Link to corresponding MLflow runs (opens in Experiments detail tab)

**T-2.16: Pipeline Status in Bottom Bar**
Add to the bottom status bar:
- Active pipeline indicator (running/idle)
- Last pipeline status (success/failed with timestamp)
- Click to jump to Pipeline tab

### 6.3 Implementation Plan and Effort Estimation

**Effort scale:** S (Small, 1-2h), M (Medium, 2-4h), L (Large, 4-8h)

**Two independent tracks** (Hydra and Airflow) can progress in parallel until T-2.9 (Sweep DAGs) which bridges them.

#### Priority Tier 1 - Must Have (Tutorial #2, Labs 3-4)

| Order | Task | Track | Effort | Deliverable | Depends on |
|-------|------|-------|--------|-------------|------------|
| 1 | T-2.1 | Hydra | **M** | `hydra_manager.py` + `hydra.py` router: walk `config/` dir, parse YAML groups, return schema JSON | - |
| 2 | T-2.2 | Hydra | **M** | `hydra_manager.py`: `compose()` using OmegaConf to resolve overrides into final YAML | T-2.1 |
| 3 | T-2.11 | Hydra | **L** | Config section in Explorer tree: groups as expandable nodes, override form (dropdowns + text), Compose button | T-2.1, T-2.2 |
| 4 | T-2.5 | Airflow | **M** | `airflow_manager.py` + `airflow.py` router: discover DAGs via Airflow REST API, filter by project | - |
| 5 | T-2.6 | Airflow | **M** | `airflow_manager.py`: `trigger_dag()` via Airflow REST, pass conf/params. Read DAG params schema for form rendering | T-2.5 |
| 6 | T-2.14 | Airflow | **L** | Pipeline section in Explorer tree: DAG list, trigger with param form, task status grid, log output | T-2.5, T-2.6 |
| 7 | T-2.4 | Hydra | **S** | Hash composed YAML (SHA-256), inject as `mlflow.log_param("hydra_config_hash")` + tag + artifact | T-2.2 |

#### Priority Tier 2 - Should Have (Tutorial #2 polish)

| Order | Task | Track | Effort | Deliverable | Depends on |
|-------|------|-------|--------|-------------|------------|
| 8 | T-2.12 | Hydra | **S** | YAML preview in config detail panel: syntax-highlighted `<pre>` of composed output | T-2.2, T-2.11 |
| 9 | T-2.7 | Airflow | **M** | `PipelineMonitor`: poll Airflow task instances, emit `pipeline:task_update` Socket.IO events | T-2.6 |
| 10 | T-2.3 | Hydra | **S** | Templates CRUD: save overrides as named JSON in `.noted/config_templates/`, dropdown in config UI | T-2.2 |
| 11 | T-2.8 | Airflow | **S** | Pipeline history endpoint: list DAG runs with status, duration, MLflow run link | T-2.7 |
| 12 | T-2.15 | Airflow | **M** | Pipeline history view: past runs table, status badges, duration, clickable MLflow link | T-2.8 |

#### Priority Tier 3 - Nice to Have (Final Delivery, Labs 5-6)

| Order | Task | Track | Effort | Deliverable | Depends on |
|-------|------|-------|--------|-------------|------------|
| 13 | T-2.16 | Airflow | **S** | Info bar: pipeline icon + Running/Idle label from PipelineMonitor events | T-2.7 |
| 14 | T-2.9 | Both | **L** | Sweep DAG generation: multi-value Hydra overrides -> DAG with dynamic task mapping | T-2.2, T-2.5 |
| 15 | T-2.10 | Airflow | **S** | Schedule CRUD: wrap Airflow timetable API, cron input in DAG detail | T-2.5 |
| 16 | T-2.13 | Both | **M** | Sweep UI: multi-value inputs, grid preview, Submit Sweep button | T-2.9, T-2.11 |

#### Effort Summary

| Track | Tasks | Effort |
|-------|-------|--------|
| Hydra | T-2.1, T-2.2, T-2.3, T-2.4, T-2.11, T-2.12 | 2S + 2M + 1L |
| Airflow | T-2.5, T-2.6, T-2.7, T-2.8, T-2.10, T-2.14, T-2.15, T-2.16 | 3S + 3M + 1L |
| Both | T-2.9, T-2.13 | 1M + 1L |

#### Dependency Graph

```
Hydra track:     T-2.1 -> T-2.2 -> T-2.3, T-2.4, T-2.11, T-2.12
                                 -> T-2.9 -> T-2.13

Airflow track:   T-2.5 -> T-2.6 -> T-2.7 -> T-2.14, T-2.16
                                         -> T-2.8 -> T-2.15
                        -> T-2.10
```

### 6.4 Exit Criteria

- A user can open the Config detail tab, select a model architecture, adjust hyperparameters, and see the composed YAML
- Config validation catches type errors before execution
- A user can click "Submit Pipeline" and see a live node graph of the Airflow execution in noted
- Task logs stream into the UI in real-time
- A sweep of 10 configurations runs with correct parallelism
- The pipeline run creates MLflow runs with correct config hash tags
- Pipeline history shows past runs with links to their experiment results

---

## 7. Phase 3: Snapshots, Registry, and Serving

**Goal:** Users can capture reproducible snapshots of their best experiments, promote models to production, and test predictions - all from within noted.

**Rationale:** After experiments are tracked (Phase 1) and parameterized/orchestrated (Phase 2), the final lifecycle steps are: (1) selecting the best result across experiments, (2) capturing it as an immutable reproducible record, (3) promoting the model for serving, and (4) demonstrating predictions. This phase completes the data-to-deployment flow.

### 7.0 Core Concept: Experiment Snapshots

An **Experiment** contains multiple training **Runs** with different hyperparameters. The user selects the best Run and marks it as the **Snapshot** - an immutable record of the entire state that produced that result. Across experiments, the user compares Snapshots to select the **Champion** model.

**Convention:** One Snapshot per Experiment. Setting a new Snapshot in the same Experiment replaces the previous one.

**What a Snapshot captures:**
- Git commit SHA (code, notebooks, DAGs, configs)
- Git branch created: `snapshot/{experiment_name}_{version}` (e.g., `snapshot/jena_gru_v2_001`)
- DVC file hashes (all tracked data versions)
- Hydra config hash + resolved config YAML (as MLflow artifact)
- MLflow run ID (metrics, params, model artifact)
- Environment spec (Python version + pip freeze, as MLflow artifact)
- User annotation (name, description)

**Snapshot flow:**
1. User trains multiple runs within an experiment
2. Compares runs, identifies the best one
3. Clicks "Snapshot" on that run
4. Backend: ensures git is clean (auto-commits if dirty), creates snapshot branch, tags the MLflow run with `noted.snapshot=true` + all lineage metadata, pushes DVC data, logs env freeze as artifact
5. Only one run per experiment can be a snapshot (setting it removes the tag from any previous snapshot in the same experiment)

**Restore Snapshot** (one click):
1. `git checkout snapshot/{experiment}_{version}`
2. `dvc checkout` (restores data files to that version)
3. Explorer tree refreshes (code, configs, notebooks from that state)
4. Kernel restarts with matching environment
5. Status bar shows: "Snapshot: {experiment}_{version}"

**New Experiment from Snapshot** (one click):
1. Restores the snapshot (same as above)
2. Creates a new git branch: `experiment/{new_experiment_name}` from the snapshot
3. Creates a new MLflow Experiment
4. User is on a fresh branch, ready to modify and run
5. Original snapshot is untouched

### 7.1 Backend Tasks

**T-3.0: Snapshot Manager**
Implement `snapshot_manager.py` with:
- `create_snapshot(project_id, experiment_id, run_id, name, description)`:
  - Validates run exists and belongs to the experiment
  - Auto-commits dirty git state with message `[noted] snapshot: {name}`
  - Creates git branch `snapshot/{experiment_name}_{version}` (sequential version per experiment)
  - Tags MLflow run: `noted.snapshot=true`, `noted.snapshot_branch`, `noted.snapshot_version`, `noted.git_commit`, `noted.dvc_hashes` (JSON of all DVC file hashes), `noted.env_hash`
  - Logs artifacts: resolved Hydra config YAML, `pip freeze` output
  - Runs `dvc push` to ensure data is in remote
  - Removes `noted.snapshot=true` from any previous snapshot run in the same experiment
  - Returns to original branch after creating snapshot branch
- `restore_snapshot(project_id, experiment_id)`:
  - Finds the snapshot run, reads `noted.snapshot_branch`
  - `git checkout {snapshot_branch}`
  - `dvc checkout`
  - Returns the restored state info
- `fork_experiment(project_id, source_experiment_id, new_experiment_name)`:
  - Restores the source snapshot
  - Creates new git branch `experiment/{new_experiment_name}` from snapshot
  - Creates new MLflow Experiment
  - Returns new experiment info
- `list_snapshots(project_id)`:
  - Scans all experiments for runs tagged `noted.snapshot=true`
  - Returns list with experiment name, run metrics, snapshot version, branch, timestamp

**T-3.0b: Run Leaderboard Endpoint**
Implement `GET /api/mlflow/experiments/{id}/leaderboard`:
- Returns all runs for an experiment sorted by a specified metric
- Columns: run name, all metrics, all params, snapshot status, data hash, config hash
- Supports sort_by, sort_order, limit parameters
- Used by the multi-run comparison table in the frontend

**T-3.1: Model Registration Endpoint**
Implement `POST /api/projects/{id}/models/register`:
- Accepts: run_id, artifact_path (within the run), model_name
- Calls MLflow Registry API to create a registered model (if new) and a new model version
- Tags the version with: source run_id, dvc.data_hash, hydra.config_hash, snapshot_branch (if the run is a snapshot)
- Returns version info

**T-3.2: Model Listing and Version Endpoints**
Implement:
- `GET /api/projects/{id}/models` - list registered models for the project
- `GET /api/projects/{id}/models/{name}/versions` - list versions with aliases, metrics, creation date

**T-3.3: Alias Management Endpoint**
Implement `PUT /api/projects/{id}/models/{name}/versions/{v}/alias`:
- Accepts: alias name (e.g., "champion", "staging")
- Calls MLflow Registry API to set the alias
- Emits `model:alias_changed` via Socket.io
- If alias is "@champion", notifies the serving container

**T-3.4: Model Lineage Endpoint**
Implement `GET /api/projects/{id}/models/{name}/versions/{v}/lineage`:
- Retrieves the version's source run from MLflow
- From the run, extracts: dvc.data_hash, hydra.config_hash, pipeline run ID (if applicable), snapshot branch
- Resolves each hash to its readable form
- Returns the complete lineage chain: Data (DVC) -> Config (Hydra) -> Code (git commit) -> Run (MLflow) -> Model (Registry)

**T-3.5: Model Comparison Endpoint**
Implement `POST /api/projects/{id}/models/compare`:
- Accepts two version references
- Returns metric diff, config diff, data version diff, architecture diff
- Reuses the run comparison logic from Phase 1

**T-3.5b: Experiment Report Generation**
Implement `GET /api/mlflow/experiments/{id}/report`:
- Generates a standalone experiment comparison report (PDF or Word via doco)
- Contains: experiment summary, ranked metrics table, parameter comparison, metric convergence charts for top N runs, config and data version info per run
- No notebook involvement - pure experiment data

**T-3.6: Model Serving Container**
Build the model-server Docker service (the only new container in the entire plan):
- FastAPI application with Uvicorn
- On startup: loads model from MLflow Registry using `@champion` alias
- `/predict` endpoint: accepts JSON, validates against model signature (Pydantic), runs inference, returns JSON
- `/health` endpoint: returns loaded model info, version, load time
- `/schema` endpoint: returns the Pydantic input/output schema as JSON Schema

**T-3.7: Hot Model Reload**
Implement model reloading in the serving container:
- Background async task checks MLflow Registry for alias changes (poll interval: 10 seconds)
- When a new version is detected for the `@champion` alias: load new model, atomic swap, release old model
- During reload, old model continues serving requests
- Emit `serving:model_loaded` via Socket.io (through noted backend)

**T-3.8: Serving Proxy Endpoints**
Implement in noted backend (ServingProxy module):
- `POST /api/projects/{id}/serving/predict` - proxies to the project's model-server `/predict`
- `GET /api/projects/{id}/serving/status` - proxies to `/health`
- `GET /api/projects/{id}/serving/schema` - proxies to `/schema`

**T-3.9: On-Demand Serving Container Management**
Implement lifecycle management for serving containers:
- Containers start when a model is first promoted to `@champion` in a project
- Containers stop after a configurable inactivity timeout (default: 30 minutes)
- noted backend tracks serving container state per project
- Docker API used to start/stop containers programmatically

### 7.2 Frontend Tasks

**T-3.10: Snapshot UI**
- "Snapshot" button on run detail page (available for any completed run)
- Snapshot confirmation modal showing what will be captured: git status, DVC files, config hash, run metrics
- Name and description input
- Warning if git has uncommitted changes (offer auto-commit)
- Snapshot badge (star icon) on snapshot runs in the Experiments tree
- "Snapshots" view: list all snapshots across experiments with metrics, sortable, filterable

**T-3.10b: Restore and Fork UI**
- "Restore Snapshot" button on snapshot runs and in the Snapshots view
- Confirmation modal: "This will switch your workspace to snapshot {name}. Uncommitted changes will be stashed."
- Loading overlay during restore (git checkout + dvc checkout)
- Status bar indicator showing current snapshot state
- "New Experiment from Snapshot" button - prompts for new experiment name, then restores + forks
- After fork, Explorer tree and Experiments section update to show the new experiment

**T-3.10c: Run Leaderboard**
- Multi-run comparison table in experiment detail page
- All runs shown in a sortable, filterable table
- Columns: run name, date, all metrics (sortable), all params, snapshot badge, data hash, config hash
- Click column header to sort (ascending/descending)
- Highlight row for best metric value
- Export table as CSV
- "Compare selected" button for 2+ checked rows

**T-3.11: Models Section in Workspace Tree**
Implement a Models category in the Workspace tree with detail tabs in the center pane:
- Tree shows registered models with version count as child nodes
- Click a model version to open a detail tab: version number, alias badge, creation date, key metric
- Alias management: dropdown to assign @champion, @staging, @archived
- "Register Model" action accessible from run detail view and snapshot view
- Real-time updates from `model:registered` and `model:alias_changed` events

**T-3.12: Model Lineage View**
Within model version detail tab:
- Visual lineage chain: Data (version + hash) -> Config (YAML preview) -> Code (git commit) -> Run (metrics summary) -> Model (version + alias)
- Each node in the chain is clickable, navigating to the corresponding detail tab
- If trained via pipeline, includes the pipeline run link
- If from a snapshot, shows snapshot branch name with "Restore" link

**T-3.13: Model Comparison View**
Select two versions via checkbox, side-by-side comparison of metrics, config, data version, architecture.

**T-3.14: Try It Tab**
Implement the Serving / Try It view as a center pane tab that opens from the Models section in the Workspace tree:
- Shows serving status: loaded model name, version, health
- Dynamic input form generated from the `/schema` endpoint
- "Predict" button sends request via the serving proxy
- Response displayed as formatted JSON
- Request/response history (in-memory, session-scoped)
- Inactive state when no champion model is set or serving container is stopped

**T-3.15: Serving Status in Bottom Bar**
Add to the bottom status bar:
- Serving indicator: active (green) / inactive (grey) / loading (yellow)
- Current champion model name and version

**T-3.16: Experiment Report Export**
- "Generate Report" button on experiment detail page
- Options: PDF or Word format
- Report includes: experiment summary, ranked runs table, metric charts for top N, parameter comparison, snapshot info
- Generated via doco integration (same pipeline as notebook export)

### 7.3 Exit Criteria

- A user can create a snapshot of their best run with one click
- A user can restore any snapshot and the entire workspace matches that state (code, data, config)
- A user can fork a new experiment from any snapshot
- The run leaderboard shows all runs sortable by any metric with snapshot badges
- A user can register a model from a completed run or snapshot
- A user can assign @champion alias and see the serving container load the model
- A user can send a prediction request from the Try It tab and see the result
- Model lineage displays the complete chain from data version through config to model
- Hot reload works: promoting a new champion updates the serving container without downtime
- Experiment reports can be exported as standalone documents

---

## 8. Phase 4: Integration and Polish

**Goal:** Close the integration gaps, add collaboration features, and deliver the end-to-end experience described in the Vision document.

**Rationale:** Phases 1-3 deliver the individual capabilities. Phase 4 connects them into a seamless workflow and adds the collaborative layer that makes noted a team tool.

### 8.1 Backend Tasks

**T-4.1: Activity Feed Service**
Implement an ActivityFeed backend module:
- All significant actions (data upload, run start/end, model registration, alias change, pipeline trigger) are recorded
- Storage: append-only table in the `noted` database (PostgreSQL)
- `GET /api/projects/{id}/activity` endpoint returns recent events
- `activity:event` Socket.io events emitted for real-time feed (via CollaborationManager rooms)

**T-4.2: Cross-Service Event Correlation**
Implement logic to link events across services:
- When an Airflow pipeline run completes, find the MLflow runs created during that pipeline run (match by time window and project)
- Attach pipeline_run_id as a tag on those MLflow runs
- When viewing a pipeline run, show links to its MLflow runs
- When viewing an MLflow run, show whether it was pipeline-triggered

**T-4.3: Processed Data Auto-Tracking**
Implement detection of output files from cell execution:
- After cell execution (extending ExecutionBridge), compare `data/processed/` directory state before and after
- If new or modified files detected, prompt the user (via Socket.io) to version them
- If user accepts, run the DVC add/push/commit cycle via ProjectVersionControl
- Track the derivation relationship: processed file version derived from current raw data version

**T-4.4: GenAI Trace Viewer Backend**
Implement trace retrieval for LLM projects:
- `GET /api/projects/{id}/experiments/runs/{run_id}/traces` - retrieves MLflow 3.x traces
- Returns structured trace data: steps, latencies, token counts, retrieval context

**T-4.5: Storage Usage Endpoint**
Implement `GET /api/projects/{id}/storage`:
- Queries MinIO Admin API for bucket/prefix size
- Returns: total bytes, object count, breakdown by category (data, artifacts, models)

**T-4.6: End-to-End Integration Tests**
Implement automated tests that verify the full workflow:
- Create project -> upload data -> configure model -> run training (explicit + auto) -> compare runs -> trigger pipeline -> register model -> promote to champion -> predict
- Scripted test, not user-facing, but critical for validating the integration

### 8.2 Frontend Tasks

**T-4.7: Activity Feed Panel (Right Sidebar)**
Implement the Activity panel (vanilla ES6 module):
- Chronological list of recent events with user name, action description, timestamp
- Click an event to navigate to the relevant detail tab
- Real-time updates from `activity:event` events
- Filter by event type (data, experiment, pipeline, model)

**T-4.8: Cross-Panel Navigation**
Implement contextual links between detail tabs:
- From a run: link to its data version (opens Data section at that version)
- From a run: link to its config (opens Config detail tab with those values)
- From a model version: link to its source run (opens run detail tab)
- From a pipeline run: link to its MLflow runs (opens Experiments, filtered)
- From an activity event: link to the relevant entity

**T-4.9: GenAI Trace Visualization**
Within run detail tab (for LLM project runs):
- Waterfall chart showing trace steps with latency
- Expandable steps showing input/output per step
- Token count and cost summary

**T-4.10: Storage Usage Display**
In the bottom status bar and project settings:
- Total storage used
- Breakdown visualization (data vs artifacts vs models)

**T-4.11: Onboarding and Empty States**
For each Workspace tree section and detail tab, implement meaningful empty states:
- Data section empty: "Upload your first dataset to get started"
- Experiments section empty: "Run a cell with MLflow tracking to see results here"
- Config section empty: "Add YAML files to config/ to define your experiment parameters"
- Pipeline tab empty: "Create a train.py entry point in src/ to enable pipeline execution"
- Models section empty: "Register a model from a completed run to manage versions"
- Serving tab empty: "Promote a model to @champion to enable predictions"

Each empty state guides the user to the next action, implementing the progressive complexity principle.

**T-4.12: UI Performance Optimization**
- Implement virtual scrolling for long run lists (100+ runs)
- Optimize Socket.io event handling to batch UI updates (debounce metric updates at 500ms)
- Implement client-side caching with TTL for panel data
- Lazy-load chart libraries only when comparison view is opened

**T-4.13: Mount/Project Unification**
Merge Projects and Mounts into a single "Mounts" section in the Explorer:
- Each mount can contain none, one, or several projects
- Remove the separate Projects section
- Project creation becomes "create project within mount"
- Affects project discovery, file paths, kernel association, git/DVC scoping, notebook discovery
- Simplifies the Explorer from two sections to one

**T-4.X: Knowledge Graph Service (replacing 3D DAG Visualization)**
Separate container (Alpine + Python, port 5523) providing a navigable 3D graph of all noted entities:
- **Entities**: projects, notebooks, experiments, runs, snapshots, models, model versions, data files, data versions, configs, DAGs, tasks, environments, tags
- **Relationships**: contains, produces, belongs_to, uses_data, uses_config, executed_by, snapshot_of, version_of, tagged_with, and more
- **Perspective views**: Lineage (data -> config -> run -> model), Performance (runs clustered by experiment, colored by metric), Versioning (timeline), Pipeline (DAG task structure), Project Overview (radial), Tag-Based (clustered by tag)
- **Search**: global search across all entity types by name, property, tag, metric value, date
- **Tags as taxonomy**: key-value tags on any entity, auto-generated tags from DVC/Hydra/Airflow, tag-based navigation and filtering
- **Backend**: GraphBuilder scans MLflow, DVC, Hydra, Airflow, file system; REST API for graph, neighborhood, search, views, tags; cached with event-driven invalidation
- **Frontend**: 3D renderer with force-directed layout, entity-type node shapes, semantic zoom, animated view transitions, bidirectional Explorer integration
- Replaces the previous DagVisualizer3D.js + Three.js vendor files (to be removed)
- See `documents/noted_knowledge_graph.md` for full design specification

**T-4.Y: Automated Test Suite** - DONE
All 31 manual test procedures automated in a dedicated `noted-test` Docker container. **128 tests, 100% pass rate.**
- **Kernel tests** (15): Socket.IO cell execution, MLflow run creation + model registration (v1/v2), Hydra config injection with overrides, terminal lifecycle, metrics:update events. Uses `python-socketio[asyncio_client]` with session-scoped event loop.
- **API tests** (92): REST endpoint coverage for setup, notebooks, git, GitHub, DVC, Hydra, pipelines, config hash, config templates, snapshots, leaderboard, registry, lineage, model comparison, serving, reports, knowledge graph, pipeline actions, nice-to-haves.
- **E2E tests** (21): Playwright headless Chromium for Explorer tree sections, pipeline health dots, DAG visualization, Hydra config selector, leaderboard filter, notebook second bar, export-as-task button, app structure.
- **Infrastructure**: `noted-test` container (Python 3.12-slim + Playwright + Chromium), self-contained `noted-testing` project, `_test_` naming convention, two-phase `run-all.sh` host script (kernel first to seed MLflow data, noted restart, then API + E2E).
- **Test project**: `noted-testing` with scaffolded Hydra config (config.yaml + model groups), CSV data, notebook, DAG, training script. Airflow DAG discovery wait in scaffold. File cleanup on teardown, MLflow data preserved across phases.

**T-4.Z: Merge Projects into Mounts**
Unify Projects and Mounts into a single "Projects" section:
- Each mount can contain zero, one, or multiple projects
- Project creation becomes "create project within mount"
- Affects project discovery, file paths, kernel association, git/DVC scoping, notebook discovery
- Simplifies the Explorer from two sections to one

### 8.4 Requirements Gap Recovery

**Must-Have (highest priority):**

**T-4.R1: Hydra Config Selector in Notebook Bar** (Req #86)
- Add a dropdown in the notebook second bar to select the active Hydra config profile
- Dropdown lists config groups with their options (e.g., model: gru/lstm/linear)
- Selection stored in notebook metadata

**T-4.R2: Hydra Config Injection into Kernel** (Req #87)
- When a notebook cell executes, inject the selected Hydra config into the kernel environment
- Pass resolved config as environment variable or Python object accessible via `from hydra import compose`
- Back-off: skip if cell contains explicit Hydra imports

**T-4.R3: New DAG from Template** (Req #119)
- Right-click in DAGs section or project dags/ folder -> "New DAG from Template"
- Template options: blank, single-task, data pipeline, training pipeline
- Generates a valid Python DAG file with standard Airflow decorators
- Opens the file in the editor after creation

**T-4.R4: Active Run Indicator in Notebook Bar** (Req #31)
- Show run name, experiment name, and live status in the notebook second bar when an MLflow run is active
- Green dot while running, disappears when run ends
- Click navigates to the run in Experiments tree

**Should-Have (medium priority) - ALL DONE:**

**T-4.R5: Config as CLI Overrides** (Req #88) - **DONE**
- Cells with `@hydra.main` or Hydra imports get `sys.argv` set with flattened config overrides
- Resolves config via HydraManager, flattens to dot-notation `key=value` pairs

**T-4.R6: Config Search in MLflow** (Req #94) - **DONE**
- Filter bar above leaderboard table with debounced input (300ms)
- Supports `=`, `!=`, `>`, `>=`, `<`, `<=` operators on params and metrics
- Multiple filters separated by commas: `model_type=GRU, lr>0.001`

**T-4.R7: Config Template for Pipeline Runs** (Req #117) - **DONE**
- "Load Last Run Config" button in trigger panel
- Fetches last 5 runs, finds last successful, pre-fills parameter inputs

**T-4.R8: "Run as Pipeline" from Notebook** (Req #135) - **DONE**
- Rocket icon button in notebook second bar (hidden when no DAGs)
- Auto-discovers project DAGs by tag match, triggers with current Hydra config
- Multi-DAG selection when multiple DAGs exist for the project

**T-4.R9: Copy Log Action** (Req #149) - **DONE**
- "Copy Log" button in task log action bar, disabled until log loads
- Clipboard write with "Copied" feedback for 1.5s

**T-4.R10: Retry Failed Task** (Req #150) - **DONE**
- "Retry Task" button shown for failed/upstream_failed tasks in task log viewer
- Calls `POST /dags/{id}/clearTaskInstances` with task_ids + dag_run_id
- Backend endpoint + AirflowManager.clear_task_instance()

**Nice-to-Have - ALL DONE:**

**T-4.R11: DVC Per-File Sync Icons** (Req #5) - **DONE**
- Green cloud = pushed, orange cloud-up = not pushed. Backend `dvc status --cloud` endpoint.

**T-4.R12: Post-Run Summary Toast** (Req #32) - **DONE**
- Toast shows run name + last metric values (up to 5, pipe-separated)

**T-4.R13: Pinned Metrics in Experiment Table** (Req #37) - **DONE**
- Columns button with checkbox dropdown for metrics + params

**T-4.R14: Epoch Progress Bar** (Req #40) - **DONE**
- Progress bar in Live Metrics panel. Shows "Epoch X / Y" when total_epochs logged.

**T-4.R16: Predict Cell Template** (Req #64) - **DONE**
- "Insert Predict Cell" button on model version detail page

**T-4.R17: APIs Section in Workspace** (Req #67) - **DONE**
- APIs section in Explorer tree with serving endpoint health/model info

**T-4.R18: Bulk Run Management** (Req #68-71) - **DONE**
- Multi-select list + "Delete Selected" on experiment detail page

**T-4.R19: Promote Best Config** (Req #102) - **DONE**
- "Promote Best" button in leaderboard saves best run's params as Hydra template

**T-4.R20: Config Inheritance View** (Req #103-107) - **DONE**
- Source file annotations in compose panel (key <- file)

**T-4.R21: Dynamic Task Generation Display** (Req #125) - **DONE**
- Mapped tasks shown with [index] suffix in task tree

**T-4.R22: Notebook-to-DAG Conversion** (Req #128) - **DONE**
- "Export as Pipeline Task" rocket button on code cells copies @task function

**T-4.R23: DAG Validation** (Req #129) - **DONE**
- "Validate" button on DAG detail checks imports, syntax, common pitfalls

**T-4.R24: Jump to Error in Logs** (Req #148) - **DONE**
- Error lines highlighted dark red, auto-scroll to first error

**T-4.R25: Visual Cron Builder** (Req #155) - **DONE**
- Preset cron buttons (@hourly, @daily, @weekly, Every 6h, Every 12h, Weekdays 9am)

**T-4.R26: Data-Aware Pipeline Triggering** (Req #160-163) - **DONE**
- DVC tracked files shown in trigger panel for the DAG's project

**T-4.R27: Template Runs** (Req #167-168) - **DONE**
- Covered by Hydra templates + "Load Last Run Config" + "Promote Best"

**T-4.R28: Pipeline Health Indicators** (Req #171-172) - **DONE**
- Colored health dot on DAGs root (green/red/blue)

**T-4.Y: Automated Test Suite** - **DONE**
- Separate test container (`noted-test`): Python 3.12-slim + pytest + httpx + playwright + python-socketio
- 3 test suites: kernel execution (Socket.IO), REST API, Playwright E2E
- 129 tests covering all 31 testing documents, 0 failures, 0 skips - 100% pass rate
- `noted-testing` project used exclusively - all artifacts created and cleaned up per session
- Two-phase pipeline: kernel tests first (creates MLflow runs/models), restart noted, then API+E2E
- Strengthened assertions: verify response values and behavior, not just status codes
- Snapshot test verifies full reproducibility chain: git branch + commit, DVC hashes, Hydra config hash, MLflow metadata, version numbering, branch existence in git
- E2E tests use real tree navigation (expand, scroll, click) simulating actual user interaction
- Found and fixed 1 backend bug: Hydra config injection ignored list-style overrides
- `run-all.sh` for CI integration, JUnit XML output support

**T-4.RV: Run Python with Venv** - **DONE**
- Right-click `.py` file in Explorer > "Run with venv" opens a terminal and auto-executes with active venv's Python
- Green play button in file editor second bar (alongside Save and File Details)
- Uses active venv (`/app/venvs/{name}/bin/python`) or falls back to system `python3`
- Reuses existing ProjectTerminal infrastructure with new `initialCommand`, `panelIcon`, `panelIconColor` options
- Terminal panel shows `filename.py (venv_name)` as title
- User can Ctrl+C to kill long-running processes (web servers, training scripts)

### 8.5 AI Assistant Tasks

**T-4.AI1: LLM Backend Infrastructure** - **DONE**
Dual-mode LLM backend supporting local inference (Ollama via agent_server) and cloud API (Anthropic Claude):
- `LLMManager` with httpx client for local models, `AnthropicLLMManager` for Claude API
- `LLMRouter` dispatches to the correct backend based on selected model
- SSE streaming from `/api/llm/chat`, health check at `/api/llm/health`
- Model selector UI with auth gate for cloud models (API key stored server-side)
- Real token usage tracking from Anthropic API responses
Scope reference: F-AI-01, F-AI-02, F-AI-03, F-AI-09

**T-4.AI2: Context Assembly and Skills** - **DONE**
Context-enriched chat with skills system:
- `llm_context.py` assembles notebook cells (in-memory), selected cell, kernel status, MLflow run, Hydra config
- `llm_skills.py` loads 36+ skill files from `data/skills/`, builds registry, handles static injection (priority 1) and dynamic loading (priority 2-3)
- `get_skill` tool registered in `llm_tools.py`
- Background skills (coding-conventions, auto-instrumentation) hidden from badge UI
- Context re-assembled on every turn from live workspace state
Scope reference: F-AI-06, F-AI-07

**T-4.AI3: Tool System** - **DONE**
20+ tools for reading and writing workspace state:
- Read tools: MLflow (get_run_details, get_experiment_runs, compare_runs), Airflow (get_dag_status, get_task_log, get_dag_runs), DVC (get_dvc_files, get_dvc_history), Files (get_file_contents), Hydra (get_resolved_config), Knowledge Graph (search_knowledge_graph), Navigation (scroll_to_cell)
- Write tools: update_cell, insert_cell with pending_action confirmation flow
- Stream-first tool loop (up to 6 rounds) with exhausted-loop fallback
- Tool badges in UI (orange pills with hover for arguments)
- ThinkingParser filters `<tool_call>` blocks from visible output
Scope reference: F-AI-04, F-AI-05, F-AI-10

**T-4.AI4: Chat Panel and Memory** - **DONE**
Full-featured chat panel with conversation persistence:
- Token-by-token streaming with ThinkingParser for extended thinking blocks
- Project-scoped memory with file persistence, auto-compaction via LLM summarization
- Clear chat button (frontend + backend), copy code blocks, auto-scroll, error cards
- Voice `<voice>` tag support (strips from display, routes to TTS)
- Chat history restore on page reload
- Buffered follow-up responses prevent JSON leaking to chat UI
- Haiku compatibility: empty assistant message placeholder
- Health LED via HTTP + Socket.IO heartbeat
- Undockable to floating jsPanel
Scope reference: F-AI-01, F-AI-08, F-AI-10

**T-4.AI5: MCP Server Integration** - **DONE**
Model Context Protocol server enabling external AI client access:
- MCP server at `/mcp/` using official `mcp` SDK v1.27.0 (low-level Server API)
- Streamable HTTP transport (single endpoint, stateless, JSON response mode)
- 25 tools exposed via `tools/list` and callable via `tools/call`
- Rate limiting: in-memory token bucket, tiered (read 30/min, write 10/min, workflow 3/min)
- Error taxonomy: -32001 (auth), -32002 (execution), -32004 (resource unavailable), -32005 (rate limited), -32006 (validation)
- Feature toggle via `NOTED_MCP_ENABLED` env var (default: true)
- Failure isolation: one-directional dependency, try/except in main.py, noted runs normally if MCP fails
- nginx proxy with streaming headers (`X-Accel-Buffering: no`)
- Write-tier tools rejected with -32001 for external clients (approval middleware)
- MCP tool schemas (`backend/app/mcp/tools.py`) are the single source of truth for all tool definitions

**T-4.AI6: Native Tool Calling** - **DONE**
Migration from text-based XML `<tool_call>` to native tool calling for both LLM backends:
- Anthropic: `tools` array in Messages API, `tool_use` content blocks in stream, `tool_result` feedback with `tool_use_id`
- Gemma 4: tools passed via OpenAI-compatible `tools` parameter, model generates native `<|tool_call>call:name{args}<tool_call|>` tokens
- Custom Gemma parser (`gemma_tool_parser.py`): handles `<|"|>` string delimiters, arrays, nested quotes, multi-line content
- Stop token (`<tool_call|>`) prevents Gemma from hallucinating tool results
- `tool_formats.py`: converts MCP schemas to Anthropic and OpenAI formats automatically
- `TOOL_DESCRIPTIONS` removed from Anthropic system prompt; agent_server system prompt cleaned (tool definitions removed, behavioral rules kept)
- Tool result feedback: Anthropic uses `tool_result` content blocks, Gemma uses OpenAI `role: "tool"` messages
- 1-based cell numbering at LLM boundary (all tools accept/return 1-based cell numbers, converted to 0-based internally)

**T-4.AI7: Dynamic Context Router** - **DONE**
Per-turn tool schema selection to reduce token cost:
- 9 domains defined: MLflow, Airflow, DVC, Files, Hydra, Notebook, Linting, Knowledge, Skills, Web
- Keyword-based domain classifier with regex patterns per domain
- Context boosting: notebook open adds notebook domain, file open adds files domain
- Default fallback: notebook + files + mlflow when no keywords match
- Retry: if LLM calls an out-of-scope tool, expands with that tool's domain and retries transparently
- Claude: filtered (typically 5-8 tools per turn). Gemma: all tools (small models need maximum visibility)

**T-4.AI8: Gemma 4 Thinking Mode** - **DONE**
Extended thinking support for Gemma 4 local LLM:
- `<|think|>` token prepended to system prompt when thinking is enabled
- Gemma output `<|channel>thought\n...<channel|>` translated to `<think>...</think>` for frontend
- `strip_gemma_tokens()` removes native tokens, hallucinated blocks, EOS tokens from display
- Thinking tokens excluded from conversation history (per Gemma 4 spec)

**T-4.AI9: Web Content Fetch (Camoufox)** - **DONE**
`fetch_url` tool for retrieving and analyzing web content:
- Camoufox anti-detect Firefox browser with C++ level TLS fingerprint spoofing
- Singleton pattern (`web_fetch_manager.py`): browser launches once, stays warm for subsequent requests
- Session auto-refresh every 50 requests or 1 hour (prevents memory leaks and tracking)
- HTML stripped to readable text before returning to LLM
- Falls back to httpx when Camoufox is not available
- `web-fetch` skill guides the model to analyze content rather than just return it
- Shutdown hook in FastAPI lifespan for clean browser exit

**T-4.AI10: Write Tool Improvements** - **DONE**
- Markdown cell re-render after `setSource` (was showing stale rendered HTML)
- Editor lookup by project_id/notebook_path from action data (fixes cases where `_activeEditorKey` is undefined)
- `create_file` mount detection fix (was using `"projects"` root type for all files, now checks `registry.is_mount()`)
- Confirm follow-up: Anthropic gets `tool_result` content blocks with `tool_use_id`, Gemma gets `role: "tool"` messages
- Gemma token cleaning in confirm follow-up (was leaking `<|channel>thought` tags)

For detailed design documentation, see:
- `documents/mcp/mcp_technical_architecture_notes.md` - MCP architecture blueprint
- `documents/mcp/mcp_development_plan.md` - MCP development plan with estimates
- `documents/mcp/mcp_testing_and_validation.md` - MCP acceptance criteria
- `documents/llm/llm08.md` - Architecture patterns and implementation guide
- `documents/llm/LLM_SKILLS_PLAN.md` - Skills system design and capability map
- `documents/llm/LLM_WRITE_TOOLS_DESIGN.md` - Write tool confirmation flow

### 8.7 Code Intelligence (LSP) Tasks

**T-4.LSP1: Ruff Linting Integration** - **DONE**
- Ruff language server for Python files and notebook cells
- Jupytext shadow files present cell content to Ruff as standalone Python
- Backend severity remapping: Ruff reports everything as Error; backend remaps to Error/Warning/Info based on rule prefix (e.g., E/W/I prefixes)
- CodeMirror decorations (underlines with severity colors)
Scope reference: F-LSP-01

**T-4.LSP2: Jedi Language Server Integration** - **DONE**
- Jedi language server for autocomplete, hover documentation, go-to-definition
- Works for both Python files and notebook cells via Jupytext shadow files
- CodeMirror autocomplete popup, hover tooltips, and file navigation
Scope reference: F-LSP-02

**T-4.LSP3: Documentation Panel** - **DONE**
- New tab in right pane showing docstrings for the symbol under cursor
- docutils reST-to-HTML rendering with Water.css styling
- Updates on cursor movement
Scope reference: F-LSP-03

**T-4.LSP4: Code Minimap** - **DONE**
- Minimap widget in file editor with bird's-eye view
- Lint severity color markers (red/yellow/blue)
- Click to scroll to position
Scope reference: F-LSP-04

**T-4.LSP5: Code Problems Panel and Lint Fix** - **DONE**
- Bottom status bar pill with error/warning counts
- Sortable diagnostics panel with severity, message, line, rule code
- Lint fix for files and notebooks with shared EditorView registry
- Diff preview approval panel before applying fixes
- Project default venv persisted in `.noted/settings.json`
Scope reference: F-LSP-05

### 8.8 Debugging (DAP) Tasks

**T-4.DAP1: Notebook Debugging** - **DONE**
- Breakpoint gutter: CodeMirror extension with red dot markers, click to toggle
- ipykernel built-in Debugger via Jupyter control channel
- ControlChannelDispatcher: single-reader dispatch for concurrent control channel access
- dumpCell for temporary file creation
- Current line highlight (gold background on paused line)
- Auto-continue on last line (prevents IOStream flush timeout)
Scope reference: F-DAP-01, F-DAP-05

**T-4.DAP2: File Debugging** - **DONE**
- BreakpointGutter in FileEditor for .py files
- Run/Debug dropdown in file toolbar
- `%run -i` execution through kernel with real file paths
- Execution error forwarding (ModuleNotFoundError etc. as notifications)
- Outside-file detection: auto-terminate when stopped in IPython internals
- Smart continue: checks for remaining breakpoints before terminating
Scope reference: F-DAP-02

**T-4.DAP3: Debug Toolbar** - **DONE**
- Continue (F5), Step Over (F10), Step In (F11), Step Out (Shift+F11), Stop (Shift+F5)
- Run mode dropdown: chevron next to play button to switch between Run and Debug
Scope reference: F-DAP-03

**T-4.DAP4: Debug Panel** - **DONE**
- Variables section: scopes + variables tree with lazy expansion for compound types
- Call Stack section: navigable frames, click to select and re-fetch variables
- Breakpoints section: checkbox enable/disable, trash delete, navigate on click
- Cross-file navigation: click stack frame to open file and jump to line
- Always available: shows breakpoints even without active debug session
Scope reference: F-DAP-04

**T-4.DAP5: Run Menu and Debug UI** - **DONE**
- Run menu in menu bar: Run Cell, Run All, Debug Cell, Continue, Step Over, Step In, Step Out, Stop, Toggle Breakpoint with keyboard shortcuts and isDebugging context
- Debug icon (red bug) in icon bar toggles Debug panel in right pane
- Debug status pill (red) in status bar during active debug sessions, clickable
Scope reference: F-DAP-06

**T-4.DAP6: Debug All Cells** - **DONE**
- Shadow file generation: POST /api/dap/debug-notebook concatenates all code cells into /tmp/noted_debug_<hash>.py with # %% markers
- Filename injection: compile(code, shadow_path, 'exec') so debugpy sees unified file while cells execute individually
- IPython-safe wrapper: transform_cell for magics, ast.Interactive for display hook
- Cell map: backend returns line-to-cell mapping; frontend translates breakpoints to shadow file lines
- Cross-cell breakpoints: all breakpoints combined into single setBreakpoints call on shadow file
- Live breakpoint updates: add/remove during active session re-sends to debugger immediately
- Cell-boundary stepping: F10 at end of cell sends continue, auto-advances to next cell
- Step throttling, combined breakpoint+arrow marker, cell stop button
Scope reference: F-DAP-07

**T-4.DAP7: Debug Stop Cleanup** - **DONE**
- Control thread deadlock fix: continue + disconnect via dispatcher BEFORE stopping dispatcher/event task
- was_paused flag: only send continue if actually paused at breakpoint
- Ghost output filter: _debugAborted flag on cells filters output from cleanup's continue
- Fallback kernel restart if continue/disconnect timeout
- Independent ZMQ sessions: debug_kc and recreated main_kc use BlockingKernelClient.load_connection_file()
Scope reference: F-DAP-08

**T-4.UI2: Theme and Scrollbar Fixes** - **DONE**
- Default theme changed to "Default" (was "Tomorrow")
- Default wallpaper changed to "natural park" (was "Diagonal Lines")
- Global jsPanel scroll containment (overscroll-behavior, wheel stopPropagation, track margins)

### 8.9 Additional Phase 4 Tasks

**T-4.GIT: Git Discard** - **DONE**
- Right-click context menu for git discard
- Notebook reload after discard

**T-4.REFACTOR: app.js Refactoring** - **DONE**
- Split app.js from 3945 lines to 1189 lines across 6 modules
- Follows the established factory+ctx pattern

**T-4.UI: Explorer and Workspace Improvements** - **DONE**
- Workspace tab close button (X button in Explorer detail pane top bar)
- Embeddings node under Assistant (placeholder)
- Assistant detail page shows active model name and skill count
- Breadcrumbs for Assistant, Skills, Embeddings nodes
- Icon color persistence for root icons when selected
- Service tab container border-radius styling

### 8.6 Exit Criteria

- The full scenario from Vision document Section 6.1 is executable end-to-end without leaving noted
- All cross-panel links work correctly
- Activity feed shows a coherent timeline of all actions
- Two concurrent users experience real-time collaboration across all panels
- Empty states guide new users through the platform's capabilities
- No panel load exceeds 3 seconds under normal conditions
- Knowledge Graph renders smoothly and search returns results within 2 seconds
- AI assistant responds with context-aware answers grounded in live workspace state
- Tool calls execute correctly and write tools require user confirmation
- Automated test suite passes on clean docker compose up

---

## 9. Phase 5: Advanced Features and Production Readiness

**Goal:** Extend the platform with advanced analysis, governance, and production capabilities drawn from improvement suggestions and real-world MLOps needs.

**Rationale:** Phases 1-4 deliver the core MLOps lifecycle within noted. Phase 5 adds capabilities that improve decision-making (impact analysis, model cards), accelerate onboarding (project templates), strengthen data quality (validation gates), and support production operations (observability, cost profiling, feature catalog).

### 9.1 Tasks

**T-5.1: Impact Analysis via Knowledge Graph** (S-M effort)
Right-click any entity in the Knowledge Graph or Explorer and select "What breaks if I change this?". The backend performs a directed BFS on downstream edges from the selected entity. Returns a list of affected runs, pipelines, models, and other dependent entities. Results are highlighted in the 3D Knowledge Graph view.

**T-5.2: Automated Model Cards** (S-M effort)
Generate structured Model Card documents from lineage data (data hash + config + code + metrics). Uses the existing DocumentConverter pipeline (Markdown -> Pandoc -> Word). Accessible via a "Generate Model Card" action on the model version detail page. Includes: model description, intended use, training data provenance, evaluation metrics, ethical considerations template, and full lineage chain.

**T-5.3: Project Templates** (M effort)
"New Project" wizard with pre-configured templates:
- LLM Fine-tuning
- Time-series Forecasting
- Computer Vision

Each template includes a Hydra config structure, starter DAG definition, example notebook, and virtual environment setup script. Templates are stored as directory skeletons and copied on project creation.

**T-5.4: Data Validation and Quality Gates via Evidently** (M effort) - PLANNED for Monday
Integrate Evidently for data quality validation and pre-pipeline quality gates. Reports generated in DAG tasks using DataSummaryPreset and custom test conditions. A "Data Health" badge in the Explorer tree is sourced from the Evidently workspace API. Pre-pipeline test suites block execution on critical failures. Replaces the previously planned Pandera approach. Container already running (`noted-evidently`, port 8009). See `documents/noted_evidently.md` for full integration plan (IP-1, IP-4).

**T-5.5: Post-Deployment Observability via Evidently** (M effort, reduced from L) - PLANNED for Monday
Data drift detection (DataDriftPreset) and model performance monitoring (RegressionPreset) via Evidently. Reports generated in evaluation DAG tasks and saved to the Evidently workspace. noted surfaces lightweight status badges on model/dataset nodes in the Explorer tree. Detailed dashboards and trend charts viewed in the Evidently UI service tab (thin integration, Option A). Replaces the previously planned custom monitoring panel. Container already running (`noted-evidently`, port 8009). See `documents/noted_evidently.md` for full integration plan (IP-2, IP-3).

**T-5.4/5.5 shared infrastructure:**
- Evidently container (`noted-evidently`, port 8009->8000) added to `services/docker-compose.yml`
- `evidently_manager.py` backend module (thin API client for workspace queries)
- Evidently UI as service tab in noted (icon + iframe + nginx proxy)
- Evidently Python package in Airflow worker and noted container requirements
- Knowledge Graph integration: Evidently report entities linked to datasets, models, pipeline runs (IP-6)

**T-5.6: Hardware and Cost Profiling** (M effort)
GPU utilization monitoring via `nvidia-smi` during training runs. Metrics (GPU memory usage, utilization percentage, temperature) are logged as MLflow metrics alongside loss curves. Displayed in the Live Metrics panel as additional time-series charts. Enables cost-aware experiment comparison.

**T-5.7: Collaborative Feature Store** (S effort)
"Feature Catalog" view in the Explorer tree. Users can register DVC-tracked files as verified features with descriptions and tags. Reuses the existing tags infrastructure from the Knowledge Graph service. Features are searchable and browsable, enabling cross-project feature discovery and reuse.

**T-5.11: Multi-Language Debug All Support** (M-L effort)
Strategy Pattern architecture for per-language debug wrappers extending Debug All Cells to non-Python kernels. Language-specific filename injection: Node.js (sourceURL), Julia (include_string), R (srcref), C++ (#line directives). Two transport protocols: ZMQ (Python/ipykernel) and TCP (Xeus kernels). See `documents/dap/noted_dap_debug_all_plan.md` and `documents/dap/multi_language_plan_feedback.md` for design details.

**T-5.JS1: JavaScript Infrastructure** (M effort) - **DONE**
IJavascript kernel installed in the noted container. fnm (Fast Node Manager) and pnpm installed for Node.js environment/package management. Node.js 20 LTS and 22 LTS available. JavaScript kernel appears in the kernel picker with appropriate icon. Notebooks can be created with JavaScript kernel. See `documents/js/noted_javascript_integration_plan.md` for full plan.

**T-5.JS2: JavaScript DAP Transport** (M effort) - **DONE**
vscode-js-debug adapter with multi-session TCP proxy. Strategy Pattern architecture (PythonStrategy + JavaScriptStrategy) for per-language debug wrappers. Debug All Cells with single-execution model. Breakpoints, stepping, and variable inspection work via TCP transport. See `documents/dap/multi_language_plan_feedback.md` for design details.

**T-5.JS3: JavaScript Environment Management** (M effort) - **DONE**
pnpm install/list operations with NODE_PATH integration. Node.js environments manageable from the Explorer Environments section. fnm runtimes and pnpm package operations available.

**T-5.JS4: JavaScript LSP Integration** (S-M effort) - **DONE**
Biome for JavaScript linting and formatting. typescript-language-server for autocomplete, hover documentation, and go-to-definition. Shadow file mechanism adapted for JavaScript notebook cells. JavaScript diagnostics appear in the Problems panel.

**T-5.JS5: JavaScript Polish** (S effort) - **DONE**
Top-level await support in JavaScript notebooks. Debug All single-execution model. Per-cell timing display. Full-stack workflow validated: Python ML backend + JavaScript frontend in one project.

**T-5.JS6: JavaScript File Execution** (S effort) - **DONE**
Node.js execution via terminal for .js files. Run button in editor toolbar for JavaScript files. Output visible in terminal panel.

**T-5.JS7: Terminal-Based File Debug** (S effort) - **DONE**
runInTerminal pattern for both Python and JavaScript file debugging. Breakpoints with output visible in terminal. Unified debug experience across notebook cells and standalone files.

**T-5.WEB1: Web Language Support (HTML/CSS/JSON)** (S effort) - **DONE**
Syntax highlighting for HTML, CSS, and JSON files via @codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json added to the CodeMirror bundle. LSP auto-completion, documentation, and linting via vscode-langservers-extracted (npm install -g vscode-langservers-extracted). Single-server architecture for HTML/CSS/JSON (one LSP server handles all three languages, unlike Python's dual ruff+jedi or JavaScript's dual biome+tsserver). VS Code-style SVG data URI icons in autocomplete dropdown. File editor improvements: Tab inserts 4 spaces, Ctrl+Home/End navigate to start/end of file, hover documentation routed to the Documentation panel (not tooltip). dynamicRegistration forced to false for all LSP client initialization (codemirror-languageserver does not support dynamic registration). rootUri rewrite maps virtual URIs to real filesystem paths in _init_server. "Virtual Environments" renamed to "Environments" in Explorer tree with Python and JavaScript as language sub-nodes using VS Code color SVG icons. JS notebook IIFE wrapping prevents const/let re-declaration errors with globalThis exports for cross-cell variable sharing. Clean startup: no panels open, no auto-open Welcome.ipynb. Verified across all 5 languages (Python, JavaScript, HTML, CSS, JSON) via testing/33_test-language-support-matrix.md.
Scope reference: F-LSP-06

**T-5.YAML1: YAML Language Support** (XS effort) - **DONE**
yaml-language-server (Red Hat) for YAML completion, schema validation, and hover docs. CodeMirror @codemirror/lang-yaml for syntax highlighting. Single-server mode (same as HTML/CSS/JSON). Validates Hydra config files, GitHub Actions workflows, docker-compose files, and any other YAML.

**T-5.R1: R Phase 1 - Kernel and Execution** (L effort) - **DONE**
Six R versions installed in the noted Docker image (R 3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) via Posit's prebuilt Ubuntu 24.04 deb packages, each living at `/opt/R/<version>/`. **ark** (Posit's Rust-based Jupyter kernel, single binary serving all R versions) installed as `/usr/local/bin/ark`. Per-runtime `runtime.json` files at `data/runtimes/r/<version>/runtime.json` declare `kernel_cmd`, `kernel_env`, `env_create_cmd`, and `package_manager` blocks. **Option E architecture** for renv state isolation: cwd = project_root, with `R_PROFILE_USER` pointing at a noted-managed `.Rprofile` that calls `renv::load(project = getwd())`, while `RENV_PATHS_LIBRARY` and `RENV_PATHS_LOCKFILE` redirect renv state to `<env_path>/renv/`. Per-runtime `kernel_env` is the generic mechanism for per-language env injection (set up here for R, reused later by T-5.R2 for the LSP). The R Explorer hides `renv/` directories from project trees. RenvPackageManager stub created (full UI deferred to a later phase). End-to-end verified for modern R via cell execution, but the original "verified for all 6 versions" claim was overconfident - the legacy R kernel issue was discovered later in T-5.R3.
Scope reference: F-R-01, F-R-02

**T-5.R2: R Phase 2 - LSP for Modern R** (L effort) - **DONE**
**RLspStrategy** registered in the LSP strategy registry (`backend/app/managers/lsp/r_strategy.py`). languageserver R package (REditorSupport, latest CRAN) installed in the Docker image for R 4.2.3 / 4.3.3 / 4.4.2 / 4.5.1. Single-server mode (one languageserver provides completion + hover + lintr-driven diagnostics). Notebook bridge generates `# %%` percent-format combined shadow files for R cells. Lintr diagnostics enriched as `<message> + R - <Label>` (e.g. `assignment_linter` -> `R - Assignment`). Per-env LSP cache key uses `(project_id, env_name, server_type)` so two R envs with different R versions in the same project don't share a single languageserver process. **`RENV_CONFIG_EXTERNAL_LIBRARIES`** injected at LSP launch via `lsp_manager._resolve_runtime_env` so the system-installed languageserver is visible from inside renv-isolated envs. The cmd[0]="R" placeholder is substituted to `/opt/R/<version>/bin/R` for R runtimes (the `/usr/local/bin/R` wrapper script ignores `R_HOME`). 4 pre-existing main.py bugs fixed alongside: did_change reference, runtime_id consistency, project_root template, per-env LSP cache key. Frontend wired in `FileEditor.js` (`.r`/`.rmd`/`.qmd` -> `r` LSP) and `CellEditor.js` (R notebook cells use the same trigger logic as other languages). End-to-end validated via the 9-test walkthrough at `testing/34_test-r-lsp-phase2.md` (L1 through L9, all pass).
Scope reference: F-R-03

**T-5.R3: R Phase 2.1 - IRkernel for Legacy R** (M effort) - **DONE**
Phase 2 walkthrough exposed that **ark 0.1.250 cannot drive R 3.6.3 or R 4.0.5** - the R API surface ark expects (via libR.so dlopen) is from the R 4.x era and the older interpreters die during init, silently, before producing any output. Original Phase 1 "verified end-to-end" claim was overconfident; real cell execution was only ever tested on R 4.4.2. Phase 2.1 swaps the kernel for legacy R: **IRkernel** (REditorSupport, the original Jupyter R kernel) installed from PPM binary repos:
- R 4.0.5 -> IRkernel 1.1.1 from PPM 2021-05-01
- R 3.6.3 -> IRkernel 1.1 from PPM 2020-04-01

Both installs are pure binary - no compilation, sidestepping the glibc 2.34 SIGSTKSZ trap that would block legacy testthat from compiling. Validated via throwaway Dockerfile probes (`/tmp/probe-irkernel-*`) before landing in the real Dockerfile, per `feedback_no_ephemeral_probes.md`. The legacy `runtime.json` `kernel_cmd` becomes `[/opt/R/<version>/bin/R, --slave, -e, IRkernel::main(), --args, {connection_file}]`. `RENV_CONFIG_EXTERNAL_LIBRARIES` is also added to `kernel_env` for legacy R (in addition to the LSP-side injection from T-5.R2) because IRkernel runs as `R --slave -e ...` and goes through `.Rprofile`/renv too.
Scope reference: F-R-01

**T-5.R4: R Phase 2.2 - languageserver for Legacy R via PPM Binary Repos** (M effort) - **DONE**
Source-installing languageserver into legacy R fails for two distinct reasons: R 3.6.3 hits a PPM source dep resolution mismatch in the pkgload/withr/waldo cluster, and R 4.0.5 hits the testthat catch.h glibc 2.34 SIGSTKSZ compile error. PPM binary repo path (`/cran/__linux__/focal/<date>`) bypasses both:
- R 4.0.5 -> languageserver 0.3.10 from PPM 2021-05-01 (binary)
- R 3.6.3 -> languageserver 0.3.5 from PPM 2020-04-01 (binary)

**libicu66** from Ubuntu's focal archive installed in the Docker image alongside libicu74 because the 2020/2021-era PPM binaries link against `libicui18n.so.66` (used by stringi, a transitive dep of languageserver via lintr). Ubuntu 24.04 ships only libicu74; the symbol versions are incompatible. The legacy .deb coexists cleanly with the modern one (different SONAME) and adds ~30MB to the image. Validated via throwaway Dockerfile probes. **Result: ALL 6 R versions get full LSP - no second-class versions.** New memory entry `feedback_probe_full_runtime_chain.md` captures the meta-lesson that probes must exercise the actual entry-point (e.g. `languageserver::run()` with stdin redirected), not just `library(pkg)`, because lazy-loaded transitive deps with `.so` mismatches sneak past `library()`-only probes.
Scope reference: F-R-03

**T-5.R5: R Run from File Editor** (S effort) - **DONE**
Per-env `bin/Rscript` shell wrapper launcher generated at env creation time via `env_post_create_files` (with `template: true` and `executable: true`). The launcher sets R_HOME, LD_LIBRARY_PATH, R_PROFILE_USER, RENV_PATHS_*, RENV_CONFIG_EXTERNAL_LIBRARIES, RENV_CONFIG_SYNCHRONIZED_CHECK=FALSE, and NOTED_PROJECT_ROOT, then execs the per-version Rscript. Frontend `app-file-editors.js` extension check extended to include `.r` files, with `isR` branch in runCmd resolving to `<env_path>/bin/Rscript <filename>`. Debug button shows a warning toast for R files ("R debugging is not yet available (Phase 3)"). Lazy-generation in `env_manager._ensure_post_create_files` regenerates missing or stale launchers for existing envs (mtime-based template upgrade detection). `RENV_CONFIG_SYNCHRONIZED_CHECK=FALSE` added to all 6 R runtime.json kernel_env blocks and the Rscript launcher template to suppress the noisy renv "project is out-of-sync" warning.
Scope reference: F-R-04

**T-5.R6: R Debugger (Phase 3 R)** (XL effort) - **PLANNED, deferred**
ark exposes a DAP, but only inside Positron - the public 0.1.250 release does not expose DAP outside Positron's process model. Phase 3 R debug is blocked on Posit either shipping a standalone DAP transport or noted reverse-engineering ark's internal DAP. Legacy R via IRkernel will **never** have debug because the IRkernel side never offered DAP. Decision deferred until ark's DAP story matures: ship debug only for modern R via ark when available, or wait for a unified R DAP solution.
Scope reference: F-R-05

### 9.2 Exit Criteria

- Impact analysis returns correct downstream dependencies for any entity type within 3 seconds
- Model cards are generated as downloadable Word documents with complete lineage information
- Project templates create a fully functional project structure with working Hydra configs and example notebooks
- Evidently data quality and test suite reports generated in pipeline tasks; "Data Health" badge in Explorer tree
- Evidently drift and performance reports generated in evaluation tasks; status badges on model nodes; Evidently UI accessible as service tab
- GPU metrics appear in Live Metrics panel during GPU-accelerated training
- Feature catalog displays registered features with descriptions, tags, and source information
- JavaScript notebooks can be created, edited, and executed with IJavascript kernel - **ACHIEVED**
- JavaScript debugging works with breakpoints, stepping, and variable inspection via TCP transport - **ACHIEVED**
- Node.js environments manageable from the UI (fnm runtimes, pnpm packages) - **ACHIEVED**
- JavaScript LSP provides autocomplete, linting, and formatting in files and notebook cells - **ACHIEVED**
- HTML/CSS/JSON files have syntax highlighting, auto-completion, documentation, and linting via vscode-langservers-extracted - **ACHIEVED**
- YAML files have syntax highlighting, schema validation, and hover docs via yaml-language-server - **ACHIEVED**
- R notebooks can be created, edited, and executed across all 6 supported R versions (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) using ark for modern R and IRkernel for legacy R - **ACHIEVED**
- All 6 R versions get full LSP via languageserver (latest CRAN for modern; era-matched PPM binary repos for legacy with libicu66 runtime support) - **ACHIEVED**
- R Run from file editor for `.R` script files via per-env Rscript launcher - **ACHIEVED (T-5.R5)**
- R debugger (Phase 3 R, blocked on ark DAP availability) - **PLANNED, deferred (T-5.R6)**
- Seven languages verified with full LSP support (syntax coloring, auto-completion, documentation, linting): Python, JavaScript, R, HTML, CSS, JSON, YAML - **ACHIEVED**
- Full-stack workflow validated: Python backend + JavaScript frontend in one project - **ACHIEVED**
- JavaScript file execution via Run button and terminal - **ACHIEVED**
- Terminal-based file debug with runInTerminal pattern for Python and JS - **ACHIEVED**

---

## 10. Demonstration Pipeline: Jena Weather Forecasting

**Goal:** Build a complete, runnable ML pipeline in the Jena Weather project that validates all noted platform capabilities and serves as the primary demonstration for platform deliveries.

**Rationale:** The noted platform (Phases 0-4) is complete. The gap is not in the platform but in the demonstration project. The Jena Weather project needs a proper end-to-end pipeline with modular scripts, a 4-stage Airflow DAG, and a demo notebook to showcase the platform live.

### 10.1 Tasks

**T-DEMO.1: Hydra Config Groups** - **DONE**
Hierarchical config groups: `config/model/gru.yaml` (units1: 128, units2: 64, dropout: 0.2), `config/model/linear.yaml`, `config/data/default.yaml` (6 features, 120h sequence, 24h horizon), `config/config.yaml` (defaults, training params).

**T-DEMO.2: Modular Pipeline Scripts** - **DONE**
Four Python modules in `src/`: `ingestion/ingest.py` (load CSV, validate 15 columns, parse datetime), `preprocessing/preprocess.py` (hourly resample, cyclical time features, standardize, sliding windows), `training/train.py` (GRU/Linear with MLflow per-epoch logging, early stopping), `evaluation/evaluate.py` (prediction plots, horizon MAE chart, optional model registration).

**T-DEMO.3: Airflow Training Pipeline DAG** - **DONE**
`dags/jena_training_dag.py` with 4-stage DAG (`ingest_data -> preprocess_data -> train_model -> evaluate_model`). Airflow 3.0 TaskFlow API. Parameterized: model_type, epochs, learning_rate, batch_size, units1, units2, dropout, register_model, hydra_config_hash. Config built from params via OmegaConf. Inter-task data via `/opt/airflow/data/` (writable volume). Single MLflow run shared between train and evaluate tasks. Tested end-to-end on GPU (80s for 30 epochs).

**T-DEMO.4: Demo Notebook** - **DONE**
`notebooks/emi_tutorial2_demo.ipynb`: 6 cells (setup, ingestion, preprocessing, training, evaluation, prediction preview). Uses noted's `cfg` injection from Hydra config selector. Calls modular scripts from `src/`.

**T-DEMO.5: Pre-trained Model for Serving** - **DONE**
JenaWeatherGRU v1 registered in MLflow Registry (30-epoch GRU, GPU-trained). Serving container auto-installs model dependencies from MLflow artifact requirements on `/load`. 3D tensor prediction supported via pyfunc unwrap (`get_raw_model()`). Tested via API: 24-hour temperature forecast returned successfully.

**T-DEMO.6: Requirements File Update** - **DONE**
`requirements.txt` updated with: pandas, numpy, scikit-learn, tqdm, mlflow, plotly, matplotlib, pyyaml, tensorflow[and-cuda], dvc[s3], hydra-core, omegaconf, joblib.

### 10.2 Dependency Graph

```
T-DEMO.6 (requirements)     T-DEMO.1 (Hydra configs)
         \                   /
          \                 /
           T-DEMO.2 (modular scripts)
                  |
          +-------+-------+
          |               |
   T-DEMO.3 (DAG)   T-DEMO.4 (notebook)
          |               |
          +-------+-------+
                  |
           T-DEMO.5 (pre-trained model)
                  |
           Movie recording
```

### 10.3 Timeline

| Day | Tasks | Deliverable | Status |
|---|---|---|---|
| Day 1 (Mar 26) | T-DEMO.1 + T-DEMO.6 + T-DEMO.2 | Config groups, requirements, scripts | Done |
| Day 2 (Mar 27) | T-DEMO.3 + T-DEMO.4 + T-DEMO.5 | DAG, notebook, pre-trained model | Done |
| Day 3 (Mar 28) | Movie recording | Record all scenes | Pending |
| Day 4 (Mar 29) | Post-production + submission | Final video with slides, voice-over, music | Pending |

### 10.4 Exit Criteria

- All 4 pipeline scripts run successfully with Hydra config
- Airflow DAG completes all 4 tasks from noted's UI
- Demo notebook runs end-to-end with live metrics visible
- Model registered, aliased @champion, and servable via Try It panel
- Snapshot captures the complete experiment state
- Video demonstrates all of the above

---

## 11. Tutorial 3: Hydra Unification, Explorer Overhaul, and Chat Fixes

**Goal:** Deliver the Hydra Configuration Composer with Time Machine, demonstrate full config lineage in the jena_weather project, and fix outstanding UX and chat issues.

### 11.1 Explorer UX Overhaul - SHIPPED 2026-04-11

| Task | Status |
|------|--------|
| T-UX.1: Tree consolidation (Model Registry + APIs under "Models"; Data Catalog + Storage under "Data") | Done |
| T-UX.2: Root node detail pages removed - root nodes expand/collapse only | Done |
| T-UX.3: Double-click to expand (single click selects; double-click toggles expand/collapse) | Done |
| T-UX.4: KB upload moved to right-click context menu | Done |
| T-UX.5: KB document undocking (clone-based floating panels; dock-back via _currentDoc = null) | Done |
| T-UX.6: Knowledge Graph as first tree child of Knowledge Base (detail tab, Three.js white scene) | Done |
| T-UX.7: R renv package manager fully implemented (list_packages via os.walk, install via renv::install + snapshot, remove via renv::remove, protected packages) | Done |
| T-UX.8: renv cache persistence (RENV_PATHS_CACHE -> data/ bind mount) | Done |
| T-UX.9: Skills open as document tabs (preview/pin, preformatted text, document-viewer-skill class) | Done |

### 11.2 Hydra Unification + Time Machine - SHIPPED 2026-04-12

| Milestone | Description | Status |
|-----------|-------------|--------|
| M1 | Overrides persistence, notebook_uid (UUID v4, lazy-generated), hydra_baseline_source field in notebook metadata | Done |
| M2 | Per-run Hydra bundle logging to MLflow via user_expressions (hydra/ folder: full config/ tree + selections.json + resolved.yaml) | Done |
| M3 | HydraSource abstraction (LocalSource / MlflowSource), in-memory HydraCache keyed by (notebook_uid, run_id), new API endpoints (GET /experiments/{id}, GET /runs/{id}/{exp_id}, POST /load-bundle, POST /compose-mlflow) | Done |
| M4 | Configuration Composer Time Machine UI: mode toggle (Local Baseline / Experiment Run), experiment/run dropdowns, archived bundle load, drift warning; Apply disabled until run selected | Done |
| M5 | Notebook bar baseline badge (BASELINE / RUN xxxxxx + colored dot: green check / orange ! with per-key drift tooltip / red X); stale metadata validation; schema refresh on Apply | Done |
| M6 | User Manual Page 2 rewrite for new baseline source model | Done |

**Bug fixes during Phase 2:**
- MLflowManager vs MlflowManager class name typo in 3 files
- MlflowSource.walk() only yielded root directory - subdirectories missing, causing incomplete config/ trees in MlflowSource bundles. Fixed: walk now adds each nested dir in the first pass
- Composer _switchToLocal was clearing state.runId/state.experimentId; now preview-only per D13. Switching back to Experiment Run restores previous selections. load-bundle returns experiment_id for dropdown restoration

### 11.3 Tutorial 3 / jena_weather Level C - SHIPPED 2026-04-13

| Task | Description | Status |
|------|-------------|--------|
| T-T3.1 | Config restructure: training block inlined into config/config.yaml, 10 override inputs in Composer (seed + 9 training knobs). Deleted config/training/ folder | Done |
| T-T3.2 | Second DVC-tracked dataset (data/jena_climate_2012.csv, 52704 rows, year 2012 only, md5 d3956bd0ef90d27c79a4fc422400fd37, 5.4 MB). Created via src/data/filter_year.py. dvc add + dvc push to noted-minio | Done |
| T-T3.3 | Data config options renamed: config/data/jena_full_dataset.yaml (full 2009-2016) and config/data/jena_2012_dataset.yaml (1-year subset) | Done |
| T-T3.4 | Notebook cells updated: cfg.seed, cfg.training.early_stopping, cfg.training.lr_reduction wired; cell 16 DATASET_PATH reads cfg.data.file (was hardcoded) | Done |
| T-T3.5 | src/models/train_eval.py: get_default_callbacks + train_model extended with es_cfg/lr_cfg parameters driving EarlyStopping + ReduceLROnPlateau from cfg. Backward compatible | Done |
| T-T3.6 | Airflow DAG Level C refactor (565 lines): _compose_config + _assemble_hydra_bundle helpers inline; data_config DAG param; all tasks read from composed cfg; new log_hydra_lineage @task that logs full Hydra bundle to MLflow and tags noted.hydra_config_hash | Done |
| T-T3.7 | Run Manager dataset redundancy eliminated: backend derives dataset_hashes from cfg.data.file when hydra_config present; frontend shows read-only Hydra-derived row instead of checkbox picker for Hydra notebooks | Done |
| T-T3.8 | Composer footgun fixes: Apply-before-run disabled, dropdown default selection fix (set select.value after options appended), stale metadata validation, badge dot visual inversion | Done |

### 11.4 Evidently Partial Delivery - SHIPPED 2026-04-10/13

| Task | Status | Remaining |
|------|--------|-----------|
| Evidently container in docker-compose, evidently_manager.py, Evidently UI service tab | Done | - |
| Data Health dot on Data node (green/yellow/red, sourced from Evidently workspace API) | Done | - |
| evidently_quality DAG task (DataSummaryPreset, data-quality tag) | Done | - |
| evidently_drift DAG task (DataDriftPreset, drift tag, run_id linkage to MLflow) | Done | - |
| Quality gates (Test Suite blocking training on failures) | Planned | - |
| Drift alert badges on Model nodes | Planned | - |
| RegressionPreset (prediction quality monitoring) | Planned | - |
| Knowledge Graph integration for Evidently entities | Planned | - |

### 11.5 Chat / Assistant Bug Fixes - SHIPPED 2026-04-13

| Task | Fix | Files |
|------|-----|-------|
| Ask Assistant duplicate messages | showUserMessage: false in sendMessage call | frontend/js/app-chat.js |
| Ask Assistant panel not opening/focusing | Added _chatVisible check, rightPanel.show('assistant'), input.focus() | frontend/js/app-chat.js |
| Truncated run IDs in Ask Assistant | Changed from 8-char shortId to full run.run_id with explicit labeling | frontend/js/panels/explorer/ExplorerMlflowViews.js |
| Gemma token regex mismatch | thought\n -> thought\s with re.DOTALL in strip_gemma_tokens and translate_gemma_thinking | backend/app/mcp/gemma_tool_parser.py |
| Pre-thinking preamble leaking | Added intermediate: bool param to _prepare_text_for_frontend; strips text before <think> when True | backend/app/routers/llm.py |
| Math rendering broken in chat | Added marked.js extension IIFE (math_block + math_inline levels) intercepting $...$ and $$...$$ before markdown, rendering via KaTeX | frontend/js/ChatPanel.js |

### 11.6 User Manual

| Page | Title | Status |
|------|-------|--------|
| 1 | Your First Project | Shipped 2026-04-13, revised as final user-facing doc 2026-04-15, published to KB |
| 2 | Configuring Your Experiment (Hydra, Composer, Time Machine, Run Manager) | Shipped 2026-04-13, revised 2026-04-15, published to KB |
| 3 | Running Your Experiment (MLflow, Run Manager, live metrics, Experiments tree, Lineage chain, compare, Ask Assistant) | Shipped 2026-04-13, revised 2026-04-15, published to KB |
| 4 | From Notebook to Pipeline (Orchestration, DAG trigger, paused DAG modal, task logs, lineage chips, promotion workflow) | Shipped 2026-04-13, revised 2026-04-15, published to KB |
| 5 | Data Quality (Evidently thin integration, Data Health dot, DAG tasks, service tab, run_id linkage) | Shipped 2026-04-13, revised 2026-04-15, published to KB |
| 6 | Serving & Deploying Models (Register, Deploy / Unload / Try It, Logged Models, external client consumption) | **New - written 2026-04-15, published to KB** |
| 7 | noted Assistant (local Gemma 4 + Claude API, ~42 skills, MCP tools, worked examples) | **New - written 2026-04-15, published to KB** |

All 7 pages stripped of the UX-friction blockquotes and friction-summary tables they carried during design review. They now read as final user documentation with no meta-commentary.

---

## 12. Model Serving Refactor and Final Delivery Docs - Apr 14/15

**Goal:** Ship a usable Model Serving experience end-to-end and complete the final-delivery documentation package for Tutorial 3.

### 12.1 Model Serving Phase 0a - SHIPPED 2026-04-14

| Task | Description | Status |
|------|-------------|--------|
| T-SRV-0a.1 | Replace "Publish / Try It" wording with MLflow-aligned **Deploy / Unload / Try It** three-button UX on every version card in the Model Registry detail | Done |
| T-SRV-0a.2 | Streaming NDJSON progress from `noted-serving`'s `/load` endpoint. New `DeployEventStream` class bridges the sync loader's phase callbacks to an async generator using `asyncio.wait(FIRST_COMPLETED)`. Emits `{phase, detail}` intermediate events and a terminal `{phase: "ready", result: {...}}` or `{phase: "error", error: "..."}` event | Done |
| T-SRV-0a.3 | Frontend `ModelDeployer` class encapsulates fetch + `ReadableStream.getReader()` + `TextDecoder` + line-based NDJSON parser. No `setTimeout` polling anywhere | Done |
| T-SRV-0a.4 | `ModelLoader` correctness fixes: RLock full serialization of the load path; content-hash cache (`_installed_reqs_hashes`) to skip re-install when same `requirements.txt` was already processed; early-return when same model+version already loaded; non-blocking `try_acquire(blocking=False)` in unload so concurrent unload during load refuses cleanly with `{refused: True}` | Done |
| T-SRV-0a.5 | Framework-specific VRAM cleanup in unload: `tf.keras.backend.clear_session`, `torch.cuda.empty_cache` + `torch._dynamo.reset`, `jax.clear_caches`. All gated on `sys.modules` so frameworks not in use are never imported | Done |
| T-SRV-0a.6 | Backend proxy in `backend/app/routers/serving.py` rewritten to use `httpx.AsyncClient().stream()` for `/api/serving/load` so the NDJSON bytes pass through without buffering. Socket.io event loop stays responsive during long deploys | Done |

### 12.2 Model Serving Step 1 Unblock - SHIPPED 2026-04-15

Phase 0a's runtime install (`_install_model_deps` calling `uv pip install --system -r model_requirements.txt`) was discovered to fail on cold deploys because Python cannot hot-swap C extension modules in a running interpreter: once `google.protobuf` and `tensorflow._pywrap_*.so` are imported into the uvicorn process, `uv pip install` rewriting the disk has zero effect on the already-loaded modules, producing a `protobuf` runtime/gencode version mismatch crash at `mlflow.pyfunc.load_model()` time.

| Task | Description | Status |
|------|-------------|--------|
| T-SRV-step1.1 | Drop `protobuf>=4.0.0,<5.0.0` pin from `client/requirements.txt`. The original pin was the root cause: it forced protobuf 4.x into the image baseline while modern TF needs 5.x or 6.x | Done |
| T-SRV-step1.2 | Remove the `_install_model_deps()` call from `_load_inner()` in `client/app/model_loader.py`. The baseline image now serves all registered model versions via MLflow's warning-mode loading (emits version-mismatch warnings but loads successfully) | Done |
| T-SRV-step1.3 | Remove `_installed_reqs_hashes` module-level cache, the `hashlib` import, and the entire `_install_model_deps` method from `model_loader.py` | Done |
| T-SRV-step1.4 | Verify end-to-end: alternate through v1-v7 of Jena Weather Forecaster. Expected: each deploy is 0.09-0.13 s (warm) or ~2-3 s (cold first-load). Verified 2026-04-15 12:10-12:12 UTC via live test | Done |

### 12.3 Logged Models UI (MLflow 3.x) - SHIPPED 2026-04-15

MLflow 3.x stores `log_model()` output as a separate **Logged Model entity** at `<experiment_id>/models/<model_id>/artifacts/` rather than under the run's direct artifact tree. noted's Registry detail view must surface these so users can see `MLmodel`, `requirements.txt`, `conda.yaml`, `python_env.yaml`, and the framework-specific weights.

| Task | Description | Status |
|------|-------------|--------|
| T-SRV-LM.1 | New `MlflowManager.list_logged_models_for_run(run_id)` scans `<experiment_id>/models/` via the MLflow artifact proxy REST API (`GET /api/2.0/mlflow-artifacts/artifacts?path=...`), opens each candidate's `MLmodel` file, matches against the run_id, and returns a flat list of `{model_id, experiment_id, artifact_uri, artifacts}` where `artifacts` is a walked tree of `{path, file_size, is_dir}` entries | Done |
| T-SRV-LM.2 | New `MlflowManager.download_logged_model_artifact(experiment_id, model_id, path)` streams individual files via the artifact proxy HTTP endpoint directly. Deliberately does **not** call `mlflow.artifacts.download_artifacts(artifact_uri=...)` because noted's global MLflow tracking URI is set to the SQLite backend store, not an HTTP tracking URI, and the high-level API refuses to resolve `mlflow-artifacts:/...` URIs in that configuration | Done |
| T-SRV-LM.3 | New backend routes `GET /api/mlflow/runs/{run_id}/logged_models` and `GET /api/mlflow/logged_models/{experiment_id}/{model_id}/download?path=...` in `backend/app/routers/mlflow.py` | Done |
| T-SRV-LM.4 | Frontend: new view functions `loadLoggedModelsCategory`, `loadLoggedModelSubdir`, `showLoggedModelsCategoryDetail`, `showLoggedModelDetail` in `ExplorerMlflowViews.js`. Tree key prefixes `mllm-cat:{runId}` (category) and `mllm:{runId}:{modelId}:{relPath}` (item). `loadRunArtifactCategories` fetches both `/artifacts` and `/logged_models` in parallel and adds a "Logged Models" category when any are present | Done |
| T-SRV-LM.5 | Dispatcher wiring in `ExplorerPanel.js`: data-type assignments (`mllm-cat` / `logged-model`), lazy-load routing, click-to-show-detail routing, and breadcrumb resolver for both prefixes | Done |
| T-SRV-LM.6 | fa-brain icon in Files grey (`#b0bec5`) via inline `setProperty('color', '#b0bec5', 'important')` in `_recolorNode` - beats the class-based `.fa-brain { color: #e091d0 !important }` rule via inline-important priority, so Logged Models rows are visually distinct from the pink Models rows elsewhere in the Registry | Done |
| T-SRV-LM.7 | hljs-highlighted file previews using the same pattern as Markdown code blocks in `DocumentViewer.js`: `<pre><code class="language-yaml">...</code></pre>` + `hljs.highlightElement(code)`. Language classes: `language-yaml` for MLmodel/conda.yaml/python_env.yaml, `language-plaintext` for requirements.txt | Done |

### 12.4 jena_client Model Serving Client - SHIPPED 2026-04-15

Generic reference client at `iscte/jena_client/` showing how external apps can consume noted-served models.

| Task | Description | Status |
|------|-------------|--------|
| T-CLIENT.1 | Rename UI from "Jena Weather Forecast" to "Model Serving Client" with a dynamic subtitle showing `{model_name} v{version}` | Done |
| T-CLIENT.2 | Three cascading dropdowns (Model / Version / Alias). Model dropdown populated from `/api/models` (which hits MLflow's `registered-models/search`). Version dropdown populated from `/api/models/{name}/versions` (which merges `registered-models/get` for aliases with `model-versions/search` for the version list). Alias dropdown lists all aliases pointing at any version of the selected model; defaults to `@champion` when present, else `<no tag>`. Selecting an alias auto-updates the version dropdown to the aliased version | Done |
| T-CLIENT.3 | Backend `load_model` socket.io handler rewritten to consume the NDJSON streaming response from `noted-serving`'s `/load`. Uses `async with client.stream("POST", ...)` + `resp.aiter_lines()`. Forwards intermediate progress events to the frontend as `status` events; emits `model_loaded` on the terminal `{phase: "ready", result: {...}}` event (the `result` field carries the full health payload with model_name, version, load_time, run_id, framework, num_parameters) | Done |
| T-CLIENT.4 | New backend endpoint `/api/run_params/{run_id}` that hits MLflow's `runs/get` REST API and returns the run's params as `{key: value}`. Frontend fetches this after `model_loaded` and extracts `target_mean` and `target_std` for inverse scaler transform | Done |
| T-CLIENT.5 | Inverse scaler transform: `prediction.map(v => v * target_std + target_mean)`. Applied only when both stats are available; otherwise displays raw z-scores with a different label. Unit flag ('degC' vs 'z') controls both the chart legend and the table header | Done |
| T-CLIENT.6 | Three-column results table: `Hour` (left-aligned), `Temperature (degC)` (right-aligned), `Raw (z)` (right-aligned). Caption above the table shows the applied formula: `Inverse transform applied: value_degC = raw * {std} + {mean}` | Done |
| T-CLIENT.7 | Clear-output-on-load: clicking Load clears the previous chart, results table, input textarea, and model info block so stale output from a different model cannot mislead the user | Done |
| T-CLIENT.8 | Noted-style scrollbars ported from `frontend/css/sidebar.css` sidebar-content pattern: 8px wide, faint `rgba(96,150,229,0.18)` background on the thumb (always visible when content overflows), darker `#6096e5ad` on container hover, darkest `#4a7bd0cc` on thumb hover/active. Applied to `.results-table`, `.log-entries`, and `textarea` | Done |

### 12.5 Supporting Fixes - SHIPPED 2026-04-15

| Task | Description | Status |
|------|-------------|--------|
| T-NB.1 | `emi_tutorial3_jena_weather.ipynb` cell 116 refactored: removed the fallback `mlflow.start_run(run_name=...) if not active_run else None` branch. The entire MLflow logging block (set_tracking_uri, set_experiment, log_params, log_metrics, set_tag, log_model) is now gated behind `if run is not None:`. Run All no longer creates orphan MLflow runs | Done |
| T-NB.2 | `emi_tutorial3_jena_weather.ipynb` cell 117 refactored: `register_and_promote()` is now gated behind the same `if run is not None:` guard | Done |
| T-NB.3 | Added `target_mean` and `target_std` to the `mlflow.log_params({...})` call in cell 116 so serving clients can de-standardize predictions back into real units | Done |
| T-GIT.1 | `execution_bridge.py _log_hydra_bundle_for_run` git-tagging block rewritten with explicit `logger.info` and `logger.warning` at every branch exit: entry log, project_path resolve result, `.git` directory check, `rev-parse HEAD` rc/stdout/stderr, tag write confirmation, branch write confirmation, exception handler with `exc_info=True`. No silent fall-throughs. New Run Manager runs now reliably tag `noted.git_commit`, `mlflow.source.git.commit`, and `mlflow.source.git.branch` | Done |
| T-LOG.1 | `client/app/main.py` `logging.basicConfig(format=...)` now includes a literal `UTC` suffix so noted-serving container logs print `2026-04-15 11:05:48,271 UTC [INFO] ...`. No behavior change - the timestamps were already UTC - but makes it explicit for anyone reading `docker logs` | Done |

### 12.6 Final Delivery Documentation - SHIPPED 2026-04-15

| Task | Description | Status |
|------|-------------|--------|
| T-DOC.1 | User Manual Pages 1-5 revised as final user-facing documentation. All `[UX FRICTION]` blockquotes stripped. Trailing `Summary: What Should Be Easier` and `UX Friction Summary` sections removed. Content updated to reflect the shipped Time Machine, Run Manager, Lineage view, Logged Models, Deploy / Unload / Try It, and jena_client demo | Done |
| T-DOC.2 | User Manual Page 6 "Serving & Deploying Models" newly written. Covers Register Model from run, Deploy / Unload / Try It workflow, Logged Models artifact inspection, external client consumption via the jena_client reference app | Done |
| T-DOC.3 | User Manual Page 7 "noted Assistant" newly written. Covers local Gemma 4 via `llama-cpp-python` vs Claude API (Sonnet 4.6 / Opus 4.6 / Haiku 4.5), ~42 skills across 7 domains (Airflow, DVC, Evidently, Hydra, MLflow, noted core, general ML), MCP tools for live state retrieval, and three worked examples (explain a run, compare two runs, debug a failed Airflow task) | Done |
| T-DOC.4 | All 7 manual pages published to the Knowledge Base: source files at `documents/user-manual/0[1-7]-*.md`, KB copies at `data/documents/files/manual_0[1-7]_*.md`, and index entries for Pages 6 and 7 added to `data/documents/documents.json` under the "noted User Manual" category | Done |
| T-DOC.5 | `NOTED_SETUP.md` created at the repo root as the reviewer-facing setup guide. Sections: quick links to GitHub (https://github.com/logus2k/noted) and live instance (https://logus2k.com/noted), prerequisites, cloning the three repositories (noted, jena_weather, jena_client), configuring environment variables via `services/.env.example` -> `services/.env`, configuring project mounts via `data/NOTED.md` upfront (with a visible note that both jena_weather and jena_client mounts are required for end-to-end review), GPU and CPU launch commands, first-run smoke test, stopping and cleaning up, troubleshooting, and next steps | Done |
| T-DOC.6 | `README.md` refreshed: Model Registry & Serving section rewritten for the three-button workflow, Logged Models, and jena_client reference client. Skills count bumped to ~42. Phase 5 heading flipped from PLANNED to IN PROGRESS. Three new roadmap sections appended: Model Serving Refactor (2026-04-14/15), jena_client Model Serving Client (2026-04-15), Final Delivery Docs (2026-04-15) | Done |
| T-DOC.7 | `noted_vision.md` version bump 2.3 -> 2.4, date 2026-04-15. New v2.4 changelog entry at the top describing the serving refactor, Logged Models, jena_client, lineage chain, Tutorial 3 Level C, 7-page manual, NOTED_SETUP.md, and Phase 0b deferral | Done |
| T-DOC.8 | `noted_scope.md` version bump 2.3 -> 2.4, date 2026-04-15, Related updated to Vision v2.4. Full v2.4 changelog entry at the top. Section 3.7 Model Serving entirely rewritten: F-SRV-01 through F-SRV-05 refreshed to reflect Deploy / Unload / Try It, Logged Models visibility, external client integration via jena_client, and the step-1 unblock status; Out of Scope updated to reflect Phase 0b deferral and remaining limitations | Done |
| T-DOC.9 | `noted_plan.md` version bump 2.6 -> 2.7, date 2026-04-15, Related updated. Full v2.7 changelog entry at the top. New Section 12 (this section) added covering serving refactor tasks T-SRV-0a.*, T-SRV-step1.*, T-SRV-LM.*, T-CLIENT.*, T-NB.*, T-GIT.*, T-LOG.*, and T-DOC.* | Done |

### 12.7 Post-Demo Backlog

Items captured in `documents/noted_backlog.md` for post-demo work:

| Item | Effort | Impact |
|------|--------|--------|
| Phase 0b Worker Subprocess Architecture | ~9h core + ~5h layers | Correct long-term fix for arbitrary-pin model serving (see `documents/serving_worker/serving_worker_plan.md`) |
| MLflow Soft-Delete Foot-gun | ~15 min + ~2-3h | Remove `except Exception: pass` in `RUN_START_CODE` + frontend modal offering restore-or-purge on deleted-experiment detection |
| Noted Terminal Child-Process Tracking | ~4-8h | Track processes launched from terminal tabs; prompt on close / rebuild / unload; Explorer Processes panel |
| Generic Output Rendering for Non-Regression Models | ~1-2h | Detect output_format and switch between line chart / bar chart / table / JSON tree in the serving client |
| UI Timestamp Audit | ~3-5h | Audit every place noted renders a timestamp; ensure browser converts UTC to local time consistently |

### 12.8 Exit Criteria

- Model Serving end-to-end works for the Tutorial 3 demo: register model from Run Manager run, click Deploy, stream progress phases to UI, click Try It, send synthetic input, render result. Verified 2026-04-15 against Jena Weather Forecaster v1 (jena_full_dataset) and v2 (jena_2012_dataset) - both with full 5-layer lineage chain (Data/Config/Code/Run/Model, plus 6th Airflow layer for DAG-produced runs).
- `noted-serving` /health returns correct model metadata; Deploy / Unload cycle works without leaking GPU memory; Logged Models artifacts inspectable with inline hljs previews and working Download buttons.
- jena_client reference app loads models via dropdowns, shows NDJSON progress, runs predictions, applies inverse scaler transform, and renders results with real Celsius values.
- User Manual 7 pages visible in noted's Knowledge Base under "noted User Manual" category, readable with working internal cross-references.
- `NOTED_SETUP.md`, `README.md`, `noted_vision.md`, `noted_scope.md`, `noted_plan.md` all reflect the current state of the platform; version numbers bumped; shipped items moved out of "planned" status.
- A reviewer who has never seen noted can clone, set up, and run the Page 1 flow in under 15 minutes following `NOTED_SETUP.md`.

---

## 13. Task Dependency Map (Platform)

```
Phase 0 (all tasks can run in parallel - verification only) [COMPLETED]
    |
    v
Phase 1A:
    T-1A.1 (Icon Bar + Sidebar Shell)
        |
        +-> T-1A.3 (Workspace Explorer Migration)
        +-> T-1A.9 (Experiments Section in tree)

    T-1A.2 (Tabbed Center Pane)
        |
        +-> T-1A.4 (Service UI Tabs)
        +-> T-1A.5 (Python File Tabs)

    T-1A.1 + T-1A.2 (layout infrastructure)
        |
        +-> All subsequent frontend tasks depend on layout

    T-1A.6 (Kernel MLflow injection - extends KernelManagerService)
        |
        +-> T-1A.7 (Explicit verification)

    T-1A.8 (Experiments API - queries MLflow directly)
        |
        +-> T-1A.9 (Experiments Section in tree)

Phase 1B:
    T-1B.1 (ProjectVersionControl)
        |
        +-> T-1B.2, T-1B.3, T-1B.4 (Data endpoints)
        |       |
        |       +-> T-1B.9 (Data Section in tree)
        |
        +-> T-1B.7 (DVC hash injection — tag + parameter)

    T-1B.5 (Auto-instrumentation - extends ExecutionBridge)
        |
        +-> T-1B.11 (Run Manager UI - explicit MLflow tracking)

    T-1B.6 (Live Metrics Streaming)
        |
        +-> Updates Experiments detail tabs in real-time

    T-1B.8 (Storage Section in tree)

    T-1B.10 (Git/DVC Terminal Escape Hatch)

    T-1B.12 (Run Comparison View)
    T-1B.13 (Artifact Browser — images, HTML/Plotly, model cards)

Phase 2:
    T-2.1, T-2.2, T-2.3 (Hydra endpoints)
        |
        +-> T-2.11, T-2.12 (Config UI)
        +-> T-2.4 (Config hash injection)
        +-> T-2.5 (DAGGenerator)
                |
                +-> T-2.6 (Pipeline trigger)
                +-> T-2.9 (Sweep DAG)
                        |
                        +-> T-2.13 (Sweep UI)

    T-2.7 (PipelineMonitor)
        |
        +-> T-2.14 (Pipeline tab)

    T-2.8 (Pipeline history)
        |
        +-> T-2.15 (History UI)

Phase 3:
    T-3.1 through T-3.5 (Registry endpoints)
        |
        +-> T-3.10, T-3.11, T-3.12 (Registry UI)

    T-3.6, T-3.7 (Serving container - only new container)
        |
        +-> T-3.8 (ServingProxy)
        +-> T-3.9 (Container lifecycle)
                |
                +-> T-3.13 (Try It tab)

Phase 4:
    All tasks depend on Phases 1A, 1B, 2, 3 being complete
    T-4.1 through T-4.6 can proceed in parallel
    T-4.7 through T-4.12 depend on their respective backend tasks
```

---

## 12. Risk Mitigation Plan

### 11.1 Technical Risks and Responses

**Risk: MLflow run lifecycle management**
- Mitigation: MLflow tracking is explicit via Run Manager only - no implicit auto-tracking that could create stale runs or conflict with user code
- Design: Clean separation between exploration (no MLflow overhead) and experimentation (Run Manager handles start/end)

**Risk: Docker Compose resource exhaustion (many containers already running)**
- Mitigation: Set resource limits on all containers. Model-server is on-demand only.
- Monitoring: Add basic resource monitoring (container stats)
- Fallback: Reduce worker count, increase swap, or migrate GPU training to a separate host

**Risk: Socket.io event ordering across multiple backend services**
- Mitigation: Include monotonic sequence numbers in events; client reconciles ordering
- Fallback: Accept slight out-of-order events in non-critical displays (activity feed)

**Risk: Kernel session model (one per client) vs project-scoped MLflow context**
- Mitigation: MLflow experiment is project-scoped (env vars injected at kernel start). Multiple kernels in the same project share the same experiment but create separate runs. This is correct MLflow behavior.

### 11.2 Scope Risks

**Risk: Feature creep in individual phases**
- Mitigation: Each phase has explicit exit criteria. A phase is complete when exit criteria are met, not when all "nice to have" features are done

**Risk: Hydra config UI complexity explosion**
- Mitigation: Limit initial support to 3 levels of nesting and standard types (int, float, str, bool, list)
- Deferral: Complex types (custom objects, recursive configs) are out of scope

---

## 13. Verification Approach

### 12.1 Per-Phase Verification

| Phase | Verification Activity                                              |
|-------|--------------------------------------------------------------------|
| 0     | Service connectivity checks, API round-trip tests, DVC round-trip  |
| 1A    | Layout functional test: sidebar, tabs, MLflow tracking end-to-end  |
| 1B    | Manual end-to-end test: upload data, run training, compare runs    |
| 2     | Manual end-to-end test: configure, trigger pipeline, see results   |
| 3     | Manual end-to-end test: register model, promote, predict           |
| 4     | Full scenario test (Vision Section 6.1), concurrent user test      |

### 12.2 Integration Test Suite (Phase 4)

A scripted test that automates the Vision scenario:
1. Create project via API
2. Upload dataset via data endpoint
3. Verify DVC tracking and version
4. Start kernel, execute training cell with auto-tracking
5. Verify MLflow run with correct tags (data hash, config hash)
6. Compose Hydra config, trigger Airflow pipeline
7. Verify pipeline completes and creates MLflow runs
8. Register model from best run
9. Promote to @champion
10. Send prediction request, verify response
11. Verify all Socket.io events were emitted correctly
12. Verify activity feed contains all actions

---

## 14. Open Questions

| # | Question                                                    | Affects        | Status / Answer                         |
|---|-------------------------------------------------------------|----------------|-----------------------------------------|
| 1 | pygit2 or git subprocess?                                   | Phase 0, 1     | RESOLVED: git subprocess (installed in container, works reliably) |
| 2 | Worker data access: volume mount or DVC pull?               | Phase 0, 2     | RESOLVED: volume mount (/opt/noted/projects:ro) |
| 3 | MLflow metric streaming: polling or kernel-level intercept? | Phase 1B       | Start with polling; optimize if needed  |
| 4 | Serving container: one per project or shared pool?          | Phase 3        | One per project with inactivity timeout |
| 5 | GPU inference in serving container?                         | Phase 3        | CPU only initially; GPU as future work  |
| 6 | How to handle notebook-to-script extraction for pipelines?  | Phase 2        | Users maintain src/train.py manually    |
| 7 | Authentication model for multi-user access?                 | All phases     | To be designed separately (currently open access) |
| 8 | Inline code completion (ghost-text)?                        | Post-Phase 4   | See `documents/llm/llm08.md` Section 7  |
| 9 | How to handle projects with no Hydra config?                | Phase 2        | Config section shows empty state; pipeline trigger requires at least a minimal config.yaml |
| 10| Docker network topology: single network or bridge?          | Phase 0        | RESOLVED: single default network via services/docker-compose.yml |
| 11| External projects: how does Git/DVC metadata coexist with host-linked notebooks? | Phase 1B | Git/DVC metadata in noted's data dir, notebooks may be symlinked from host |

---

## 15. Academic Curriculum Alignment

noted supports end-to-end MLOps curricula covering progressive lab-style learning. The platform phases map naturally to a typical MLOps course progression:

| Phase | Curriculum Coverage |
|-------|--------------------|
| **0** (done) | Infrastructure: Docker Compose, multi-service deployment |
| **1A** (done) | MLflow connectivity, project structure, experiment tracking |
| **1B** (done) | DVC data versioning, artifact browser, run comparison, live metrics |
| **2** (done) | Hydra configuration, Airflow DAGs, parameterized triggers |
| **3** (done) | Model registry, model serving, snapshots |
| **4** (done) | AI assistant, knowledge graph, full lineage, Evidently monitoring, LSP code intelligence, DAP debugging |
| **5-JS** (done) | Multi-language support: JavaScript infrastructure, DAP debugging, environment management, LSP integration, file execution, terminal-based debug |
| **5-R** (done) | R as third notebook language: 6 R versions (3.6.3 / 4.0.5 / 4.2.3 / 4.3.3 / 4.4.2 / 4.5.1), two-kernel architecture (ark for modern, IRkernel for legacy), all 6 with full LSP via languageserver (latest CRAN for modern, PPM binary repos for legacy), renv environment isolation. R Run-from-file and R debugger remain Planned. |
| **5-WEB** (done) | Web language support: HTML/CSS/JSON syntax highlighting and LSP via vscode-langservers-extracted, VS Code-style completion icons, file editor polish |

All platform phases are complete. JavaScript integration (phases 1-7) is complete, HTML/CSS/JSON/YAML language support is complete, and R support is complete (kernel + LSP for all 6 R versions). Students and researchers can perform the full MLOps lifecycle - from data versioning to model deployment - in Python, JavaScript, R, and web languages without leaving noted. Seven languages have full LSP support: Python, JavaScript, R, HTML, CSS, JSON, YAML.
4. **Parameterized DAG trigger forms** (added to T-2.6): Lab 5 uses `Param`/`ParamsDict` — noted must render the form from the DAG's params schema
5. **Graceful task skip display** (added to T-2.14): Lab 5-P2 uses exit 99 — Pipeline Tab must show "skipped" state with distinct color

---

## 16. What This Document Does Not Cover

- Detailed API request/response schemas (to be defined during implementation)
- Architecture design principles and anti-patterns (see Architecture Principles document)
- UI wireframes and visual design (to be produced during development)
- CI/CD pipeline for noted itself (to be defined)
- Inline code completion (ghost-text) implementation (planned, see `documents/llm/llm08.md` Section 7)
- Security and authentication design (planned approach: OAuth2-Proxy at nginx layer, zero custom auth code)
- Cost estimation and resource procurement (separate discussion)
- Team assignment and individual workload (separate discussion)

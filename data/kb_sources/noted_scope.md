# noted - Integrated MLOps Platform Scope

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Product Scope                      |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 2.4                                |
| Date          | 2026-04-15                         |
| Status        | Draft                              |
| Related       | Vision Document v2.4               |
| Changes       | See [Changelog](#changelog) below                                                |

---

## Changelog

### v2.4

Final delivery milestone. **Model Serving Refactor shipped** - F-SRV-* features rewritten: Deploy / Unload / Try It three-button UX aligned with MLflow terminology (replaces "Publish / Try It" wording), streaming NDJSON progress from `/load` (resolving -> downloading -> loading_model -> ready phases), in-process `ModelLoader` correctness fixes (RLock full serialization, content-hash cache, early-return on same-version re-deploy, non-blocking try-acquire in unload), framework-specific VRAM cleanup gated on `sys.modules`. Logged Models (MLflow 3.x) exposed in the Registry version detail via new backend endpoints `GET /api/mlflow/runs/{run_id}/logged_models` and `GET /api/mlflow/logged_models/{experiment_id}/{model_id}/download`, with hljs-highlighted inline previews for MLmodel/conda.yaml/python_env.yaml/requirements.txt. Step-1 serving unblock (2026-04-15): dropped `protobuf<5.0.0` pin from `client/requirements.txt`, removed `_install_model_deps()` call from `_load_inner()`; baseline image now serves all registered model versions via MLflow warning-mode loading (verified v1-v7 of Jena Weather Forecaster). Phase 0b worker-subprocess architecture designed in `documents/serving_worker/serving_worker_plan.md` but deferred to post-demo since step-1 unblock eliminates the immediate crash vector. **jena_client Model Serving Client shipped** as a generic reference client at `iscte/jena_client/`: three-dropdown UI (Model/Version/Alias with `@champion` default), NDJSON streaming `load_model` handler, inverse scaler transform using `target_mean`/`target_std` logged as MLflow params, three-column prediction table (Hour / Temperature degC / Raw z-score) with scaler formula caption. **5-6 layer Lineage Chain** (Data/Config/[Pipeline]/Code/Run/Model) lit on every new Registry version via git-tagging instrumentation in `execution_bridge.py _log_hydra_bundle_for_run` (no more silent fall-throughs on `noted.git_commit` tagging). **jena_weather Tutorial 3 Level C** shipped: training block inlined into `config.yaml` (10 override inputs), second DVC dataset `jena_climate_2012.csv`, Airflow DAG `log_hydra_lineage` task, `target_mean`/`target_std` MLflow params. **User Manual 7 pages** published to Knowledge Base - Pages 1-5 refreshed as final user-facing documentation, Page 6 (Serving & Deploying Models) and Page 7 (noted Assistant) newly written. **NOTED_SETUP.md** added at repo root. Post-demo backlog entries captured in `documents/noted_backlog.md`: Phase 0b worker subprocess, MLflow soft-delete foot-gun, noted terminal child-process tracking, generic output rendering for non-regression models, UI timestamp audit.

### v2.3

Hydra Unification shipped - Configuration Composer (F-HYD-*) extended with Time Machine (Experiment Run mode), self-contained per-run Hydra bundles logged to MLflow artifacts, HydraSource abstraction (LocalSource/MlflowSource), in-memory cache, baseline badge (BASELINE/RUN xxxxxx with colored dot), stale metadata validation, schema refresh on Apply. Run Manager dataset section updated (read-only Hydra-derived row for Hydra-using notebooks). Evidently scope updated: T-5.4/T-5.5 partially shipped - evidently_quality (DataSummaryPreset) and evidently_drift (DataDriftPreset with run_id linkage) DAG tasks operational; Data Health dot and Evidently UI service tab shipped; quality gates (Test Suite), drift alert on Model nodes, RegressionPreset, and KG integration remain planned. Explorer UX: tree consolidation, root node detail pages removed, double-click expand, Knowledge Graph as KB tree child, KB document undocking.

### v2.2

R as third notebook language. Section 3.18 added (F-R-01 R Kernels, F-R-02 R Environment Management, F-R-03 R LSP, F-R-04 R Run from File Editor [Planned], F-R-05 R Debugger [Planned, Phase 3 deferred]). Six R versions supported simultaneously (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1). Two kernels: ark (Posit, Rust) for modern R 4.2-4.5, IRkernel (REditorSupport, the original Jupyter R kernel) for legacy R 3.6.3 / 4.0.5 because ark cannot drive R 3.x / 4.0 interpreters. ALL 6 R versions get full LSP via languageserver - latest CRAN for modern, era-matched PPM binary releases for legacy (PPM 2020-04-01 for R 3.6.3, PPM 2021-05-01 for R 4.0.5). RENV_CONFIG_EXTERNAL_LIBRARIES injected to expose system languageserver from inside renv envs. libicu66 from Ubuntu focal archive installed alongside libicu74 to satisfy stringi.so runtime linking for legacy R binary packages. Section 3.17.3 Out of Scope updated to remove R. End-to-end validated via 9-test walkthrough at testing/34_test-r-lsp-phase2.md. Seven languages with full LSP: Python, JavaScript, R, HTML, CSS, JSON, YAML.

### v2.1

YAML language support via yaml-language-server (Red Hat).

### v2.0

Web language support added. HTML/CSS/JSON syntax highlighting via @codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json. LSP for HTML/CSS/JSON via vscode-langservers-extracted (single-server mode - one server handles all three, unlike Python's dual ruff+jedi or JS's dual biome+tsserver). F-LSP-06 added. "Virtual Environments" renamed to "Environments" with Python/JS language grouping sub-nodes and VS Code color SVG icons. VS Code-style SVG completion icons in autocomplete dropdown. File editor improvements: Tab=4 spaces, Ctrl+Home/End, hover docs routed to Documentation panel only. JS notebook IIFE wrapping for const/let re-declaration fix with globalThis exports for cross-cell variable sharing. Clean startup with no panels open. dynamicRegistration forced false for all LSP init (codemirror-languageserver compatibility). rootUri rewrite for virtual-to-real filesystem paths in _init_server. Five languages with full LSP: Python, JavaScript, HTML, CSS, JSON. Verified test matrix at testing/33_test-language-support-matrix.md.

### v1.9

Multi-Language Support added as Section 3.17 (F-ML-01 through F-ML-05). JavaScript as first additional language via xeus-javascript kernel, fnm/pnpm environment management, typescript-language-server/Biome LSP, Strategy Pattern execution, TransportManager for ZMQ/TCP debug protocols. Evidently section 3.16.3 out-of-scope reference updated.

### v1.7

DAP Phase D4 added (F-DAP-06 Run Menu, F-DAP-07 Debug All Cells, F-DAP-08 Debug Stop Cleanup). Debug All Cells covers shadow file generation, filename injection, IPython-safe wrapper, cell map, cross-cell breakpoints, live breakpoint updates, and cell-boundary stepping.

### v1.6

Code Intelligence (LSP) added as Section 3.15 (F-LSP-01 through F-LSP-05). Debugging (DAP) added as Section 3.16 (F-DAP-01 through F-DAP-05).

### v1.5

All platform phases (0-4) completed. Jena Weather reference implementation added. AI Assistant consolidated as first-class feature (F-AI-01 through F-AI-10). Auto-tracking removed in favor of explicit Run Manager. DAG trigger enhanced with Hydra dropdowns.

### v1.4

Multi-notebook tab support. VS Code-style preview/pin tab behavior. F-DVC-07 refined as Run Manager Dataset Selection.

### v1.3

Academic use case requirements added.

### v1.2

UI layout redesigned as VS Code-like 4-column layout. Workspace tree expanded to all MLOps artifact categories. Phase 0 completed.

---

## 1. Purpose

This document defines the boundaries of what noted will and will not deliver. It enumerates every feature, integration, and technical component required to realize the vision described in the Vision document. It serves as the authoritative reference for what is "in scope" and what is explicitly excluded or deferred.

---

## 2. Existing Foundation

noted is not being built from scratch. The following capabilities already exist and are the foundation upon which all new work is built.

### 2.1 Current Application State

| Capability                          | Status    | Technology                                      |
|-------------------------------------|-----------|--------------------------------------------------|
| Single-container deployment         | Built     | Docker, FastAPI + Uvicorn serving API + static files |
| Notebook editing (nbformat 4)       | Built     | Vanilla ES6, CodeMirror 6, 7 editor themes       |
| Real-time collaboration             | Built     | Socket.io, cell-level locking with TTL (60s)     |
| Multi-runtime kernel execution      | Built     | jupyter_client, Python 3.10-3.14 + free-threaded |
| GPU acceleration                    | Built     | CUDA runtime, LD_LIBRARY_PATH injection          |
| Environment management              | Built     | Per-runtime venvs/envs, PTY-streaming package install, language grouping (Python/JS sub-nodes with VS Code color SVG icons) |
| Project organization                | Built     | Hierarchical projects/notebooks, external linking |
| Cell operations                     | Built     | Add, delete, move, copy/cut/paste, multi-select  |
| Markdown cells                      | Built     | Marked, Highlight.js, KaTeX math rendering       |
| Terminal                            | Built     | xterm.js with 10+ color themes, per-environment  |
| UI panels                           | Built     | jsPanel, Wunderbaum tree, Split.js               |

### 2.2 Existing Backend Managers

| Manager                  | Responsibility                                          |
|--------------------------|---------------------------------------------------------|
| NotebookManager          | CRUD for projects and .ipynb files                      |
| KernelManagerService     | Jupyter kernel lifecycle, one per client session, idle timeout (600s) |
| ExecutionBridge          | Socket.io <-> Jupyter ZMQ message bridge                |
| CollaborationManager     | Rooms, cell locks, presence, user join/leave broadcast  |
| EnvironmentManager       | Runtime-aware venv creation, package install/uninstall  |
| ExternalProjectsConfig   | Singleton; parses projects.txt at startup               |

### 2.3 Existing Socket.io Events

The following events are already implemented and form the foundation for new MLOps events:

**Client to Server (existing):**

| Event              | Description                              |
|--------------------|------------------------------------------|
| `notebook:open`    | Join a notebook editing session           |
| `notebook:close`   | Leave a notebook session                  |
| `notebook:save`    | Save notebook to disk                     |
| `cell:lock`        | Acquire editing lock on a cell            |
| `cell:unlock`      | Release cell lock                         |
| `cell:update`      | Broadcast source change to other users    |
| `cell:add`         | Add a new cell                            |
| `cell:delete`      | Delete a cell                             |
| `cell:move`        | Move a cell                               |
| `cell:execute`     | Execute cell code on the kernel           |
| `kernel:start`     | Start a kernel with a specific environment|
| `kernel:stop`      | Stop the active kernel                    |
| `kernel:restart`   | Restart the kernel                        |
| `kernel:interrupt` | Interrupt running execution               |
| `heartbeat`        | Keep-alive (renews locks, prevents timeout)|

**Server to Client (existing):**

| Event                   | Description                              |
|-------------------------|------------------------------------------|
| `notebook:state`        | Full state on notebook open              |
| `notebook:saved`        | Save confirmation                        |
| `cell:updated`          | Another user edited a cell               |
| `cell:added`            | Another user added a cell                |
| `cell:deleted`          | Another user deleted a cell              |
| `cell:moved`            | Another user moved a cell                |
| `cell:output`           | Streaming execution output               |
| `cell:execute_complete` | Execution finished                       |
| `cell:lock_changed`     | Lock state broadcast                     |
| `kernel:status`         | Kernel state change                      |
| `user:joined`           | User joined the notebook                 |
| `user:left`             | User left the notebook                   |
| `error`                 | Error notification                       |

### 2.4 Existing REST API

noted already exposes REST endpoints for projects, notebooks, runtimes, and environments. New MLOps endpoints will follow the same patterns and naming conventions. See PROJECT_STATUS.md for the full existing API surface.

### 2.5 Existing Infrastructure (Running)

| Service                        | Status    | Container Name                  |
|--------------------------------|-----------|---------------------------------|
| noted                          | Running   | noted                           |
| MinIO                          | Running   | noted-minio                     |
| MLflow 3.x                     | Running   | noted-mlflow                    |
| Airflow API Server (3.0)       | Running   | noted-airflow-apiserver         |
| Airflow Scheduler              | Running   | noted-airflow-scheduler         |
| Airflow Worker                 | Running   | noted-airflow-worker            |
| Airflow Triggerer              | Running   | noted-airflow-triggerer         |
| Airflow DAG Processor          | Running   | noted-airflow-dag-processor     |
| PostgreSQL                     | Running   | noted-postgres                  |
| Redis (Airflow-managed)        | Running   | noted-redis                     |
| nginx reverse proxy            | Running   | noted-nginx (local only via docker-compose.local.yml) |
| GPU (NVIDIA)                   | Available | Host-level, CUDA 13.1           |

---

## 3. Feature Scope by Domain

Each subsection defines a domain of functionality, the specific features within it, acceptance criteria, and the backend tools involved.

---

### 3.1 Object Storage Integration (MinIO)

**Purpose:** Provide persistent, versioned object storage accessible to all platform services.

#### 3.1.1 Features

**F-MINIO-01: Project Bucket Provisioning**
When a new noted project is created, the backend automatically creates a dedicated MinIO bucket (or prefix within a shared bucket) for that project. Bucket naming follows the pattern `noted-{project_id}`.

**F-MINIO-02: Artifact Store Configuration**
MLflow is configured to use MinIO as its artifact store. The backend sets `MLFLOW_ARTIFACT_ROOT` to `s3://noted-mlflow-artifacts/{project_id}/` with MinIO endpoint credentials.

**F-MINIO-03: DVC Remote Configuration**
Each project's DVC configuration points to MinIO as the remote storage backend. The remote URL follows `s3://noted-dvc/{project_id}/`.

**F-MINIO-04: Pre-signed URL Generation**
The backend generates time-limited pre-signed URLs for direct browser downloads of large artifacts (model files, datasets) without proxying the data through the noted API.

**F-MINIO-05: Storage Usage Display**
The UI shows per-project storage consumption (total bytes, object count) retrieved via the MinIO Admin API.

#### 3.1.2 Acceptance Criteria

- MLflow artifacts are retrievable from MinIO using standard S3 clients
- DVC push/pull operates against MinIO without manual credential configuration by the user
- Pre-signed URLs expire after a configurable TTL (default: 1 hour)
- Deleting a project archives (not deletes) its MinIO data with a configurable retention period

#### 3.1.3 Out of Scope

- MinIO cluster management (multi-node, erasure coding configuration)
- Bucket lifecycle policies beyond project-level retention
- Cross-region replication
- MinIO admin UI embedding

---

### 3.2 Data Versioning (DVC + Git)

**Purpose:** Track dataset versions with full lineage, enabling reproducible experiments without exposing Git complexity to users.

#### 3.2.1 Features

**F-DVC-01: Backend Git Repository Management**
Each project is backed by a bare Git repository initialized and managed by the noted backend. Users never interact with Git directly. The backend handles init, add, commit, tag, and branch operations programmatically via pygit2 or subprocess.

**F-DVC-02: DVC Initialization**
When a project is created, the backend runs `dvc init` within the project directory and configures the MinIO remote. DVC configuration files (`.dvc/config`) are committed to the backend Git repo.

**F-DVC-03: Dataset Upload and Tracking**
When a user uploads a file to `data/raw/` via the UI:
1. File is written to the project directory
2. Backend runs `dvc add data/raw/{filename}`
3. Backend runs `dvc push` to store the file in MinIO
4. Backend commits the `.dvc` pointer file and `.gitignore` to Git
5. Backend creates a Git tag (e.g., `data-v1`) for the version

**F-DVC-04: Dataset Version Browser**
The Data panel in the UI displays:
- All tracked files with their current version number
- File size, last modified date, and derived-from lineage (if applicable)
- A version history per file (derived from Git tags/commits)
- Ability to select a specific version for use in the current session

**F-DVC-05: Version Switching**
When a user selects a different dataset version in the UI, the backend runs `git checkout {tag}` followed by `dvc checkout` to materialize the correct file versions in the working directory. The kernel is notified of the change.

**F-DVC-06: Processed Data Tracking**
When notebook cells produce output files in `data/processed/`, the backend can (optionally, user-triggered) run `dvc add` on those outputs, establishing a dependency chain: processed v1 derived from raw v1.

**F-DVC-07: Data Hash Injection into MLflow**
Whenever an MLflow run is created via the Run Manager, the backend injects the current DVC data hash as both an MLflow run tag (`dvc.data_hash`) and an MLflow parameter (`dvc_data_hash`). The parameter form enables filtering and searching runs by data version in the MLflow experiment table. This establishes traceability from model to data version.

**F-DVC-08: Collaborative Conflict Resolution**
When two users modify data simultaneously:
1. The backend uses a project-level lock (extending the existing CollaborationManager's cell-lock pattern) for Git operations
2. DVC operations are serialized per project
3. If a conflict occurs on a `.dvc` file, the backend resolves by accepting the latest push and notifying the other user
4. For non-standard Git/DVC errors (merge conflicts, lock contention, cache corruption), the UI shows a toast notification with the error description and an **"Open Terminal"** action button that opens xterm.js pre-navigated to the project directory (see Architecture Principles, P6: Terminal Escape Hatch)

**F-DVC-09: ProjectVersionControl Abstraction**
All Git and DVC operations go through a `ProjectVersionControl` service interface. This decouples the rest of the backend from the specific VCS implementation, allowing future migration to `--no-scm` mode or alternative backends.

#### 3.2.2 Acceptance Criteria

- Uploading a 500MB dataset completes within 60 seconds on the target server
- Version switching materializes the correct files without kernel restart
- Every MLflow run has a non-empty `dvc.data_hash` tag
- Two simultaneous uploads to the same project do not corrupt Git or DVC state
- The UI never displays Git concepts (commits, branches, refs) - only version numbers and dates

#### 3.2.3 Out of Scope

- User-facing Git operations (commit messages, branch management, merge UI)
- DVC pipeline definitions (`dvc.yaml`) authored by users in the UI (pipelines are Airflow's domain)
- `dvc repro` triggered from the UI (deferred to future iteration)
- DVC metrics and plots (MLflow handles metrics; DVC is for data only)
- Git hosting or remote push to GitHub/GitLab

---

### 3.3 Experiment Tracking (MLflow)

**Purpose:** Record, compare, and analyze ML experiment results with full provenance.

#### 3.3.1 Features

**F-MLF-01: MLflow Server Configuration**
The existing MLflow 3.x Tracking Server (container `noted-mlflow`) is configured with:
- PostgreSQL as the backend store (metadata) - uses the existing `noted-postgres` instance with a dedicated `mlflow` database
- MinIO as the artifact store (models, plots, data samples)
- Accessible only via the noted backend on the Docker internal network

**F-MLF-02: Experiment-Project Mapping**
Each noted project maps to exactly one MLflow Experiment. The experiment is created when the project is created. The mapping is stored in `project.json`.

**F-MLF-03: Kernel Environment Injection**
When a kernel starts for a project (via the existing `kernel:start` Socket.io event), the KernelManagerService injects environment variables:
- `MLFLOW_TRACKING_URI` - pointing to the MLflow server (Docker internal URL)
- `MLFLOW_EXPERIMENT_NAME` - set from project metadata
- `MLFLOW_RUN_TAGS` - JSON containing project_id, notebook name
- Existing `LD_LIBRARY_PATH` injection for CUDA is preserved

This enables explicit mode without any user configuration.

**F-MLF-04: Explicit Instrumentation Support**
Users write standard MLflow API calls in notebook cells. The backend does not intercept or modify these calls. MLflow is available as a default dependency in ML-oriented environments (installed via the existing EnvironmentManager).

**F-MLF-05: Run Manager with Framework Autologging**
MLflow experiment tracking is managed exclusively through the Run Manager:
1. Users define named runs and assign cells (individually or via "Select All")
2. On Execute Run, the backend wraps the cell sequence with `mlflow.start_run()`/`mlflow.end_run()`
3. Post-execution: detects ML frameworks (PyTorch, scikit-learn, TensorFlow, XGBoost, LightGBM) and activates autologging
4. Runs are tagged `instrumentation: experiments`
5. Individual cell execution (outside Run Manager) has no MLflow overhead

This cleanly separates exploration (free cell execution) from experimentation (intentionally tracked runs).

**F-MLF-06: Live Metrics Streaming**
During training, metrics logged via MLflow are intercepted by the backend (via polling the MLflow API or a callback mechanism) and pushed to the frontend via Socket.io. The Experiments sidebar shows:
- Current run name and status
- Live-updating metric charts (loss, accuracy, MAE, etc.)
- Epoch/step counter

**F-MLF-07: Run List and Filtering**
The Experiments panel displays all runs for the current project with:
- Run name, status (running/completed/failed), start time, duration
- Key metrics (configurable per project)
- Tags including instrumentation mode, data version hash, Hydra config hash
- Filtering by status, date range, metric thresholds, and tags
- Sorting by any metric or timestamp

**F-MLF-08: Run Comparison**
Users can select 2-5 runs and view:
- Overlaid metric charts (e.g., loss curves on the same axes)
- Parameter diff table (highlighting differences)
- Hydra config diff (if both runs have config snapshots)
- Data version comparison (same or different DVC hash)

**F-MLF-09: Artifact Browser**
Within a run's detail view, users can browse artifacts stored in MinIO:
- Model files with download links (pre-signed URLs) — supports PyTorch `.pt2` models, Prophet binary artifacts, and other framework-specific formats
- Plots and images rendered inline (PNG, JPEG, SVG)
- HTML artifacts rendered in a sandboxed iframe — supports Plotly interactive charts (e.g., forecast-vs-actuals plots)
- Log files viewable in a text panel
- Hydra config snapshots viewable as formatted YAML

**F-MLF-10: GenAI Tracing (MLflow 3.x)**
For projects using LLM-based workflows:
- The Experiments panel can display MLflow traces showing prompt-response chains
- Trace visualization includes latency per step, token counts, and retrieval context
- This is a read-only view of data logged by the user via MLflow's tracing API

#### 3.3.2 Acceptance Criteria

- Metrics appear in the UI sidebar within 2 seconds of being logged in the kernel
- Run comparison loads within 3 seconds for runs with up to 10,000 logged metric steps
- Run Manager correctly starts and ends MLflow runs, with framework autologging activated at run completion
- Individual cell execution outside Run Manager has no MLflow side effects
- All artifacts are accessible via pre-signed URLs without the user needing MinIO credentials

#### 3.3.3 Out of Scope

- MLflow Projects (noted has its own project model)
- MLflow UI embedding or direct access (all interaction through noted UI)
- MLflow AI Gateway / LLM routing (evaluated separately)
- Custom MLflow plugins
- Multi-experiment views (cross-project comparison)

---

### 3.4 Configuration Management (Hydra + OmegaConf)

**Purpose:** Enable structured, validated, swappable configuration for ML experiments without hardcoding parameters.

#### 3.4.1 Features

**F-HYD-01: Config Directory Convention**
Each project has a `config/` directory following Hydra's config group structure. The directory layout defines the available configuration options:
```
config/
    config.yaml          # defaults list
    model/
        gru.yaml
        transformer.yaml
    data/
        jena.yaml
    training/
        default.yaml
```

**F-HYD-02: Structured Config Validation**
Projects can define Python dataclasses (in `src/`) as OmegaConf Structured Configs. The backend uses these to validate configuration values at the type level before any execution occurs.

**F-HYD-03: Config Editor UI**
The Config panel renders a dynamic form based on the project's Hydra config structure:
- Config groups appear as dropdowns (e.g., model: GRU | Transformer)
- Selecting a group dynamically renders that group's fields
- Numeric fields validate type constraints from Structured Configs
- String fields with known enum values render as selects
- Nested configs render as collapsible sections

The form generates a set of Hydra CLI overrides (e.g., `model=transformer model.n_heads=8`).

**F-HYD-04: Config Composition via Backend**
The backend uses `hydra.compose()` to assemble a complete configuration from the user's selections. This composed config is:
- Validated against Structured Configs
- Displayed as a read-only YAML preview before execution
- Logged as an MLflow artifact when a run starts
- Passed as CLI overrides when triggering Airflow DAGs

**F-HYD-05: Config Versioning**
When a run executes with a specific Hydra config, the exact composed YAML is:
1. Saved in the Hydra `outputs/` directory (automatic Hydra behavior)
2. Logged as an MLflow artifact
3. Hashed and stored as an MLflow run tag (`hydra.config_hash`)
This enables config-to-model traceability.

**F-HYD-06: Config Templates**
Users can save a specific configuration as a named template (stored in `config/templates/`). Templates appear in the Config panel as quick-select options for common experiment setups.

**F-HYD-07: Sweep Configuration**
The Config panel supports defining Hydra multirun sweeps:
- Users specify ranges or lists for parameters (e.g., `learning_rate: 0.001, 0.01, 0.1`)
- The UI previews the total number of combinations
- Sweep configs are passed to Airflow for distributed execution (Phase 3)

#### 3.4.2 Acceptance Criteria

- Config form renders correctly for configs with up to 3 levels of nesting
- Type validation catches mismatches (string in int field) before execution
- Config composition completes within 500ms
- Config hash is deterministic: same selections always produce the same hash
- Changing a config group in the UI updates dependent fields within 200ms

#### 3.4.3 Out of Scope

- Visual config graph editor (connections between config nodes)
- Config inheritance visualization
- Hydra plugin management (Sweeper plugins like Optuna are CLI-configured)
- OmegaConf custom resolvers defined through the UI

---

### 3.5 DAG Orchestration (Airflow)

**Purpose:** Execute ML workflows as production-grade, scheduled, monitored pipelines.

#### 3.5.1 Features

**F-AIR-01: Airflow Service Integration**
The existing Airflow 3.0 deployment (already running) consists of:
- API Server (`noted-airflow-apiserver`) - REST API endpoint
- Scheduler (`noted-airflow-scheduler`)
- DAG Processor (`noted-airflow-dag-processor`)
- Celery Worker (`noted-airflow-worker`)
- Triggerer (`noted-airflow-triggerer`)
- PostgreSQL backend (shared with MLflow, `noted-postgres`)
- Redis broker (`noted-redis`, Airflow-managed)

The Airflow web UI remains accessible for admin use only (not exposed to noted users).

**F-AIR-02: DAG Management**
noted supports two DAG authoring modes:

*Generated DAGs:* The backend generates Airflow DAG Python files from project metadata:
- Entry point: `src/train.py` (or user-configured script)
- Parameters: serialized Hydra config overrides
- Data step: `dvc pull` to ensure correct dataset version on the worker
- Training step: execute the entry point with Hydra overrides
- Logging step: handled within the training script via MLflow

*User-authored DAGs:* Users write DAG files directly in the project's `dags/` or `pipelines/` directory using the Python file editor. This supports:
- Multiple DAGs per project (e.g., separate ingestion, training, and evaluation DAGs)
- BashOperator tasks with Hydra CLI override syntax (e.g., `python src/train.py model=lstm tracking.experiment_name=...`)
- Parameterized DAGs with `Param` and `ParamsDict` for Airflow UI form fields (date ranges, model selection dropdowns)
- Dynamic task generation from config directory scanning (e.g., iterating `conf/model/*.yaml` to create per-model tasks)
- Jinja templating in task commands (e.g., `{{ params.start_date }}`)
- Graceful task skipping via exit codes (e.g., `exit 99` for Airflow "Skipped" state)

All DAG files (generated or user-authored) are synced to the Airflow DAGs directory accessible by `noted-airflow-dag-processor`.

**F-AIR-03: Pipeline Trigger from UI**
The Pipeline panel provides a "Submit Pipeline" button that:
1. Lists available DAGs for the project (generated and user-authored)
2. For generated DAGs: validates the current Hydra config and generates/updates the DAG file
3. For parameterized DAGs: renders a trigger form from the DAG's `params` schema (text fields, date pickers, dropdowns), pre-filled with defaults
4. Calls the Airflow API Server to trigger a DAG run with params and/or Hydra config overrides
5. Returns a run ID for status tracking

**F-AIR-04: Pipeline Status Monitoring**
The Pipeline panel shows:
- A node graph of the DAG's task structure
- Real-time task state updates (queued, running, success, failed, skipped) via Socket.io
- Color-coded nodes matching Airflow's state conventions
- Task duration and timing information
- Ability to expand a task node to see its logs

**F-AIR-05: Task Log Streaming**
When a pipeline task is running, its stdout/stderr is streamed to the noted UI via Socket.io. The backend polls (or subscribes to) the Airflow log endpoint and forwards output to connected clients. This extends the same PTY-streaming pattern already used by the EnvironmentManager for package installation.

**F-AIR-06: Sweep Execution**
When a Hydra multirun sweep is configured (F-HYD-07), the backend generates a DAG with dynamic task mapping:
- Each parameter combination becomes a mapped task instance
- Airflow handles parallelism and retry logic
- The Pipeline panel shows individual sweep run status

**F-AIR-07: Pipeline History**
The Pipeline panel maintains a history of all DAG runs for the project:
- Run ID, trigger time, duration, final status
- Link to the corresponding MLflow runs generated during execution
- Ability to re-trigger a past run with the same or modified configuration

**F-AIR-08: Pipeline Scheduling**
Users can configure recurring schedules for pipelines:
- Cron expression or interval-based scheduling
- Schedule management (pause, resume, delete) from the UI
- Next run time display

#### 3.5.2 Acceptance Criteria

- DAG generation from project metadata completes within 5 seconds
- Pipeline trigger-to-first-task-start latency is under 30 seconds
- Task state updates appear in the UI within 3 seconds of state change
- Log streaming has less than 5 seconds latency from worker to UI
- A sweep of 20 configurations executes with correct parallelism (limited by worker count)
- Failed tasks show clear error messages in the UI without requiring Airflow UI access

#### 3.5.3 Out of Scope

- Airflow plugin management
- Airflow user/role management (handled at the infrastructure level)
- Cross-project DAG dependencies
- Sensor-based triggers (e.g., waiting for external events beyond MinIO notifications)
- Airflow UI embedding or direct user access

---

### 3.6 Model Registry and Governance (MLflow Registry)

**Purpose:** Version, alias, and govern trained models from experiment to production.

#### 3.6.1 Features

**F-REG-01: Model Registration from Run**
From a completed run's detail view, users can register the run's model artifact:
1. Select the model artifact from the run's artifact browser — supports all MLflow-compatible model flavors: `mlflow.pytorch` (PyTorch `.pt2` models), `mlflow.prophet` (Prophet binaries), `mlflow.sklearn`, `mlflow.tensorflow`, and `mlflow.pyfunc` (generic)
2. Assign a model name (or select an existing registered model)
3. The backend calls the MLflow Registry API to create a new model version
4. The version is automatically tagged with the run ID, data hash, and config hash

**F-REG-02: Models Panel**
The Models panel displays all registered models for the project:
- Model name
- All versions with: version number, creation date, source run link, key metrics, current alias
- Alias badges (`@staging`, `@champion`, `@archived`, or custom)
- Model description (editable)

**F-REG-03: Alias Management**
Users can assign or reassign aliases to model versions:
- Drag-and-drop or dropdown-based alias assignment
- Assigning `@champion` to a new version automatically removes it from the previous holder
- Alias changes are logged with timestamp and user for audit purposes
- Alias changes trigger a Socket.io event to notify connected clients

**F-REG-04: Model Lineage View (shipped)**
For any model version, the UI displays the full lineage as a stack of cards representing the end-to-end chain:

- **Data (DVC)** - dataset file path and DVC hash.
- **Config (Hydra)** - `noted.hydra_config_hash` of the resolved config used for training.
- **Pipeline (Airflow)** - DAG ID and DAG run ID, present only for runs produced by an Airflow pipeline.
- **Code (Git)** - full SHA and branch, captured at training time by the git-tagging instrumentation in `execution_bridge.py _log_hydra_bundle_for_run`.
- **Run (MLflow)** - source MLflow run (link jumps to the run's detail page in the Experiments tree).
- **Model (Registry)** - the version itself with its aliases.

Layers with no data render as "Not tracked" in grey. A complete chain means every component needed to reproduce the model is identified and addressable.

**F-REG-05: Model Comparison**
Users can select two model versions and compare:
- Metric differences
- Config differences (Hydra diff)
- Data version differences
- Architecture differences (if different model config groups)

**F-REG-06: Model Download**
Users can download any model version's artifacts via pre-signed MinIO URLs.

**F-REG-07: Experiment Snapshots**
Users can capture an immutable reproducible record of their best run within an experiment:
1. Click "Snapshot" on any completed run
2. Backend captures: git commit SHA, DVC file hashes, resolved Hydra config (as artifact), MLflow run ID, Python environment (pip freeze as artifact)
3. Creates a snapshot git branch: `snapshot/{experiment_name}_{version}`
4. Tags the MLflow run with `noted.snapshot=true` and all lineage metadata
5. Only one snapshot per experiment - setting a new one replaces the previous
6. Runs `dvc push` to ensure data is available in remote storage

**F-REG-08: Snapshot Restore**
Users can restore any snapshot to recreate the exact workspace state:
1. Click "Restore Snapshot" on any snapshot run or from the Snapshots view
2. Backend: `git checkout {snapshot_branch}`, `dvc checkout`
3. Explorer tree refreshes to show code/configs/notebooks from that state
4. Status bar shows current snapshot state
5. User can browse, inspect, and re-run the exact experiment

**F-REG-09: New Experiment from Snapshot**
Users can fork a new experiment from any snapshot:
1. Click "New Experiment from Snapshot"
2. Backend: restores snapshot, creates new git branch `experiment/{name}`, creates new MLflow Experiment
3. User is on a fresh branch ready to modify and run
4. Original snapshot remains untouched

**F-REG-10: Run Leaderboard**
Multi-run comparison table within an experiment:
- All runs shown in a sortable, filterable table
- Columns: run name, date, all metrics (sortable), all params, snapshot badge, data hash, config hash
- Highlight best metric value per column
- Export table as CSV
- "Compare selected" for 2+ checked rows

**F-REG-11: Experiment Report Export**
Generate a standalone experiment comparison report (PDF or Word):
- Experiment summary (name, total runs, date range)
- Ranked metrics table sorted by primary metric
- Metric convergence charts for top N runs
- Parameter comparison highlighting what changed
- Snapshot lineage info per run
- Generated via doco integration, no notebook involvement

#### 3.6.2 Acceptance Criteria

- Model registration completes within 5 seconds
- Alias reassignment takes effect within 2 seconds across all connected clients
- Lineage view loads within 3 seconds and displays all four lineage components
- Model versions list loads within 2 seconds for models with up to 100 versions

#### 3.6.3 Out of Scope

- Model approval workflows (multi-stage review gates)
- Model A/B testing infrastructure
- Model performance monitoring in production (drift detection)
- Automated promotion rules (e.g., auto-promote if metric exceeds threshold)
- Model deletion (only archival via alias)

---

### 3.7 Model Serving

**Purpose:** Deploy any registered MLflow model version into a FastAPI endpoint for testing and external consumption, operated through an explicit Deploy / Unload / Try It UX aligned with MLflow's own terminology.

**Status (2026-04-15):** Shipped. Phase 0a landed 2026-04-14 (three-button UX + streaming NDJSON progress + ModelLoader correctness fixes). Step-1 unblock landed 2026-04-15 (dropped `protobuf<5.0.0` pin, stopped runtime `_install_model_deps`, image baseline now serves all registered model versions via MLflow warning-mode loading). Phase 0b worker-subprocess architecture designed in `documents/serving_worker/serving_worker_plan.md` but deferred to post-demo since step-1 unblock eliminates the crash vector.

#### 3.7.1 Features

**F-SRV-01: Serving Container (shipped)**
A dedicated FastAPI service (`noted-serving`) runs alongside the noted stack:
- Exposes `/health` (current state), `/load` (streaming NDJSON), `/unload`, `/predict`, and `/schema` endpoints.
- Loads registered models from the MLflow Registry on demand. Exactly one model is deployed at a time; deploying a new version replaces the currently loaded one.
- Resolves MLflow 3.x Logged Model artifacts via `<experiment_id>/models/<model_id>/artifacts` scan, matched by run_id.
- Pre-installed frameworks: TensorFlow 2.21, PyTorch, scikit-learn, XGBoost, LightGBM.

**F-SRV-02: Deploy / Unload / Try It (shipped)**
Each registered model version card in the Registry detail view shows three controls:
- **Deploy** - streams NDJSON progress phases (`resolving` -> `downloading` -> `loading_model` -> `ready`) from the `/load` endpoint via `DeployEventStream` (backend) and `ModelDeployer` (frontend). The frontend parses the stream line-by-line using `ReadableStream.getReader()` + `TextDecoder` (no polling, no `setTimeout`).
- **Unload** - drops the current model from memory. Uses a non-blocking `RLock.acquire(blocking=False)` so concurrent unload during load refuses cleanly without deadlocking. Framework-specific VRAM cleanup runs in the unload path (`tf.keras.backend.clear_session`, `torch.cuda.empty_cache` + `torch._dynamo.reset`, `jax.clear_caches`), all gated on `sys.modules` so frameworks not in use are never imported.
- **Try It** - opens an input form derived from the model's signature with a **Generate Sample** button. Prediction output is rendered by schema type: line chart (time series), bar chart (class probabilities), scalar, table (DataFrame), or JSON tree.

State machine keeps "Deployed here" / "Deployed elsewhere" / "Not deployed" accurate across all version cards, updated via a `serving:model-changed` event.

**F-SRV-03: Logged Models (MLflow 3.x) visibility (shipped)**
Each version card exposes the MLflow 3.x Logged Model entity under **Artifacts > Logged Models**:
- Backend endpoints: `GET /api/mlflow/runs/{run_id}/logged_models` (scans `<exp_id>/models/` via MLflow artifact proxy REST API and matches by run_id) and `GET /api/mlflow/logged_models/{experiment_id}/{model_id}/download?path=...` (streams artifacts via the proxy HTTP endpoint, not `mlflow.artifacts.download_artifacts`, to avoid the noted backend's SQLite tracking URI constraint).
- Frontend tree shows the standard archived layout: `MLmodel`, `conda.yaml`, `python_env.yaml`, `requirements.txt`, and the framework-specific `data/` folder (for example `data/model.keras`).
- Inline previews with hljs syntax highlighting: `language-yaml` for MLmodel / conda.yaml / python_env.yaml, `language-plaintext` for requirements.txt.
- fa-brain icon rendered in Files grey (`#b0bec5`) via inline `setProperty('color', ..., 'important')` in `_recolorNode` so the Logged Models rows are visually distinct from the pink Registry rows.

**F-SRV-04: Serving Health Display (shipped)**
- `/health` response includes the currently loaded model name, version, run_id, load time, model_uri, framework, and parameter count.
- Status-bar pill in the main noted UI shows the current loaded model / version and updates every 10 seconds.

**F-SRV-05: External Client Integration (shipped)**
The serving container's HTTP API is consumable by any external client. A reference client ships at `iscte/jena_client/`:
- Generic **Model Serving Client** title (not jena-specific), with a dynamic subtitle showing `{model_name} v{version}`.
- Three dropdowns (Model / Version / Alias) populated from MLflow REST API (`registered-models/search`, `model-versions/search`, merged with `registered-models/get` for alias lists). Alias dropdown defaults to `@champion` when present, else `<no tag>`.
- Load button sends `{model_name, version}` (alias selection resolves to a version client-side so the wire contract stays unambiguous).
- NDJSON streaming `load_model` handler consumes `resp.aiter_lines()` and forwards progress events to the frontend as status updates; emits `model_loaded` on the terminal `{phase: "ready", result: {...}}` event.
- Inverse scaler transform: the frontend fetches `target_mean` / `target_std` from the run's MLflow params (logged by the training notebook), applies `value * std + mean` to predictions, and renders a three-column table (Hour / Temperature degC / Raw z-score) with the scaler formula in a caption above the table.

#### 3.7.2 Acceptance Criteria

- Warm deploy (cached model, same requirements) completes in under 1 second. **Verified 2026-04-15**: 0.09-0.13s per deploy across v1-v7 of Jena Weather Forecaster.
- Cold deploy (first load of a new model in the current container) completes in under 10 seconds for models up to 500 MB. **Verified**: 2-3 s for the 800 KB Keras GRU used in the demo.
- Prediction latency (excluding model inference) adds less than 50 ms overhead at the Try It panel.
- Deploy / Unload / Try It state machine stays consistent across all version cards for the same model, even after container restart.
- External clients can enumerate registered models + versions + aliases in one request chain without requiring a noted UI session.

#### 3.7.3 Out of Scope

- **Simultaneous multi-model serving in a single container**. One model at a time per `noted-serving` instance. Phase 0b worker-subprocess architecture would enable a worker pool with hash-based routing but is deferred to post-demo.
- Batch prediction endpoints (the current `/predict` is single-request).
- Model serving autoscaling.
- External-facing authenticated prediction APIs (the current endpoint is internal to the noted Docker network; any external client runs on the same network).
- Serving framework alternatives (TorchServe, TF Serving, Triton).
- Load balancing across multiple serving replicas.
- Automated A/B traffic splitting between champion and challenger.

---

### 3.8 Collaborative Features (Extensions to Existing)

**Purpose:** Extend noted's existing collaboration model to cover all new MLOps domains.

#### 3.8.1 Features

**F-COL-01: Shared Experiment Visibility**
All collaborators on a project see the same Experiments sidebar. When one user starts a run, all connected users see it appear in real-time. This extends the existing CollaborationManager's room-based broadcasting.

**F-COL-02: Shared Pipeline Status**
Pipeline submissions and task state changes are visible to all connected project collaborators.

**F-COL-03: Shared Model Registry View**
Model registration and alias changes are reflected immediately for all connected users.

**F-COL-04: Activity Feed**
A lightweight activity log showing recent actions across all domains:
- "{User} uploaded dataset v3"
- "{User} started run #42 (GRU, lr=0.01)"
- "{User} promoted JenaForecaster v5 to @champion"
- "{User} triggered pipeline sweep (12 configs)"

**F-COL-05: Concurrent Data Upload Serialization**
When multiple users upload data simultaneously, operations are serialized per project to prevent Git/DVC conflicts. Users see a queue indicator.

#### 3.8.2 Acceptance Criteria

- Events propagate to all connected clients within 2 seconds
- Activity feed displays the 50 most recent actions per project
- No data corruption under concurrent operations from up to 5 simultaneous users

#### 3.8.3 Out of Scope

- Role-based access control (viewer, editor, admin per project)
- Approval workflows for model promotion
- Commenting or annotation on runs, models, or data versions
- Notification system (email, Slack integration for events)

---

### 3.9 UI Layout

**Purpose:** Define the spatial organization of all features within the noted interface.

#### 3.9.1 Layout Structure

The UI adopts a VS Code-like 4-column layout:

```
+----+----------+------------------------------------+----------+
|    |          |  Tab Bar                           |          |
| I  | Workspace|  [notebook.ipynb ×] [model.py ×]   |  Chat    |
| C  | Explorer |  [MLflow ×]                        |  Panel   |
| O  |          |------------------------------------| (AI      |
| N  | Projects |  Center Pane                       |  Assist) |
|    |  └ my-pr |  (active tab content)              |          |
| B  | Envs     |                                    |          |
| A  | Storage  |  - notebook editor                 |          |
| R  | Pipelines|  - Python file editor              |          |
|    | Models   |  - service UI iframe               |          |
|    | APIs     |  - detail view (runs, lineage...)  |          |
+----+----------+------------------------------------+----------+
|  Status Bar: Kernel | Pipeline | Storage                      |
+--------------------------------------------------------------+
```

**Icon Bar** (leftmost): Narrow vertical strip with icons for each Workspace category. Toggles the Workspace Explorer sidebar and selects the active section. Always visible.

**Workspace Explorer**: Collapsible tree panel showing all platform artifacts:
- Projects (existing: hierarchy with notebooks and files)
- Environments (existing: Python, JavaScript, and R runtime management, with language grouping sub-nodes)
- Storage (MinIO bucket browser — Phase 1B)
- DAGs (Airflow DAGs with status — Phase 2)
- Models (MLflow Registry with versions — Phase 3)
- APIs (deployed model endpoints — Phase 3)

Replaces the previous floating modal (jsPanel) Explorer. Categories are populated incrementally across phases.

**Center Tabbed Pane**: Primary content area with multiple tab types:
- Notebook tabs (existing notebook editor)
- Python file tabs (CodeMirror-based text editor for project satellite files like model.py, utils.py — edit and save, no execution UI). Also supports JavaScript, HTML, CSS, and JSON files with language-specific syntax highlighting.
- Service UI tabs (MLflow, Airflow, MinIO web UIs as iframes)
- Detail view tabs (experiment runs, model lineage, pipeline graphs, data browsers — opened from Workspace tree clicks)

**Chat Panel** (rightmost): AI assistant, collapsible, unchanged from current.

All side elements are independently collapsible. The center pane resizes relative to sidebar and chat panel using existing Split.js patterns.

#### 3.9.2 Panel Behavior

- Icon bar is always visible (narrow, minimal space)
- Workspace Explorer is collapsible — icon bar click toggles it
- Chat panel is collapsible — toolbar button toggles it
- Center pane tabs support: close, reorder (drag), and restore on session reload
- Tab state (open tabs, active tab, tab order) persists per user per project (localStorage)
- Workspace tree loads categories lazily — only fetch data when a section is expanded
- Detail view tabs are opened by tree item clicks and can be closed independently
- Service UI tabs (MLflow, Airflow, MinIO) are singleton — clicking the tree icon focuses the existing tab or creates one

#### 3.9.3 Acceptance Criteria

- Panel expansion/collapse animates within 200ms
- Switching between panels does not trigger data refetch if data is fresh (client-side cache with TTL)
- Layout is functional at viewport widths down to 1280px
- All panels are keyboard-navigable

---

### 3.10 Knowledge Graph

**Purpose:** Provide a navigable 3D visualization of all noted entities and their relationships, serving as a unified navigation and discovery layer across the entire platform.

#### 3.10.1 Features

**F-KG-01: Entity Discovery**
The Knowledge Graph scans all data sources (MLflow, DVC, Hydra, Airflow, file system) and presents every managed entity as a graph node. Entity types include: projects, notebooks, files, experiments, runs, snapshots, models, model versions, data files, data versions, configs, config groups, config options, DAGs, DAG tasks, DAG runs, environments, and tags.

**F-KG-02: Relationship Mapping**
Directed edges connect entities based on their relationships: contains, produces, belongs_to, uses_data, uses_config, executed_by, snapshot_of, version_of, tagged_with, derived_from, and others. Relationships are resolved automatically from entity properties.

**F-KG-03: Perspective Views**
The graph supports multiple built-in perspectives that filter and emphasize different entity types and relationships:
- **Lineage**: data -> config -> run -> model (hierarchical left-to-right)
- **Performance**: runs clustered by experiment, colored by metric value, sized by metric magnitude
- **Versioning**: data versions, model versions, snapshots on a timeline
- **Pipeline**: DAG task structure with state coloring
- **Project Overview**: radial layout with project at center
- **Tag-Based**: entities clustered by user-selected tags

Users can create and save custom views per project.

**F-KG-04: Search**
A global search bar queries across all entity types by name, property value, tag, metric threshold, file path, or date. Results appear as a dropdown list and center the 3D graph on the selected entity with a highlight effect.

**F-KG-05: Tags as Taxonomy**
Key-value tags can be attached to any entity. Tags are both user-defined and auto-generated (e.g., `noted.snapshot`, `dvc.data_hash`, `hydra.config_hash`, `airflow.dag_id`). Tag-based navigation shows all entities sharing a tag, with support for multi-tag intersection.

**F-KG-06: Bidirectional Explorer Integration**
Every entity in the Explorer tree has a "Show in Graph" action. Clicking an entity in the 3D graph navigates to its detail in the Explorer. The Knowledge Graph panel can be opened from Explorer title bar, run detail, model detail, or data detail views.

#### 3.10.2 Acceptance Criteria

- Graph builds and renders within 5 seconds for projects with up to 500 entities
- Search returns results within 2 seconds
- View switching animates smoothly (nodes reposition, new nodes fade in, removed nodes fade out)
- Entity click navigates to the correct Explorer detail view
- Custom views persist across sessions

#### 3.10.3 Out of Scope

- Semantic search / RAG-based querying (deferred to future)
- Historical graph comparison (graph diff between snapshots)
- Real-time graph streaming (graph rebuilds on request, not continuously)
- Cross-project graph views

### 3.11 Requirements Gap Recovery

**Purpose:** Address remaining requirements from the original spec documents (noted_dvc.md, noted_mlflow.md, noted_hydra.md, noted_airflow.md) that have not yet been implemented.

#### 3.11.1 Must-Have Features

**F-GAP-01: Hydra Config Selector**
Dropdown in the notebook second bar to select active Hydra config profile. Lists config groups with options. Selection stored in notebook metadata. Resolved config injected into kernel environment on cell execution.

**F-GAP-02: New DAG from Template**
Right-click context menu in DAGs section or project dags/ folder offers template-based DAG creation: blank, single-task, data pipeline, training pipeline. Generates a valid Python DAG file with standard Airflow decorators.

**F-GAP-03: Active Run Indicator**
Visual indicator in the notebook second bar showing the current active MLflow run (name, experiment, live status). Green dot while running, click navigates to run in Experiments tree.

#### 3.11.2 Should-Have Features

**F-GAP-04: Config as CLI Overrides**
Pass Hydra config overrides as command-line arguments for scripts using @hydra.main.

**F-GAP-05: Leaderboard Config Filter**
Filter runs in the leaderboard by config parameter values.

**F-GAP-06: Pipeline Config Templates**
Pre-fill trigger panel with last successful run's config. "Re-run with same config" button.

**F-GAP-07: Run as Pipeline from Notebook**
Button in notebook bar to trigger the associated DAG with current config.

**F-GAP-08: Log Viewer Actions**
Copy log to clipboard and retry failed task buttons in the task log viewer.

#### 3.11.3 Nice-to-Have Features (18 items)

DVC per-file sync icons, post-run summary toast, pinned metrics, epoch progress bar, "Log to MLflow" context menu, predict cell template, APIs workspace section, bulk run management, promote best config, config inheritance view, dynamic task display, notebook-to-DAG conversion, DAG validation, jump to error in logs, visual cron builder, data-aware triggering, template runs, pipeline health indicators.

Full inventory and status tracked in `documents/requirements_tracker.md`.

---

### 3.12 Advanced Features (Phase 5)

**Purpose:** Extend the platform with advanced analysis, governance, onboarding, data quality, production observability, and collaboration capabilities.

#### 3.12.1 Features

**F-ADV-01: Impact Analysis via Knowledge Graph**
Right-click any entity in the Knowledge Graph or Explorer and select "What breaks if I change this?". The backend performs a directed BFS on downstream edges from the selected entity. Returns a list of affected runs, pipelines, models, and other dependent entities. Results are highlighted in the 3D Knowledge Graph view.

Acceptance criteria:
- BFS traversal returns correct downstream dependencies for any entity type
- Results render within 3 seconds for graphs with up to 500 entities
- Affected entities are visually highlighted in the 3D graph

**F-ADV-02: Automated Model Cards**
Generate structured Model Card documents from lineage data (data hash + config + code + metrics). Uses the existing DocumentConverter pipeline. Accessible via a "Generate Model Card" action on the model version detail page. Includes model description, intended use, training data provenance, evaluation metrics, ethical considerations template, and full lineage chain.

Acceptance criteria:
- Model card generated as downloadable Word document within 5 seconds
- All lineage fields populated from MLflow run, DVC, Hydra, and git data
- Missing lineage components shown as "Not tracked" rather than omitted

**F-ADV-03: Project Templates**
"New Project" wizard with pre-configured templates: LLM Fine-tuning, Time-series Forecasting, Computer Vision. Each template includes a Hydra config structure, starter DAG definition, example notebook, and virtual environment setup script.

Acceptance criteria:
- Template creates a fully functional project with working Hydra configs
- Example notebook executes without errors on a fresh environment
- At least 3 templates available (LLM, time-series, CV)

**F-ADV-04: Data Validation and Quality Gates (Evidently)**
Integrate Evidently for data quality validation and pre-pipeline quality gates. Reports generated in DAG tasks using DataSummaryPreset and custom test conditions (min/max values, missing value share, row count). A "Data Health" badge appears in the Explorer tree for validated datasets, sourced from the Evidently workspace API. Replaces the previously planned Pandera approach with a richer, zero-config solution that also covers drift and monitoring (F-ADV-05). See `documents/noted_evidently.md` for full integration plan.

Acceptance criteria:
- Evidently data quality report generated in pipeline tasks
- "Data Health" badge shows pass (green) or fail (red) in the Explorer tree
- Pre-pipeline test suite blocks execution on critical test failures

**F-ADV-05: Post-Deployment Observability (Evidently)**
Data drift detection and model performance monitoring via Evidently. Drift reports (DataDriftPreset) compare current data distributions against training data reference. Performance reports (RegressionPreset) track MAE/RMSE trends over time. noted surfaces lightweight status badges on model nodes in the Explorer tree; detailed dashboards and trend charts are viewed in the Evidently UI service tab. Replaces the previously planned custom monitoring panel. See `documents/noted_evidently.md` for full integration plan.

Acceptance criteria:
- Drift detection reports generated in evaluation pipeline tasks
- Drift/performance status badges on model nodes in the Explorer tree
- Evidently UI accessible as a service tab for detailed dashboards
- Anomaly events linked to training data and config via Knowledge Graph

**F-ADV-06: Hardware and Cost Profiling**
GPU utilization monitoring via `nvidia-smi` during training runs. Metrics (GPU memory usage, utilization percentage, temperature) logged as MLflow metrics. Displayed in the Live Metrics panel alongside loss curves.

Acceptance criteria:
- GPU metrics appear in Live Metrics panel during GPU-accelerated training
- Metrics logged to MLflow for post-hoc comparison across runs
- No measurable impact on training performance from monitoring

**F-ADV-07: Collaborative Feature Store**
"Feature Catalog" view in the Explorer tree. Users can register DVC-tracked files as verified features with descriptions and tags. Reuses the existing tags infrastructure from the Knowledge Graph service.

Acceptance criteria:
- Features registerable from DVC-tracked file context menu
- Feature catalog searchable by name, description, and tags
- Features visible across all projects sharing the same mount

### 3.13 Demonstration Pipeline - Jena Weather Forecasting

**Purpose:** Provide a complete, runnable reference implementation that validates all noted platform capabilities and serves as the primary demonstration for platform deliveries.

The Jena Weather Forecasting project is not part of the noted platform itself, but is the reference project mounted into noted that exercises every integration point. It lives in the team's external repository and is mounted via `docker-compose.mounts.yml`.

#### 3.13.1 Features

**F-DEMO-01: Modular Pipeline Scripts**
Four Python modules in `src/` implementing the ML pipeline stages: ingestion (load and validate CSV), preprocessing (resample, clean, standardize, split), training (GRU/Linear model with MLflow tracking), and evaluation (metrics computation, visualization, optional model registration).

**F-DEMO-02: Hydra Config Groups**
Hierarchical YAML configuration with model groups (`model/gru.yaml`, `model/linear.yaml`) and data groups (`data/default.yaml`). All hyperparameters, file paths, and data settings managed via config.

**F-DEMO-03: Airflow Training Pipeline DAG**
A 4-stage DAG (`ingest_data -> preprocess_data -> train_model -> evaluate_model`) using the Airflow 3.0 TaskFlow API. Parameterized with model type, epochs, learning rate, batch size, and optional model registration flag.

**F-DEMO-04: Demo Notebook**
A presentation-ready notebook that walks through the pipeline interactively, calling the modular scripts with live MLflow metrics streaming visible in the noted UI.

**F-DEMO-05: Pre-trained Model for Serving**
A GRU model trained on Jena Climate data, registered in MLflow Registry as "JenaWeatherGRU" with @champion alias, loadable by the `noted-serving` container for live prediction via the Try It panel.

#### 3.13.2 Acceptance Criteria

- Pipeline runs end-to-end both interactively (notebook) and automated (Airflow DAG)
- MLflow runs contain DVC data hash, Hydra config hash, and training metrics
- Snapshot captures the complete reproducible state
- Model serves predictions via the Try It panel
- Total demo notebook execution time under 3 minutes (with reduced epochs)

#### 3.13.3 Out of Scope

- PatchTST Transformer implementation (mentioned in project goals but not required for Tutorial 2)
- Multi-step forecasting (1-step ahead sufficient for demo)
- Production-grade hyperparameter optimization (Optuna sweep deferred)
- Real-time data ingestion from external APIs

### 3.14 AI-Powered Development Assistant

**Purpose:** Provide a context-aware AI assistant that understands the full MLOps workspace and can navigate, query, and modify it through natural language.

**F-AI-01: Chat Interface**
Streaming chat panel with token-by-token rendering, extended thinking blocks (collapsible), voice output support, copy code blocks, auto-scroll, and error cards. Undockable to a floating jsPanel. Chat history restores on page reload.

Acceptance criteria:
- Tokens stream to the UI within 500ms of the first generated token
- Thinking blocks render as collapsible sections, hidden by default
- Chat panel is dockable/undockable without losing conversation state

**F-AI-02: Dual-Mode Backend (Local + Cloud)**
Support both local LLM inference (Ollama, on-premises) and cloud API access (Anthropic Claude). Local mode keeps all data within the Docker network. Cloud mode sends workspace context to the Anthropic API.

Acceptance criteria:
- Local mode works without internet connectivity
- Cloud mode streams responses from the Anthropic API with real token counts
- Switching between modes preserves conversation history

**F-AI-03: Model Selector with Auth Gate**
Dropdown in the chat panel header listing available models. Cloud models (Claude Sonnet, Opus, Haiku) require an API key before use. Local models are available without authentication. Selected model persists per session.

Acceptance criteria:
- Model selector lists all available local and cloud models
- Selecting a cloud model without a stored API key triggers an auth prompt
- API key is stored server-side, never sent to the browser

**F-AI-04: Tool System (20+ Tools)**
Read tools (auto-execute): MLflow run details, experiment runs, run comparison, Airflow DAG status, task logs, DVC file listing, file contents, Hydra resolved config, Knowledge Graph search, scroll_to_cell. Write tools (require confirmation): update_cell, insert_cell. Tool loop supports up to 6 sequential tool calls per turn.

Acceptance criteria:
- Read tools execute automatically and return results to the LLM within the same turn
- Tool badges (orange pills) appear in the chat UI showing which tools were called
- Tool results are incorporated into the assistant's follow-up response

**F-AI-05: Write Tool Confirmation**
When the assistant proposes a write action (update_cell, insert_cell), a jsPanel with a diff preview appears. The user sees exactly what will change and clicks Apply or Reject. Pending actions expire after 5 minutes. Only the originating session can confirm.

Acceptance criteria:
- Diff panel shows old vs new content with syntax highlighting
- Apply executes the change and the assistant receives a success result
- Reject returns a rejection message and the assistant acknowledges it
- No write action executes without explicit user approval

**F-AI-06: Skills System**
36+ focused knowledge files in `data/skills/` with frontmatter (name, description, triggers, priority, max_tokens). Priority-1 skills auto-inject based on context conditions. Priority-2/3 skills loaded on demand via `get_skill` tool. Background skills (coding conventions, auto-instrumentation) hidden from the skill badge UI. New skills added by dropping a Markdown file - zero code changes.

Acceptance criteria:
- Skill registry appended to system prompt as a compact list (names + descriptions)
- Static skills inject when trigger conditions match (max 2000 tokens per turn)
- Dynamic skills load via tool call and return content as tool result
- Adding a new `.md` file to `data/skills/` makes it available on next startup

**F-AI-07: Context Assembly**
On every conversation turn, the backend assembles a fresh context snapshot: open notebook cells (in-memory, not from disk), selected cell index, kernel status, active MLflow run (metrics, params, tags), resolved Hydra config hash, DVC data hashes, active DAG ID. Context is injected as a structured system message.

Acceptance criteria:
- Context reflects the current editor state, not the last saved state
- Cell outputs longer than 2000 characters are truncated with a note
- Maximum 20 cells included regardless of notebook size

**F-AI-08: Conversation Memory**
Project-scoped, file-persistent conversation history keyed by client_id + project_id. Auto-compaction via LLM summarization when token budget threshold is reached. History survives container restarts.

Acceptance criteria:
- Conversations persist across page reloads and container restarts
- Compaction reduces history size while preserving key context
- Clear chat button wipes both frontend and backend state

**F-AI-09: Token Usage Tracking**
Real token counts from the Anthropic API (input tokens, output tokens) displayed per message. Local models show estimated counts.

Acceptance criteria:
- Cloud model responses show actual token usage from the API response
- Cumulative token usage visible in the chat panel

**F-AI-10: Buffered Follow-Up Responses**
After tool execution, the assistant's follow-up response is buffered and parsed before rendering to prevent raw JSON or tool-call markup from leaking into the chat UI.

Acceptance criteria:
- No `<tool_call>` blocks or raw JSON visible in the chat output
- Follow-up responses render cleanly after tool execution completes

**F-AI-11: MCP Server**
noted exposes its tool surface through the Model Context Protocol at `/mcp/`, enabling external AI clients (Claude Code, Claude Desktop, Cursor) to discover and invoke noted's tools without the noted UI. Streamable HTTP transport (mcp SDK v1.27.0), rate limiting (tiered token bucket), structured error taxonomy (-32001 to -32006), and feature toggle (`NOTED_MCP_ENABLED`). Failure-isolated: one-directional dependency, noted runs normally if MCP fails.
- Acceptance: external MCP client connects, calls `tools/list`, receives 25 tools; read-tier tool call returns real data; write-tier tool rejected with -32001.

**F-AI-12: Native Tool Calling**
Both LLM backends use their native tool calling mechanisms instead of text-based XML parsing. Anthropic uses `tools` array with `tool_use` content blocks. Gemma 4 uses native `<|tool_call>` tokens with a custom parser. MCP tool schemas are the single source of truth, converted to each backend's format automatically.
- Acceptance: Claude calls a tool via native `tool_use`, result fed back as `tool_result`; Gemma calls a tool via native tokens, parser extracts name and arguments correctly including multi-line content with quotes.

**F-AI-13: Dynamic Context Router**
Keyword-based domain classifier selects only relevant tool schemas per turn for Claude (typically 5-8 out of 25). Nine domains defined. Automatic retry when LLM calls an out-of-scope tool. Gemma receives all tools (small models need maximum visibility).
- Acceptance: Claude MLflow query receives only MLflow + always-included tools; out-of-scope tool call triggers transparent retry with expanded tool set.

**F-AI-14: Web Content Fetch**
`fetch_url` tool retrieves web content using Camoufox anti-detect Firefox browser (C++ TLS fingerprint spoofing). Singleton pattern for persistent browser instance. Session auto-refresh every 50 requests or 1 hour. Falls back to httpx. `web-fetch` skill guides analysis.
- Acceptance: LLM calls `fetch_url` with a URL, receives page text content, incorporates it into analysis.

**F-AI-15: Gemma 4 Thinking Mode**
Extended thinking for the local Gemma 4 model via `<|think|>` system prompt token. Output `<|channel>thought` blocks translated to `<think>` for the frontend. Gemma native tokens stripped from display.
- Acceptance: user enables thinking, Gemma produces collapsible reasoning blocks followed by answer.

#### 3.14.1 Out of Scope

- Inline ghost-text code completion in CodeMirror (planned, not yet implemented)
- Autonomous multi-step agents that act without per-action confirmation
- Fine-tuning or training custom models within noted
- Voice input (voice output is supported via `<voice>` tags)
- MCP external client API key management and settings UI (planned)
- MCP Resource Layer with `noted://` URI scheme (planned)
- KV cache persistence for local LLM (planned)

### 3.15 Code Intelligence (LSP)

**Purpose:** Provide IDE-grade linting, autocomplete, hover documentation, and navigation for Python, JavaScript, HTML, CSS, and JSON files and notebook cells without requiring an external editor.

#### 3.15.1 Features

**F-LSP-01: Ruff Linting**
Ruff language server provides linting and formatting for Python files and notebook cells. Notebook cells are presented to Ruff via Jupytext shadow files. The backend remaps Ruff's severity levels (Ruff reports everything as Error) to Error, Warning, or Info based on rule prefix. Lint diagnostics appear as CodeMirror decorations (underlines with severity colors) and in the Problems panel.

**F-LSP-02: Jedi Language Server**
Jedi provides autocomplete, hover documentation, and go-to-definition for Python files and notebook cells. Completions appear in CodeMirror's autocomplete popup. Hover documentation shows in a tooltip. Go-to-definition navigates to the target file and line.

**F-LSP-03: Documentation Panel**
A tab in the right pane displays docstrings for the symbol under the cursor. Documentation is rendered from reST to HTML using docutils with Water.css styling. Updates on cursor movement.

**F-LSP-04: Code Minimap**
A minimap widget in the file editor provides a bird's-eye view of the file with lint severity color markers (red for errors, yellow for warnings, blue for info). Click to scroll to the corresponding position.

**F-LSP-05: Code Problems Panel**
A bottom status bar pill displays aggregate error and warning counts. Clicking the pill opens a sortable diagnostics panel listing all lint issues across the current file with severity, message, line number, and rule code. Lint fix actions are available for both files and notebook cells, with a diff preview approval panel before applying changes.

**F-LSP-06: HTML/CSS/JSON Language Support**
Syntax highlighting for HTML, CSS, and JSON files via @codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json. Auto-completion, hover documentation, and linting provided by vscode-langservers-extracted (npm install -g). Uses a single-server architecture where one LSP server handles all three languages, unlike Python's dual-server (ruff + jedi) or JavaScript's dual-server (biome + tsserver) approach. VS Code-style SVG data URI icons in the autocomplete dropdown for all languages. dynamicRegistration forced to false for all LSP client initialization (codemirror-languageserver does not support dynamic registration). rootUri rewritten from virtual URIs to real filesystem paths in _init_server. Hover documentation is routed to the Documentation panel (not inline tooltip). File editor improvements: Tab inserts 4 spaces, Ctrl+Home/End navigate to file start/end. Five languages now have full LSP support: Python, JavaScript, HTML, CSS, JSON.

#### 3.15.2 Acceptance Criteria

- Ruff diagnostics appear within 1 second of file save or cell blur
- Jedi completions appear within 500ms of typing trigger characters
- Documentation panel updates within 500ms of cursor movement
- Minimap renders correctly for files up to 5000 lines
- Problems panel accurately reflects current diagnostics state
- HTML/CSS/JSON files have syntax coloring, auto-completion, documentation, and linting
- Completion icons display as VS Code-style SVG icons for all languages

#### 3.15.3 Out of Scope

- Inline ghost-text code completion (planned for Phase 5)
- Custom Ruff rule configuration per project (uses default ruleset)

---

### 3.16 Debugging (DAP)

**Purpose:** Provide interactive debugging for Python files and notebook cells with breakpoints, stepping, and variable inspection.

#### 3.16.1 Features

**F-DAP-01: Notebook Debugging**
Set breakpoints in notebook cells and debug with stepping and variable inspection. Uses ipykernel's built-in Debugger via the Jupyter control channel. A ControlChannelDispatcher implements single-reader dispatch for concurrent control channel access. Cell code is sent via dumpCell for temporary file creation. Auto-continue on last line prevents IOStream flush timeout.

**F-DAP-02: File Debugging**
Breakpoint gutter and Run/Debug dropdown for `.py` files. File execution uses `%run -i` through the kernel with real file paths (no dumpCell needed). Execution errors (ModuleNotFoundError, etc.) are forwarded as UI notifications. Outside-file detection auto-terminates when stopped in IPython internals. Smart continue checks for remaining breakpoints before terminating.

**F-DAP-03: Debug Toolbar**
A toolbar providing Continue (F5), Step Over (F10), Step In (F11), Step Out (Shift+F11), and Stop (Shift+F5) buttons. Current paused line highlighted with gold background. Run mode dropdown (chevron next to play button) to switch between Run and Debug execution modes.

**F-DAP-04: Debug Panel**
A tab in the right pane providing three sections during debug sessions: Variables (scopes and variables tree with lazy expansion for compound types), Call Stack (navigable frames - click to select and re-fetch variables, cross-file navigation opens file and jumps to line), and Breakpoints (checkbox enable/disable, trash delete, navigate on click). The panel is always available, showing breakpoints even without an active debug session.

**F-DAP-05: Breakpoint Gutter**
CodeMirror extension rendering red dot markers in the gutter. Click to toggle breakpoints. Breakpoints are maintained per file/cell and synchronized with the debug adapter.

**F-DAP-06: Run Menu and Debug UI**
Run menu in the menu bar with Run Cell, Run All, Debug Cell, Continue, Step Over, Step In, Step Out, Stop, and Toggle Breakpoint commands with keyboard shortcuts and isDebugging context. Debug icon (red bug) in the icon bar toggles the Debug panel in the right pane. Debug status pill (red) in the status bar during active debug sessions, clickable to open Debug panel.

**F-DAP-07: Debug All Cells**
Cross-cell debugging for notebooks. POST `/api/dap/debug-notebook` concatenates all code cells into a shadow file (`/tmp/noted_debug_<hash>.py`) with `# %%` markers and returns a line-to-cell mapping. Filename injection via `compile(code, shadow_path, 'exec')` makes debugpy see one unified file while cells execute individually through `kc.execute()`, preserving per-cell output. IPython-safe wrapper uses `transform_cell` for magics and `ast.Interactive` for the display hook (charts, dataframes render correctly). All breakpoints from all cells combined into a single `setBreakpoints` call on the shadow file. Live breakpoint updates during active sessions re-send to the debugger immediately. Cell-boundary stepping: F10 at end of cell sends continue and auto-advances to the next cell. Step throttling prevents rapid F10 from losing gold line tracking. Combined breakpoint+arrow marker (red arrow with rounded left edge) when paused at a breakpoint line.

**F-DAP-08: Debug Stop Cleanup**
Control thread deadlock fix: continue + disconnect sent via dispatcher BEFORE stopping dispatcher/event task. was_paused flag ensures continue is only sent if actually paused at a breakpoint. Ghost output filter (_debugAborted flag on cells) filters output and completion from cleanup's continue. Fallback kernel restart if continue/disconnect timeout. Independent ZMQ sessions: debug_kc and recreated main_kc use BlockingKernelClient.load_connection_file() for independent sessions.

**F-DAP-09: Terminal-Based File Debugging**
runInTerminal pattern for debugging standalone files with output visible in the terminal. The backend picks an available port and the frontend runs the debug command in a terminal instance. For Python: `debugpy --listen {port} --wait-for-client {file}` launches the file paused until the DAP client attaches. For JavaScript: `node --inspect-brk={port} {file}` launches Node.js paused at the first line, with vscode-js-debug attaching as the DAP adapter. Both languages share the same UX - the user sees program output directly in the terminal while breakpoints, stepping, and variable inspection work through the Debug panel.

#### 3.16.2 Acceptance Criteria

- Breakpoints can be set and hit in both notebook cells and Python files
- Step Over, Step In, Step Out execute within 500ms
- Variables panel displays correct values for primitive and compound types
- Call Stack updates on each stop event with correct file and line information
- Debug session terminates cleanly when Stop is pressed or execution completes
- Debug All Cells generates a correct shadow file with line-to-cell mapping
- Cross-cell breakpoints hit correctly in any cell during Debug All
- Cell-boundary stepping advances to the next cell without manual intervention
- Run menu commands are enabled/disabled based on isDebugging context
- Debug status pill appears during active debug and disappears on stop
- Live breakpoint changes during active session take effect immediately
- Terminal-based file debugging launches and attaches for both Python and JavaScript
- Program output is visible in the terminal during file debug sessions

#### 3.16.3 Out of Scope

- Remote debugging (debugging code running on a different host)
- Conditional breakpoints (break only when expression is true)
- Watch expressions panel
- Multi-thread debugging visualization
- Debugging non-Python languages beyond JavaScript (JavaScript debugging implemented in Section 3.17)

---

### 3.17 Multi-Language Support

**Purpose:** Extend noted beyond Python to support additional programming languages, starting with JavaScript/Node.js. Enable full-stack web application development (Python backend + JS frontend) within a single workspace.

#### 3.17.1 Features

**F-ML-01: JavaScript Kernel**
IJavascript kernel providing Jupyter-compatible JavaScript execution. IJavascript is an npm package that uses Node.js vm.runInThisContext for code evaluation (xeus-javascript only works in JupyterLite). Installed in the noted container alongside Python kernels. Kernel appears in the kernel picker with a JavaScript icon. Notebooks can be created with either Python or JavaScript kernels.

**F-ML-02: JavaScript Environment Management**
fnm (Fast Node Manager) for Node.js version management, mirroring Python's multi-runtime model. pnpm for package management with PTY-streaming install output (same UX as pip/uv). Integrated into the existing EnvironmentManager with a language-aware interface. Node.js environments appear in the Environments section of the Explorer tree. Python and JavaScript are displayed as language sub-nodes under Environments with VS Code color SVG icons.

**F-ML-03: JavaScript LSP**
typescript-language-server for autocomplete, hover documentation, and go-to-definition in JavaScript files and notebook cells. Biome for linting and formatting, replacing Ruff's role for JavaScript. Per-cell shadow files for JavaScript notebooks (.nb.cellN.js) prevent cross-cell parse error bleeding. Diagnostics appear in the Problems panel alongside Python diagnostics. JS notebook cells use IIFE wrapping to prevent const/let re-declaration errors, with globalThis exports enabling cross-cell variable sharing.

**F-ML-04: JavaScript Debugging**
Full DAP debugging for JavaScript notebooks and files using vscode-js-debug as a standalone DAP server (vendored). Multi-session TCP proxy with parent/child sessions - the parent session manages the debug adapter while child sessions attach to individual Node.js processes. For file debugging, --inspect-brk launches Node.js paused at the first line. For notebook debugging, an IIFE wrapper with a debugger; statement provides the sync point for attaching. Breakpoints, stepping, variable inspection - same UX as Python debugging. Debug All Cells supported via V8 sourceURL pragma for filename injection.

**F-ML-05: Transport Abstraction**
TransportManager providing a unified interface for debug protocol transport across languages. ZMQDebugTransport for Python/ipykernel (existing). TCP transport for vscode-js-debug with child session routing via startDebugging reverse request - the DAP server requests the client to start a child debug session, and the TransportManager routes messages to the correct session. Breakpoints cached on the parent session and replayed to the child when it attaches. Strategy Pattern: PythonStrategy and JavaScriptStrategy encapsulate language-specific execution wrapping, filename injection, and debug behavior. New languages are added by implementing a LanguageStrategy without modifying core infrastructure.

#### 3.17.2 Acceptance Criteria

- JavaScript notebooks can be created, edited, and executed with the IJavascript kernel
- Node.js versions can be installed and managed via fnm from the Environments UI
- npm packages can be installed via pnpm with live terminal output
- Autocomplete, hover docs, and linting work in JavaScript files and notebook cells
- Breakpoints can be set and hit in JavaScript notebooks and files
- Debug All Cells works for JavaScript notebooks with correct cell-boundary stepping
- TransportManager correctly routes debug traffic via ZMQ (Python) or TCP with child session routing (JavaScript)

#### 3.17.3 Out of Scope

- TypeScript kernel (TypeScript supported via typescript-language-server type checking only)
- Browser-based JavaScript debugging (only Node.js runtime)
- Languages beyond JavaScript and R in this section (Julia, C++ planned as future Strategy implementations; R has its own section 3.18)
- JavaScript-specific Run Manager integration (uses same Run Manager as Python)

---

### 3.18 R Language Support

**Purpose:** Make R a first-class notebook language alongside Python and JavaScript, with explicit support for both modern (4.2 - 4.5) and legacy (3.6.3, 4.0.5) R versions to serve academic reproducibility workflows where exact-version replication of 2018-2021 code matters.

#### 3.18.1 Features

**F-R-01: R Kernels (Two-Kernel Architecture)**
Six R versions installed in the noted Docker image (R 3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) via Posit's prebuilt Ubuntu 24.04 deb packages, each living at `/opt/R/<version>/`. Two kernel implementations are used per R version's compatibility:

- **ark** (Posit's Rust-based Jupyter kernel, single binary serving all R versions via `R_HOME` / `LD_LIBRARY_PATH` dispatch) for modern R 4.2.3 / 4.3.3 / 4.4.2 / 4.5.1. Selected because ark provides the richest feature surface (Positron-style data viewer hooks, plot manager, future DAP support in Phase 3) and is the kernel Posit is actively investing in.
- **IRkernel** (REditorSupport, the original Jupyter R kernel) for legacy R 3.6.3 and R 4.0.5. ark 0.1.250 cannot drive these interpreters - the R API surface ark expects (via libR.so dlopen) is from the R 4.x era and the older interpreters die during init, silently, before producing output. IRkernel is pure R + zeromq with stable cross-version bindings dating back to R 3.x, installed from PPM binary repos (PPM 2021-05-01 for R 4.0.5 yielding IRkernel 1.1.1; PPM 2020-04-01 for R 3.6.3 yielding IRkernel 1.1) so no compilation is needed - sidestepping the glibc 2.34 SIGSTKSZ trap that would block legacy testthat from compiling under modern Ubuntu.

The kernel choice is encoded per version in `data/runtimes/r/<version>/runtime.json` via the `kernel_cmd` field; modern R uses `["/usr/local/bin/ark", "--connection_file", ...]`, legacy R uses `["/opt/R/<version>/bin/R", "--slave", "-e", "IRkernel::main()", "--args", "{connection_file}"]`. From the user perspective the kernel choice is invisible - both implementations speak the standard Jupyter messaging protocol.

**F-R-02: R Environment Management (Option E Architecture)**
Per-env isolation via **renv**, with the renv library and lockfile redirected to noted-managed paths. The Option E architecture (validated through extensive design audit) sets:

- **cwd = project_root** (matches Python and JavaScript for consistency)
- `R_HOME` and `LD_LIBRARY_PATH` -> select the env's R version
- `R_PROFILE_USER` -> noted-managed `.Rprofile` in env_path that calls `renv::load(project = getwd())`
- `RENV_PATHS_LIBRARY` -> env's renv library (`<env_path>/renv/library`)
- `RENV_PATHS_LOCKFILE` -> env's renv.lock (`<env_path>/renv.lock`)
- `NOTED_PROJECT_ROOT` -> available to cells as `PROJECT_ROOT`

This is the only configuration that satisfies all four requirements simultaneously: project files visible to cwd, multiple R envs per project, working `renv::snapshot()` dependency scan, and no project root pollution beyond a 56-byte `renv/.gitignore`. Critical empirical findings: `R_LIBS_USER` is silently ignored when a `.Rprofile` runs `renv::activate()` so we **cannot** use it to redirect the library; ark also **suppresses** the standard `R_PROFILE_USER` loading so the noted-managed startup script must be passed via ark's `--startup-file` flag.

R envs appear in the Explorer's Environments section as a third sub-node alongside Python and JavaScript, with its own VS Code-style language icon. Each env shows the R version it targets and its package count.

**F-R-03: R LSP (languageserver) - All Six Versions**
Full LSP support via the `languageserver` R package (REditorSupport), in single-server mode (one server provides completion, hover, AND lintr-driven diagnostics, unlike Python's dual ruff+jedi). Modern R installs the latest CRAN release at image build time. **Legacy R installs era-matched binary releases from Posit Public Package Manager** (`/cran/__linux__/focal/<date>`):

- R 4.0.5 -> PPM 2021-05-01 -> languageserver 0.3.10
- R 3.6.3 -> PPM 2020-04-01 -> languageserver 0.3.5

The binary repo path bypasses two distinct source-install failures: R 3.6.3's PPM source dep resolution mismatch in the pkgload/withr/waldo cluster, and R 4.0.5's testthat catch.h glibc 2.34 SIGSTKSZ compile error. **Result: ALL 6 R versions get full LSP - no second-class versions.**

**`RENV_CONFIG_EXTERNAL_LIBRARIES`** (renv's native hook) is injected at LSP launch via `lsp_manager._resolve_runtime_env`, pointing at `/opt/R/<version>/lib/R/library` so renv appends the system library to `.libPaths()` AFTER `renv::load()`. This makes the system-installed languageserver visible from inside renv-isolated envs without polluting the user's renv lockfile. The same env var is also injected via `kernel_env` in legacy R runtime.json files because IRkernel runs as `R --slave -e ...` and goes through `.Rprofile`/renv too.

**libicu66** from Ubuntu's focal archive is installed alongside libicu74 in the Docker image because the 2020/2021-era PPM binaries link against `libicui18n.so.66` (used by stringi, a transitive dep of languageserver via lintr). Ubuntu 24.04 ships only libicu74 - the symbol versions are incompatible. The legacy .deb coexists cleanly with the modern one and adds ~30MB to the image.

The notebook bridge generates a `# %%` percent-format combined shadow file for R cells, with lintr diagnostics enriched as `<message> + R - <Label>` (e.g. `assignment_linter` becomes "R - Assignment"). Per-env LSP isolation uses `(project_id, env_name, server_type)` as the cache key so two R envs with different R versions in the same project don't share a single languageserver process.

**F-R-04: R Run from File Editor (Done)**
Per-env `bin/Rscript` shell wrapper launcher generated at env creation time via `env_post_create_files` (with `template: true` and `executable: true`). The launcher sets R_HOME, LD_LIBRARY_PATH, R_PROFILE_USER, RENV_PATHS_*, RENV_CONFIG_EXTERNAL_LIBRARIES, RENV_CONFIG_SYNCHRONIZED_CHECK=FALSE, and NOTED_PROJECT_ROOT, then execs the per-version Rscript. Frontend `app-file-editors.js` extension check extended to include `.r` files, with `isR` branch in runCmd resolving to `<env_path>/bin/Rscript <filename>`. Debug button shows a warning toast for R files ("R debugging is not yet available (Phase 3)"). Lazy-generation in `env_manager._ensure_post_create_files` regenerates missing or stale launchers for existing envs (mtime-based template upgrade detection).

**F-R-05: R Debugger (Phase 3 - Deferred)**
ark exposes a DAP, but only inside Positron - the public 0.1.250 release does not expose DAP outside Positron's process model. Phase 3 R debug is blocked on Posit either shipping a standalone DAP transport or noted reverse-engineering ark's internal DAP. Legacy R via IRkernel will **never** have debug because the IRkernel side never offered DAP. Decision deferred until ark's DAP story matures: ship debug only for modern R via ark when available, or wait for a unified R DAP solution.

#### 3.18.2 Acceptance Criteria

- Six R versions appear in the runtime registry and can each create envs
- An R notebook can be created, the kernel can be picked, and `cat("hello", R.version.string)` runs and produces the correct version string for all 6 R versions
- `library(jsonl` (with cursor inside the parenthesis) triggers an auto-completion popup showing `jsonlite` in any R notebook cell, on any R version, without Ctrl+Space
- Hovering a base R function (`cat`, `sum`, `paste`) shows the R help documentation in the Documentation panel
- A deliberately bad line `if (x = 1) cat("bad")` produces a wavy underline within ~3 seconds with the lintr message "use of `=` for assignment in if statement", labeled `R - Assignment`
- Switching the notebook kernel between two R envs of different versions spawns separate per-env languageserver processes with the right R version's env vars
- Closing and reopening a notebook tied to a kernel-only R version (if any are added later) does NOT spam ERROR logs per keystroke; one WARNING line per session is acceptable
- Cell-edit completion sees identifiers defined in OTHER cells of the same notebook session without requiring kernel restart
- Ctrl+Z inside a focused R cell does character-level undo via CodeMirror's history
- The Knowledge Base shows the same documents whether served from disk-canonical `documents/` or runtime `data/documents/`

#### 3.18.3 Out of Scope

- R 1.x / R 2.x support (no longer in regular use; ark and IRkernel both require at least R 3.x)
- R 3.x versions before 3.6.3 (older R versions have known security issues and PPM binary repos are sparser)
- Quarto rendering / preview (`.qmd` files get LSP and edit support, but rendering is deferred)
- R Markdown rendering (`.rmd` files same as Quarto)
- R script Run from file editor (Done, see F-R-04)
- R debugger (Planned, see F-R-05)
- shiny app preview / runtime
- knitr execution outside notebooks
- R-specific test runner UI (testthat works inside notebooks via cells)

---

## 4. Backend Service APIs

This section defines the API surface that the noted backend adds for MLOps features. All new endpoints follow the existing REST API patterns and are prefixed with `/api/`. Existing endpoints (projects, notebooks, runtimes, environments) remain unchanged.

### 4.1 Data Management

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| POST   | /api/projects/{id}/data/upload                    | Upload and DVC-track a file          |
| GET    | /api/projects/{id}/data                           | List tracked files with versions     |
| GET    | /api/projects/{id}/data/{path}/versions           | Get version history for a file       |
| POST   | /api/projects/{id}/data/checkout                  | Switch to a specific data version    |
| GET    | /api/projects/{id}/data/{path}/download           | Get pre-signed download URL          |

### 4.2 Configuration

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| GET    | /api/projects/{id}/config/schema                  | Get config structure for form generation |
| GET    | /api/projects/{id}/config/current                 | Get current composed config          |
| POST   | /api/projects/{id}/config/compose                 | Compose and validate config from overrides |
| GET    | /api/projects/{id}/config/templates               | List saved config templates          |
| POST   | /api/projects/{id}/config/templates               | Save current config as template      |

### 4.3 Experiments

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| GET    | /api/projects/{id}/experiments/runs               | List runs with filtering/sorting     |
| GET    | /api/projects/{id}/experiments/runs/{run_id}      | Get run detail (metrics, params, tags) |
| GET    | /api/projects/{id}/experiments/runs/{run_id}/artifacts| List run artifacts                |
| POST   | /api/projects/{id}/experiments/compare            | Compare selected runs                |

### 4.4 DAGs

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| POST   | /api/projects/{id}/pipelines/trigger              | Trigger a pipeline DAG run           |
| GET    | /api/projects/{id}/pipelines/runs                 | List pipeline run history            |
| GET    | /api/projects/{id}/pipelines/runs/{run_id}/status | Get task-level status                |
| GET    | /api/projects/{id}/pipelines/runs/{run_id}/logs/{task}| Get task logs                    |
| POST   | /api/projects/{id}/pipelines/schedule             | Create or update a schedule          |
| DELETE | /api/projects/{id}/pipelines/schedule             | Remove a schedule                    |

### 4.5 Model Registry

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| GET    | /api/projects/{id}/models                         | List registered models               |
| POST   | /api/projects/{id}/models/register                | Register a model from a run          |
| GET    | /api/projects/{id}/models/{name}/versions         | List versions of a model             |
| PUT    | /api/projects/{id}/models/{name}/versions/{v}/alias| Set alias on a version              |
| GET    | /api/projects/{id}/models/{name}/versions/{v}/lineage| Get full lineage for a version    |
| POST   | /api/projects/{id}/models/compare                 | Compare two model versions           |

### 4.6 Serving

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| GET    | /api/projects/{id}/serving/status                 | Get serving container health         |
| POST   | /api/projects/{id}/serving/predict                | Proxy prediction request             |
| GET    | /api/projects/{id}/serving/schema                 | Get input/output schema              |

### 4.7 AI Assistant

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| POST   | /api/llm/chat                                     | Main chat endpoint (SSE streaming)   |
| POST   | /api/llm/complete                                 | Single-turn code completion (JSON)   |
| GET    | /api/llm/health                                   | LLM backend connectivity status      |
| GET    | /api/llm/models                                   | List available models (local + cloud)|
| POST   | /api/llm/confirm                                  | Approve or reject a pending write action |
| POST   | /api/llm/auth                                     | Store API key for cloud models       |
| POST   | /api/llm/model                                    | Switch active LLM model              |
| GET    | /api/llm/skills                                   | List available skills with metadata  |
| GET    | /api/llm/skills/{name}                            | Get skill content and metadata       |

### 4.8 MCP Server (Model Context Protocol)

| Method | Endpoint                                          | Purpose                              |
|--------|---------------------------------------------------|--------------------------------------|
| POST   | /mcp/                                             | MCP Streamable HTTP endpoint (JSON-RPC: initialize, tools/list, tools/call) |

The MCP server uses the official `mcp` Python SDK v1.27.0 with Streamable HTTP transport. All 25 tools are exposed via `tools/list`. Read-tier tools execute immediately; write-tier tools are rejected with -32001 for external clients. Rate limiting enforced per session (read 30/min, write 10/min, workflow 3/min). Feature toggle via `NOTED_MCP_ENABLED` env var. See `documents/mcp/mcp_technical_architecture_notes.md` for the full architecture.

### 4.9 New Socket.io Events (MLOps)

These events extend the existing Socket.io event vocabulary:

| Event Name                  | Direction       | Payload                                   |
|-----------------------------|-----------------|-------------------------------------------|
| `metric:update`             | Server -> Client| run_id, metric_name, step, value, timestamp |
| `run:status`                | Server -> Client| run_id, status, timestamp                  |
| `pipeline:task_status`      | Server -> Client| pipeline_run_id, task_id, state, timestamp |
| `pipeline:task_log`         | Server -> Client| pipeline_run_id, task_id, log_line         |
| `data:version_created`      | Server -> Client| file_path, version, hash, timestamp        |
| `model:alias_changed`       | Server -> Client| model_name, version, alias, user, timestamp|
| `model:registered`          | Server -> Client| model_name, version, run_id, timestamp     |
| `serving:model_loaded`      | Server -> Client| model_name, version, load_time             |
| `activity:event`            | Server -> Client| user, action, details, timestamp           |

---

## 5. Infrastructure Scope

### 5.1 Docker Services

**Already running (no changes needed):**

| Service                | Container Name                  | Ports (internal) | Notes                         |
|------------------------|---------------------------------|------------------|-------------------------------|
| noted                  | noted                           | 8123             | Single container: API + frontend |
| mlflow-server          | noted-mlflow                    | 5000             | MLflow 3.x, tracking + registry |
| airflow-apiserver      | noted-airflow-apiserver         | 8080             | Airflow 3.0 REST API           |
| airflow-scheduler      | noted-airflow-scheduler         | -                |                                |
| airflow-worker         | noted-airflow-worker            | -                | Celery worker                  |
| airflow-triggerer      | noted-airflow-triggerer         | -                | Airflow 3.0                    |
| airflow-dag-processor  | noted-airflow-dag-processor     | -                | Airflow 3.0                    |
| minio                  | noted-minio                     | 9000, 9001       |                                |
| postgres               | noted-postgres                  | 5432             | Shared: MLflow + Airflow       |
| redis                  | noted-redis                     | 6379             | Airflow-managed Celery broker  |
| nginx                  | noted-nginx                     | 80, 443          | SSL termination, routing (local only via docker-compose.local.yml) |

**To be added:**

| Service                | Purpose                         | Notes                         |
|------------------------|---------------------------------|-------------------------------|
| model-server           | FastAPI model serving           | On-demand, per project        |
| knowledge-graph        | Knowledge Graph Service (Alpine + Python, port 5523) | Entity graph, search, perspectives |
| evidently              | Data quality, drift detection, model monitoring (port 8009->8000) | Evidently AI service, local workspace storage |

### 5.2 Network Architecture

```
[Internet]
    |
[nginx reverse proxy] (SSL termination)
    |
    +-- /noted/         -> noted:8123
    +-- /api/           -> noted:8123
    +-- /ws/            -> noted:8123 (Socket.io)
    +-- /admin/airflow/ -> airflow-apiserver:8080 (admin only)
    +-- /admin/minio/   -> minio:9001 (admin only)
```

All services are defined in the same Docker Compose file (`services/docker-compose.yml`) and share the default network. Only nginx is exposed externally.

### 5.3 Database Schema

PostgreSQL hosts separate databases within the shared instance (`noted-postgres`):
- `noted` - noted application metadata (projects, users, sessions) - to be created
- `mlflow` - MLflow tracking metadata (existing or to be confirmed)
- `airflow` - Airflow metadata (existing)

No cross-database queries. Services own their schemas exclusively.

### 5.4 Resource Requirements

| Service            | CPU   | RAM    | GPU  | Disk             |
|--------------------|-------|--------|------|------------------|
| noted              | 2     | 2GB    | Yes  | 10GB (projects)  |
| mlflow-server      | 1     | 1GB    | No   | Minimal          |
| airflow (all)      | 2     | 4GB    | No   | 5GB              |
| minio              | 1     | 2GB    | No   | Scales with data |
| postgres           | 1     | 2GB    | No   | 20GB             |
| redis              | 0.5   | 512MB  | No   | Minimal          |
| model-server       | 2     | 4GB    | Optional | Minimal       |
| evidently          | 0.5   | 512MB  | No   | 1GB (workspace) |
| **Total baseline** | **10** | **16GB** | - | **36GB+**    |

---

## 6. Technical Constraints

### 6.1 Compatibility Requirements

- **Airflow version:** 3.0 (already deployed and running)
- **MLflow version:** 3.x (already deployed and running)
- **DVC version:** 3.x with S3-compatible remote support
- **Hydra version:** 1.3+ with Compose API and Structured Config support
- **Python version:** 3.11+ for noted backend; 3.10-3.14 for project kernels (already supported)
- **Browser support:** Chrome/Edge 120+, Firefox 120+, Safari 17+
- **Frontend:** Vanilla ES6 modules (no build step, no framework)

### 6.2 Performance Constraints

- Socket.io event latency: under 2 seconds end-to-end
- API response time for read operations: under 1 second (p95)
- API response time for write operations: under 5 seconds (p95)
- Concurrent users per project: up to 5
- Concurrent projects with active kernels: up to 10
- Maximum dataset size for DVC tracking: limited by MinIO storage and network bandwidth, not by noted

### 6.3 Security Constraints

- No backend service (MLflow, Airflow, MinIO) is directly accessible from the browser
- All inter-service credentials are managed via Docker secrets or environment variables
- Pre-signed URLs have a maximum TTL of 1 hour
- CORS restricted to the noted frontend origin
- Authentication: currently open access (to be designed separately)

---

## 7. Dependencies and Risks

### 7.1 External Dependencies

| Dependency                | Risk Level | Mitigation                                    |
|---------------------------|------------|-----------------------------------------------|
| Airflow 3.0 API stability | Low        | Already deployed and running                  |
| MLflow 3.x Registry API  | Low        | Already deployed and running                  |
| DVC + pygit2 integration | Medium     | Subprocess fallback if pygit2 is problematic  |
| Hydra Compose API        | Low        | Mature and stable                             |
| MinIO S3 compatibility   | Low        | Battle-tested with MLflow and DVC             |
| Evidently API stability  | Low        | Pin Docker image version, verify on upgrade   |

### 7.2 Technical Risks

| Risk                                      | Impact | Likelihood | Mitigation                                  |
|-------------------------------------------|--------|------------|----------------------------------------------|
| Git corruption in backend-managed repos   | High   | Low        | Regular integrity checks, backup strategy    |
| Airflow worker cannot access project data | High   | Medium     | Shared volume mount or DVC pull in DAG       |
| MLflow autolog conflicts with user code   | Medium | Medium     | Detection logic, graceful fallback to explicit|
| Hydra compose fails on complex configs    | Medium | Low        | Validation layer, error reporting to UI      |
| Docker Compose resource exhaustion        | High   | Medium     | Resource limits per container, monitoring    |
| Socket.io event ordering across services  | Medium | Medium     | Sequence numbers, client-side reconciliation |
| Kernel session model vs project model     | Medium | Medium     | Clear mapping: one kernel per session, MLflow env per project |

---

## 8. Glossary

| Term              | Definition                                                              |
|-------------------|-------------------------------------------------------------------------|
| Artifact          | Any file produced by an ML run: model weights, plots, logs, configs     |
| Alias             | A named tag on a model version (e.g., @champion, @staging)              |
| Config Group      | A Hydra directory containing alternative YAML configs for one component |
| DAG               | Directed Acyclic Graph - Airflow's representation of a pipeline         |
| Data Hash         | The DVC-computed hash of a tracked dataset, used for lineage            |
| Explicit Mode     | MLflow instrumentation where the user writes tracking code manually     |
| Auto Mode         | MLflow instrumentation where the backend detects and logs automatically |
| Lineage           | The traceable chain: data version -> config -> run -> model version     |
| Pointer File      | A `.dvc` file containing the hash of a large file stored in MinIO      |
| Structured Config | A Python dataclass used by OmegaConf for type-validated configuration  |
| Snapshot          | An immutable record capturing a run's full state: git commit, DVC hashes, Hydra config, MLflow run, environment spec. One snapshot per experiment. |
| Snapshot Branch   | A git branch (`snapshot/{experiment}_{version}`) preserving the exact code state at snapshot time |
| Champion          | The model version currently served in production, identified by the `@champion` alias |
| Leaderboard       | A sortable multi-run comparison table within an experiment, used to identify the best run |
| Sweep             | A Hydra multirun executing the same script with multiple config combos  |
| ExecutionBridge   | noted's existing Socket.io to Jupyter ZMQ message bridge               |
| CollaborationManager | noted's existing real-time collaboration service                    |
| EnvironmentManager | noted's existing runtime-aware virtual environment service            |

---

## 9. What This Document Does Not Cover

- Phase sequencing, timelines, and task breakdowns (see Plan document)
- Architectural decisions rationale (see Vision document)
- Architecture design principles, anti-patterns, and decisions log (see Architecture Principles document)
- Inline code completion (ghost-text) specification (planned, see `documents/llm/llm08.md` Section 7)
- Detailed UI wireframes and component specifications (to be produced during development)
- Security model, authentication, and authorization design (to be defined — planned approach: OAuth2-Proxy at nginx layer)
- Testing strategy and quality assurance plan (to be defined)
- Operational runbooks and incident response (to be defined)

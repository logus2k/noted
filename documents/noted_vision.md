# noted - Integrated MLOps Platform Vision

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Product Vision                     |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 2.4                                |
| Date          | 2026-04-15                         |
| Status        | Draft                              |
| Changes       | See [Changelog](#changelog) below                                                |

---

## Changelog

### v2.4

Final delivery milestone. **Model Serving Refactor shipped**: Deploy / Unload / Try It three-button UX aligned with MLflow terminology, streaming NDJSON progress from `/load`, Logged Models (MLflow 3.x) visible in the Registry detail with hljs-highlighted previews of `MLmodel` / `conda.yaml` / `python_env.yaml` / `requirements.txt`, step-1 unblock (drop protobuf pin + stop runtime install) de-risks serving for all registered versions via MLflow warning-mode loading. **jena_client Model Serving Client shipped** as a generic reference client (three dropdowns Model/Version/Alias with `@champion` default, NDJSON streaming, inverse scaler transform via `target_mean`/`target_std` MLflow params, three-column prediction table). **5-6 layer Lineage Chain** (Data/Config/[Pipeline]/Code/Run/Model) lit on every new Registry version including `noted.git_commit` tags for Git code identity. **jena_weather Tutorial 3 Level C** (second DVC dataset, 10 override inputs inlined into config.yaml, `log_hydra_lineage` DAG task, `target_mean`/`target_std` params logged for serving-time de-standardization). **User Manual 7 pages** published to Knowledge Base - Pages 1-5 refreshed as final user-facing documentation, Page 6 (Serving & Deploying Models) and Page 7 (noted Assistant) newly written. **NOTED_SETUP.md** added at repo root as the reviewer-facing setup guide. Phase 0b worker-subprocess architecture designed but deferred to post-demo since step-1 unblock eliminates the immediate crash vector.

### v2.3

Hydra Unification + Time Machine shipped - Configuration Composer with Experiment Run mode (Time Machine) and self-contained per-run Hydra bundles closes the config-to-run lineage gap described in Section 2. Evidently thin integration partially shipped (Data Health dot, DAG tasks for quality and drift, Evidently UI service tab). Explorer UX overhaul (tree consolidation, double-click expand, Knowledge Graph as tree node). User Manual Pages 1-5 published, providing the friction inventory that feeds the Section 7 cockpit redesign.

### v2.2

R as third notebook language alongside Python and JavaScript. Six R versions supported (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) with two kernels: Posit's ark (Rust) for modern R 4.2-4.5 because it offers richer feature surface and is the kernel Posit is actively investing in; IRkernel (REditorSupport) for legacy R 3.6.3 / 4.0.5 because ark cannot drive the older R API surface. ALL 6 R versions get full LSP via the languageserver R package - latest CRAN for modern, era-matched binary repos from Posit Public Package Manager (PPM 2020-04-01 for R 3.6.3, PPM 2021-05-01 for R 4.0.5) for legacy, sidestepping both the testthat/glibc-2.34 compile failure and the PPM source dep resolution mismatch. RENV_CONFIG_EXTERNAL_LIBRARIES injected to expose system languageserver from inside renv-isolated R envs without polluting renv lockfiles. Option E architecture: cwd=project_root, R_PROFILE_USER points at noted-managed `.Rprofile` calling `renv::load`, RENV_PATHS_LIBRARY/LOCKFILE redirect renv state to env directory. Seven languages now have full LSP: Python, JavaScript, R, HTML, CSS, JSON, YAML. The R Run-from-file-editor and R debugger remain Planned (R debug is Phase 3, blocked on ark exposing its DAP outside Positron; legacy R via IRkernel will never have DAP).

### v2.1

YAML language support via yaml-language-server (Red Hat).

### v2.0

Web language support added - HTML/CSS/JSON syntax highlighting (@codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json) and LSP via vscode-langservers-extracted (single-server mode). Five languages now have full LSP support: Python, JavaScript, HTML, CSS, JSON. "Virtual Environments" renamed to "Environments" with language grouping (Python/JS sub-nodes, VS Code color SVG icons). VS Code-style SVG completion icons. File editor polish (Tab=4 spaces, Ctrl+Home/End, Documentation panel hover). JS notebook IIFE wrapping for const/let re-declaration with globalThis exports. Clean startup (no panels, no auto-open). dynamicRegistration fix and rootUri rewrite for LSP reliability. Section 7.8 updated with web language LSP architecture.

### v1.9

JavaScript integration plans added - second language alongside Python via xeus-javascript kernel, fnm/pnpm environment management, typescript-language-server/Biome LSP, Strategy Pattern for multi-language execution (PythonStrategy + JavaScriptStrategy), TransportManager for ZMQ/TCP debug protocols. Evidently integration points detailed (5 integration points, thin integration pattern). Section 7.8 updated with multi-language extensibility. Section 6.1 updated with full-stack web application capability.

### v1.7

DAP Phase D4 completed (Run menu, debug icon, debug status pill). Debug All Cells feature added - shadow file generation with filename injection for cross-cell debugging, IPython-safe wrapper with ast.Interactive, cell map for breakpoint translation, cell-boundary stepping. Live breakpoint updates during active sessions. Debug stop cleanup (control thread deadlock fix, was_paused flag, ghost output filter). UI polish (step throttling, combined breakpoint+arrow marker). Multi-language debug extensibility plan (Strategy Pattern, ZMQ/TCP transports). Section 7.8 updated.

### v1.6

LSP integration added (Ruff linting, Jedi completions, Documentation panel, minimap, Problems panel). DAP integration added (notebook and file debugging with breakpoint gutter, debug toolbar, Debug panel in right pane). Section 7.6 updated with Debug panel. Section 7.8 added for Code Intelligence. Section 8.3 updated to reflect IDE-grade capabilities.

### v1.5

All platform phases (0-4) completed. Jena Weather project pipeline added as the primary demonstration vehicle. End-state scenario (Section 6.1) now fully realizable. Added Section 6.4 describing the video demo strategy. AI Assistant consolidated as first-class feature (Section 7.7).

### v1.4

Multi-notebook support implemented. Center pane updated for VS Code-style preview/pin tab behavior.

### v1.3

Added academic use case alignment (Section 6.2).

### v1.2

Updated UI architecture to VS Code-like layout with left icon bar, collapsible Workspace Explorer, tabbed center pane, and right Chat panel. Workspace tree expanded to include all MLOps artifacts (Storage, DAGs, Models, APIs). Phase 0 completed. Python file editing support added.

---

## 1. Purpose

This document defines the product vision for **noted** - a collaborative, web-based MLOps platform that evolves from an interactive notebook environment into a unified interface for the full machine learning lifecycle: data management, experimentation, orchestration, tracking, model governance, and deployment.

The vision is grounded in tools and infrastructure that already exist, both as open-source projects and as components already built within the noted application. The goal is integration, not invention.

---

## 2. Problem Statement

Modern MLOps requires practitioners to operate across a fragmented landscape of tools:

- **Data versioning** happens in DVC or ad-hoc file naming
- **Configuration management** lives in scattered YAML files or hardcoded values
- **Experiment tracking** requires switching to the MLflow UI
- **Orchestration** requires switching to the Airflow UI
- **Model serving** requires manual deployment pipelines
- **Object storage** is managed through MinIO console or CLI

Each tool has its own interface, its own authentication model, and its own mental model. Practitioners spend significant time context-switching between browser tabs, terminals, and dashboards. Configuration drift between what was experimented with and what gets deployed is a persistent source of production failures.

There is no unified interface that lets a practitioner go from raw data to deployed model within a single, coherent experience while maintaining full traceability.

---

## 3. Vision Statement

**noted** is a collaborative, web-based platform where ML practitioners interact with their full MLOps stack through a single, integrated interface. It combines the interactive exploration of a notebook environment with production-grade data versioning, experiment tracking, pipeline orchestration, configuration management, and model deployment - all accessible without leaving the application.

The underlying tools (MinIO, DVC, MLflow, Airflow, Hydra) remain the engines. noted is the cockpit.

---

## 4. Target Users

### 4.1 Primary: ML Engineers and Data Scientists

Practitioners who develop, train, evaluate, and deploy machine learning models. They currently work across Jupyter notebooks, terminal commands, and multiple web UIs. They need a single workspace that supports both exploration and production workflows.

### 4.2 Secondary: MLOps / Platform Engineers

Engineers responsible for maintaining the infrastructure. They need visibility into pipeline health, storage utilization, and model registry state. noted gives them a unified dashboard without requiring direct access to each service's admin interface.

### 4.3 Tertiary: Technical Leads and Reviewers

People who need to review experiment results, approve model promotions, or audit the lineage between a dataset version and a production model. They need read access and governance controls without needing to understand the underlying tool APIs.

---

## 5. Core Principles

### 5.1 Integration Over Aggregation

noted is not a dashboard that merely aggregates other tools' UIs. It is a purpose-built interface that communicates with backend services through their APIs, presenting a unified experience where actions in one domain (e.g., promoting a model) are immediately reflected in others (e.g., the Models section of the Workspace tree, the detail tab in the center pane). Service UIs (MLflow, Airflow, MinIO) are accessible as tabs in the center pane for advanced use, but the primary interaction model is through noted's own purpose-built views.

### 5.2 Backend Services Stay Canonical

MLflow remains the source of truth for experiments and model registry. Airflow remains the source of truth for pipeline execution. MinIO remains the source of truth for object storage. DVC remains the source of truth for data versioning. noted reads from and writes to these services but never duplicates their state into its own database (except for UI metadata like layout preferences).

### 5.3 Progressive Complexity

A new user can open noted, create a notebook, write Python, and execute cells - exactly like Google Colab. As their needs grow, they discover data versioning, experiment tracking, and orchestration features organically. The UI does not front-load complexity.

### 5.4 Explicit Over Magical

When noted performs an action on the user's behalf (e.g., committing a DVC pointer file, triggering an Airflow DAG, logging an MLflow metric), the user can see exactly what happened. No hidden side effects. Automatic instrumentation is opt-in and transparent.

### 5.5 Collaboration as Default

Building on noted's existing collaborative editing foundation (cell-level locking, TTL leases, Socket.io presence), every MLOps feature is designed for multi-user scenarios: shared experiment views, collaborative model review, team-visible pipeline status.

---

## 6. The End-State Experience

The following narrative describes the target user experience when all phases are complete. It is aspirational but architecturally grounded in the tools and integrations defined in this document.

### 6.1 Scenario: Weather Prediction Model Development

**Context:** A team is building time-series forecasting models using the Jena Climate dataset. Two team members are comparing GRU and Transformer architectures.

**Step 1 - Data Ingestion**

A researcher opens the noted workspace and navigates to Data in the Workspace tree. They drag the raw `jena_climate_2009_2016.csv` file into the upload area. The backend stores the file in MinIO, runs `dvc add` and `dvc push`, and commits the `.dvc` pointer file to the project's backend-managed Git repository. The detail tab shows:

```
data/raw/jena_climate.csv    v1    42MB    uploaded 2 min ago
```

**Step 2 - Preprocessing**

In a notebook cell, the researcher writes a preprocessing pipeline that standardizes features and creates train/test splits. They execute the cell. The backend detects that new files were written to `data/processed/`, runs `dvc add` on them, and the Data detail tab updates:

```
data/raw/jena_climate.csv       v1    42MB
data/processed/scaled.npz       v1    18MB    derived from raw v1
```

**Step 3 - Configuration**

The researcher opens the Config section in the Workspace tree, which opens a detail tab. They see a form generated from the project's Hydra structured configs:

```
Architecture:  [GRU v]        (dropdown: GRU, Transformer)
Hidden Dim:    [128]
Num Layers:    [2]
Learning Rate: [0.001]
Batch Size:    [64]
Epochs:        [50]
```

Selecting "Transformer" from the dropdown dynamically replaces "Hidden Dim" and "Num Layers" with "Attention Heads", "d_model", and "Feedforward Dim."

**Step 4 - Interactive Training**

The researcher opens the Run Manager, selects all code cells with one click, and executes the run. The backend wraps the entire cell sequence in a single MLflow run with automatic start/end. The Experiments section in the Workspace tree updates, and a detail view opens as a center tab showing a live-updating chart:

```
Run #14  |  GRU  |  Epoch 23/50  |  MAE: 2.41  |  Running...
```

Metrics update in real-time via Socket.io. The second team member, working in the same project, sees this run appear in their Workspace tree as well.

**Step 5 - Comparison**

After both team members have completed several runs, they open the Experiments section in the Workspace tree and select runs to compare. A comparison view shows overlaid loss curves, final metrics, and the exact Hydra config diff between runs. The data version hash is displayed alongside each run, confirming both used `data/raw v1`.

**Step 6 - Pipeline Execution**

The lead researcher wants to run a full hyperparameter sweep. They switch to "Pipeline" mode, which generates an Airflow DAG from the project's `src/train.py` entry point and the Hydra multirun config. They click "Submit." A Pipeline view opens as a center tab showing a node graph:

```
[Pull Data v1] --> [Validate Config] --> [Train (x12 configs)] --> [Log Results]
     DONE              DONE               8/12 RUNNING             PENDING
```

Task stdout streams into a terminal panel via Socket.io.

**Step 7 - Snapshot and Champion Selection**

After multiple experiments (GRU v1, GRU v2, Transformer v1), the researcher has found the best run in each. They click "Snapshot" on the best run within each experiment. A snapshot captures everything: the git commit (code, notebooks, DAGs, configs), DVC data hashes, resolved Hydra config, MLflow run metrics, and the Python environment - all linked as an immutable record. A snapshot branch is created in git (`snapshot/transformer_v1_001`) preserving the exact state.

The researcher opens the Snapshots view and sees all experiments side by side, sorted by MAE. The Transformer v1 snapshot (MAE: 1.87) is clearly the winner. They click "Register Model" on that snapshot's run and assign `@champion`.

A colleague later wants to build on the GRU v2 work. They click "New Experiment from Snapshot" on the GRU v2 snapshot - noted restores the entire workspace (code, data, configs) to that exact state and creates a new experiment branch. They modify the architecture and start training. The original GRU v2 snapshot remains untouched.

**Step 8 - Model Promotion and Serving**

The Models section in the Workspace tree shows:

```
JenaForecaster
  v1   GRU         MAE: 2.41   @archived    snapshot/gru_v1_001
  v2   Transformer MAE: 1.87   @champion    snapshot/transformer_v1_001
```

Each version card shows a five-layer **Lineage Chain** (Data -> Config -> Code -> Run -> Model, with an optional Pipeline layer inserted when the run came from Airflow) and a three-button serving controller: **Deploy**, **Unload**, **Try It**. The researcher clicks Deploy on v2. A progress card streams NDJSON events (`resolving` -> `downloading` -> `loading_model` -> `ready`) in under three seconds for a warm container. They click Try It, the panel renders an input form derived from the model's signature with a **Generate Sample** button, they click Predict, and a chart plus a table render the 24-hour temperature forecast inline.

The same version card exposes the archived **Logged Model** artifacts under **Artifacts > Logged Models**: `MLmodel`, `conda.yaml`, `python_env.yaml`, `requirements.txt`, and the framework-specific weights under `data/`. Each file previews with syntax highlighting and has a Download button - the exact environment needed to serve this model outside noted, ready to hand off to any consumer.

For external consumption, noted ships a **standalone Model Serving Client** (`iscte/jena_client/`) that connects to `noted-serving`'s HTTP API. Its UI has three dropdowns (Model / Version / Alias with `@champion` auto-selected), a streaming load indicator, and inverse scaler transforms applied on the client side using `target_mean` / `target_std` logged as MLflow params - so predictions display in real units without the model itself having to de-standardize. Any application that can make HTTP requests can consume noted-served models the same way.

For the final report, the researcher clicks "Generate Report" on the experiment comparison view. A PDF is generated containing the ranked metrics table, convergence charts, parameter comparisons, and snapshot lineage - a complete reproducibility record without manually assembling screenshots.

**Step 9 - Advanced Capabilities (Phase 5)**

As the team's workflow matures, they leverage advanced features. The lead researcher right-clicks the processed dataset node in the Knowledge Graph and selects "What breaks if I change this?" - an Impact Analysis query traverses downstream edges and highlights all affected runs, pipelines, and models, revealing that 12 runs and 2 deployed models depend on this data version.

When promoting the Transformer model to production, the researcher clicks "Generate Model Card" on the model version detail page. A structured document is produced automatically, pulling lineage data (training data hash, Hydra config, code commit, evaluation metrics) into a standardized Model Card format - ready for review or compliance.

New team members joining the project use "New Project" with the Time-series Forecasting template, which scaffolds a complete project structure with Hydra configs, a starter DAG, an example notebook, and environment setup - eliminating hours of boilerplate configuration.

With multi-language support, the team builds a complete web application for their forecasting model. JavaScript notebooks running on the IJavascript kernel develop a React frontend that calls the model serving API, while Python notebooks handle the ML workflow. Both languages share the same debugging experience - breakpoints, stepping, variable inspection - with terminal-based file debugging showing output directly in the integrated terminal. JavaScript files get Biome linting (Rust-based, fast) and typescript-language-server for autocomplete and hover docs. HTML, CSS, and JSON files get syntax highlighting and full LSP support (auto-completion, documentation, linting) via vscode-langservers-extracted. Environment management uses fnm for Node.js versions and pnpm for packages, mirroring the Python model of isolated environments per runtime. The Environments section in the Explorer tree groups runtimes by language (Python and JavaScript sub-nodes with VS Code color SVG icons). The entire stack - data pipeline, model training, API serving, and web frontend - lives in one noted project.

### 6.2 Academic Use Case

noted is designed as a teaching and research platform for end-to-end MLOps curricula. It integrates the same technology stack commonly taught in MLOps courses: **DVC** (data versioning), **Hydra** (configuration management), **Airflow** (pipeline orchestration), **MLflow** (experiment tracking), **PyTorch/TensorFlow** (model training), plus Docker Compose as infrastructure. Students and researchers currently context-switch between the MLflow UI, Airflow UI, MinIO console, and terminal - exactly the fragmentation problem noted solves.

**Key academic requirements noted supports:**
- **DVC hash as MLflow parameter** (not just tag): enables data traceability patterns taught in versioning labs
- **Multiple DAGs per project**: supports complex multi-pipeline project structures
- **Parameterized DAG triggers with UI forms**: Hydra config dropdowns and parameter overrides from the trigger panel
- **Model artifact types**: TensorFlow/Keras models, sklearn models, and visualization artifacts logged to MLflow
- **Complete workflow in one interface**: from `dvc add` to model evaluation pipelines without leaving noted

### 6.3 What This Demonstrates

Every step in this scenario uses a different backend tool, but the user never leaves noted:

| User Action                | Backend Tool          |
|----------------------------|-----------------------|
| Upload dataset             | MinIO + DVC + Git     |
| Configure model            | Hydra                 |
| Run training interactively | Notebook kernel + MLflow |
| Submit pipeline            | Airflow REST API      |
| Compare experiments        | MLflow Tracking API   |
| Promote model              | MLflow Registry API   |
| Test predictions           | FastAPI serving       |
| Monitor data quality/drift | Evidently             |
| All real-time updates      | Socket.io             |

### 6.4 Tutorial 2 Delivery: Video Demonstration (2026-03-29)

As of v1.5, all noted platform phases (0-4) are complete. The end-state scenario described in Section 6.1 is now fully realizable. A recorded video demonstration using the **Jena Weather Forecasting** project serves as the live use case.

The video demonstrates noted as the single interface for the complete MLOps lifecycle:

1. **Docker Compose launch** - 10+ containers starting from a single command
2. **Hydra configuration** - switching model architectures (GRU/Linear) via config groups in the UI
3. **Live notebook execution** - real cells running in real time with live metrics streaming
4. **Airflow pipeline** - 4-stage DAG (Ingest -> Preprocess -> Train -> Evaluate) triggered and monitored from noted
5. **Experiment Snapshots** - capturing the complete reproducible state (git + DVC + Hydra + MLflow) in one click
6. **Model Registry** - registering the best model and assigning the @champion alias
7. **Model Serving** - loading the champion model and running live predictions via the Try It panel

The video demonstrates the platform's end-to-end readiness across all integrated tools.

See `documents/tutorial2_implementation_plan.md` for the full implementation plan and `documents/tutorial2_movie_script.md` for the scene-by-scene recording script.

---

## 7. Architectural Philosophy

### 7.1 Single Container with Proxy Pattern

noted runs as a **single Docker container** serving both the vanilla ES6 frontend (static files) and the FastAPI backend. This container is the sole intermediary between the browser and all backend services. The frontend never communicates directly with MLflow, Airflow, MinIO, or any other service.

```
[Browser]
    |
    | HTTP + Socket.io
    |
[nginx reverse proxy] (SSL termination)
    |
[noted container]  <-- single process: FastAPI + Uvicorn + Socket.io
    |               serves static frontend files
    |               proxies all backend service calls
    |
    +-- MLflow API
    +-- Airflow REST API
    +-- MinIO S3 API
    +-- DVC Python API
    +-- Hydra Compose API
    +-- Git (libgit2/pygit2)
    +-- jupyter_client (existing kernel management)
```

Benefits:
- Secrets (MinIO keys, Airflow tokens) never reach the browser
- Cross-service operations (e.g., "promote model and trigger deployment") are atomic from the frontend's perspective
- Authentication and authorization are centralized
- Single deployment unit simplifies operations

### 7.2 Event-Driven Communication

Building on the existing Socket.io infrastructure (which already handles cell updates, lock state, kernel status, user presence, and execution output streaming), all new long-running operations push status updates to connected clients:

- Kernel execution output (existing)
- MLflow metric updates during training
- Airflow task state transitions
- DVC push/pull progress
- Model serving readiness changes

No polling. No setTimeout-based synchronization.

### 7.3 Project as the Unit of Organization

Everything revolves around a noted project:

- A project has one Git repository (backend-managed)
- A project has one MLflow Experiment
- A project has one DVC remote configuration
- A project has one Hydra config root
- A project can generate one or more Airflow DAGs
- A project can register one or more models in the MLflow Registry

noted already supports both internal projects (stored in noted's data directory) and external projects (linked from the host via `projects.txt` symlinks). The MLOps features build on this existing project model.

### 7.4 Multi-Runtime Kernel Architecture

noted already supports multiple Python runtimes (3.10, 3.11, 3.12, 3.13, 3.14, including free-threaded variants) with isolated virtual environments per runtime. The MLOps integration leverages this:

- MLflow client is installed as a default dependency in environments used for ML work
- Environment variables (`MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`) are injected at kernel startup
- CUDA runtime is already available with `LD_LIBRARY_PATH` injection for GPU-accelerated training
- The existing EnvironmentManager handles package installation with PTY streaming, which extends naturally to installing DVC, Hydra, and other MLOps dependencies

### 7.8 Code Intelligence and Debugging

noted integrates Language Server Protocol (LSP) and Debug Adapter Protocol (DAP) to provide IDE-grade code assistance within the browser-based environment.

**LSP integration** provides IDE-grade code intelligence for seven languages. Python uses Ruff linting (with severity remapping from Ruff's all-Error reports to Error/Warning/Info based on rule prefix) and Jedi language server for autocomplete, hover documentation, and go-to-definition (dual-server architecture). JavaScript uses Biome for linting and typescript-language-server for completions (dual-server architecture). **R uses the `languageserver` R package (REditorSupport)** in single-server mode - it provides completion, hover docs, and lintr-driven diagnostics from one server per env. All 6 supported R versions (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) get full LSP: modern R installs the latest CRAN release; legacy R uses era-matched binary releases from Posit Public Package Manager (PPM 2020-04-01 for R 3.6.3 yielding languageserver 0.3.5, PPM 2021-05-01 for R 4.0.5 yielding languageserver 0.3.10), bypassing both the source-install dependency resolution mismatch (R 3.6.3) and the testthat catch.h glibc 2.34 SIGSTKSZ compile failure (R 4.0.5). The `RENV_CONFIG_EXTERNAL_LIBRARIES` environment variable injected at LSP launch makes the system-installed languageserver visible from inside renv-isolated envs without polluting renv lockfiles. HTML, CSS, and JSON use vscode-langservers-extracted in a single-server architecture (one server handles all three). YAML uses yaml-language-server (Red Hat). Notebook cells are supported through shadow files - Jupytext for Python, per-cell shadow files (.nb.cellN.js) for JavaScript, manual `# %%` percent-format combined shadow for R. CodeMirror bundles include @codemirror/lang-html, @codemirror/lang-css, @codemirror/lang-json, @codemirror/lang-yaml, and a CodeMirror R mode for syntax highlighting. Completions display VS Code-style SVG data URI icons. The completion popup accepts items via Tab (in addition to Enter) - implemented with `Prec.highest` so the binding wins against the default Tab indent handler, and falls through to indent when no popup is open. A Documentation panel in the right pane renders hover documentation (routed from the editor, not shown as tooltip). The file editor includes a code minimap with lint severity color markers, a Problems panel accessible from the status bar, Tab inserts 4 spaces (when no popup), and Ctrl+Home/End navigate to file boundaries. dynamicRegistration is forced to false for all LSP client initialization (codemirror-languageserver compatibility), and rootUri is rewritten from virtual URIs to real filesystem paths in _init_server.

**DAP integration** provides interactive debugging for both notebooks and Python files. Notebook debugging uses ipykernel's built-in Debugger accessed through the Jupyter control channel, with a ControlChannelDispatcher implementing single-reader dispatch for concurrent access. File debugging uses `%run -i` execution through the kernel. Both modes share a breakpoint gutter (CodeMirror extension with red dot markers), a debug toolbar (Continue, Step Over, Step In, Step Out, Stop), and a Debug panel in the right pane showing Variables (with lazy expansion for compound types), Call Stack (with cross-file navigation), and Breakpoints (with enable/disable and delete). A Run menu in the menu bar provides keyboard-shortcut-driven access to all debug commands, a debug icon (red bug) in the icon bar toggles the Debug panel, and a debug status pill in the status bar indicates active sessions.

**Debug All Cells** enables cross-cell debugging for notebooks. A POST to `/api/dap/debug-notebook` concatenates all code cells into a shadow file (`/tmp/noted_debug_<hash>.py`) with `# %%` markers and returns a line-to-cell mapping. Filename injection via `compile(code, shadow_path, 'exec')` makes debugpy see one unified file while cells continue to execute individually through `kc.execute()`, preserving per-cell output (charts, prints, dataframes). An IPython-safe wrapper uses `transform_cell` for magic commands and `ast.Interactive` for the display hook. All breakpoints from all cells are combined into a single `setBreakpoints` call on the shadow file, with live updates during active sessions. Cell-boundary stepping (F10 at end of cell) sends continue and auto-advances to the next cell.

**Multi-language extensibility** is implemented via a Strategy Pattern architecture, applied uniformly across kernels, LSP, package managers, and (eventually) debug. For each language, an execution Strategy encapsulates wrapping, filename injection, and debug behavior; an LSP Strategy encapsulates server type, build command, init capabilities, and diagnostic enrichment; and a PackageManager Strategy encapsulates package install/list/remove operations. Python uses PythonStrategy / PythonLspStrategy / PipPackageManager (compile() injection, IPython-safe wrapper, debugpy via ipykernel). JavaScript uses JavaScriptStrategy / JavaScriptLspStrategy / PnpmPackageManager (V8 sourceURL pragma, IJavascript kernel, vscode-js-debug adapter). **R uses RLspStrategy / RenvPackageManager** with a per-runtime kernel dispatched via runtime.json `kernel_cmd` and `kernel_env` (ark for modern R, IRkernel for legacy). Additional languages (Julia, C++) follow the same pattern. This architecture enables adding new language support without modifying core debug, LSP, or package management infrastructure - each addition is a new strategy file plus a registry entry.

JavaScript was the first additional language, chosen because it enables building complete web applications (Python backend + JavaScript frontend) within a single noted workspace. The IJavascript kernel (npm ijavascript) provides Jupyter protocol compliance for notebook execution - xeus-javascript was evaluated but is limited to JupyterLite. File debugging uses vscode-js-debug with a multi-session TCP proxy and the runInTerminal pattern, where the debug adapter launches the Node.js process in noted's integrated terminal so output is visible to the user - the same pattern used for Python file debugging. Environment management mirrors Python's model: fnm (Fast Node Manager) for Node.js version management and pnpm for package management, integrated into the existing EnvironmentManager. LSP support uses typescript-language-server for autocomplete, hover docs, and go-to-definition, plus Biome (Rust-based) for linting and formatting. See `documents/js/noted_javascript_integration_plan.md` for the full integration plan.

**R is the third notebook language**, chosen because it remains the dominant language in academic statistics, biostatistics, and reproducibility-driven research. Six R versions are supported simultaneously (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2, 4.5.1) so users can faithfully reproduce papers from any era between 2018 and the present, dispatched per version via `R_HOME` and `LD_LIBRARY_PATH`. Two kernels are used: **ark** (Posit's Rust-based kernel, single binary serving multiple R versions via `R_HOME` dispatch) for modern R 4.2.3 - 4.5.1 because it provides the richer Positron-style feature surface (data viewer hooks, plot manager, future DAP) and is the kernel Posit actively maintains; and **IRkernel** (REditorSupport, the original Jupyter R kernel) for legacy R 3.6.3 and 4.0.5 because ark 0.1.250 cannot drive R 3.x / R 4.0 interpreters - the R API surface ark expects is from the R 4.x era and the older interpreters die during init. IRkernel installs from PPM binary repos (no compilation, no glibc 2.34 SIGSTKSZ trap). All 6 R versions get full LSP via the `languageserver` R package - modern R installs the latest CRAN release, legacy R installs era-matched PPM binary releases. Environment isolation uses **renv** with per-env library and lockfile, redirected to noted-managed paths via `RENV_PATHS_LIBRARY` / `RENV_PATHS_LOCKFILE` environment variables. The noted-managed `.Rprofile` calls `renv::load(project = getwd())` so renv activates against the project root for dependency scanning, while the env vars redirect state. **R debug is Phase 3**, deferred until ark exposes its DAP outside Positron; legacy R via IRkernel will never have DAP since the IRkernel side never offered one. **R run-from-file-editor (.R script play button) is Shipped** via a per-env `bin/Rscript` shell wrapper launcher generated at env creation time, matching the Python and JavaScript file workflows. See `documents/r/r_implementation_notes.md` for the full architecture and `testing/34_test-r-lsp-phase2.md` for the end-to-end validation walkthrough.

### 7.5 Infrastructure as Docker Compose

All services run as containers alongside the noted container. This is appropriate for the current scale (team-level, single-server deployment). Migration to Kubernetes is architecturally possible but not planned.

Current running infrastructure (already deployed):

```
noted              (noted)         - FastAPI + static frontend, single container
mlflow             (noted-mlflow)  - Tracking + Registry, MLflow 3.x
airflow-apiserver  (noted-airflow-apiserver)   - Airflow 3.0 API Server
airflow-scheduler  (noted-airflow-scheduler)   - Airflow 3.0
airflow-worker     (noted-airflow-worker)      - Celery Worker
airflow-triggerer  (noted-airflow-triggerer)   - Airflow 3.0
airflow-dag-processor (noted-airflow-dag-processor) - Airflow 3.0
minio              (noted-minio)   - Object storage
postgres           (noted-postgres) - Shared metadata: MLflow + Airflow
redis              (noted-redis)   - Airflow Celery broker, Airflow-managed
nginx              (noted-nginx)   - Reverse proxy, SSL termination (local only, via docker-compose.local.yml)
```

Additional services to be added:

```
model-server       (FastAPI serving, on-demand per project)
evidently          (noted-evidently) - Data quality, drift detection, model monitoring (Evidently AI)
```

### 7.6 UI Architecture

noted adopts a VS Code-like layout with four columns:

1. **Icon Bar** (leftmost) — A narrow vertical strip with icons for each Workspace category. Clicking an icon expands or collapses the Workspace Explorer to the corresponding section. Always visible.

2. **Workspace Explorer** — A collapsible tree panel showing all platform artifacts organized by category:
   - Projects (existing: project hierarchy with notebooks)
   - Environments (existing: Python, JavaScript, and R runtime management, with language sub-nodes and VS Code color SVG icons)
   - Storage (MinIO bucket browser)
   - DAGs (Airflow DAGs with status)
   - Models (MLflow Registry with versions and aliases)
   - APIs (deployed model serving endpoints)

   The tree provides project-centric navigation (drill into a project to see its notebooks, data, experiments) and platform-wide views (all models, all DAGs). Clicking a tree item opens a detail view in the center pane. The Workspace Explorer replaces the previous floating modal (jsPanel) used for project/environment browsing.

3. **Center Tabbed Pane** — The primary content area supporting multiple simultaneous tabs:
   - **Notebook tabs**: Multiple notebooks open simultaneously, each with its own kernel/editor state. Single-click opens preview tabs, double-click pins them (VS Code-style)
   - **File tabs**: CodeMirror-based text editors for satellite files (model.py, utils.py, index.html, styles.css, config.json, etc.) with language-specific syntax highlighting for Python, JavaScript, HTML, CSS, and JSON. Edit and save only — no cell execution UI.
   - **Service UI tabs**: MLflow, Airflow, and MinIO web UIs loaded as iframes within tabs, replacing the previous floating panel approach
   - **Detail view tabs**: Experiment run details, model lineage, pipeline graphs, data version browsers — opened from Workspace tree interactions

   Tabs can be closed individually. Tab state persists across sessions via localStorage.

4. **Right Panel** (rightmost) — A tabbed panel hosting the AI Chat assistant, the Documentation panel (LSP hover docs with reST rendering), the Debug panel (Variables, Call Stack, Breakpoints during debug sessions), and optionally the Skills panel. Collapsible.

All three side elements (icon bar, Workspace Explorer, Chat panel) are independently collapsible, allowing the center pane to maximize available space. The center pane is resizable relative to the sidebar and chat panel, maintaining the existing Split.js resize behavior.

### 7.7 AI-Powered Development Assistant

noted includes a context-aware AI assistant that understands the full MLOps workspace - notebooks, experiments, configurations, pipelines, data versions, and models - and can both reason about them and act on them through tool calls.

**Why it matters:** Generic AI chat tools require the practitioner to copy-paste code, manually describe their experiment state, and translate answers back into actions. noted's assistant has direct, structured access to the live workspace. When a user asks "why did validation loss spike at epoch 14?", the assistant reads the actual MLflow metric history, the Hydra config that produced it, and the notebook cells that ran - no copy-paste, no context loss.

**Dual-mode inference:** The assistant supports both local Gemma 4 E4B inference via llama-cpp-python (on-premises, zero data leaves the host) and cloud API access (Anthropic Claude - Sonnet 4.6, Opus 4.6, Haiku 4.5). Both backends use their native tool calling mechanisms. A model selector in the chat panel lets the practitioner choose the right trade-off between latency, quality, and privacy per session. Cloud models require an API key (auth gate); local models work out of the box.

**Native tool calling:** Both backends use structured, model-native tool calling rather than text-based prompt injection. Claude uses Anthropic's `tools` array with `tool_use` content blocks. Gemma 4 uses its trained `<|tool_call>` special tokens. MCP tool schemas (defined in `backend/app/mcp/tools.py`) are the single source of truth, automatically converted to each backend's format. This eliminates the fragile XML-based `<tool_call>` pattern and enables reliable structured arguments, including multi-line content with nested quotes.

**Dynamic Context Router:** For Claude, a keyword-based domain classifier selects only the relevant tool schemas per turn (typically 5-8 out of 25), reducing per-turn token cost. Nine domains are defined (MLflow, Airflow, DVC, Files, Hydra, Notebook, Linting, Knowledge, Skills, Web). If the LLM calls an out-of-scope tool, the router automatically expands the tool set and retries transparently. Gemma 4 receives all tools (small models benefit from maximum tool visibility).

**Thinking mode:** Both backends support step-by-step reasoning. Claude uses `/think` and `/no_think` directives. Gemma 4 uses the `<|think|>` token (prepended to the system prompt when thinking is enabled), with its `<|channel>thought` output translated to `<think>` blocks for the frontend's collapsible reasoning display.

**MCP Server:** noted exposes its tool surface through the Model Context Protocol (MCP) at `/mcp/`, enabling external AI clients (Claude Code, Claude Desktop, Cursor) to discover and invoke noted's capabilities. The server uses Streamable HTTP transport (official `mcp` SDK v1.27.0), with rate limiting (tiered token bucket), a structured error taxonomy, and a feature toggle. This transforms noted from a notebook with an AI chat into a headless AI execution engine controllable by any MCP-compatible client. See `documents/mcp/mcp_technical_architecture_notes.md` for the full architecture blueprint.

**Tool system:** 25 tools give the assistant read and write access to the MLOps stack: query MLflow runs and experiments, check Airflow DAG and task status, inspect DVC tracked files, read Hydra configs, search the Knowledge Graph, navigate to specific notebook cells, fetch and analyze web content (via Camoufox anti-detect browser), check lint diagnostics, and propose code changes. Write tools (update_cell, insert_cell, create_file, update_file, fix_lint_issues, batch_update_cells) require explicit user confirmation with a diff preview before execution.

**Web content fetch:** The `fetch_url` tool retrieves web content using Camoufox, a persistent anti-detect Firefox browser with C++ level TLS fingerprint spoofing. The browser launches once as a singleton and stays warm for subsequent requests, with automatic session refresh every 50 requests or 1 hour. Falls back to httpx when Camoufox is not available. This enables the assistant to read documentation, API references, articles, or any URL shared by the user and incorporate the content into its analysis.

**Skills system:** 37+ focused knowledge files covering MLflow interpretation, Airflow debugging, DVC tracking, Hydra composition, auto-instrumentation conventions, web fetch guidance, and cross-cutting MLOps patterns. Priority-1 skills auto-inject when their trigger conditions are met (e.g., a failed run is in context). Priority-2/3 skills are loaded on demand when the assistant determines it needs specialized knowledge. New skills are added by dropping a Markdown file in a folder - zero code changes required.

**Context assembly:** On every conversation turn, the backend assembles a fresh context snapshot from the live workspace: open notebook cells, selected cell, kernel status, active MLflow run, resolved Hydra config, DVC data hashes. The assistant always reasons over current state, not stale descriptions. Cell numbering is 1-based at the LLM boundary, matching what users see in the UI.

**Conversation memory:** Project-scoped, file-persistent memory with auto-compaction via LLM summarization when token budget thresholds are reached. Conversations survive container restarts and page reloads.

The assistant is not a bolt-on feature. It is a first-class component of the noted interface, occupying the rightmost panel of the VS Code-like layout and accessible from task log viewers ("Ask Assistant"), cell toolbars, and context menus throughout the application. Through MCP, it is also accessible to external AI clients as a headless execution engine.

For detailed architecture and implementation, see `documents/mcp/mcp_technical_architecture_notes.md` (MCP blueprint), `documents/mcp/mcp_development_plan.md` (MCP development plan), `documents/llm/llm08.md` (architecture patterns), `documents/llm/LLM_SKILLS_PLAN.md` (skills system), and `documents/llm/LLM_WRITE_TOOLS_DESIGN.md` (write tool confirmation flow).

---

## 8. Integration Boundaries

### 8.1 What noted Owns

- The web UI and all user-facing interactions (vanilla ES6 modules, CodeMirror 6, jsPanel, Wunderbaum, xterm.js)
- The FastAPI backend and all cross-service orchestration logic
- Project lifecycle management (create, configure, archive, external project linking)
- Notebook CRUD and nbformat 4 compatibility (existing NotebookManager)
- Kernel lifecycle management (existing KernelManagerService)
- Socket.io collaboration infrastructure (existing CollaborationManager)
- Environment management (existing EnvironmentManager)
- Backend Git repository management for DVC
- Real-time event distribution via Socket.io (existing ExecutionBridge, extended for MLOps events)

### 8.2 What noted Delegates

| Concern                    | Delegated To        | Interface             |
|----------------------------|---------------------|-----------------------|
| Experiment metrics storage | MLflow              | Tracking API          |
| Model versioning           | MLflow Registry     | Registry API          |
| Object/artifact storage    | MinIO               | S3-compatible API     |
| Data versioning            | DVC                 | Python API + CLI      |
| Pipeline scheduling        | Airflow             | REST API (API Server) |
| Config composition         | Hydra               | Compose API           |
| Config type validation     | OmegaConf           | Structured Configs    |
| Model inference            | FastAPI serving pod  | REST API              |
| Data quality & drift monitoring | Evidently        | Workspace API + UI    |

### 8.3 What noted Does Not Do

- noted does not replace MLflow's tracking database - it reads from it
- noted does not implement its own DAG scheduler - Airflow handles this
- noted does not implement its own object store - MinIO handles this
- noted does not build its own drift/monitoring dashboards - Evidently handles this (noted surfaces badges and delegates to the Evidently UI for details)
- noted does not implement Git hosting - it manages bare repos internally
- noted does not manage Kubernetes, cloud deployments, or multi-cluster orchestration
- noted is not a general-purpose IDE, but provides IDE-grade code intelligence (LSP: linting, autocomplete, go-to-definition, hover docs for Python, JavaScript, HTML, CSS, and JSON) and debugging (DAP: breakpoints, stepping, variable inspection for Python and JavaScript) within the MLOps workflow

---

## 9. Differentiation from Existing Tools

| Existing Tool           | What It Does Well                  | What noted Adds                                     |
|-------------------------|------------------------------------|-----------------------------------------------------|
| Google Colab            | Interactive notebooks              | Integrated MLOps lifecycle, collaboration, self-hosted |
| MLflow UI               | Experiment comparison              | Embedded in notebook workflow, live streaming         |
| Airflow UI              | DAG monitoring                     | Triggered from notebook context, inline status        |
| MinIO Console           | Bucket management                  | Data versioning overlay via DVC, project-scoped view  |
| Jupyter Hub             | Multi-user notebooks               | Full MLOps integration, not just kernel management    |
| Kubeflow Pipelines      | K8s-native ML pipelines            | Simpler deployment model, notebook-first experience   |
| Weights & Biases        | Experiment tracking SaaS           | Self-hosted, integrated with orchestration            |

noted's differentiation is not any single feature but the integration: the ability to go from data upload to deployed model within one interface, with full traceability, without requiring the user to understand six different tools' UIs.

---

## 10. MLflow Instrumentation Modes

noted supports three distinct modes for experiment tracking, selectable per project:

### 10.1 Explicit Mode (Default)

The user writes MLflow API calls directly in notebook cells (`mlflow.start_run()`, `mlflow.log_metric()`, etc.). The backend provides environment variables (`MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`) and injects run tags (project ID, data version hash, Hydra config hash) but does not modify the user's code.

This mode gives full control and is appropriate for experienced practitioners.

### 10.2 Run Manager Mode (Recommended)

The Run Manager provides explicit experiment tracking. Users define named runs by selecting which notebook cells to include (individually or via "Select All"), then execute them as a single MLflow experiment run. The backend wraps the entire cell sequence with automatic `start_run`/`end_run`, detects common ML frameworks (PyTorch, scikit-learn, TensorFlow, XGBoost, LightGBM), and activates framework-specific autologging at run completion. Metrics stream to the UI in real-time via Live Metrics.

This approach cleanly separates exploration (running cells freely without MLflow overhead) from experimentation (intentionally tracked runs with full lineage). DVC dataset hashes and Hydra config hashes are logged automatically when selected.

### 10.3 AI-Assisted Mode (Future)

An AI agent analyzes notebook code semantically to suggest what metrics, parameters, and artifacts should be tracked. It can propose instrumentation code that the user reviews and accepts before execution.

This mode is documented here for completeness but will be scoped separately.

---

## 11. DVC and Git Strategy

### 11.1 Chosen Approach: Backend-Managed Git Repositories

Each noted project is backed by a bare Git repository, managed entirely by the noted backend. Users never interact with Git directly.

**Rationale:** DVC's full feature set - `dvc repro`, `dvc diff`, pipeline caching, and branching - requires Git. Operating in `--no-scm` mode loses precisely the features that make DVC valuable for reproducibility, which is a core requirement.

### 11.2 How It Works

- When a project is created, the backend initializes a bare Git repo and runs `dvc init`
- Data operations (upload, preprocess) trigger `dvc add` + `dvc push` + `git commit` on the backend
- The UI presents a version list (derived from Git tags or commit history) without exposing Git concepts
- Collaborative conflict resolution (two users modifying the same `.dvc` file) is handled by the backend via a lock-and-merge strategy, leveraging noted's existing cell-level locking patterns

### 11.3 Abstraction Layer

A `ProjectVersionControl` service interface abstracts Git operations. This allows future migration to a different backend (e.g., `--no-scm` mode for lightweight projects) without changing the rest of the stack.

### 11.4 Relationship to External Projects

noted already supports external projects linked from the host filesystem. For external projects, the backend-managed Git repo is still created within noted's data directory - the Git/DVC metadata is noted's concern, while the notebook files may live on the host.

---

## 12. Project Directory Structure

Every noted project follows a standardized layout that accommodates all integrated tools:

```
/data/projects/{project_id}/
    .git/                          # backend-managed, invisible to user
    .dvc/                          # DVC init, config pointing to MinIO remote

    notebooks/                     # interactive exploration (existing)
        experiment_01.ipynb
        experiment_02.ipynb

    src/                           # extractable Python modules
        __init__.py
        model.py
        data_loader.py
        train.py                   # Hydra entry point

    config/                        # Hydra config root
        config.yaml                # defaults list
        model/
            gru.yaml
            transformer.yaml
        data/
            jena.yaml
            custom.yaml
        training/
            default.yaml

    data/
        raw/                       # DVC-tracked, immutable input
            dataset.csv
            dataset.csv.dvc
        processed/                 # DVC-tracked, pipeline outputs
            scaled.npz
            scaled.npz.dvc

    artifacts/                     # MLflow artifact staging (local cache)
        runs/

    pipelines/                     # Airflow DAG definitions (generated)
        dag_{project_id}.py

    outputs/                       # Hydra auto-generated run outputs
        {date}/{time}/
            .hydra/
                config.yaml
                overrides.yaml

    project.json                   # noted metadata
```

Key conventions:
- `notebooks/` is for interactive work; `src/` is for production-grade code
- `config/` follows Hydra's config group directory structure natively
- `data/raw/` is immutable input; `data/processed/` is reproducible output
- `pipelines/` contains generated Airflow DAGs, not user-authored ones
- `outputs/` is owned by Hydra for per-run config snapshots
- Environments are managed by noted's existing EnvironmentManager (per-runtime, shared across projects), not per-project

---

## 13. Existing Backend Managers

noted already has a well-defined set of backend managers. The MLOps integration extends this architecture rather than replacing it:

| Existing Manager          | Responsibility                                    | MLOps Extension                              |
|---------------------------|---------------------------------------------------|----------------------------------------------|
| NotebookManager           | CRUD for projects and .ipynb files                | Extended with DVC-aware data operations      |
| KernelManagerService      | Jupyter kernel lifecycle, idle cleanup             | MLflow env injection at kernel startup       |
| ExecutionBridge           | Socket.io to Jupyter ZMQ message bridge            | MLflow metric streaming, Run Manager lifecycle |
| CollaborationManager      | Rooms, cell locks, presence, broadcast             | MLOps event broadcasting (runs, pipelines, models) |
| EnvironmentManager        | Runtime-aware venv creation, package ops           | MLflow/DVC/Hydra as default dependencies     |
| ExternalProjectsConfig    | Parses projects.txt at startup                     | Git/DVC metadata for external projects       |

New managers to be added:

| New Manager               | Responsibility                                    |
|---------------------------|---------------------------------------------------|
| ProjectVersionControl     | Git + DVC operations, project-level locking        |
| ConfigComposer            | Hydra compose, validation, schema generation       |
| DAGGenerator              | Airflow DAG file generation from project metadata  |
| PipelineMonitor           | Airflow status polling, Socket.io event forwarding |
| ServingProxy              | Model server lifecycle and request proxying        |
| ActivityFeed              | Cross-service event logging and retrieval          |

---

## 14. Success Criteria

The platform is successful when:

1. A user can complete the full scenario described in Section 6 without leaving noted
2. Every MLflow run has a traceable link to the exact data version (DVC hash) and configuration (Hydra config snapshot) that produced it
3. Pipeline execution via Airflow is triggerable and monitorable from the noted UI with real-time feedback
4. Model promotion from experiment to production serving happens through the noted interface
5. Two or more users can collaborate on the same project simultaneously, seeing each other's experiment results and pipeline status in real-time
6. No user-facing operation requires direct access to MLflow UI, Airflow UI, MinIO Console, or a terminal
7. The UI layout provides seamless navigation across all MLOps domains through a unified Workspace Explorer, without requiring the user to open external browser tabs

---

## 15. What This Document Does Not Cover

- Detailed feature specifications and boundaries (see Scope document)
- Phase sequencing, timelines, and task breakdowns (see Plan document)
- Architecture design principles and anti-patterns (see Architecture Principles document)
- Inline code completion (ghost-text) design (planned, see `documents/llm/llm08.md` Section 7)
- Security model and authentication design (to be defined - planned approach: OAuth2-Proxy at nginx layer, zero custom auth code)
- Performance requirements and scaling limits (to be defined)

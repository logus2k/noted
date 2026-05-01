# noted - MLOps Integrations Reference

A comprehensive reference of noted's integration features with Airflow, MLflow, DVC, and Hydra. Each section describes the available features, backend API, frontend UI, and concrete use cases.

---

## 1. Apache Airflow - Pipeline Orchestration

noted integrates with Apache Airflow to define, trigger, monitor, and debug ML pipelines directly from the notebook environment.

### 1.1 DAG Discovery & Browsing

**What it does:** Lists all available Airflow DAGs, shows their status, schedule, tags, and task dependency graph.

**Backend API:**
- `GET /api/airflow/health` - Check Airflow API connectivity
- `GET /api/airflow/dags` - List all DAGs (optional tag filter)
- `GET /api/airflow/dags/{dag_id}` - DAG details including parameters
- `GET /api/airflow/dags/{dag_id}/tasks` - List tasks in a DAG
- `GET /api/airflow/dags/{dag_id}/structure` - Task dependency graph (nodes + edges)

**Frontend UI:**
- Explorer tree shows all DAGs under a "Pipelines" node with status icons
- DAG detail panel shows status (active/paused), schedule, tags, owners
- SVG-based task dependency graph visualization using dagre layout
- Color-coded task nodes: green (success), blue (running), red (failed), orange (queued), gray (skipped)
- Hover tooltips on task nodes showing operator type and trigger rule

**Use case:** *A team lead opens the Explorer, navigates to Pipelines, and clicks on `training_pipeline`. The detail panel shows the DAG is active with a daily schedule. The task graph reveals 5 tasks: `load_data -> preprocess -> train -> evaluate -> register_model`. Each node shows its current state from the last run.*

### 1.2 DAG Triggering

**What it does:** Trigger a DAG run with custom parameters directly from the UI, without accessing the Airflow web interface.

**Backend API:**
- `POST /api/airflow/dags/{dag_id}/trigger` - Trigger with optional config/parameters

**Frontend UI:**
- "Run DAG" button on the DAG detail panel opens a Trigger Panel (floating jsPanel)
- Parameter input fields auto-generated from DAG schema (text, number, boolean)
- JSON config textarea for complex parameters
- "Load Last Run Config" button pre-fills from the last successful run
- "Load Hydra Config" button composes the project's Hydra config, flattens nested values (e.g., `model.type` -> `model_type`, `training.epochs` -> `epochs`), and pre-fills all DAG parameters including the Hydra config hash for lineage tracking
- Data lineage display showing which Mount/S3 files the DAG uses

**Use case:** *A data scientist wants to retrain a model with a different learning rate. They open the training DAG, click "Run DAG", then click "Load Hydra Config" - all parameters are pre-filled from the project's `config.yaml` (model type, epochs, batch size, learning rate, layer units, dropout). They adjust `learning_rate` from 0.0005 to 0.0001, and click "Trigger". The Hydra config hash is included in the run for lineage tracking, so the exact configuration used can always be traced back.*

### 1.3 Parameter Sweep (Hyperparameter Tuning)

**What it does:** Trigger multiple DAG runs simultaneously for all combinations of parameter values (Cartesian product), enabling grid search over hyperparameters.

**Backend API:**
- `POST /api/airflow/dags/{dag_id}/sweep` - Trigger runs for all parameter combinations

**Frontend UI:**
- "Sweep" button on Trigger Panel (visible only for DAGs with parameters)
- Multi-value input fields (comma-separated: `0.001, 0.0005, 0.0001`)
- Real-time preview table showing all combinations before submission
- Combination counter (e.g., "12 runs will be triggered")
- Results table showing each run's status after submission

**Use case:** *A researcher wants to test 3 learning rates x 2 model types x 2 batch sizes = 12 combinations. They enter `learning_rate: 0.001, 0.0005, 0.0001`, `model_type: GRU, LSTM`, `batch_size: 32, 64` and click "Submit Sweep". All 12 DAG runs are triggered in parallel, each with a unique parameter combination and a shared `_sweep_id` for grouping.*

### 1.4 Run Monitoring

**What it does:** Monitor DAG runs and individual tasks in real-time with live status updates.

**Backend API:**
- `GET /api/airflow/dags/{dag_id}/runs` - List recent runs (configurable limit)
- `GET /api/airflow/dags/{dag_id}/runs/{dag_run_id}` - Run details
- `GET /api/airflow/dags/{dag_id}/runs/{dag_run_id}/tasks` - Task instances
- `GET /api/airflow/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/logs` - Task logs

**Frontend UI:**
- Run history table on DAG detail panel: status, start time, duration, MLflow run link
- DAG Run detail panel with task dependency graph showing live task states
- Task list with execution order, operator type, duration
- Task log viewer with monospace output
- Real-time updates via Socket.IO: `pipeline:status` and `pipeline:task_status` events
- Toast notifications on run completion (success/failed)
- Task graph nodes animate color transitions as tasks complete

**Use case:** *After triggering a sweep, the user clicks on the first run to see progress. The task graph updates live: `load_data` turns green, `preprocess` turns blue (running), and the remaining tasks are gray (pending). A toast appears: "Run manual_2026-03-20 completed successfully". They click on the `train` task to view its logs.*

### 1.5 Task Retry

**What it does:** Clear a failed task instance so it can be re-executed without re-running the entire DAG.

**Backend API:**
- `POST /api/airflow/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/clear` - Clear task for retry

**Frontend UI:**
- "Retry Task" button appears on failed/upstream_failed task detail panels
- "Ask Assistant" button sends task log to the LLM for error analysis

**Use case:** *A `train` task fails because the GPU ran out of memory. The user views the task log, sees the OOM error, clicks "Ask Assistant" to get a suggestion (reduce batch size), then clicks "Retry Task" after adjusting the config.*

### 1.6 DAG Pause/Unpause

**What it does:** Pause or resume a DAG's scheduled runs.

**Backend API:**
- `PATCH /api/airflow/dags/{dag_id}/pause` - Toggle pause state

**Frontend UI:**
- "Pause" / "Unpause" toggle button on DAG detail panel
- Status indicator updates immediately

**Use case:** *Before deploying a new model version, the team pauses the `daily_retrain` DAG to prevent conflicting runs, deploys the new serving container, then unpauses it.*

### 1.7 Schedule Management

**What it does:** Set or modify a DAG's schedule using Airflow Variables, with visual cron presets.

**Backend API:**
- `GET /api/airflow/dags/{dag_id}/schedule` - Current schedule
- `PUT /api/airflow/dags/{dag_id}/schedule` - Set/clear schedule

**Frontend UI:**
- Text input for cron expressions or Airflow presets (`@daily`, `@hourly`, `@weekly`)
- Visual preset buttons: "Every 6h", "Every 12h", "Weekdays 9am"
- Save/Clear buttons
- Changes take effect on the next DAG parse cycle (~30 seconds)

**Use case:** *The team decides to retrain daily at 2 AM instead of every 6 hours. They click on the DAG, change the schedule from `0 */6 * * *` to `0 2 * * *`, and click Save.*

### 1.8 DAG Templates & Validation

**What it does:** Create new DAGs from templates and validate DAG files for common issues.

**Backend API:**
- `GET /api/airflow/templates` - List DAG templates
- `POST /api/airflow/validate-dag` - Validate DAG Python file
- `POST /api/airflow/dags/create-from-template` - Create DAG from template

**Frontend UI:**
- "Validate" button on DAG detail panel
- Checks: Airflow imports present, DAG definition exists, no `datetime.now()` at parse time, no heavy imports at module level (pandas, numpy, torch, tensorflow, sklearn)
- Warnings and errors displayed inline

**Use case:** *A developer creates their first DAG by selecting the "training_pipeline" template and filling in their project-specific parameters. Before deploying, they click "Validate" and get a warning: "Heavy import detected at module level: pandas. Move import inside task function for faster DAG parsing."*

---

## 2. MLflow - Experiment Tracking & Model Registry

noted provides deep integration with MLflow for experiment tracking, run management, metrics visualization, artifact browsing, model registration, and model serving.

### 2.1 Experiment Management

**What it does:** Create, list, and manage MLflow experiments. Each project can have one or more experiments.

**Backend API:**
- `GET /api/mlflow/experiments` - List all active experiments
- `DELETE /api/mlflow/experiments/{experiment_id}` - Archive an experiment

**Frontend UI:**
- Explorer tree shows experiments under each project with vial icon
- Experiment detail panel shows total runs, snapshot count
- Clickable experiment list with IDs

**Use case:** *A team has separate experiments for "GRU Baseline", "LSTM Comparison", and "PatchTST". Each appears in the Explorer tree. Clicking on "GRU Baseline" shows 12 runs sorted by start time.*

### 2.2 Run Definition & Execution (Run Manager)

**What it does:** Define named run templates by selecting groups of notebook cells, then execute them as MLflow runs with auto-instrumentation.

**Frontend UI (RunManagerPanel):**
- "Experiments" panel with "Add Run" button
- Each run template has: colored bookmark, editable name, cell count badge, play button
- Click code cells to toggle membership in the active run
- Dataset section: checkboxes to include/exclude DVC-tracked files
- 8-color palette for visual distinction between run templates

**Use case:** *A researcher defines two run templates: "Quick Test" (cells 1-5, small dataset) and "Full Training" (cells 1-12, full dataset). They click the play button on "Quick Test" to validate their code before committing to a full training run. Both runs are logged to MLflow automatically.*

### 2.3 Auto-Instrumentation

**What it does:** Automatically logs MLflow metrics, parameters, and artifacts when notebook cells are executed through the Run Manager - no explicit `mlflow.start_run()` code required.

**Backend:**
- Auto-instrumentation captures: execution time, cell outputs, Hydra config hash, DVC data hashes
- Tags each run with `instrumentation: experiments`
- Links runs to the project's MLflow experiment

**Use case:** *A developer writes a training loop in their notebook without any MLflow tracking code. They click "Run" in the Experiments panel. noted automatically creates an MLflow run, logs the training metrics (loss, accuracy), parameters (from Hydra config), and the notebook's output. The run appears in the Experiments panel immediately.*

### 2.4 Run Details & Metrics

**What it does:** View comprehensive run information including metrics, parameters, tags, and inline charts.

**Backend API:**
- `GET /api/mlflow/runs/{run_id}` - Full run details
- `GET /api/mlflow/runs/{run_id}/metrics/{metric_key}` - Metric history (step/value pairs)
- `POST /api/mlflow/runs/{run_id}/stop` - Stop a running run
- `DELETE /api/mlflow/runs/{run_id}` - Archive a run

**Frontend UI:**
- Run info card: status (colored badge), run ID, start/end time, duration
- Metrics grid: 2-column layout of all metrics (key-value pairs)
- Parameters grid: sorted parameter list with values
- Tags grid: custom tags display
- Inline metric charts: ECharts line charts per metric (for metrics with 2+ data points)
- "Ask Assistant" button to analyze run metrics with the LLM

**Use case:** *After a training run completes, the user clicks on it to see: val_loss=0.0342 (with a declining chart), train_loss=0.0128, MAE=1.24, R2=0.89. They notice val_loss plateaued after step 50 and click "Ask Assistant" to get suggestions for improvement.*

### 2.5 Live Training Metrics (Metrics Panel)

**What it does:** Real-time visualization of training metrics as they are logged during execution.

**Frontend UI (MetricsPanel):**
- Three view modes: Split (one chart per metric), Combined (all on one chart), Summary (table)
- Live updates via Socket.IO as metrics stream in
- Epoch progress bar when `total_epochs` metric is detected
- Info bar showing latest value for each metric
- Copy button to export chart as PNG or table as TSV
- History panels to load and overlay metrics from previous runs

**Use case:** *A researcher starts a 100-epoch training run. The Metrics Panel opens showing live charts of `train_loss` and `val_loss` updating every epoch. The progress bar shows "Epoch 42/100 (42%)". They see val_loss starting to increase at epoch 35 and consider early stopping.*

### 2.6 Run Comparison

**What it does:** Side-by-side comparison of two MLflow runs with metrics diff, parameter diff, and overlaid charts.

**Frontend UI:**
- Comparison panel (floating jsPanel) with green/blue color scheme
- Metrics diff table: key, Run A value, Run B value, delta (%), highlighted if different
- Parameters diff table: highlighted changed parameters
- Overlaid metric charts: both runs on same axes for visual comparison
- "Explain Differences" button sends diff to the LLM

**Use case:** *A researcher compares their best GRU run against their best LSTM run. The comparison shows LSTM has 12% lower MAE but took 3x longer to train. The overlaid loss chart shows LSTM converges slower but reaches a lower minimum.*

### 2.7 Artifact Management

**What it does:** Browse, view, and download run artifacts organized by type (models, images, charts, files).

**Backend API:**
- `GET /api/mlflow/runs/{run_id}/artifacts` - Classified artifact list
- `GET /api/mlflow/runs/{run_id}/artifacts/download?path={path}` - Download artifact

**Frontend UI:**
- Artifacts categorized: Models, Images, HTML Charts, Files
- File-type-specific viewers:
  - Images (.png, .jpg, .svg): inline image viewer
  - HTML Charts (.html): sandboxed iframe viewer
  - Text files (.yaml, .json, .txt, .csv, .py): monospace code viewer
  - Model directories: MLmodel YAML displayed as model card

**Use case:** *After training, the user browses artifacts and finds: a confusion matrix image, a training loss chart (HTML), the saved model directory, and a predictions CSV. They view the confusion matrix inline and download the predictions CSV for further analysis.*

### 2.8 Experiment Leaderboard & Reports

**What it does:** View all runs in an experiment as a sortable leaderboard and export reports.

**Backend API:**
- `GET /api/mlflow/experiments/{experiment_id}/leaderboard` - All runs with metrics/params
- `GET /api/reports/experiment/{experiment_id}` - Generate Word (.docx) or Markdown (.md) report

**Frontend UI:**
- Leaderboard view: all runs sorted by a selected metric
- Export buttons: "Export Word" (.docx) and "Export Markdown" (.md)
- Reports include experiment summary, run details, metrics, and parameters

**Use case:** *Before a project review meeting, the team lead exports a Word report of the "GRU Baseline" experiment showing all 12 runs ranked by validation MAE, with charts and parameter tables.*

### 2.9 Model Registry

**What it does:** Register trained models from run artifacts, manage versions, assign lifecycle aliases (@champion, @staging, @archived).

**Backend API:**
- `POST /api/registry/models/register` - Register model from run artifact
- `GET /api/registry/models` - List all registered models
- `GET /api/registry/models/{model_name}/versions` - List versions
- `PUT /api/registry/models/{model_name}/versions/{version}/alias` - Assign alias
- `DELETE /api/registry/models/{model_name}/aliases/{alias}` - Remove alias

**Frontend UI:**
- Models root view: total count, model list with brain icon and alias badges
- Model detail: version count, current aliases with version numbers
- Version table: version, aliases, run ID, created date, alias selector
- "Compare Versions" button for side-by-side version comparison
- "Go to Source Run" navigation button

**Use case:** *After finding the best run, the researcher clicks "Register Model" on the model artifact. They name it `jena_weather_gru`. Version 1 is created. They assign alias `@champion` to mark it as the production model. When they train a better model later, they register it as version 2 and move `@champion` to the new version.*

### 2.10 Model Lineage

**What it does:** Trace the full provenance chain for a model version: Data (DVC) -> Config (Hydra) -> Code (Git) -> Run (MLflow) -> Model (Registry).

**Backend API:**
- `GET /api/registry/models/{model_name}/versions/{version}/lineage` - Full lineage chain

**Frontend UI:**
- Visual lineage chain with 6 layers, each showing relevant metadata:
  - Data Layer: DVC file hash
  - Config Layer: Hydra config hash
  - Code Layer: Git commit, branch, snapshot name
  - Pipeline Layer: Airflow DAG ID and run (if applicable)
  - Run Layer: MLflow run ID, name, status (clickable)
  - Model Layer: name, version, aliases
- Arrows connecting layers
- Collapsed opacity for missing layers

**Use case:** *A production model starts producing unexpected results. The team clicks on the model version's lineage view and traces back: the model was trained with Hydra config hash `abc123`, using DVC data version `def456`, from git commit `789abc` on branch `main`. They checkout the code at that commit and the data at that DVC version to reproduce the exact training conditions.*

### 2.11 Model Serving & Inference

**What it does:** Load registered models into a serving container and run predictions directly from the UI.

**Backend API:**
- `GET /api/serving/health` - Serving container status
- `POST /api/serving/load` - Load model (by name, version, or alias)
- `POST /api/serving/unload` - Unload current model
- `GET /api/serving/schema` - Input/output schema
- `POST /api/serving/predict` - Run inference

**Frontend UI:**
- "Try It" panel with auto-generated input fields from model schema
- Named fields for dataframe-format models (type-aware: number for int/float, text for string)
- JSON textarea for advanced input
- Output visualization based on schema: value/scalar, line chart, bar chart, table
- Prediction history (last 5 predictions)
- "Insert Predict Cell" button generates Python code for the notebook

**Use case:** *The team wants to test their deployed weather forecasting model. They load `jena_weather_gru@champion`, enter the last 24 hours of temperature readings, and click "Predict". The output shows a line chart of predicted temperatures for the next 24 hours. They click "Insert Predict Cell" to add the API call code to their notebook for batch predictions.*

### 2.12 Snapshots

**What it does:** Create immutable snapshots of experiment runs for reproducibility and sharing.

**Frontend UI:**
- "Create Snapshot" button on completed runs
- "Restore Snapshot" button on snapshot runs
- "Fork New Experiment" to create a new experiment from a snapshot

**Use case:** *Before the project deadline, the researcher snapshots their best 3 runs. Two weeks later, they need to reproduce the exact results. They restore the snapshot, which brings back the full run context including data versions, config, and code state.*

---

## 3. DVC - Data Version Control

noted integrates with DVC for tracking large data files (datasets, models, images) with version control, backed by MinIO object storage.

### 3.1 File Tracking

**What it does:** Track large files with DVC using a right-click context menu. Auto-initializes DVC in the project if needed.

**Backend API:**
- `POST /api/dvc/track` - Add file to DVC tracking (runs `dvc add`)
- `POST /api/dvc/remove` - Remove DVC tracking
- `POST /api/dvc/rename` - Rename tracked file (removes, renames, re-adds)

**Frontend UI:**
- Right-click context menu shows "Track with DVC" for trackable file extensions
- Supported: .csv, .pkl, .h5, .hdf5, .parquet, .feather, .arrow, .npy, .npz, .pt, .pth, .onnx, .safetensors, .joblib, .pb, .tflite, .keras, and 20+ more
- DVC-specific confirmation dialog on delete (warns about DVC tracking removal)
- Rename handles .dvc pointer file and .gitignore updates

**Use case:** *A developer adds a 500 MB Parquet dataset to their project. They right-click the file and select "Track with DVC". noted auto-initializes DVC in the project, runs `dvc add`, creates the `.dvc` pointer file, and stages the git changes. The actual data is stored in MinIO, and only the pointer is committed to git.*

### 3.2 Data Status & Overview

**What it does:** Show which files are tracked by DVC across all projects and mounts, with local and cloud sync status.

**Backend API:**
- `POST /api/dvc/status` - Tracked files, changed files, initialization state (5s cache)
- `POST /api/dvc/cloud-status` - Which files are pushed to remote (30s cache)
- `GET /api/dvc/data-overview` - All DVC-tracked files across the workspace

**Frontend UI:**
- Explorer tree shows DVC-tracked files under a "Data" node
- File detail panel shows: file size, MD5 hash, source, DVC pointer file path
- Cloud status indicates which files are synced with MinIO

**Use case:** *A team lead opens the Data section in the Explorer to check the workspace. They see 3 tracked datasets across 2 projects: `jena_weather.csv` (120 MB, synced), `processed_features.parquet` (45 MB, synced), and `predictions.csv` (2 MB, not pushed). They know they need to push the predictions file before the presentation.*

### 3.3 Push & Pull (Remote Sync)

**What it does:** Synchronize DVC-tracked files with MinIO object storage for team sharing and backup.

**Backend API:**
- `POST /api/dvc/push` - Push tracked files to MinIO
- `POST /api/dvc/pull` - Pull tracked files from MinIO

**Use case:** *developer A finishes preprocessing the dataset and pushes it with `dvc push`. developer B, working on the same project from a different machine, runs `dvc pull` to get the latest version of the data. Both developers work with identical datasets without copying large files.*

### 3.4 Version History & Checkout

**What it does:** View the complete version history of a DVC-tracked file (from git log) and restore any previous version.

**Backend API:**
- `POST /api/dvc/file-history` - Version history from git log
- `POST /api/dvc/checkout-version` - Restore a previous version

**Frontend UI:**
- Version history section on file detail panel
- Each version shows: commit hash (7 chars), commit message, file size, date
- "CURRENT" badge on active version
- "Checkout" button on non-current versions to restore

**Use case:** *A researcher discovers their latest preprocessing step introduced a bug that corrupted the dataset. They open the file's version history, see 4 versions, and click "Checkout" on the version from 3 days ago. DVC restores the correct data from MinIO, and they can re-run their preprocessing.*

### 3.5 Integration with Run Manager

**What it does:** Link DVC-tracked datasets to MLflow runs, enabling data lineage tracking.

**Frontend UI:**
- Dataset section in RunManagerPanel shows checkboxes for DVC-tracked files
- Selected datasets are tagged in the MLflow run metadata
- Data hashes are included in the model lineage chain

**Use case:** *Before running an experiment, the researcher selects which datasets to include. The resulting MLflow run records the DVC hash of `jena_weather.csv`, so they can always trace which exact version of the data was used for training.*

---

## 4. Hydra - Configuration Management

noted integrates with Hydra for structured, composable configuration of ML experiments.

### 4.1 Config Schema & Browsing

**What it does:** Display the project's Hydra configuration structure including config groups, options, defaults, and parameter types.

**Backend API:**
- `GET /api/hydra/schema/{project_id}` - Config structure, groups, parameters, defaults

**Frontend UI:**
- Explorer tree shows configuration node (purple sliders icon) under each project
- Supports flat config (single YAML file) or grouped config (multiple groups with options)
- Config groups expandable to show options
- Default option marked with gold star icon
- Config detail panel shows: config dir, config name, groups count, parameters count
- Parameters grid with key, value, and type annotation (int, float, str, list)

**Use case:** *A project has Hydra config groups: `model/` (gru, lstm, transformer), `data/` (full, subset), `optimizer/` (adam, sgd). The Explorer tree shows this hierarchy. Clicking on `model/gru` displays the YAML content with all GRU-specific hyperparameters.*

### 4.2 Config Composition

**What it does:** Compose a resolved Hydra configuration by selecting group options and applying overrides, with hash-based tracking.

**Backend API:**
- `POST /api/hydra/compose` - Compose config with overrides and group selections
  - Returns: resolved config dict, YAML string, SHA-256 hash, source file mapping
- `GET /api/hydra/group/{project_id}/{group}/{option}` - View specific group option

**Frontend UI:**
- "Compose Config" button opens a floating jsPanel
- Dropdown selectors for each config group (pre-filled with defaults)
- Override input fields for each parameter with type hints
- Result area shows: SHA-256 hash, full resolved YAML, source file mapping
- Source tracking: shows which file defined each parameter (overrides in orange, group selections in blue)
- "Copy YAML" button

**Use case:** *A researcher wants to train with LSTM instead of the default GRU and a smaller batch size. They open Compose Config, select `model: lstm` from the dropdown, change `training.batch_size` from 32 to 16, and click Compose. The panel shows the resolved config with hash `sha256:abc123`. This hash is recorded in the MLflow run for reproducibility.*

### 4.3 Config Templates

**What it does:** Save and load named configuration presets for quick experiment setup.

**Backend API:**
- `GET /api/hydra/templates/{project_id}` - List saved templates
- `POST /api/hydra/templates/{project_id}` - Save template
- `GET /api/hydra/templates/{project_id}/{name}` - Load template
- `DELETE /api/hydra/templates/{project_id}/{name}` - Delete template

**Frontend UI:**
- Template dropdown in Compose Config panel
- "Load" button (blue) to apply template values to the form
- "Save" button (green) to save current settings as a named template with description
- "Delete" button (red) to remove a template

**Use case:** *The team defines templates: "Quick Test" (small dataset, 10 epochs, GRU), "Full GRU" (full dataset, 100 epochs, GRU), "Full LSTM" (full dataset, 100 epochs, LSTM). Any team member can select a template to reproduce the exact same configuration.*

### 4.4 Integration with Pipelines

**What it does:** Pass Hydra configuration to Airflow DAG runs via the "Load Hydra Config" button in the Trigger Panel. The Hydra config is the single source of truth for hyperparameters - DAG param defaults mirror the config but are overridden at trigger time with the composed values.

**Backend API:**
- `POST /api/hydra/compose` - Compose resolved config (called by Trigger Panel)

**Frontend UI:**
- "Load Hydra Config" button in the DAG Trigger Panel
- Detects the project from DAG tags, composes the Hydra config, flattens nested keys to match DAG param names
- Includes the SHA-256 config hash as `hydra_config_hash` param for lineage

**Use case:** *When triggering the `jena_training_pipeline` DAG, the user clicks "Load Hydra Config". The panel pre-fills all parameters from the project's `config.yaml`: model type (GRU), epochs (30), batch size (256), learning rate (0.0005), layer units (128/64), and dropout (0.2). The config hash `sha256:abc123` is also set. After the run completes, the hash links the MLflow run to the exact configuration used, enabling full reproducibility.*

### 4.5 Suggest Sweep

**What it does:** Use the LLM Assistant to suggest hyperparameter sweep configurations based on the current Hydra config.

**Frontend UI:**
- "Suggest Sweep" button (green, chat icon) on the Configuration detail panel
- Sends the current config to the LLM with a request for sweep suggestions

**Use case:** *A developer is unsure which hyperparameters to tune. They click "Suggest Sweep" on their config. The LLM analyzes the parameters and suggests: "Try learning_rate: [0.001, 0.0005, 0.0001], hidden_size: [64, 128], dropout: [0.1, 0.3]. This gives 12 combinations. Focus on learning_rate first as it typically has the largest impact on GRU training."*

---

## 5. Cross-Integration Features

The real power of noted comes from how these four systems work together:

### 5.1 End-to-End Lineage

**Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry)**

Every model registered in noted carries a complete provenance chain. Given any model version, you can trace back to the exact data version, configuration, source code, pipeline execution, and training run that produced it.

### 5.2 LLM Assistant Integration

All four integrations are accessible to the LLM Assistant via tool calling:
- **MLflow tools:** `get_experiment_runs`, `get_run_details`, `compare_runs`
- **Airflow tools:** `list_dags`, `get_dag_status`, `get_task_log`
- **DVC tools:** `get_dvc_data_overview`, `get_dvc_file_history`
- **Hydra tools:** `get_hydra_config`

The Assistant can answer questions like "why did this run fail?", "compare my last two experiments", or "what data version was used to train the production model?" by querying the relevant system.

### 5.3 Notebook-Centric Workflow

All interactions happen within the notebook environment:
1. Write code in notebook cells
2. Define runs using the Run Manager (select cells + DVC datasets)
3. Configure with Hydra (select template or compose custom)
4. Execute (locally via Run Manager, or at scale via Airflow)
5. Monitor metrics live in the Metrics Panel
6. Compare runs in the Experiment panel
7. Register the best model
8. Serve and test predictions
9. Export reports for stakeholders

No context switching to separate web UIs for Airflow, MLflow, or DVC.

---

## Appendix: API Endpoint Summary

| Integration | Endpoints | Purpose |
|---|---|---|
| Airflow | 13 endpoints | DAG management, triggering, monitoring, scheduling |
| MLflow | 11 endpoints | Experiment/run management, metrics, artifacts |
| Registry | 7 endpoints | Model registration, versioning, aliases, lineage |
| Serving | 5 endpoints | Model loading, inference, schema |
| DVC | 10 endpoints | File tracking, sync, versioning |
| Hydra | 6 endpoints | Config schema, composition, templates |
| Reports | 1 endpoint | Experiment report generation |
| **Total** | **53 endpoints** | |

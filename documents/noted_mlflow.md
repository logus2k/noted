# noted + MLflow: Experiment Tracking and Model Registry Integration

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Tool Integration: MLflow           |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 2.0                                |
| Date          | 2026-03-14                         |
| Status        | Draft                              |
| Related       | noted_vision.md, noted_scope.md, noted_plan.md |

---

## 1. Overview

MLflow is the experiment tracking and model registry backbone of noted's MLOps stack. It is already fully integrated at the infrastructure level: the `noted-mlflow` container is running, the MLflow tracking URI is injected into every kernel session, and notebooks can `import mlflow` and log runs without any configuration. The `noted-mlflow-artifacts` bucket in MinIO stores all logged artifacts.

What Phase 1A delivered is the invisible plumbing. What the remaining phases build is the surface: purpose-built views in noted's UI that make MLflow's data actionable without requiring users to navigate to the MLflow web application. The MLflow tab in the center pane remains available for advanced use (custom visualizations, artifact browsing, registry administration), but the most common practitioner workflows — logging a run, comparing experiments, promoting a model — are native to noted.

This document describes the use cases across the full MLflow feature set: experiment tracking, artifact management, model registry, and model serving.

---

## 2. What Is Already Working (Phase 1A — Completed)

The following is already functional as of 2026-03-11:

- `MLFLOW_TRACKING_URI=http://mlflow:5000` and `MLFLOW_EXPERIMENT_NAME={project_name}` injected into every kernel by `kernel_manager.py`
- `mlflow` auto-installed in every new virtual environment via `runtime.json` post-create commands
- Notebooks can call `mlflow.start_run()`, `mlflow.log_metric()`, `mlflow.log_param()`, `mlflow.log_artifact()` without any setup
- `mlflow.autolog()` captures sklearn, PyTorch, Keras parameters and metrics automatically
- Experiment name matches the project name — runs are organized by project automatically
- MLflow web UI accessible at `/mlflow` as an embedded center tab
- Service health check with toast notification on connect/disconnect

The use cases below describe what noted's UI will add on top of this foundation.

---

## 3. Use Cases

### 3.1 Logging an Experiment Run

**Context:** A data scientist trains a model in a notebook, trying different hyperparameters. They want each training attempt recorded with its parameters and results, without manually managing a spreadsheet or remembering to call MLflow APIs at the right points.

**Default approach (manual):** Users write standard MLflow code directly in notebook cells. This is always supported and is the default:

```python
import mlflow
mlflow.autolog()

with mlflow.start_run(run_name="baseline"):
    model = LinearRegression()
    model.fit(X, y)
```

This works out of the box because the kernel already has `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_NAME` injected. No configuration needed.

**noted Run Manager (visual approach):** For users who prefer not to write MLflow boilerplate, noted provides the Run Manager — a visual tool that defines run boundaries using cell selection. See section 3.10 for the full Run Manager design.

**noted UI support:**

- **Active run indicator in notebook bar**: When an MLflow run is active (whether started manually or via Run Manager), the notebook's second bar shows a small indicator: run name, experiment name, and a live metric stream (the last logged metric value updates in real time).
- **Post-run summary**: After a run completes, a toast notification shows the run's key metrics and a "View in MLflow" link that opens the run detail in the MLflow center tab.

---

### 3.2 Browsing and Comparing Experiments

**Context:** After 15 runs with different hyperparameters, the user wants to find the best-performing configuration. They want to sort by validation accuracy, filter by run duration, and compare the top 3 runs side by side.

**MLflow approach:** The MLflow UI's experiment table provides sorting, filtering, and a compare view. But it requires leaving the notebook context.

**noted UI support:**

- **Experiments panel in workspace tree**: The workspace tree's root has an "Experiments" section. Expanding the current project's experiment shows all runs in a compact table: run name, status, key metric (configurable), timestamp.
- **Run sort and filter**: The experiment table can be sorted by any logged metric and filtered by parameter value or tag. This uses MLflow's `mlflow.search_runs()` API under the hood.
- **Side-by-side compare**: Selecting two or more runs in the experiment table opens a comparison panel — parameter diffs, metric plots (line chart for each logged metric over training steps), and artifact list diff.
- **Metric plot**: For a single run, the logged metric history (e.g., `val_loss` at each epoch) is plotted as a line chart in the run detail panel. Hovering a data point shows the step number and value.
- **Pinned metrics**: Users can configure which metrics appear in the experiment table's "key metric" column — persisted per project in noted's local settings.

---

### 3.3 Live Metric Streaming During Training

**Context:** A long training run is executing in a notebook kernel. The user wants to watch the loss and accuracy curves update in real time as each epoch completes — without waiting for the run to finish.

**MLflow approach:** `mlflow.log_metric('loss', value, step=epoch)` inside the training loop. The MLflow UI's metric charts refresh periodically.

**noted UI support:**

- **Live metric panel**: When an active run is detected, noted polls MLflow for new metric values every few seconds and renders a live-updating line chart in a side panel (pinned to the right of the notebook, or in the right panel). The chart grows as new data points are logged.
- **Multi-metric display**: Multiple metrics plotted on the same chart (dual Y-axis for different scales) or on separate mini-charts — user configurable.
- **Epoch progress bar**: If the run logs a `total_epochs` parameter, a progress bar shows how far through training the run is.
- **Stop run from UI**: A "Stop Run" button in the live metric panel that interrupts the kernel (equivalent to `kernel:interrupt` Socket.io event) and calls `mlflow.end_run(status='KILLED')` so the partial run is recorded cleanly.

---

### 3.4 Attaching Artifacts to Runs

**Context:** A user trains a model and wants to log the confusion matrix, a sample of misclassified images, the model weights, and a text report alongside the metrics — so future reviewers have everything they need to evaluate the run.

**MLflow approach:** `mlflow.log_figure(fig, 'confusion_matrix.png')`, `mlflow.log_artifact('report.md')`, `mlflow.pytorch.log_model(model, 'model')`.

**noted UI support:**

- **Artifact panel in run detail**: The run detail view (accessible from the experiments panel) lists all logged artifacts in a file tree. Rendering depends on artifact type:
  - **Images** (PNG, JPEG, SVG): rendered inline as thumbnails — confusion matrices, training plots, sample images
  - **HTML files**: rendered in a sandboxed iframe — supports interactive Plotly charts (e.g., forecast-vs-actuals plots from EMI Lab 6)
  - **Text/markdown**: rendered as formatted text in a code viewer
  - **YAML files**: syntax-highlighted YAML display — Hydra config snapshots, model metadata
  - **Model directories**: model card showing framework info (PyTorch `.pt2`, Prophet binary, sklearn pickle), model signature, artifact URI. Supports all MLflow model flavors: `mlflow.pytorch`, `mlflow.prophet`, `mlflow.sklearn`, `mlflow.tensorflow`, `mlflow.pyfunc`
- **Artifact download**: One-click download of any artifact from the run detail panel — fetched from MinIO via noted's artifact proxy endpoint.

---

### 3.5 Reproducibility: Restoring an Experiment

**Context:** A user wants to reproduce the exact conditions of a past run — same code version, same data version, same environment, same hyperparameters.

**MLflow approach:** MLflow logs the Git commit SHA (via `mlflow.log_param('git_commit', ...)` or git integration). Combined with DVC checkout (for data) and environment recreation (for packages), the run can be re-created.

**noted UI support:**

- **Restore environment from run**: The run detail panel has a "Restore" button that: (1) checks out the Git commit SHA logged in the run, (2) runs `dvc checkout` to restore the data version, (3) creates or activates the virtual environment matching the `python_version` and package list logged in the run.
- **Reproduced run**: After restoration, the user can re-execute the notebook from scratch and compare the new run to the original. If metrics match, the run is confirmed reproducible. noted flags the comparison with a "Reproduced" badge if the key metrics are within a configurable tolerance.
- **Lineage chain**: The run detail panel shows the full lineage chain: Git commit → DVC data hash → Hydra config → MLflow run → registered model version (if promoted). Each link is clickable.

---

### 3.6 Model Registry: Promoting a Model

**Context:** A model that performed well in experiments is ready to move to staging for integration testing. The team uses MLflow's model registry to track model versions and their stage (staging / production / archived).

**MLflow approach:** `mlflow.register_model(run_uri, 'ModelName')` creates a version in the registry. Stage transitions via the MLflow UI or API.

**noted UI support:**

- **Models section in workspace tree**: A "Models" node lists all registered models from MLflow's registry. Expanding a model shows its versions (v1, v2, ...) with their current stage (None / Staging / Production / Archived) and the run that produced them.
- **Promote from run detail**: A "Register" button in the experiment run detail panel opens a dialog to register the run's model artifact under a registry name. The user selects the name from existing models or creates a new one.
- **Stage transition**: On a model version node in the workspace tree, a dropdown sets the stage (Staging / Production / Archived). noted calls MLflow's transition API and updates the tree immediately.
- **Promotion approval**: (Phase 3) For teams requiring review before promotion, noted can enforce an approval step — a promotion request is created, assigned to a reviewer, and the transition only executes after approval.
- **Changelog**: The model version detail view shows the diff between this version and the previous one: which parameters changed, which metrics improved or regressed, which DVC data version was used.

---

### 3.7 Model Comparison Across Versions

**Context:** Before promoting a new model version to production, the team wants to compare its performance against the current production model to confirm the regression test passes.

**MLflow approach:** Load both models via MLflow, evaluate them on the same validation set, and compare metrics.

**noted UI support:**

- **Version compare panel**: Selecting two model versions in the Models tree opens a comparison view: side-by-side metrics from their originating runs, parameter diffs, and artifact diffs. If both versions have logged the same metric names, a bar chart shows the delta.
- **Champion/challenger evaluation**: A "Compare on dataset" action that loads both model versions in the same kernel session and evaluates them on a user-specified validation dataset (selected from the project's DVC-tracked data files). Results are logged to MLflow as a comparison run.
- **Production impact estimate**: If the validation metrics show a regression in any configured "production critical" metric (e.g., precision below 0.90), noted flags the promotion with a warning and blocks the stage transition until the user explicitly acknowledges the regression.

---

### 3.8 Model Serving and Prediction

**Context:** A production model registered in MLflow should be queryable from notebooks and from external systems. The team wants to serve the model as a REST endpoint without standing up a separate serving infrastructure.

**MLflow approach:** `mlflow models serve --model-uri models:/ModelName/Production --port 5001` starts a local serving endpoint. For production, noted can run MLflow serving in a sidecar process or integrate with a FastAPI serving layer.

**noted UI support:**

- **Serve model**: A "Serve" button on a model version in the workspace tree starts an MLflow serving process (or noted's own FastAPI wrapper) for the selected version. The serving endpoint URL is displayed in the model version detail.
- **Test prediction from notebook**: A "Predict" cell template that imports the model from the registry and sends a sample input. `import mlflow; model = mlflow.pyfunc.load_model('models:/ModelName/Production')`.
- **Serving status indicator**: Active serving endpoints are shown in the Models tree with a green indicator and the endpoint URL. Clicking the URL opens a simple Swagger/test UI in the center pane.
- **APIs section in workspace**: A top-level "APIs" section in the workspace tree lists all active serving endpoints (including any custom FastAPI endpoints defined in `src/`), their health status, and their request count (from noted's proxy metrics).

---

### 3.9 Experiment Hygiene

**Context:** After months of experimentation, the MLflow experiment for a project has hundreds of runs. Many are junk (failed runs, quick tests, debugging runs). The user wants to archive or delete the noise without losing the valuable runs.

**MLflow approach:** Runs can be deleted (`mlflow.delete_run(run_id)`) or tagged (`mlflow.set_tag(run_id, 'status', 'archived')`).

**noted UI support:**

- **Bulk run management**: Multi-select runs in the experiment table → "Archive selected" tags them with `status=archived` and hides them from the default view (with a "Show archived" toggle).
- **Auto-archive**: A project setting that automatically archives runs shorter than N seconds (incomplete runs that failed before logging any metrics) or runs tagged with `debug`.
- **Run notes**: A free-text notes field on each run (stored as an MLflow tag `noted.notes`) that the user can edit directly from the experiment table, without opening the run detail. Useful for recording why a particular run was interesting or why it was discarded.
- **Experiment export**: Export all runs (or selected runs) as a CSV or JSON file for offline analysis or sharing with stakeholders who do not have noted access.

---

### 3.10 Run Manager: Visual Run Definition and Execution

**Context:** A data scientist has a notebook with data loading, preprocessing, training, and evaluation cells. They want to define reproducible experiment runs — specific subsets of cells that form a coherent training pipeline — without writing MLflow boilerplate. They may also want multiple run configurations in the same notebook (e.g., a "baseline" using cells 1,3,5,7 and a "tuned" using cells 1,3,5,8 where cell 8 has different hyperparameters).

**Design principles:**

- **Manual MLflow is the default.** The Run Manager is a convenience layer. Users who write `mlflow.start_run()` directly always have full control. The Run Manager never overrides explicit MLflow code.
- **Runs are templates, not singletons.** A run definition ("baseline" = cells 1,3,5,7) is a reusable recipe. Each time the user executes it, a new MLflow run instance is created. MLflow shows `baseline`, `baseline`, `baseline` — three separate runs with different timestamps, metrics, and params.
- **One active run at a time.** The user selects which run to activate in the Run Manager. No parallel runs — simple mental model.
- **Cells can belong to multiple runs.** A DataLoader cell might be shared across "baseline" and "tuned" runs. It gets a badge for each run it belongs to.
- **Sparse cell selection.** Runs don't need to be contiguous. Only the cells that matter for the experiment are included. Data exploration cells, documentation cells, debugging cells — all excluded.
- **Only code cells are taggable.** Markdown cells are not part of run definitions.

**UI components:**

1. **Run Manager button in notebook second bar.** Replaces the auto-tracking checkbox. A button labeled "Runs" (similar to the Post-it button) that opens/closes the Run Manager panel.

2. **Run Manager panel.** A panel (similar to Post-it index) listing all defined runs for this notebook:
   - Each run shows: number, name (editable), cell count, color indicator
   - "Add Run" button creates a new run definition
   - "Delete Run" removes a run definition and clears badges from its cells
   - Selecting a run in the panel makes it the active run for cell assignment and execution
   - "Execute Run" button runs all assigned cells sequentially, wrapped in a single MLflow run

3. **Cell assignment via selection.** When the Run Manager is open and a run is selected, the user uses the existing cell selection mechanism (clicking cells, shift-click for range) to assign cells to the selected run. Clicking an already-assigned cell removes it from the run.

4. **Cell badges.** On the right side of each cell, small colored badges indicate run membership. Each run has a distinct color. The badge shows the run number (e.g., "1", "2"). A cell in runs 1 and 3 shows two badges. Badges are visible at all times (not just when the Run Manager is open) so the user always sees the notebook's run structure.

5. **Run execution flow.** When the user clicks "Execute Run" for a run named "baseline" with cells 1, 3, 5, 7:
   - The backend injects `mlflow.start_run(run_name="baseline")` before cell 1
   - Cells 1, 3, 5, 7 execute sequentially in notebook order
   - Framework-specific autolog is activated (sklearn, pytorch, etc.)
   - The backend injects `mlflow.end_run()` after cell 7
   - A new MLflow run appears in the experiment with all captured metrics and params
   - The user can change a hyperparameter, click "Execute Run" again, and get a fresh MLflow run to compare

6. **Back-off.** If any cell in the run contains explicit `mlflow.start_run()`, the Run Manager skips its own start/end injection for that cell. The user's code takes precedence.

**Storage:** Run definitions are stored in notebook metadata:

```json
{
  "metadata": {
    "mlflow_runs": {
      "1": { "name": "baseline", "color": "#4a90d9" },
      "2": { "name": "tuned_lr", "color": "#d94a4a" }
    }
  }
}
```

Cell membership is stored in each cell's metadata:

```json
{
  "cell_type": "code",
  "metadata": {
    "mlflow_runs": [1, 2]
  }
}
```

This keeps everything portable — the notebook file is self-contained, shareable, and compatible with standard Jupyter (which simply ignores the extra metadata).

---

## 4. The Cross-Tool Integration Picture

MLflow is the hub that connects all other tools in noted's stack:

| Tool    | Connection to MLflow |
|---------|---------------------|
| **DVC** | Git commit SHA logged as run param → enables `dvc checkout` from run detail |
| **Hydra** | Resolved config logged as artifact `hydra_config.yaml` → enables config comparison |
| **Airflow** | DAG run ID logged as tag `airflow.dag_run_id` → links execution to experiment |
| **MinIO** | Artifact store backend; model artifacts stored as S3 objects |
| **noted notebooks** | Kernel env vars wire `import mlflow` to the right experiment automatically |

The run detail panel in noted is the single view that shows all of these connections: where the code came from (Git), what data it used (DVC), how it was configured (Hydra), how it was executed (Airflow or notebook), and what it produced (artifacts + model version).

---

## 5. Build Order

MLflow integration in noted builds in this order:

**Phase 1A (COMPLETED):**
- Kernel env injection (tracking URI, experiment name)
- Auto-install in venvs
- MLflow tab in center pane
- Auto-instrumentation engine (silent code injection for pre/post cell execution)

**Phase 1B:**
1. Run Manager UI (run definitions, cell assignment, badges, execute run) [T-1B.11 — done]
2. Experiments section in workspace tree (run list per project) [done]
3. Run detail panel (metrics, params, artifacts inline) [done — basic]
4. Artifact browser with HTML/Plotly rendering and model cards [T-1B.13]
5. DVC hash injection as both tag and parameter [T-1B.7]

**Phase 2:**
4. Live metric streaming during active runs
5. Run compare panel (side-by-side metrics + param diff)
6. Active run indicator in notebook bar
7. Log artifact from notebook output (context menu)

**Phase 3:**
8. Models section in workspace tree (registry browser)
9. Register and promote from run detail
10. Champion/challenger comparison
11. Model serving + APIs section

**Phase 4:**
12. Full lineage chain view (Git → DVC → Hydra → run → model)
13. Reproducibility restore (checkout + dvc checkout + env recreate)
14. Bulk run management and experiment hygiene
15. Promotion approval workflow
16. Config comparison (Hydra artifact diff between runs)

---

## 6. Design Principles for noted's MLflow Integration

- **Manual first, visual optional**: Users always have full access to the MLflow Python API. The Run Manager and other visual tools are convenience layers that generate the same MLflow calls — never a replacement. A user who writes `mlflow.start_run()` is a first-class citizen.
- **Experiment context is always present**: Cell badges show run membership at a glance. The active run name and live metrics are visible in the notebook bar during training. The user never wonders what is being tracked or where.
- **Runs are recipes**: A run definition is a reusable template of cell selections. Each execution creates a fresh MLflow run instance. This matches the natural experiment workflow: define once, iterate many times.
- **The registry is the handoff point**: Model promotion from experiment to registry is the boundary between exploration and production. noted makes this transition explicit, controlled, and auditable.
- **MLflow stays canonical**: noted never duplicates run data into its own database. All experiment data is fetched from MLflow's API. The MLflow tab remains the source of truth and the escape hatch for advanced queries.
- **Lineage is automatic**: The connections between a run and its Git commit, data version, config, and Airflow execution are derived automatically from logged tags and params — not from manual user input.
- **No magic behind the curtains**: Every file created, every MLflow call injected, every run started is visible to the user through badges, indicators, and the workspace tree. Users understand and trust what noted does on their behalf.

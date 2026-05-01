# Page 3: Running Your Experiment

**Goal**: Execute a training run with MLflow tracking, monitor it
live, explore the results in the Explorer, and compare it against
other runs.

**Prerequisite**: A project with a Hydra config and a notebook that
uses `cfg` (Pages 1 and 2).

**Time**: ~15 minutes, plus the time it takes to train.

---

## What is MLflow?

MLflow is the tracking backend that records what happened during each
training run: the parameters you used, the metrics that resulted, and
the artifacts (models, plots, config bundles) that were saved.

In noted, every run created via the Run Manager is automatically
registered in MLflow. You do not write any MLflow boilerplate. noted
handles `mlflow.start_run()`, parameter logging, and artifact storage
transparently.

Runs are grouped into **experiments**. noted uses your **project
name** as the experiment name, so all runs from a project land in
the same experiment automatically.

---

## Step 1: Define a run in the Run Manager

If you completed Page 2 Step 11, you already have a run definition.
If not:

1. Open the notebook.
2. Click the **Experiments icon** (test tube) in the notebook toolbar.
3. Click **Add Run** and give it a name (for example `baseline-gru`).
4. Tag the cells you want to include by hovering over each cell and
   checking the checkbox, or click **Select All** in the Run Manager.

The dataset row fills in automatically:

- If the notebook uses a Hydra config, a read-only row labeled
  **"from Hydra config"** shows the filename from `cfg.data.file`.
  No selection needed; it derives from what the Composer set.
- If no Hydra config is in use, a DVC-tracked file picker appears
  with checkboxes.

Run definitions (name and cell membership) are stored in the
notebook's metadata, so they persist across sessions.

---

## Step 2: Execute the run

1. In the Run Manager panel, click the **play button** (▶) next to
   your run name.
2. noted:
   - Resolves the dataset DVC hash (from the Hydra config or your
     manual picks).
   - Sets the MLflow experiment to your project name.
   - Opens an MLflow run with the name you defined.
   - Executes the tagged cells in order inside that run context.
3. Cell outputs appear in the notebook as cells execute.
4. Live metrics stream to the Metrics panel as training progresses
   (Step 3).

When execution finishes, the run closes and appears in the
**Experiments** section of the Explorer tree.

> **Important**: only cells executed via the Run Manager are wrapped
> in an MLflow run. Running cells manually via the notebook's
> **Run All** button or the Shift+Enter cell-by-cell flow does **not**
> open an MLflow run. Cells will execute, but no parameters, metrics,
> model, or lineage will be captured. Always use the Run Manager play
> button for tracked experiments.

---

## Step 3: Monitor live metrics during training

If your training code calls `mlflow.log_metric()` (or uses noted's
`_MLflowEpochLogger` Keras callback), metrics stream to the
**Metrics panel** in real time.

The Metrics panel opens automatically when a run starts. You can also
open it manually from the notebook toolbar.

**Panel views**:

- **Split** (default): one chart per metric, two columns side by side.
- **Combined**: all metrics overlaid on a single chart.
- **Table**: summary table of final metric values.

**Epoch progress bar**: when epoch-like metrics are detected, a
progress bar appears showing `current epoch / total epochs` with a
percentage, useful for estimating remaining time on long training
runs.

**Historical data**: you can also open the Metrics panel for a past
run from its detail page in the Explorer. Each run opens an
independent panel, so you can monitor two runs side by side.

---

## Step 4: Explore results in the Experiments tree

Once a run finishes, click **Experiments** in the Explorer icon bar
to see the tree.

```
Experiments
  └─ your-project-name            (experiment)
       ├─ ✓ 2026-04-13 - baseline-gru    (finished run)
       ├─ ▶ 2026-04-13 - fast-experiment (running run)
       └─ ✗ 2026-04-12 - broken-run      (failed run)
```

Run status icons:

- **Green check** - FINISHED
- **Blue play** - RUNNING
- **Red X** - FAILED
- **Orange stop** - KILLED

Clicking a run opens its **detail panel**, which shows:

- **Status**, **Run ID** (full ID in monospace), **Started / Ended /
  Duration**.
- **Metrics** - final metric values in a sorted key-value grid.
- **Parameters** - all logged params in a sorted grid.
- **Tags** - run tags (MLflow system tags hidden by default).
- **Inline charts** - one line chart per metric with 2+ data points,
  two columns, interactive (step on X axis, value on Y axis).
- **Action buttons** (for finished runs):
  - **Register Model** - promotes the run's model to the Model
    Registry.
  - **Create Snapshot** - captures a point-in-time snapshot of the
    run.
  - **Ask Assistant** - opens the AI assistant pre-loaded with the
    run's context (Step 6).

**Artifacts**: scroll down in the detail panel to see the run's
stored artifacts, organized into categories:

- **Models** - saved model files.
- **Images** - plots and figures.
- **HTML Charts** - interactive reports (Evidently, etc.).
- **Files** - everything else, including the `hydra/` bundle
  (`hydra/config/`, `hydra/selections.json`, `hydra/resolved.yaml`).
- **Logged Models** - the MLflow 3.x Logged Model entities produced
  by `log_model()` calls. Each Logged Model contains the standard
  `MLmodel`, `conda.yaml`, `python_env.yaml`, `requirements.txt`, and
  the framework-specific weights under `data/`. Clicking any file in
  the tree previews it inline; requirements.txt and the YAML files
  open with syntax highlighting.

---

## Step 5: The Lineage view

Click a **model version** in the Registry (Models > Model Registry)
to see its full lineage chain:

```
Data (DVC) → Config (Hydra) → Pipeline (Airflow) → Code (Git) → Run (MLflow) → Model (Registry)
```

Each layer is a card showing the relevant identifier:

- **Data (DVC)** - the dataset file path and its DVC hash.
- **Config (Hydra)** - the `noted.hydra_config_hash` for that run.
- **Pipeline (Airflow)** - the DAG ID and DAG run ID (if the run was
  produced by an Airflow pipeline).
- **Code (Git)** - the Git commit SHA and branch of the project at
  training time.
- **Run (MLflow)** - the MLflow run ID, name, and status. Clicking
  jumps to the run in the Explorer tree.
- **Model (Registry)** - the model name, version, and any aliases.

Missing layers show `Not tracked` in grey. A complete chain means
every component needed to reproduce the model is identified and
addressable.

---

## Step 6: Compare two runs

Comparing runs lets you see side-by-side diffs of metrics and
parameters to understand what changed.

1. In the Experiments tree, click the first run to open its detail.
2. In the detail panel, click **Compare**.
3. A picker appears listing all other runs in the same experiment.
4. Select the second run.

A comparison panel opens showing:

- **Side-by-side headers** with run names and IDs (color-coded).
- **Metrics diff table** - both values and the numeric delta (with
  percent change) between runs; rows with differences are highlighted.
- **Parameters diff table** - side-by-side params for both runs.
- **Tags diff table** - non-system tags for both runs.
- **Overlaid metric charts** - two-column grid of time-series charts
  with both runs drawn on the same axes for direct visual comparison.
- **Explain Differences** button - sends both run IDs and names to
  the Assistant (Step 7).

---

## Step 7: Ask the Assistant about a run

Every run detail panel has an **Ask Assistant** button. Clicking it:

1. Opens (or focuses) the Assistant panel on the right.
2. Pre-populates the chat with a message that includes the full run
   ID and run name, asking the Assistant to analyze its metrics and
   parameters.

The comparison panel has an **Explain Differences** button that
works similarly, sending both run IDs and names to the Assistant.

The Assistant can retrieve additional context via MCP tools
(`get_notebook_cells`, `mlflow-run-interpretation`, and others) to
provide deeper analysis. Page 7 covers the Assistant in full.

---

## Step 8: Reproduce or iterate from a past run

If a run performed well and you want to reproduce it exactly or
iterate from it, use the **Time Machine** (covered in Page 2,
Steps 9-10):

1. Find the run in the Experiments tree.
2. Open the Configuration Composer from the notebook bar.
3. Switch to **Experiment Run** mode.
4. Select the experiment and the run from the dropdowns.
5. The Composer loads the archived `hydra/` bundle from that run and
   pre-populates selections and overrides.
6. Optionally tweak overrides, then click **Apply to Notebook**.
7. Execute a new run via the Run Manager.

The new run carries its own fresh `hydra/` bundle, keeping the
self-containment guarantee for all runs.

---

## Where to go next

- **Page 4 - From Notebook to Pipeline** shows how to promote a
  successful notebook run into an Airflow DAG for scheduled training.
- **Page 5 - Data Quality** introduces DVC for dataset versioning
  and Evidently for drift detection.
- **Page 6 - Serving & Deploying Models** explains how to deploy a
  registered model into the serving endpoint and test it.

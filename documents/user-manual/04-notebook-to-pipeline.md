# Page 4: From Notebook to Pipeline

**Goal**: Trigger an Airflow DAG from noted, monitor its execution,
debug failures, and trace the resulting MLflow run back to its
source.

**Prerequisite**: A project with a working notebook experiment
(Pages 1-3). A DAG that mirrors the notebook's training logic must
already exist in the Airflow `dags/` folder.

**Time**: ~10 minutes, plus pipeline execution time.

---

## Why pipelines?

A notebook experiment is interactive and exploratory. A pipeline is
repeatable and scheduled. Once you have validated an approach in the
notebook, you promote it to an Airflow DAG so it can:

- Run on a schedule (nightly retraining, fresh data ingestion).
- Run on larger infrastructure without occupying your browser.
- Be triggered by upstream events (new data landed in storage).
- Produce MLflow runs with identical config tracking as your
  notebook.

In noted, DAG runs and notebook Run Manager runs land in the **same
MLflow experiment**. There is no gap: a model trained by the DAG is
visible in the same Experiments tree as one trained interactively.

---

## Step 1: Explore the Orchestration tree

Click the **Orchestration icon** in the Explorer icon bar (network
diagram icon) to open the Orchestration section.

```
Orchestration
  └─ jena_training_pipeline       (DAG, active)
       ├─ 2026-04-13 11:00 - success   (run)
       │    ├─ ingest_data             (task)
       │    ├─ preprocess_data         (task)
       │    ├─ train_model_task        (task)
       │    ├─ log_hydra_lineage       (task)
       │    ├─ promote_model           (task)
       │    └─ evidently_drift         (task)
       └─ 2026-04-12 23:00 - failed    (run)
```

DAG status icons: play = active, pause = paused.
Run status icons: green = success, red = failed, blue = running,
orange = queued.

Clicking a **DAG node** opens the DAG detail panel. Clicking a **run
node** opens the run detail panel. Clicking a **task node** opens
the task log viewer.

---

## Step 2: Review the DAG detail panel

Click the DAG name (for example `jena_training_pipeline`) to open
its detail panel. You see:

- **Status badge** - Enabled or Paused.
- **Description** - from the DAG's `doc_md` or description field.
- **Schedule** - cron expression or `None`.
- **Task graph** - SVG dependency diagram of all tasks in the DAG.
- **Schedule editor** - change or clear the cron schedule directly
  from noted, with presets (`@hourly`, `@daily`, `@weekly`,
  "Every 6h").
- **Pause / Unpause** button - toggle the DAG's active state.
- **Run DAG** button - opens the trigger panel (Step 3).
- **Run history table** - last 10 runs with started time, duration,
  state, and **lineage chips** (Step 7).

---

## Step 3: Trigger a DAG run

Click **Run DAG** in the DAG detail panel. A trigger panel opens
titled `Run DAG: {dag_id}`.

**If your project uses Hydra config**, the trigger panel shows a
**Hydra Configuration** section at the top:

- One dropdown per config group (data, model, scaler, and so on).
- Changing a dropdown recomposes the config and auto-fills the
  corresponding param fields below.
- A **Hydra config hash** is displayed and will be tagged on the
  resulting MLflow run.

**DAG Parameters section**: below the Hydra section (or at the top
if no Hydra config), each DAG parameter appears as a typed input
field:

- Text or number fields with descriptions and default values.
- Checkboxes for boolean parameters.
- Dropdowns where the DAG defines a fixed set of choices.

**Useful buttons in the trigger panel**:

- **Load Last Run Config** - pre-fills all fields from the most
  recent successful run. Essential for "run again with one change"
  workflows.
- **Custom JSON** - text area to merge arbitrary extra fields into
  the run conf, for edge cases not covered by the param schema.

**Triggering**: click **Trigger** at the bottom of the panel. On
success, the panel shows the new run ID and initial state (usually
`queued`). The run appears in the Orchestration tree within a few
seconds.

---

## Step 4: Paused DAG handling

If you try to trigger a paused DAG, a modal appears with three
options:

- **Cancel** - abort the trigger.
- **Keep Paused & Queue Run** - submit the run but leave the DAG
  paused; the run sits in the queue and does not execute until the
  DAG is manually unpaused.
- **Unpause & Run Immediately** - unpauses the DAG and triggers the
  run in one action (the most common choice).

You can also toggle the DAG's paused state directly from the DAG
detail panel using the **Pause / Unpause** button.

---

## Step 5: Monitor the run

Click the new run node in the Orchestration tree to open its detail
panel.

The run detail shows:

- **State badge** - queued → running → success / failed.
- **Run ID** - the full `dag_run_id`.
- **Timestamps** - logical date, actual start, end.
- **Config** - the full JSON config passed to the run (formatted).
- **Task graph** - SVG of task dependencies, nodes colored by current
  task state (green = success, red = failed, blue = running, grey =
  pending).
- **Task list** - sortable rows showing start time, state icon, task
  ID, operator type, and duration. Click any row to open the task
  log.

**Stop Run** button: if the run is in `running` or `queued` state,
a red **Stop Run** button appears at the top of the detail panel.
Clicking it marks the run as failed and stops execution.

Re-click the run node to get the latest state.

---

## Step 6: Inspect task logs

Click any task row in the run detail to open the **task log
viewer**. It shows a full xterm.js terminal with the task's
stdout/stderr output (ANSI colors rendered, 5000-line scrollback).

- If the task is running or queued, logs auto-refresh every 3
  seconds.
- **Copy Log** button copies the full log text to the clipboard.
- **Retry Task** button (for failed tasks) clears the task state so
  Airflow re-queues it on the next scheduler tick. Use this after
  fixing the underlying issue.

The task log viewer has an **Ask Assistant** button. Clicking it
sends the last 1000 characters of the log plus the task state and
names to the AI assistant, pre-loaded with context for error
analysis - useful for quickly diagnosing a failed task without
leaving noted.

---

## Step 7: Trace the MLflow lineage

After a DAG run completes, the **Run History table** in the DAG
detail panel shows a **Lineage** column with clickable chips:

- **MLflow chip** (blue, flask icon) - shows the first 10 characters
  of the MLflow run ID. Clicking it expands the Experiments section
  of the Explorer tree, finds the matching run, and navigates to
  it, switching context from Orchestration to Experiments in one
  click.
- **Hydra hash chip** - the SHA-256 of the resolved config, matching
  the `noted.hydra_config_hash` tag on the MLflow run.
- **DVC hash chip(s)** - dataset hashes registered with the run.

The MLflow run produced by the DAG lands in the **same experiment**
(project name) as all Run Manager runs from that project. It has:

- Full metrics and parameters logged by the training task.
- A `hydra/` artifact bundle uploaded by the `log_hydra_lineage`
  task: `hydra/config/` (full YAML tree),
  `hydra/selections.json`, `hydra/resolved.yaml`.
- The `noted.hydra_config_hash` tag.

This means the DAG-produced run is fully compatible with the Time
Machine: you can load it in the Composer's Experiment Run mode,
inspect its config, and reproduce or iterate from it exactly like
any Run Manager run.

---

## Step 8: The promotion workflow

A typical promotion workflow from notebook to pipeline looks like
this:

1. **Notebook** (interactive): run experiments via Run Manager,
   compare results, identify the winning config.
2. **Time Machine**: load the winning run in the Composer to capture
   its exact config.
3. **DAG**: ensure the DAG's parameters match the Hydra groups and
   override keys from the Composer.
4. **Trigger**: use the Hydra dropdowns in the trigger panel to
   select the same config as the winning run.
5. **Verify**: after the DAG run completes, use the MLflow chip to
   navigate to the DAG's MLflow run and compare it against the
   notebook run. Metrics should match within noise.

---

## Where to go next

- **Page 5 - Data Quality** covers DVC for dataset versioning and
  Evidently for drift detection - the inputs to any reliable
  pipeline.
- **Page 6 - Serving & Deploying Models** explains how to deploy the
  model produced by this pipeline into the serving endpoint.

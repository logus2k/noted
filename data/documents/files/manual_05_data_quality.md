# Page 5: Data Quality

**Goal**: Understand how noted uses Evidently to track data quality
and feature drift, read the Data Health indicator in the Explorer,
and explore detailed reports in the Evidently UI.

**Prerequisite**: A project with a working Airflow pipeline
(Page 4). The pipeline must include the `evidently_quality` and
`evidently_drift` tasks.

**Time**: ~10 minutes.

---

## What is Evidently?

Evidently is an open-source library and UI service that computes
statistical reports on datasets: summary statistics, missing values,
distribution shapes, and feature-level drift scores. It is the
monitoring engine behind noted's data quality surface.

noted's integration is intentionally thin. noted does not render its
own drift charts or quality report panels. Instead, it:

- Surfaces a **Data Health dot** (green / yellow / red) on the Data
  node in the Explorer tree, sourced from the Evidently API.
- Provides a **full Evidently UI** as a service tab for deep
  exploration.
- Lets DAG tasks generate and save Evidently snapshots automatically.

The detailed dashboards, time-series trend panels, and per-feature
drill-downs live in the Evidently UI. This is the same pattern as
MLflow (noted shows run badges; MLflow shows detailed charts) and
Airflow (noted shows task status; Airflow shows the Gantt view).

---

## Step 1: Read the Data Health dot

In the Explorer sidebar, click the **Data** icon. Look at the "Data"
root node title - you may see a small colored dot to the right of
the label:

- **Green dot** - the latest Evidently data quality report passed.
  Feature statistics look healthy (no missing values above threshold,
  distributions within expected ranges).
- **Yellow dot** - warning. One or more quality checks found
  potential issues (some missing values, a feature with unusual
  variance).
- **Red dot** - problem detected. At least one quality check failed
  (missing data above threshold, unexpected distribution, constant
  column).

Hovering the dot shows a short summary from the report.

The dot refreshes automatically when the Explorer loads. If no
Evidently project exists yet for this noted instance, the dot is
absent.

---

## Step 2: Understand which reports the pipeline generates

The jena_weather training DAG (`jena_training_pipeline`) contains
two Evidently tasks that run automatically as part of every pipeline
execution.

### `evidently_quality`

- **What it computes**: a `DataSummaryPreset` report on the
  engineered feature dataset - the full dataset after resampling and
  feature engineering, before the train/val/test split.
- **What it measures**: per-column statistics (mean, std, min, max,
  missing value count, value range, distribution shape) for all
  numerical feature columns.
- **Tags**: `data-quality`, `jena-weather`, `pipeline`.
- **When it runs**: after `preprocess_data` completes, in parallel
  with `train_model_task`.

### `evidently_drift`

- **What it compares**: training split (reference) vs test split
  (current). Detects whether the test distribution has drifted from
  the distribution the model was trained on.
- **What it measures**: a `DataDriftPreset` report - per-feature
  drift scores using statistical tests (KS test for numerical
  features), an overall dataset drift score, and per-feature drift
  labels (drifted / not drifted).
- **Tags**: `drift`, `jena-weather`, `pipeline`.
- **Metadata**: the `run_id` of the corresponding MLflow training
  run, linking the drift report to the model trained on this split.
- **When it runs**: after `train_model_task` completes, in parallel
  with `log_hydra_lineage` and `promote_model`.

Both tasks save their reports as **snapshots** to the Evidently
workspace, where they accumulate over time and form the basis of
trend dashboards.

---

## Step 3: Open the Evidently UI

Click the **Evidently icon** in the bottom section of the icon bar.
The Evidently UI opens as a tab in the center pane.

The Evidently UI is organized into **projects**. The jena_weather
pipeline saves all its reports to a project named `Jena Weather`
(created automatically on first run if it does not exist).

Click the `Jena Weather` project. You see a dashboard with:

- **Snapshot list** - all saved reports, sorted by time, with tags
  and run metadata.
- **Panels** - configurable time-series charts tracking how metric
  values evolve across snapshots (drift score over successive
  pipeline runs, missing value rate over time, and so on).

---

## Step 4: Read a data quality report

In the Evidently project, filter by tag `data-quality` to see
quality snapshots. Click any snapshot to open its interactive
report.

A `DataSummaryPreset` report shows:

- **Dataset summary** - row count, column count, missing value rate,
  duplicate row count.
- **Per-column statistics** - for each numerical feature, a row
  with mean, std, min, max, missing %, and a small distribution
  histogram.
- **Column type summary** - confirms which columns are treated as
  numerical.

Use this to verify that the ingested data looks as expected before
trusting training results. If the temperature column shows an
unexpected mean or a spike in missing values, the model trained on
that data is unreliable regardless of its loss metrics.

---

## Step 5: Read a drift report

Filter by tag `drift` to see drift snapshots. Click any snapshot to
open the drift report.

A `DataDriftPreset` report shows:

- **Dataset-level drift verdict**: "Dataset Drift Detected" or "No
  Drift Detected" based on the share of drifted features.
- **Per-feature drift table**: one row per feature, with the drift
  score, the statistical test used, and a label.
- **Distribution plots**: for each feature, overlaid histograms of
  the reference (training) and current (test) distributions.

For the jena_weather dataset, the training split is early years and
the test split is the most recent period. Some drift is expected
and acceptable. Significant drift in the temperature or pressure
features may indicate a seasonal shift that the model has not seen.

The `run_id` metadata on each drift snapshot links back to the
MLflow training run. To trace a drift finding to the model it
affects:

1. Copy the `run_id` value from the Evidently report metadata.
2. Switch to the Experiments section in the Explorer.
3. Search for the run with that ID to see its metrics and
   parameters.

---

## Step 6: Track trends over time

The Evidently UI's dashboard panels show how quality and drift
metrics evolve across pipeline runs. After several pipeline
executions, you can:

- See whether data quality is improving or degrading.
- Detect seasonal drift patterns in the weather features.
- Correlate drift score increases with drops in model performance
  by cross-referencing the MLflow run IDs in the snapshot metadata.

To add a custom panel, use Evidently's panel builder in the project
dashboard. For example, add a "Drift Share" time-series panel that
tracks the percentage of drifted features per pipeline run.

---

## Where to go next

- **Page 6 - Serving & Deploying Models** explains how to deploy a
  model from the Registry into the serving endpoint and test it.
- **Page 7 - noted Assistant** introduces the in-product AI
  assistant that can interpret data quality reports, drift scores,
  and run lineage with the MCP tools built into noted.

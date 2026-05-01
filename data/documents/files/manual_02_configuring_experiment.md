# Page 2: Configuring Your Experiment

**Goal**: Set up a Hydra configuration for your project, use the
Configuration Composer to pick options and overrides, and use the
Time Machine to reproduce or iterate from any past MLflow run.

**Prerequisite**: A project with a notebook and a Python environment
(Page 1).

**Time**: ~10 minutes

---

## What is Hydra configuration?

Hydra is a configuration framework that organizes experiment settings
as YAML files grouped by concern: model, data, training, scaler, and
so on. Instead of hardcoding values like `epochs = 50` in a notebook,
you define them in a config file and noted injects the resolved
configuration into the running kernel automatically as a variable
called `cfg`.

In Hydra's mental model, the files under `config/` are **templates**,
not "the config". A run is defined by:

- which option you picked from each group, and
- any per-parameter overrides.

noted follows this model literally. Your notebook's metadata records
the selections and overrides. At run time, noted composes them with
the baseline YAML files and injects the result into the kernel.

This gives you:

- Hyperparameter changes without editing code.
- Side-by-side comparison of experiments that used different configs.
- Full lineage of which config produced which run.
- One-click reproduction or iteration from any past MLflow run.

---

## Step 1: Create the config directory structure

Hydra configs live in a `config/` folder at the root of your project.
Each subfolder is a "config group" (for example `model`, `data`,
`training`).

A typical layout looks like:

```
config/
  config.yaml          (main entry point)
  model/
    gru_baseline.yaml
  data/
    default.yaml
  training/
    default.yaml
```

Create each folder and file using right-click > **New Folder** /
**New File** on the project or its subfolders.

---

## Step 2: Write the config files

Click each YAML file to open it in the editor.

**`config/config.yaml`** (main entry point):

```yaml
defaults:
  - model: gru_baseline
  - data: default
  - training: default

seed: 42
```

**`config/model/gru_baseline.yaml`**:

```yaml
type: GRU
units: 128
dropout: 0.2
```

**`config/data/default.yaml`**:

```yaml
file: data/my_dataset.csv
features:
  - temperature
  - humidity
  - pressure
target: temperature
lookback: 120
horizon: 24
split:
  train: 0.7
  val: 0.15
  test: 0.15
```

**`config/training/default.yaml`**:

```yaml
epochs: 50
batch_size: 128
learning_rate: 0.0002
```

Save each file with **Ctrl+S**.

---

## Step 3: Enable Hydra view on the config folder

Once the config files are saved, enable the Hydra-aware view on the
config folder so noted understands the structure.

1. Expand your project in the Explorer to reveal the `config/` folder.
2. Right-click `config/` and choose **Enable Hydra View**.
3. The folder icon changes to the Hydra icon to confirm Hydra view is
   active.

With Hydra view enabled:

- Clicking the `config/` folder shows the **Configuration overview**:
  the config directory, all groups with option counts and defaults,
  discovered parameters, and a **Compose Config** button.
- Clicking a group subfolder (for example `config/model/`) shows the
  **group detail**: available options and which one is the default.
- Clicking individual YAML files still opens them in the editor for
  manual editing.

The Hydra view setting is stored per-project in `.noted/settings.json`
and persists across sessions. To revert, right-click the config folder
and choose **Disable Hydra View** - it returns to a normal directory
view.

---

## Step 4: Open the Configuration Composer

The Configuration Composer is the panel where you pick group options,
adjust overrides, and preview the resolved YAML.

1. Open a notebook in your project.
2. In the notebook's top bar, click the **Hydra icon** button.
3. The Composer opens.

You can also open it from the config folder's detail view by clicking
the **Compose Config** button there.

The Composer has a top header with two modes and a two-column body.

**Top header**:

- **Baseline label** - what the Composer is reading from:
  - `Baseline: Local` when reading from the project's `config/` folder.
  - `Baseline: Run xxxxxx` when reading from a past MLflow run's
    archived config bundle.
- **Mode toggle** - two buttons, `Local Baseline` and `Experiment Run`.
  Toggling is **preview-only**: the notebook is not changed until you
  click Apply.
- **Experiment and Run dropdowns** - enabled in Experiment Run mode.
  List experiments and runs for the current project that have a
  Hydra bundle archived.
- **Apply to Notebook button** - writes the current state
  (selections + overrides + baseline source) into the notebook's
  metadata. Nothing persists until this is clicked. In Experiment Run
  mode the button is disabled until an actual run is selected, so you
  cannot accidentally clear the notebook's selections.

**Left column**:

- **Config Groups** - one dropdown per group, pre-populated with the
  current selection.
- **Overrides** - one input per parameter, pre-populated with the
  current value. Changing an input to a different value records it
  as an override.
- **Templates** - save, load, or delete named combinations of
  selections and overrides (Local mode only).
- **Compose** and **Copy YAML** buttons.
- **Source Files** - which YAML file contributed each top-level key
  in the resolved config.
- **Hash** - the SHA-256 of the resolved config, used as a lineage
  tag on MLflow runs.

**Right column**:

- **Resolved Config** - the full composed YAML with syntax highlighting.

Changing a dropdown or an override updates the resolved preview
instantly.

---

## Step 5: Apply selections to the notebook

The Composer is a preview. Nothing is written to the notebook until
you click **Apply to Notebook** at the top right.

On Apply, the Composer writes three fields into
`notebook.metadata.noted`:

```json
{
  "notebook_uid": "<uuid-v4>",
  "hydra_baseline_source": "project://config/",
  "hydra_selections": {
    "group_selections": { "model": "gru_baseline", "data": "default" },
    "overrides": { "training.epochs": "10" }
  }
}
```

`notebook_uid` is generated automatically the first time a notebook
uses Hydra, and is stable across renames.

From this point on, every cell run in this notebook receives a
freshly composed `cfg` variable built from the recorded selections
and overrides.

---

## Step 6: The baseline badge in the notebook bar

Next to the Hydra icon in the notebook's top bar, noted shows a badge
with two parts: a **label** and a colored **dot**.

**Label** - what the notebook is reading from:

- `BASELINE` - the local `config/` folder (the normal case).
- `RUN xxxxxx` - pinned to an archived MLflow run's baseline (six
  characters of the run ID). Clicking the badge jumps to that run in
  the Explorer tree.

**Dot** - whether the current selections match expectations:

- **Green check** - everything is consistent. For a local baseline,
  this means the schema defaults are in use. For a pinned run, the
  current selections exactly match the archived run's
  `selections.json`.
- **Orange exclamation** - drift detected. For a local baseline, you
  have custom selections or overrides on top of the defaults. For a
  pinned run, your current selections diverge from the archived run's
  snapshot. Hovering the badge shows a tooltip listing exactly which
  keys differ.
- **Red X** - the baseline is unreachable. The archived MLflow run is
  missing, the bundle is incomplete, or MLflow is unavailable. The
  tooltip names the failure. Open the Composer to pick a different
  baseline.

The badge updates live when you Apply changes in the Composer.

---

## Step 7: Use the config in your notebook

Every cell execution automatically injects the resolved configuration
as a variable named `cfg`.

Create a new code cell and type:

```python
print(type(cfg))
print(cfg.model.type)
print(cfg.training.epochs)
print(cfg.data.features)
```

Run the cell. You should see:

```
<class 'omegaconf.dictconfig.DictConfig'>
GRU
50
['temperature', 'humidity', 'pressure']
```

The `cfg` object is an OmegaConf `DictConfig` - you can access nested
values with dot notation (`cfg.model.type`) or dict notation
(`cfg['model']['type']`).

> **Note**: OmegaConf must be installed in your environment for dot
> notation. Install it via the Environments panel if it is not already
> present.

---

## Step 8: Per-run Hydra bundle logging

Every time a cell executes with a Hydra config active, noted logs a
self-contained `hydra/` folder to the MLflow run:

```
run artifacts:
  hydra/
    config/              (full baseline YAML tree)
      config.yaml
      model/gru_baseline.yaml
      data/default.yaml
      training/default.yaml
    selections.json      (group_selections + overrides used)
    resolved.yaml        (the composed output)
```

This bundle is **self-contained**. Each run captures the exact
configuration that was injected into its kernel, regardless of whether
the baseline came from the local `config/` folder or from a past run.
No cross-run dependency chains.

The SHA-256 hash of `resolved.yaml` is also tagged on the MLflow run
as `noted.hydra_config_hash`, usable as a lineage label.

---

## Step 9: Travel back in time

The Composer's Experiment Run mode lets you load any past run's Hydra
baseline and use it for the current notebook.

1. Open the Configuration Composer from the notebook bar.
2. Click **Experiment Run** in the top header.
3. In the **Experiment** dropdown, pick the experiment that contains
   the run you want to reproduce.
4. In the **Run** dropdown, pick the run. Only runs with archived
   Hydra bundles appear in the list.
5. The Composer replaces its schema with the archived version and
   pre-populates selections and overrides from the archived
   `selections.json`.
6. Review and optionally tweak selections or overrides.
7. Click **Apply to Notebook**.

The notebook's metadata is updated:

- `hydra_baseline_source` becomes `mlflow://<run_id>`.
- `hydra_selections` reflects your (possibly tweaked) selections.
- The notebook-bar badge changes to `RUN <6 chars>`.

From this point on, every cell execution in this notebook composes
against the **archived** baseline files, not the current local
`config/`. The archived files are fetched once and cached in memory.
Failures (MLflow unreachable, run deleted, bundle missing) produce a
clear error that names the pointer and the failure - noted never
falls through to a different source.

When a cell runs under an Experiment Run baseline, a new MLflow run
is created for it, and that new run logs its own fresh `hydra/`
bundle containing the same baseline files the notebook used. This
preserves the self-containment guarantee: every run can be reproduced
from its own bundle alone.

To switch back to local baseline, open the Composer again, click
**Local Baseline**, and click Apply.

---

## Step 10: Creating new baselines from past runs

noted deliberately does not automate promoting a past run's config
back into the local `config/` folder. If you find a past run whose
configuration you want to become the new team baseline:

1. Open the MLflow UI for that run.
2. Download the `hydra/config/` folder from its artifacts.
3. Copy the files into your project's `config/` folder.
4. Commit to Git if you want version history.

This is an explicit choice. noted never writes to `config/` on your
behalf.

---

## Step 11: Run your experiment with MLflow tracking

The **Run Manager** is the panel that wraps a notebook execution in
an MLflow run. It handles dataset registration, run naming, and the
MLflow lifecycle so you do not have to add tracking boilerplate to
your cells.

**Opening the Run Manager**:

1. In the notebook's top bar, click the **Experiments icon** (test
   tube, second icon group on the left).
2. A panel titled **Experiments** opens.

**Creating a run definition**:

1. Click **Add Run** in the panel toolbar.
2. Give the run a name (for example `baseline-gru`).
3. In the notebook, cells now show a checkbox on hover. Check the
   cells you want to include in this run, or click **Select All** in
   the panel.

**Dataset tracking**:

- If your notebook uses a Hydra config, the dataset section shows a
  single read-only row with the filename from `cfg.data.file`, a
  Hydra icon, and the label "from Hydra config". noted derives the
  dataset automatically - switching datasets is done via the
  Composer, not here.
- If your notebook does not use Hydra, a DVC-tracked file picker
  appears so you can select which datasets this run uses.

**Executing**:

1. Click the **play button** next to the run name.
2. noted wraps the selected cells in an `mlflow.start_run()` context,
   executes them in order, and registers the DVC dataset hashes with
   the MLflow run.
3. When complete, the new run appears in the Experiments section of
   the Explorer tree with full metrics, parameters, and the `hydra/`
   bundle.

---

## Step 12: Change parameters and re-run

The power of Hydra is changing parameters without editing code:

1. Open the Configuration Composer.
2. Change `training.epochs` from 50 to 10 in the Overrides section.
3. The resolved YAML on the right updates automatically.
4. Click **Apply to Notebook**.
5. Execute the run via the Run Manager. `cfg.training.epochs` now
   returns 10, and the new MLflow run carries its own `hydra/`
   bundle reflecting the override.

Compare the two runs in the Experiments section of the Explorer:
select both, right-click, and choose **Compare Runs** for a
side-by-side diff of metrics and parameters.

---

## Where to go next

- **Page 3 - Running an Experiment** goes deeper on the Run Manager,
  kernel sessions, live metrics streaming, and the Experiment Run
  browser.
- **Page 4 - From Notebook to Pipeline** shows how to promote a
  successful notebook run into an Airflow DAG for scheduled training.
- **Page 6 - Serving & Deploying Models** explains how to deploy a
  registered model into the serving endpoint and test it with the
  Try It panel or an external client.

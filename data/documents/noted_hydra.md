# noted + Hydra: Configuration Management Integration

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Tool Integration: Hydra            |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-03-12                         |
| Status        | Draft                              |
| Related       | noted_vision.md, noted_scope.md, noted_plan.md |

---

## 1. Overview

Hydra is a configuration management framework from Meta that composes and overrides YAML-based configurations at runtime. It solves a persistent MLOps problem: experiments that were run with specific hyperparameters and settings that no one recorded, making results impossible to reproduce.

In a typical workflow without Hydra, configuration values are scattered across hardcoded constants in notebooks, command-line arguments with no history, and ad-hoc YAML files that drift out of sync with the code. Hydra makes configuration a first-class artifact: structured, composable, versioned, and automatically logged.

In noted's stack, Hydra sits between the notebook/pipeline layer and MLflow. When a training run uses a Hydra config, the full resolved configuration (including any overrides applied at runtime) is logged to MLflow as an artifact. This creates an unbroken chain: MLflow stores what the model achieved, Hydra stores exactly how it was configured to achieve it.

---

## 2. How Hydra Fits Into noted

Hydra config files live in the project's `conf/` directory (by convention). They are `.yaml` files that define groups of parameters — model architecture, optimizer settings, dataset paths, training schedule — organized hierarchically. Hydra composes a final config by merging groups, then allows point overrides at runtime.

In noted:

- **Config files** live in the project tree and are editable via the YAML editor
- **Config composition** is visualized before a run so users can see the resolved config
- **Config artifacts** are logged to MLflow automatically, linking each run to its exact configuration
- **Config sweeps** allow users to run the same notebook or pipeline stage with a grid of parameter combinations, managed by Hydra's multirun capability

---

## 3. Use Cases

### 3.1 Structuring Experiment Configuration

**Context:** A data scientist is tired of changing hardcoded values in notebook cells before each experiment. They want a single place to define all parameters, with the ability to switch between presets (e.g., "small model", "large model") without touching code.

**Hydra approach:** Define config groups in `conf/model/small.yaml` and `conf/model/large.yaml`. The training script (or notebook via `hydra.initialize`) loads the selected group. Switching presets is a config choice, not a code change.

**noted UI support:**

- **Config tree in workspace**: The project tree includes a `conf/` folder that expands to show config groups and their files. Config files have a dedicated icon (gear/sliders) to distinguish them from code files.
- **Config file editor**: Clicking a config YAML opens it in the center pane editor — syntax-highlighted, with schema validation hints based on Hydra's structure conventions.
- **Config selector in notebook bar**: A dropdown in the notebook's second bar (alongside the kernel selector) allows selecting the active Hydra config profile (e.g., `model=small`, `model=large`). This selection is passed to the kernel environment so that notebook code using `hydra.initialize` picks it up automatically.
- **Resolved config preview**: A panel that shows the fully resolved Hydra config (after group selection and any overrides), giving users a clear picture of exactly what parameters will be used before they run any cells.

---

### 3.2 Tracking Configuration Across Experiments

**Context:** After running 20 experiments, the user wants to know which configuration produced the best F1 score. MLflow stores metrics but the configs were specified as ad-hoc overrides and are no longer traceable.

**Hydra approach:** When using `@hydra.main`, the resolved config is automatically saved to `outputs/<date>/<time>/.hydra/config.yaml`. Logging this file to MLflow as an artifact (`mlflow.log_artifact('.hydra/config.yaml')`) ties the config to the run.

**noted UI support:**

- **Auto-log Hydra config**: When a notebook run completes and an active MLflow run exists, noted's kernel integration automatically logs the resolved Hydra config (if present) as an MLflow artifact. No user action required.
- **Config in run detail**: The MLflow experiment browser (accessible via the MLflow center tab or a future native panel) shows the logged Hydra config artifact inline in the run detail view — rendered as a pretty-printed YAML, not a raw file download.
- **Config comparison**: Selecting two MLflow runs shows a side-by-side diff of their logged Hydra configs, highlighting which parameters differed between them. This is the fastest path to understanding why two runs produced different results.
- **Config search**: Filter MLflow runs by config values — e.g., "show all runs where `model.learning_rate` was `0.001`" — without requiring the user to know which MLflow parameter keys were used.

---

### 3.3 Parameter Sweeps (Multirun)

**Context:** A researcher wants to compare model performance across a grid of learning rates and batch sizes: 3 learning rates × 4 batch sizes = 12 runs. Currently they manage this with a shell script. They want to see all 12 runs' results side by side.

**Hydra approach:** `python train.py --multirun optimizer.lr=0.001,0.01,0.1 dataloader.batch_size=16,32,64,128` launches all 12 combinations. Each gets its own MLflow run, its own output directory, and its own logged config.

**noted UI support:**

- **Sweep launcher**: A "Sweep" button in the notebook bar or the project's pipeline detail that opens a sweep configuration dialog. Users define the parameter grid using a simple form (parameter name + comma-separated values or range). noted constructs the Hydra multirun command and executes it.
- **Sweep run group**: All runs from a sweep are grouped in the MLflow experiment browser under a common parent — a visual run group with a summary table showing parameter values and key metrics for all variants.
- **Parallel execution**: noted can distribute sweep runs across available kernels (up to the number of active environments) for faster completion on multi-core systems.
- **Best-run highlight**: Within a sweep group, the run with the best value for a selected metric is highlighted. One-click "Promote best config" updates the project's default config to match the winning parameters.

---

### 3.4 Config Inheritance and Composition

**Context:** A team maintains configs for multiple model architectures that share common training settings (optimizer, schedule, data augmentation). They want to avoid duplicating these settings across every architecture config.

**Hydra approach:** Hydra's config composition lets a `conf/model/transformer.yaml` file specify `defaults: [base_training]` to inherit common settings, then override only what is architecture-specific. The resolved config merges all layers.

**noted UI support:**

- **Config inheritance view**: The config file editor shows an "inheritance chain" sidebar — a visual list of which config files are merged to produce the current file's effective config. Hovering a key shows which file in the chain defined it.
- **Override annotation**: In the resolved config preview, keys that are overriding a parent value are annotated with a small indicator and the parent value shown on hover.
- **Validate before run**: Before executing a notebook or pipeline, noted validates that the resolved config is well-formed (no missing required keys, no type mismatches against any registered schema) and surfaces errors in the notebook bar — before the user wastes compute on a malformed run.

---

### 3.5 Sharing Config Presets Across the Team

**Context:** A team lead has tuned a configuration that reliably produces good results. They want other team members to be able to use it as a starting point without having to understand the full config structure.

**Hydra approach:** The config files live in the Git-tracked `conf/` directory. Sharing the config is the same as sharing the code — a Git commit or branch.

**noted UI support:**

- **Config as a project artifact**: The workspace tree treats `conf/` as a first-class project section, alongside `src/` and notebooks. New config group files can be created from a template via the UI without editing raw YAML.
- **Config presets**: Users can mark a specific config composition (group selections + overrides) as a named preset. Presets are stored as small JSON files in `conf/presets/` and appear in the config selector dropdown in the notebook bar.
- **Export config to MLflow**: A one-click action to log the current resolved config as a named artifact to MLflow — useful for pinning a "production config" before a model submission.

---

### 3.6 Airflow Pipeline Runs with Hydra Configs

**Context:** A pipeline defined in Airflow needs to accept different configurations for development (small data, fast model) vs. production (full data, large model) without maintaining separate DAG definitions.

**Hydra approach:** The Airflow task (Python operator or script) uses Hydra to load its config. The DAG definition passes config overrides as task parameters. Different DAG runs can specify different config profiles.

**noted UI support:**

- **Pipeline run with config**: When triggering an Airflow pipeline run from the noted Pipelines section, a "Config overrides" field accepts Hydra override syntax (e.g., `model=large dataset=production`). These are passed to the Airflow run as parameters and forwarded to the task's Hydra config loader.
- **Config in pipeline history**: The Airflow run history view in noted shows the config profile used for each run, alongside the run status and duration.
- **Config template for new runs**: When scheduling a new pipeline run, noted pre-fills the config field with the overrides used in the last successful run, reducing the chance of accidental configuration drift.

---

## 4. The MLflow Connection

Hydra and MLflow are designed to work together. noted makes this connection automatic:

- When a notebook cell initializes an MLflow run and Hydra config is present, noted's kernel integration logs the resolved config as a named artifact (`hydra_config.yaml`) without requiring explicit user code.
- MLflow's parameter logging is augmented: Hydra's flat key path notation (`model.layers.hidden_size`) maps cleanly to MLflow parameter names, allowing filter/search to work across config hierarchy.
- Hydra's output directory (where per-run configs and logs are saved) is redirected to the project's `.hydra_outputs/` directory, which is tracked by DVC — creating a three-way link between code (Git), data (DVC), and configuration (Hydra artifacts in MLflow).

---

## 5. Build Order (Phase 2)

Hydra integration in noted builds in this order:

1. **Config tree display**: Show `conf/` directory in workspace tree with config file editor (YAML + CodeMirror).
2. **Config selector in notebook bar**: Dropdown to choose active config profile, injected into kernel environment.
3. **Resolved config preview**: Panel showing merged/resolved config before execution.
4. **Auto-log to MLflow**: Kernel integration automatically logs resolved config artifact on run completion.
5. **Config comparison in MLflow run detail**: Side-by-side YAML diff for two selected runs.
6. **Sweep launcher**: Parameter grid UI + multirun execution.
7. **Sweep run grouping in MLflow browser**: Visual grouping and best-run highlighting.
8. **Pipeline run config**: Config override field in Airflow trigger dialog.

Steps 1–4 are Phase 2 deliverables. Steps 5–8 extend into Phase 4.

---

## 6. Design Principles for noted's Hydra Integration

- **Config is code**: Config files in `conf/` are version-controlled, editable in the IDE, and treated with the same care as Python source files. They are not a bolt-on.
- **Composition over duplication**: The inheritance view makes it clear how configs compose, encouraging teams to maintain shared base configs rather than copying and diverging.
- **Config drives the run, not the notebook**: Users set the config profile before running — the notebook code reads from config, not from hardcoded cells. noted reinforces this pattern by making the config selector prominent.
- **Every run is reproducible by default**: The combination of auto-logged Hydra config in MLflow + DVC data versioning means every MLflow run is fully reproducible from noted's UI without the user having to think about it.

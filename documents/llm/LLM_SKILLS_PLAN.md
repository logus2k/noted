# LLM Skills Plan

A systematic mapping of every user activity in noted's MLOps integrations to the skill knowledge the LLM needs to assist effectively.

---

## Architecture

### Design Pattern

This follows the skill injection pattern used in production LLM systems: a registry of focused knowledge files that are loaded on demand rather than bloating the system prompt. The system prompt contains only skill names and descriptions (the registry). Full skill content is loaded only when needed, keeping the base prompt lean.

### Data Flow

```
User sends message
    |
    v
Context Assembly (llm_context.py)
    |
    |--> Detect context conditions (notebook open? MLflow run? failed task?)
    |--> Match conditions against skill triggers
    |--> Auto-inject priority 1 skills into context message
    |
    v
LLM receives: system prompt + skill registry + auto-injected skills + workspace context + history
    |
    |--> LLM reasons about the question
    |--> If it needs specialized knowledge: calls get_skill("skill_name") tool
    |--> Receives skill content as tool result
    |--> Incorporates skill knowledge into its answer
    |
    v
Response streamed to user
```

### System Prompt Integration

The skill registry is appended to the system prompt as a compact list (names + descriptions only, ~500 tokens for 36 skills):

```
Available skills (use get_skill tool to load detailed instructions):
- mlflow_run_interpretation: How to interpret MLflow run results in noted
- airflow_task_debugging: Diagnosing failed pipeline tasks
- noted_auto_instrumentation: How noted creates MLflow runs without code
- hydra_pipeline_integration: How Hydra config flows into DAG params
... (36 skills)
```

The LLM sees this list and can request any skill via the `get_skill` tool when it determines one is relevant.

### Skill File Format

```markdown
---
name: skill_identifier
description: One-line description (shown to LLM for dynamic selection)
triggers: [context_condition_1, context_condition_2]
priority: 1-3 (1=always inject when triggered, 2=suggested by context, 3=only on demand)
max_tokens: 800
---
Skill content here - compact, directive, noted-specific.
Written as authoritative instructions that override generic model knowledge.
```

### Injection Paths

**Static (auto-injected based on context) - Priority 1:**
- Context assembly in `llm_context.py` detects conditions (notebook open, MLflow run present, etc.)
- Matching skills with `priority: 1` are injected into the workspace context message
- These are always-on for their trigger conditions - the model doesn't need to request them
- Budget: max 2000 tokens total for static skills per turn
- Currently 7 priority-1 skills identified

**Dynamic (LLM requests via tool) - Priority 2-3:**
- LLM sees skill names + descriptions in the system prompt registry
- Calls `get_skill("skill_name")` when it needs specialized knowledge
- Skill content returned as tool result (consumed in the tool loop)
- No fixed token budget (counts against the 32K context like any tool result)
- Currently 29 priority 2-3 skills identified

### Extensibility

Adding a new skill requires zero code changes:
1. Create a new `.md` file in `data/skills/` with the frontmatter format above
2. The skill loader scans the folder on startup and builds the registry
3. The skill name and description appear in the system prompt automatically
4. If `priority: 1` with a trigger, it auto-injects when that condition is met

### Implementation Components

```
Backend:
  backend/app/managers/llm_skills.py     - Skill loader, registry, static injection logic
  backend/app/managers/llm_tools.py      - get_skill tool registration
  backend/app/managers/llm_context.py    - Static skill injection in context assembly

Agent Server:
  agent_server/data/prompts/noted_system_prompt.txt  - Skill registry appended

Skills Library:
  data/skills/                           - All SKILL.md files (36 planned)
    mlflow_run_interpretation.md
    airflow_task_debugging.md
    noted_auto_instrumentation.md
    ...
```

### Skill Library Location
```
data/skills/
  mlflow_run_interpretation.md
  mlflow_experiment_comparison.md
  dvc_data_tracking.md
  hydra_config_patterns.md
  airflow_dag_debugging.md
  ...
```

---

## Capability Map

### 1. MLflow - Experiment Tracking

| User Activity | Skill Needed | Trigger Condition | Priority |
|---|---|---|---|
| Viewing run metrics after training | `mlflow_run_interpretation` | mlflow_run_in_context | 1 |
| Comparing two runs | `mlflow_run_comparison` | user asks "compare" or "difference" | 2 |
| Understanding why a run failed | `mlflow_run_debugging` | run status = FAILED | 1 |
| Choosing best hyperparameters from multiple runs | `mlflow_hyperparameter_analysis` | experiment with 3+ runs | 2 |
| Interpreting training curves (loss, metrics over epochs) | `mlflow_training_curves` | metric history data present | 2 |
| Understanding auto-instrumentation | `noted_auto_instrumentation` | mlflow experiment in context | 1 |
| Registering a model from a run | `mlflow_model_registration` | user asks about registration/deployment | 2 |
| Interpreting model artifacts | `mlflow_artifacts` | artifacts in context | 3 |
| Creating experiment reports | `mlflow_reporting` | user asks about reports/export | 3 |
| Understanding snapshots | `mlflow_snapshots` | user asks about snapshot/restore | 3 |

#### Skill: `mlflow_run_interpretation`
**What the LLM should know:**
- Runs in noted are created via auto-instrumentation, not manual `mlflow.start_run()` code
- The `hydra_config_hash` tag links to the exact Hydra configuration used
- The `instrumentation: experiments` tag indicates auto-instrumented runs
- Metrics are logged incrementally (step-based) - look at trends, not just final values
- A run's duration includes cell execution overhead, not just training time
- Common metric patterns: train_loss should decrease, val_loss should decrease then plateau
- When val_loss increases while train_loss decreases = overfitting signal

#### Skill: `mlflow_run_comparison`
**What the LLM should know:**
- Use `compare_runs` tool to get side-by-side metrics and params
- Focus on parameters that differ between runs (marked with `*` in comparison)
- Calculate relative improvement (%) not just absolute differences
- When comparing architectures (GRU vs LSTM), consider training time AND accuracy
- Suggest which run is "better" based on the primary metric for the task
- Note any trade-offs (accuracy vs speed, complexity vs performance)

#### Skill: `mlflow_run_debugging`
**What the LLM should know:**
- Check run status: FAILED runs have error info in tags or artifacts
- Common failure causes: OOM (reduce batch size), NaN loss (reduce learning rate), data loading errors
- If run duration is very short + FAILED = likely a setup/import error, not training failure
- Use `get_task_log` if the run was triggered via Airflow pipeline
- Suggest concrete fixes, not generic advice

#### Skill: `mlflow_hyperparameter_analysis`
**What the LLM should know:**
- Use `get_experiment_runs` to see all runs with their params and metrics
- Identify which hyperparameters have the most impact on the target metric
- Look for patterns: does increasing hidden_size always improve performance?
- Suggest next hyperparameters to try based on observed trends
- Reference Hydra config structure when suggesting parameter changes
- Recommend whether to do fine-grained search or explore new parameter dimensions

#### Skill: `mlflow_training_curves`
**What the LLM should know:**
- Use metric history (step/value pairs) to analyze training dynamics
- Healthy training: both train_loss and val_loss decrease, gap stays small
- Overfitting: train_loss decreases, val_loss starts increasing
- Underfitting: both losses plateau at high values
- Learning rate too high: loss oscillates or diverges
- Learning rate too low: loss decreases very slowly
- Suggest early stopping epoch based on val_loss minimum
- Recommend learning rate schedule adjustments

---

### 2. Airflow - Pipeline Orchestration

| User Activity | Skill Needed | Trigger Condition | Priority |
|---|---|---|---|
| Understanding DAG structure | `airflow_dag_overview` | dag_in_context | 2 |
| Debugging a failed task | `airflow_task_debugging` | task state = failed | 1 |
| Configuring a DAG trigger | `airflow_trigger_config` | user in trigger panel context | 2 |
| Setting up a sweep | `airflow_sweep_strategy` | user asks about sweep/grid search | 2 |
| Understanding schedule expressions | `airflow_scheduling` | user asks about schedule/cron | 3 |
| Creating a new DAG | `airflow_dag_creation` | user asks to create pipeline | 2 |
| Understanding task dependencies | `airflow_task_dependencies` | dag structure in context | 3 |
| Monitoring pipeline performance | `airflow_performance` | multiple dag runs in context | 3 |

#### Skill: `airflow_task_debugging`
**What the LLM should know:**
- Use `get_task_log` tool to fetch the actual error log
- Common task failures: import errors, file not found, OOM, timeout
- In noted, DAG files live in the project's `dags/` folder (mounted into Airflow)
- Tasks run in the Airflow worker container, not in the notebook kernel
- If a task needs Python packages, they must be in the worker's environment
- "Retry Task" clears the task instance for re-execution without re-running the whole DAG
- Check if the DAG was paused (paused DAGs don't execute even manually triggered runs)

#### Skill: `airflow_sweep_strategy`
**What the LLM should know:**
- Sweeps create a Cartesian product of all parameter combinations
- Keep sweep size manageable: 3 x 3 x 2 = 18 runs, not 10 x 10 x 10 = 1000
- Start with coarse search (few values, wide range), then refine
- Parameters with most impact should have more values
- All sweep runs share a `_sweep_id` for grouping
- After sweep completes, use `get_experiment_runs` to compare results
- Suggest which parameters to sweep based on the model architecture

#### Skill: `airflow_dag_creation`
**What the LLM should know:**
- noted provides DAG templates via `GET /api/airflow/templates`
- DAGs use Airflow SDK decorators (`@dag`, `@task`)
- Parameters should map to Hydra config keys (not hardcoded values)
- Include `hydra_config_hash` param for lineage tracking
- Tags should include `noted` and the project name
- Schedule via Variable for UI editability
- Validate DAG before deploying (heavy imports, datetime.now warnings)

---

### 3. DVC - Data Version Control

| User Activity | Skill Needed | Trigger Condition | Priority |
|---|---|---|---|
| Tracking a new data file | `dvc_tracking` | user asks about tracking data | 2 |
| Understanding data versions | `dvc_versioning` | dvc files in context | 2 |
| Debugging push/pull failures | `dvc_sync_debugging` | user reports sync error | 2 |
| Choosing what to track | `dvc_best_practices` | new project setup | 3 |
| Understanding data lineage | `dvc_lineage` | model lineage in context | 2 |
| Restoring a previous data version | `dvc_checkout` | user asks about restoring/rollback | 3 |

#### Skill: `dvc_tracking`
**What the LLM should know:**
- In noted, right-click a file -> "Track with DVC" (no CLI needed)
- DVC auto-initializes in the project if not already set up
- MinIO is the remote storage backend (S3-compatible, on-premises)
- Supported file types: .csv, .pkl, .h5, .parquet, .npy, .pt, .onnx, .safetensors, etc.
- DVC creates a `.dvc` pointer file and adds the data file to `.gitignore`
- After tracking, `dvc push` uploads to MinIO, `dvc pull` downloads
- The DVC hash uniquely identifies a data version for lineage

#### Skill: `dvc_best_practices`
**What the LLM should know:**
- Track: raw datasets, processed features, trained models, large outputs
- Don't track: code files, config files, small metadata, notebooks
- Use meaningful commit messages when versioning data changes
- Push to remote after each significant data change
- Link datasets to MLflow runs via the Run Manager's dataset checkboxes
- Version your preprocessing pipeline alongside data versions

---

### 4. Hydra - Configuration Management

| User Activity | Skill Needed | Trigger Condition | Priority |
|---|---|---|---|
| Setting up a config for a new project | `hydra_setup` | no config found in project | 2 |
| Composing a config with overrides | `hydra_composition` | hydra config in context | 2 |
| Understanding config groups | `hydra_groups` | config groups detected | 3 |
| Designing a sweep config | `hydra_sweep_design` | user asks about hyperparameter tuning | 2 |
| Linking config to pipeline | `hydra_pipeline_integration` | DAG + Hydra in context | 1 |
| Saving/loading templates | `hydra_templates` | user asks about saving config | 3 |

#### Skill: `hydra_composition`
**What the LLM should know:**
- noted's Hydra integration composes configs without requiring Hydra CLI
- Config is composed via `POST /api/hydra/compose` with optional overrides and group selections
- Each composed config gets a SHA-256 hash for reproducibility tracking
- The hash is included in MLflow runs and Airflow DAG runs for lineage
- Overrides use dotted-key notation: `model.type=LSTM`, `training.epochs=100`
- Config groups allow switching entire parameter sets: `model: gru` vs `model: lstm`
- Source tracking shows which file defined each parameter

#### Skill: `hydra_pipeline_integration`
**What the LLM should know:**
- The "Load Hydra Config" button in the Trigger Panel maps Hydra values to DAG params
- Mapping convention: nested Hydra keys flatten to DAG param names
  - `model.type` -> `model_type`
  - `training.epochs` -> `epochs`
  - `training.learning_rate` -> `learning_rate`
- The `hydra_config_hash` param is always included for lineage
- DAG Param defaults should mirror the Hydra config defaults
- When designing sweeps, vary Hydra config values, not raw DAG params

---

### 5. Cross-Cutting Skills

| User Activity | Skill Needed | Trigger Condition | Priority |
|---|---|---|---|
| Understanding end-to-end lineage | `noted_lineage` | model version in context | 2 |
| Writing/editing notebook code | `noted_coding_conventions` | notebook cell selected | 1 |
| Explaining noted's architecture | `noted_platform_overview` | user asks "how does noted work" | 3 |
| Understanding auto-instrumentation | `noted_auto_instrumentation` | any MLflow context | 1 |
| Troubleshooting connectivity | `noted_troubleshooting` | user reports error | 2 |
| General ML workflow guidance | `ml_workflow_guidance` | new experiment setup | 3 |

#### Skill: `noted_auto_instrumentation`
**What the LLM should know:**
- noted automatically creates MLflow runs when cells are executed via the Run Manager
- No `mlflow.start_run()` or tracking code is needed in the notebook
- Auto-instrumentation captures: execution metrics, Hydra config hash, DVC data hashes
- Runs are tagged with `instrumentation: experiments`
- A notebook's MLflow experiment can have runs even without any MLflow code in the cells
- The experiment name is typically the project ID
- NEVER suggest adding manual MLflow tracking code unless explicitly asked

#### Skill: `noted_coding_conventions`
**What the LLM should know:**
- noted uses Python as the primary language
- Notebooks support multiple runtimes/venvs per project
- Code cells should be self-contained and executable in order
- Prefer standard library + common ML packages (numpy, pandas, sklearn, torch, tensorflow)
- When suggesting code changes, provide minimal diffs not full rewrites
- Reference specific cell numbers when discussing code
- Markdown cells use standard markdown + LaTeX math notation

#### Skill: `noted_lineage`
**What the LLM should know:**
- Full lineage chain: Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry)
- Each layer stores a hash or ID that links to the next
- DVC hash identifies the exact data version
- Hydra config hash identifies the exact configuration
- Git commit identifies the exact code version
- Airflow DAG run ID identifies the pipeline execution
- MLflow run ID identifies the training run
- Model version in Registry points back to the source run
- Use lineage to reproduce any model from scratch

---

## Implementation Summary

### Total Skills: ~30

| Category | Skills | Priority 1 (static) | Priority 2-3 (dynamic) |
|---|---|---|---|
| MLflow | 10 | 3 | 7 |
| Airflow | 8 | 1 | 7 |
| DVC | 6 | 0 | 6 |
| Hydra | 6 | 1 | 5 |
| Cross-cutting | 6 | 2 | 4 |
| **Total** | **36** | **7** | **29** |

### Token Budget Estimate
- Average skill: ~400-800 tokens
- Static skills per turn (max 2-3): ~1200-2000 tokens
- Remaining for conversation + context: ~30K tokens
- Comfortable within 32K window

### Implementation Steps
1. Create `data/skills/` folder with initial skill files
2. Create `backend/app/managers/llm_skills.py` - skill loader + static injection logic
3. Add `get_skill` tool to `llm_tools.py`
4. Integrate static injection into `llm_context.py` context assembly
5. Update system prompt to list available skills for dynamic selection
6. Test with each trigger condition

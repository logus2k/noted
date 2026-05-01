---
name: mlflow-run-interpretation
description: How to interpret MLflow run metrics, parameters, and tags in noted. Use when user asks about run metrics, training results, experiment outcomes, why a metric value is high/low, or what a run's status means.
triggers: [mlflow_run_in_context]
priority: 1
max_tokens: 500
---
When interpreting MLflow runs in noted:

RUN STATUS:
- FINISHED = completed successfully. Check metrics for quality.
- FAILED = error during execution. Check task logs if pipeline-triggered, or cell output if notebook-triggered.
- RUNNING = still in progress. Metrics may be incomplete.
- KILLED = manually stopped by user.

METRICS:
- Metrics are logged incrementally (step-based). Analyze trends, not just final values.
- Common patterns: train_loss decreasing + val_loss decreasing = healthy training.
- train_loss decreasing + val_loss increasing = overfitting. Suggest regularization, dropout, or early stopping.
- Both losses plateauing high = underfitting. Suggest more capacity, longer training, or feature engineering.
- Use the `get_run_details` tool to see full metrics if only a summary is shown.

PARAMETERS:
- Parameters come from Hydra config (via Run Manager), not manually set.
- The `hydra_config_hash` links to the exact configuration. Use `get_hydra_config` to see it.

TAGS:
- `instrumentation: experiments` = Run Manager-created run (no manual MLflow code needed).
- Custom tags may indicate run purpose or category.

DURATION:
- Run duration includes notebook cell execution overhead, not just training time.
- Very short duration + FINISHED = likely a non-training run (setup, validation).

Always reference specific metric values from the data. Never fabricate metrics that don't appear in the tool results.

TOOL CHOICE BY QUESTION SHAPE:
- "Is a val_mae of X good for this task?" / "is run Y competitive?" / "how does run Z compare to published baselines?"
  - If the user names a specific run, call `get_run_details(run_id=<id>)` ONCE to see the full metrics/params and then ANSWER from domain knowledge. Do NOT call `get_experiment_runs` first if a specific run is already named.
  - If the question is purely "is X good?" without needing a specific run, answer from domain knowledge without any tool call.
- "Is my model competitive with published baselines?" (conceptual benchmarking question) -> NO tool calls EVER - not even get_experiment_runs. The answer compares the user-stated value to typical published ranges for that task; cite well-known benchmark values where possible. External benchmarks are not in MLflow.
- "How many runs are in experiment X?" / "what's the size of experiment X?" -> `get_experiment_runs(experiment_name=X)` ONCE, then answer with ONLY the count + a one-line status-mix summary (e.g. "5 runs, all FINISHED"). Do NOT enumerate every run's metrics/params - the user asked HOW MANY, not WHICH. If they want the list, they'll follow up.

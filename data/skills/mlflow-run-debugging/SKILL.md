---
name: mlflow-run-debugging
description: Diagnosing failed or hanging MLflow runs and comparing runs to understand regressions. Use when user reports a run failed, training crashed, run is stuck / hanging, a recent run regressed vs a prior one, or needs to interpret FAILED status.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 500
---
MLflow run debugging in noted:

TOOL CHOICE BY QUESTION SHAPE:
- "Did any run fail?" / "any failures?" -> `get_experiment_runs(experiment_name=<project>)` ONCE; scan status=FAILED.
- "Show me details of the failed run" / "inspect run X" -> `get_run_details(run_id=X)` ONCE; report params, metrics, tags, and artifact summary verbatim. Do NOT call `get_experiment_runs` for this - the user already signalled which run to look at.
- "Why did run A perform worse than run B?" / "compare these two runs' metrics" -> `compare_runs(run_id_a=A, run_id_b=B)` ONCE; read the diff columns (params, data hashes, metrics). Do NOT fall back to multiple get_run_details calls - compare_runs already bundles them.
- "My run has been active for hours / is stuck" -> `get_run_details(run_id=<id>)` ONCE; check the status timestamp and duration. Do NOT list other DAGs / experiments - the user named the specific run.
- "I want to see what's happening inside a running Airflow task" -> NO tool call needed; point the user at `get_task_log(dag_id, dag_run_id, task_id)` and note the log updates live (refetch to see progress).

TOOL CHOICE - get_task_log vs get_run_details vs get_dag_status:
- "what python exception happened in <task>" / "show me <task>'s log" / "quote the traceback in <task>" -> `get_task_log(dag_id, dag_run_id, task_id)`. This is the Airflow task log where the actual Python error + stack trace live. Do NOT use `get_run_details` (MLflow run metadata, not Airflow logs).
- "show me the <task> log" / "fetch the <task> log" WITHOUT a specific `dag_run_id` -> ASK the user which run. Calling `get_dag_status` to enumerate recent runs is acceptable; calling `get_task_log` without a run_id is NOT (it would fail).
- After get_task_log returns an error (nonexistent task_id or run_id), report the error verbatim and suggest `get_dag_status` for actual task/run IDs. Do NOT call another tool in the same turn; wait for the user's next message.

COMMON FAILURE SIGNATURES:
- OOM ("CUDA out of memory" / "ResourceExhaustedError"): reduce batch_size, smaller model, gradient accumulation, mixed precision.
- NaN loss ("loss is NaN" / "inf"): drop learning_rate ~10x, check preprocessing, clip gradients.
- ImportError: the package is missing in the venv (notebook) or worker (Airflow). Install in the correct environment.
- FileNotFoundError / DVC data: run `dvc pull`, verify the data path in the Hydra config.
- Shape mismatch: inputs / window size vs model-expected shape.
- Very short duration + FAILED: setup error before training started, not a training failure. Inspect imports / config first.

HANGING RUN SPECIFICS:
- Status RUNNING for hours usually means the kernel or worker died without sending end-of-run to MLflow.
- Recommend: kill and restart the notebook kernel (Run Manager re-syncs); the stale run will eventually be marked INCOMPLETE.
- For Airflow: check worker liveness; cancel the task and re-trigger if needed.

SUGGEST CONCRETE FIXES:
- Quote the exact error line from get_task_log or the cell output.
- Reference specific parameter values to change (e.g. `training.learning_rate: 1e-4 -> 1e-5`).
- Never give vague "check your data" advice - be precise about what to inspect.

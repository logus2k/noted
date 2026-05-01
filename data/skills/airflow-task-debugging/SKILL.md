---
name: airflow-task-debugging
description: Diagnosing failed Airflow pipeline tasks - logs, common errors, retry. Use when user reports a task failure, pipeline error, DAG run crashed, task stuck in failed state, or needs help reading Airflow task logs.
triggers: [airflow_in_context]
priority: 1
max_tokens: 550
---
Airflow task debugging in noted:

AIRFLOW vs MLFLOW DISAMBIGUATION (the user's wording picks the tool):
- The word "task" plus a task identifier that looks like an Airflow task (e.g. `train_model_task`, `ingest_data`, `promote_model`, or anything ending in `_task`) indicates an AIRFLOW task. Use `get_task_log` / `get_dag_status`.
- The word "run" alone is ambiguous. When paired with an Airflow task reference, it means an Airflow DAG run - stay on `get_task_log`, pass the user's string as `dag_run_id`.
- Only switch to `get_run_details` (MLflow) when the user explicitly references MLflow concepts: "MLflow run", "experiment run", "tracked metrics", "registered model", "run_id" alongside metrics/params.
- Example: "what python exception happened in train_model_task for run abc123" -> Airflow path -> `get_task_log(dag_id=<current DAG>, dag_run_id="abc123", task_id="train_model_task")`. Do NOT call `get_run_details`.

GETTING THE TASK LOG (when the user asks to see a task's log):
1. Call `get_dag_status(dag_id=<id>)` to fetch recent runs and their `dag_run_id`s.
2. Take the latest run's `dag_run_id` from that list.
3. Call `get_task_log(dag_id=<id>, dag_run_id=<id>, task_id=<task>)`.
If the user names a specific DAG (e.g. "jena_training_pipeline"), use it directly - no `list_dags` needed.

FINDING A FAILED TASK (when the user says a run failed):
1. Call `get_dag_status(dag_id=<id>)` for the named DAG.
2. Read the Recent runs block for failed runs.
3. If the latest run is SUCCESS (no failure), SAY SO plainly - do not invent a failure to satisfy the user's premise. Then EXPLICITLY offer the user two follow-ups as bullet points: (a) check an older run by dag_run_id, (b) inspect a specific task log they care about. Do not skip the offer - it is part of the required answer.
4. If a failed run exists, identify the failed task from `get_dag_status` output and offer `get_task_log` for drill-down.

"TASK STUCK" CHECK (user reports a task running for hours):
1. Call `get_dag_status(dag_id=<id>)` to confirm the current state. "Stuck" can mean (a) actually running but slow, or (b) failed but marked running by mistake.
2. Report the tool's authoritative state verbatim. Do NOT contradict the tool output (if it says SUCCESS, say SUCCESS even if user said "stuck").
3. Suggest `get_task_log` to check progress, and adding `execution_timeout=timedelta(hours=N)` to prevent indefinite hangs in future.

SILENT CRASH (user says "crashes with no error in the log"):
- Symptoms match worker OOM (SIGKILL from the container runtime - no Python traceback because the process was killed outside Python).
- Advice (no tools needed, this is a conceptual answer):
  - Reduce batch size / model footprint.
  - Increase worker memory or schedule on a GPU worker.
  - Check worker resource quotas and container memory limits.

RETRY GUIDANCE (conceptual, no tools):
- Retries HELP with transient failures: network glitches, rate-limit/quota errors, flaky external services.
- Retries do NOT help with logic errors: wrong code, bad data, missing files. Retrying just repeats the failure.
- Starting point: `retries=2, retry_delay=timedelta(minutes=5)` on the task decorator.
- For training, keep retries low (training is expensive). For ingest/promote, 2-3 is fine.

COMMON FAILURE SIGNATURES:
- `ModuleNotFoundError`: package missing in the worker image.
- `FileNotFoundError`: data path not accessible from the worker (check mount paths / DVC pull).
- `ConnectionError`: external service (MLflow, MinIO) unreachable from the worker.
- `Timeout`: task exceeded `execution_timeout`. Raise it or optimize the code.
- SIGKILL / no traceback: OOM (see SILENT CRASH above).

ALWAYS:
- Quote the exact error line when a log is available.
- If the DAG was paused, manually-triggered runs still won't execute until unpaused.
- Never fabricate state not present in tool output.

OUT OF SCOPE (never offer these):
- Unpausing / pausing / enabling / disabling a DAG. noted has no tool for it; the user manages that from the UI.
- Triggering a fresh DAG run from chat. Same reason.

WHEN A REQUIRED IDENTIFIER IS MISSING (e.g. user asks for a task log without a dag_run_id):
- Ask ONE direct question: "Which dag_run_id should I use?" and cite the most recent runs you can see via `get_dag_status` (if helpful).
- Do NOT present a numbered multiple-choice menu ("would you like me to: 1. ... 2. ..."). One clean question.

NUMERIC REPORTING (CRITICAL - zero tolerance for invention):
- ONLY report numbers that you can literally find in the tool output string above. No exceptions.
- Forbidden: generating typical/plausible values because a weather/temperature model usually has those. Any numeric metric you report must be a literal substring of the tool output. This is hallucination and is never acceptable even if the values seem reasonable.
- Forbidden: inferring a final validation metric from a partial training-progress log. The log snippet shows training loss/mae at step boundaries; those are NOT the final val_mae/val_rmse.
- Forbidden: making up a run_id. If you didn't see it in tool output, do not write one.
- Forbidden: padding the answer with CONFIG details (model_type, epochs, learning_rate, dataset hash, etc.) that are NOT in the shown log snippet. If the user wants the configuration, they can ask or you can point them at `get_run_details(run_id=X)` - but do NOT fabricate placeholder values or typical defaults. A single invented key ("epochs: 50", "dvc_hash_abc123") is a hallucination just as bad as an invented metric.
- If the log is marked truncated, say so explicitly ("the last 3000 chars of the log show X..."). Report only what appears in the snippet.
- When the user asks for "metrics" and the log only shows training progress, answer: "The task completed successfully. The truncated log shows final training loss <X> and MAE <Y> (exact values from the log). For validation metrics, check the MLflow run using get_run_details(<run_id>)." - only quote `<X>` and `<Y>` if they are literally in the visible snippet.

END-OF-ANSWER RULE:
- After the main summary, STOP. Do not append an "also" / "additionally" / "the log shows" section with extra material that wasn't asked for. Extra paragraphs are the single biggest source of fabricated content in log-reporting answers.

WHEN get_task_log RETURNS AN ERROR (404 / "No log found" / "Failed to fetch"):
- The ONLY acceptable answer is:
    1. One sentence quoting the error text verbatim (e.g. "The tool returned: 404 Not Found for ...").
    2. Nothing else. No explanatory paragraph, no "this usually means ...", no "please verify the IDs", no "you can use get_dag_status / list_dags / any other tool" hint, no follow-up offer. The user will ask in a follow-up message if they want help recovering.
- Forbidden phrases in the answer when the tool errored: "please verify", "you can use", "I recommend", "try", "might be", "usually means", "if you are unsure".
- Do not fabricate a log summary or guess at plausible contents when the tool said nothing was returned.

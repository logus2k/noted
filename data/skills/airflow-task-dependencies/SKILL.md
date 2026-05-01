---
name: airflow-task-dependencies
description: Task ordering, trigger rules, and branching patterns. Use when user asks how to set task order, run tasks in parallel, use trigger rules, create conditional branches, or handle fan-out/fan-in patterns.
triggers: [airflow_in_context]
priority: 1
max_tokens: 350
---
Task dependencies in Airflow DAGs:

BASIC ORDERING:
- TaskFlow API: pass return values between tasks to create implicit dependencies.
  `data = preprocess(); model = train(data); evaluate(model)`
- Classic operators: use `>>` notation: `preprocess >> train >> evaluate`.
- Fan-out: `preprocess >> [train_gru, train_lstm]` runs both in parallel.
- Fan-in: `[train_gru, train_lstm] >> compare` waits for both to finish.

TRIGGER RULES:
- `all_success` (default): task runs only if all upstream tasks succeeded.
- `all_failed`: runs only if all upstream tasks failed (useful for error handlers).
- `one_success`: runs as soon as any upstream task succeeds.
- `all_done`: runs regardless of upstream success/failure (for cleanup tasks).
- `none_skipped`: runs only if no upstream tasks were skipped.
- Set via: `@task(trigger_rule="all_done")`.

BRANCHING:
- Use `@task.branch` to choose which downstream path to execute.
- The branch task returns the task_id of the next task to run.
- Unselected branches are marked as "skipped".
- Useful for conditional logic: train different models based on data characteristics.

COMMON PATTERNS:
- Linear: preprocess -> train -> evaluate -> register.
- Parallel training: preprocess -> [model_a, model_b] -> compare -> register_best.
- Conditional: check_data -> branch -> [retrain / skip].
- Cleanup: all tasks -> cleanup_task (trigger_rule=all_done).

NOTED-SPECIFIC:
- The task graph is visualized in the Pipelines panel.
- Click on edges to see the dependency type.
- Failed upstream tasks cause downstream tasks to enter "upstream_failed" state.
- Use `get_dag_details` tool to inspect the task dependency graph programmatically.

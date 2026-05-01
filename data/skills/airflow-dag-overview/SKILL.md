---
name: airflow-dag-overview
description: Understanding DAG structure, tasks, status, tags, and how to check pipeline health. Use when user asks what a DAG is, how pipelines work, what task states mean, how to view DAG runs, or whether a pipeline is healthy.
triggers: [airflow_in_context]
priority: 1
max_tokens: 450
---
Airflow DAGs in noted:

DAG STRUCTURE:
- A DAG (Directed Acyclic Graph) defines a pipeline of tasks with dependencies.
- DAG files are Python scripts in the project's `dags/` folder.
- Airflow mounts them automatically; each has a unique dag_id, optional schedule, and a task set.

TASKS:
- Each task is one logical unit (e.g., ingest, preprocess, train, promote).
- Task states: success, failed, running, queued, upstream_failed, skipped.
- Task logs via `get_task_log`.

DAG RUNS:
- A DAG run is one execution. States: success, failed, running.
- Manual triggers have `manual__` prefix in the run ID.

TAGS:
- Used for organization (e.g., "training", "sweep"). Set in `@dag(tags=[...])`.

WHAT "PIPELINE" MEANS IN NOTED:
- In Airflow context, "pipeline" = DAG (orchestration). Use `get_dag_status` / `get_dag_runs`.
- MLflow runs are training/experiment records, not pipelines - do not conflate them.
- When the user asks "is the training pipeline healthy?" and `airflow_in_context` is set, check the DAG via `get_dag_status` (one call on the project-local training DAG), NOT `get_experiment_runs`.

HEALTH-CHECK WORKFLOW:
1. If only one DAG in the current project matches (tag `training` or similar), call `get_dag_status(dag_id=<that_id>)` once.
2. If multiple candidates exist, still prefer the project-local DAG; disambiguate in the answer only if truly ambiguous.
3. If the latest run failed, offer `get_task_log` as the next step.

VIEWING IN NOTED:
- The Pipelines panel shows all DAGs, status, and recent runs; expand for the task graph.

INVENTORY / OVERVIEW QUESTIONS:
- When the user asks broad "what runs here / what is automated / what pipelines are there / what kind of automation is set up" questions, START with `list_dags()` to enumerate the project's DAGs. Then briefly characterize each one based on its dag_id (e.g. "my_training_pipeline appears to handle model training"). Do NOT answer these from memory or skills alone - ground the inventory in the actual list_dags output.

IMPORTANT:
- DAG code runs in the Airflow worker, not the notebook kernel.
- Packages must be available in the Airflow container.
- A paused DAG will not execute even if manually triggered.

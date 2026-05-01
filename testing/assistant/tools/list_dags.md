# Tool: list_dags

**Type:** tool
**Tier:** read
**Domain:** airflow
**Handler:** [backend/app/managers/llm_tools.py `_tool_list_dags`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists all Airflow DAGs (pipelines). No args. Used to discover dag_ids before `get_dag_status` / `get_task_log` and to answer "what automation is set up?"

## Input schema

- No arguments.

## Output shape

```
DAGs (3):
  - jena_training_pipeline (active)
  - data_ingestion (paused)
  - drift_check (active)
```

## Setup prerequisites

- Airflow scheduler container reachable; at least one DAG registered.

## Scenarios

### S1 - Basic listing
"what DAGs are available?" → `list_dags`; do not auto get_dag_status.

### S2 - Specific DAG check
"is there a DAG called X?" → `list_dags`, report present/absent.

### S3 - Pre-flight optional
"show details for training pipeline DAG" → `get_dag_status` direct (or `list_dags` first to confirm id).

### S4 - Pipeline overview
"what automation is set up?" → list and briefly characterize.

### S5 - "Runs" disambiguation
"what runs do we have?" → likely MLflow runs given context; call `get_experiment_runs`.

### S6 - Multi-turn list then drill
T1: `list_dags`. T2: "give me details on the first" → `get_dag_status` reusing dag_id.

### S7 - Paused-only DAGs (DEFERRED)
### S8 - No DAGs (DEFERRED)

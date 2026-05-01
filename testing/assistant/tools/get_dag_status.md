# Tool: get_dag_status

**Type:** tool
**Tier:** read
**Domain:** airflow
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_dag_status`](../../../backend/app/managers/llm_tools.py)

## Purpose

DAG details + recent runs for a specific dag_id. Used after `list_dags` (to confirm the id) or when the dag_id is implied by user language.

## Input schema

- `dag_id` (required, string).

## Setup prerequisites

- DAG `jena_training_pipeline` registered.

## Scenarios

### S1 - Basic status
"what's the status of jena_training_pipeline?" → `get_dag_status` only; no get_task_log.

### S2 - Recent runs
"show recent runs of jena_training_pipeline" → list dag_run_ids + states.

### S3 - Failure detection
"did it fail recently?" → scan, name failed run_ids, offer task_log on request; no auto-fetch.

### S4 - Nonexistent DAG
Tool errors; report; suggest `list_dags`.

### S5 - Multi-turn list then status
T1: `list_dags`. T2: details on first → `get_dag_status` reusing dag_id.

### S6 - Last run outcome
Identify most-recent run; report state.

### S7 - 100+ runs DAG (DEFERRED)
### S8 - Task-level granularity (DEFERRED)

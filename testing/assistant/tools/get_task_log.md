# Tool: get_task_log

**Type:** tool
**Tier:** read
**Domain:** airflow / debugging
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_task_log`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns the log output for a specific task in a DAG run. Used to drill into failed tasks or diagnose specific behavior.

## Input schema

- `dag_id`, `dag_run_id`, `task_id` (all required).

## Setup prerequisites

- A DAG run with the named task exists.

## Scenarios

### S1 - Fetch a task log
Direct call; report content; large log → summarize tail.

### S2 - Failed task drill-down
T1: `get_dag_status` finds failed run. T2: `get_task_log` for the failed task; quote error.

### S3 - Nonexistent task
Tool errors; report; suggest `get_dag_status`.

### S4 - Missing dag_run_id
Ask user; `get_dag_status` to enumerate is acceptable.

### S5 - Quote exception
Extract Traceback verbatim; no speculation.

### S6 - Long log summary
Report phases; quote warnings/errors; do not paste whole log.

### S7 - Multi-MB log truncation (DEFERRED)
### S8 - Streaming running task (DEFERRED)

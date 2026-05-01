# Skill: mlflow-run-debugging

**Type:** skill
**Source:** [data/skills/mlflow-run-debugging/SKILL.md](../../../data/skills/mlflow-run-debugging/SKILL.md)

## Purpose

Debugging recipes for MLflow runs: failed, hanging, metric regression.

## Scenarios

### S1 - Find failed
`get_experiment_runs` scan.

### S2 - Inspect failed
`get_run_details`; error tags; task_log if DAG.

### S3 - Metric regression
`compare_runs`; look for param / data hash differences.

### S4 - Hanging run
Likely kernel died; restart; INCOMPLETE status.

### S5 - Log streaming (Airflow)
`get_task_log`; refetch for live updates.

### S6 - OOM (DEFERRED)
### S7 - GPU-specific (DEFERRED)

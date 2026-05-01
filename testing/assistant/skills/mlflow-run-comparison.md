# Skill: mlflow-run-comparison

**Type:** skill
**Source:** [data/skills/mlflow-run-comparison/SKILL.md](../../../data/skills/mlflow-run-comparison/SKILL.md)

## Purpose

Comparing MLflow runs to pick winners for deployment.

## Scenarios

### S1 - Compare two runs
`compare_runs`; table; winner.

### S2 - Versions → runs
T1: `list_model_versions`. T2: `compare_runs` reusing run_ids.

### S3 - "My last 2 runs"
`get_experiment_runs` → pick 2 → `compare_runs`.

### S4 - Best by metric
`get_experiment_runs` + details; winner.

### S5 - No metric overlap
Explain compare_runs shows blanks; suggest alignment.

### S6 - 3-way compare (DEFERRED)
### S7 - Non-overlapping schemas (DEFERRED)

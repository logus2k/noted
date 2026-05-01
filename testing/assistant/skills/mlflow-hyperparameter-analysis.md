# Skill: mlflow-hyperparameter-analysis

**Type:** skill
**Source:** [data/skills/mlflow-hyperparameter-analysis/SKILL.md](../../../data/skills/mlflow-hyperparameter-analysis/SKILL.md)

## Purpose

Analysis recipes over MLflow runs: best hyperparam identification, sweep summary, seed variance.

## Scenarios

### S1 - Best by metric
`get_experiment_runs` → winner → `get_run_details`.

### S2 - Sweep summary
Group by sweep tag; identify best.

### S3 - Winning LR
Min-loss run; report lr.

### S4 - Compare two choices
Find runs per value; compare metrics.

### S5 - Seed sensitivity
Group by non-seed params; report variance.

### S6 - Parallel-coord chart (DEFERRED)
### S7 - Failed-run handling (DEFERRED)

# Skill: mlflow-training-curves

**Type:** skill
**Source:** [data/skills/mlflow-training-curves/SKILL.md](../../../data/skills/mlflow-training-curves/SKILL.md)

## Purpose

Interpreting per-step training metrics logged to MLflow.

## Scenarios

### S1 - Request curves
`get_run_details`; min/max/final; MLflow UI for graphs.

### S2 - Overfitting
Classic signal; regularize / early-stop.

### S3 - LR schedule
Drops = plateau detections.

### S4 - Compare curves
MLflow UI overlay.

### S5 - Sudden spike
Bad batch / LR / gradient; bisect.

### S6 - Plateau detection (DEFERRED)
### S7 - Patience tuning (DEFERRED)

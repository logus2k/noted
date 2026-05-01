# Skill: mlflow-artifacts

**Type:** skill
**Source:** [data/skills/mlflow-artifacts/SKILL.md](../../../data/skills/mlflow-artifacts/SKILL.md)

## Purpose

How to inspect / drill into MLflow run artifacts and understand classic-vs-LoggedModel distinction.

## Scenarios

### S1 - Artifact summary
`get_run_details` classified summary; do not auto-drill.

### S2 - Drill into model/
`list_run_artifacts(path="model")`.

### S3 - Hydra bundle
Check for hydra/ subtree.

### S4 - Terminology
Classic artifacts vs MLflow 3.x Logged Models.

### S5 - Download locally
mlflow.artifacts.download_artifacts or UI.

### S6 - Cross-run compare (DEFERRED)
### S7 - Retention (DEFERRED)

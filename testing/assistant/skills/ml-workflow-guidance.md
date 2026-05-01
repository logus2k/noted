# Skill: ml-workflow-guidance

**Type:** skill
**Source:** [data/skills/ml-workflow-guidance/SKILL.md](../../../data/skills/ml-workflow-guidance/SKILL.md)

## Purpose

Recommends the end-to-end ML workflow in noted: DVC → Hydra → Notebook → Run Manager → MLflow → Registry → Deploy.

## Scenarios

### S1 - Experimentation flow
Outline the stages + entry points.

### S2 - Code location (cells vs src/)
src/ for reuse; cells orchestrate.

### S3 - Reproducibility
DVC + Hydra + Run Manager + seed.

### S4 - Run Manager vs Airflow
Interactive vs scheduled; both log to MLflow.

### S5 - Notebook → DAG
Reuse src/; point to airflow-dag-creation.

### S6 - Productionization (DEFERRED)
### S7 - Team collab (DEFERRED)

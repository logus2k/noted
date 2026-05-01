# Skill: airflow-dag-overview

**Type:** skill
**Source:** [data/skills/airflow-dag-overview/SKILL.md](../../../data/skills/airflow-dag-overview/SKILL.md)

## Purpose

High-level overview of Airflow DAGs in noted: purpose, when to use vs Run Manager, typical shape, status.

## Scenarios

### S1 - Purpose
Scheduled pipelines; shared lineage with MLflow.

### S2 - List DAGs
`list_dags`.

### S3 - DAG vs Run Manager
Interactive vs automated; both log to same experiment.

### S4 - Standard training DAG
compose → ingest → preprocess → train → log bundle → promote → drift.

### S5 - Health check
`get_dag_status`; drill task_log on failure.

### S6 - Multi-DAG deps (DEFERRED)
### S7 - Versioning (DEFERRED)

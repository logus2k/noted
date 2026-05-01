# Skill: airflow-dag-creation

**Type:** skill
**Source:** [data/skills/airflow-dag-creation/SKILL.md](../../../data/skills/airflow-dag-creation/SKILL.md)

## Purpose

Creating new DAGs: structure, location, task pattern, MLflow integration.

## Scenarios

### S1 - New training DAG
Outline template; don't create_file without user OK.

### S2 - Code location
dags/ at root.

### S3 - Task pattern
@task; idempotent; MLflow logging.

### S4 - MLflow integration
Explicit start_run + tags; different from auto-instrumentation.

### S5 - Generate template
`create_file`; minimal DAG skeleton.

### S6 - xcom (DEFERRED)
### S7 - TaskFlow vs classic (DEFERRED)

# Skill: airflow-trigger-config

**Type:** skill
**Source:** [data/skills/airflow-trigger-config/SKILL.md](../../../data/skills/airflow-trigger-config/SKILL.md)

## Purpose

Triggering DAGs manually with parameters.

## Scenarios

### S1 - Trigger with params
UI config / CLI --conf.

### S2 - Define params
`params={"key": Param(default, type=...)}`.

### S3 - Sweep pattern
Loop trigger or sweep-DAG.

### S4 - Find triggered run
Airflow UI / `get_dag_status`.

### S5 - Conditional (DEFERRED)
### S6 - Dataset triggers (DEFERRED)

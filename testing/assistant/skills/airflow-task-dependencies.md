# Skill: airflow-task-dependencies

**Type:** skill
**Source:** [data/skills/airflow-task-dependencies/SKILL.md](../../../data/skills/airflow-task-dependencies/SKILL.md)

## Purpose

Sequential, fan-out, diamond, and cross-DAG dependency patterns.

## Scenarios

### S1 - Sequential
`a >> b >> c`.

### S2 - Fan-out
`train >> [eval_a, eval_b]`.

### S3 - Diamond
`A >> [B, C] >> D`.

### S4 - Cross-DAG
ExternalTaskSensor vs TriggerDagRunOperator.

### S5 - Branch (DEFERRED)
### S6 - Dynamic task mapping (DEFERRED)

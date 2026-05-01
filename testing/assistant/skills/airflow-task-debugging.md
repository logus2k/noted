# Skill: airflow-task-debugging

**Type:** skill
**Source:** [data/skills/airflow-task-debugging/SKILL.md](../../../data/skills/airflow-task-debugging/SKILL.md)

## Purpose

Finding + diagnosing failed / stuck Airflow tasks.

## Scenarios

### S1 - Find failed
`get_dag_status`; offer task_log drill.

### S2 - Drill log
`get_task_log`; quote errors.

### S3 - Retries
Transient only; 2 retries default.

### S4 - Stuck running
Check log for progress; add execution_timeout.

### S5 - Silent crash = OOM
Reduce batch / increase memory.

### S6 - Worker-level (DEFERRED)
### S7 - Scheduler issues (DEFERRED)

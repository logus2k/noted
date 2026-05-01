# Skill: airflow-performance

**Type:** skill
**Source:** [data/skills/airflow-performance/SKILL.md](../../../data/skills/airflow-performance/SKILL.md)

## Purpose

Tuning DAG throughput: parallelism, caching, heavy-task profiling.

## Scenarios

### S1 - Slow DAG
`get_dag_status`; slowest tasks; parallelize.

### S2 - Parallel tasks
Use `[a, b]`; check pool size.

### S3 - Cache preprocessing
Key by DVC hash; skip if cached.

### S4 - Heavy training
MLflow metrics; early stop; mixed precision.

### S5 - Executor tuning (DEFERRED)
### S6 - Database perf (DEFERRED)

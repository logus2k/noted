# Skill: airflow-sweep-strategy

**Type:** skill
**Source:** [data/skills/airflow-sweep-strategy/SKILL.md](../../../data/skills/airflow-sweep-strategy/SKILL.md)

## Purpose

Orchestrating hyperparameter sweeps via Airflow.

## Scenarios

### S1 - Grid sweep
Dynamic task mapping; tag with sweep_id.

### S2 - Random sweep
Sample N combos; tag.

### S3 - Analyze
Filter by sweep_id; sort by metric.

### S4 - Cost guard
Early stop + concurrency limits.

### S5 - Bayesian (DEFERRED)
### S6 - Multi-objective (DEFERRED)

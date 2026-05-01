# Skill: airflow-scheduling

**Type:** skill
**Source:** [data/skills/airflow-scheduling/SKILL.md](../../../data/skills/airflow-scheduling/SKILL.md)

## Purpose

Cron syntax, manual-only DAGs, catchup, common cadences.

## Scenarios

### S1 - Daily at 2 AM
`0 2 * * *` / `@daily`.

### S2 - Manual-only
`schedule=None`.

### S3 - Catchup
catchup=False default; True fills missed runs.

### S4 - Weekly
`0 9 * * 1` (Monday).

### S5 - Timezone (DEFERRED)
### S6 - DST (DEFERRED)

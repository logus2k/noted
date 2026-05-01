# Skill: dvc-checkout

**Type:** skill
**Source:** [data/skills/dvc-checkout/SKILL.md](../../../data/skills/dvc-checkout/SKILL.md)

## Purpose

Retrieving DVC-tracked files (full / single / after delete / different version).

## Scenarios

### S1 - dvc pull
Full checkout.

### S2 - Single file
`dvc pull data.csv`.

### S3 - Restore deleted
`dvc checkout` from cache; fallback to pull.

### S4 - Switch version
git checkout .dvc; dvc checkout.

### S5 - Airflow worker (DEFERRED)
### S6 - Sparse (DEFERRED)

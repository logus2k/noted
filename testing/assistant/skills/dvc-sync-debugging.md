# Skill: dvc-sync-debugging

**Type:** skill
**Source:** [data/skills/dvc-sync-debugging/SKILL.md](../../../data/skills/dvc-sync-debugging/SKILL.md)

## Purpose

Diagnosing sync / modified / push-fail / conflict issues.

## Scenarios

### S1 - Spurious "modified"
Touched / re-encoded; `dvc checkout` to restore.

### S2 - Push fails
Check remote + MinIO; dvc push -v.

### S3 - Pull no-op
Missing .dvc file; dvc status; use `get_dvc_data_overview`.

### S4 - .dvc conflict
Pick correct md5; dvc checkout; careful resolution.

### S5 - Remote auth (DEFERRED)
### S6 - Partial pull (DEFERRED)

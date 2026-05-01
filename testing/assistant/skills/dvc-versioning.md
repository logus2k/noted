# Skill: dvc-versioning

**Type:** skill
**Source:** [data/skills/dvc-versioning/SKILL.md](../../../data/skills/dvc-versioning/SKILL.md)

## Purpose

Creating + rolling back DVC dataset versions.

## Scenarios

### S1 - New version
`dvc add` + git commit + push.

### S2 - Rollback
git checkout .dvc file; dvc checkout.

### S3 - History
`get_dvc_file_history`.

### S4 - Diff
DVC tracks hashes, not content; use pandas after checkout.

### S5 - Tags/branches (DEFERRED)
### S6 - lfs interop (DEFERRED)

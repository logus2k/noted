# Skill: noted-troubleshooting

**Type:** skill
**Source:** [data/skills/noted-troubleshooting/SKILL.md](../../../data/skills/noted-troubleshooting/SKILL.md)

## Purpose

Common troubleshooting recipes for stuck cells, missing runs, serving 404s, lint pile-up, kernel death, DVC sync.

## Scenarios

### S1 - Stuck cell
Interrupt button; restart kernel.

### S2 - Missing MLflow run
Manual exec ≠ tracked; use Run Manager.

### S3 - Serving 404
`get_serving_status`; if idle, suggest deploy.

### S4 - Lint pile-up
`fix_lint_issues` for bulk.

### S5 - Kernel died
Source autosaved; outputs lost; re-run.

### S6 - DVC out of sync
Point to dvc-sync-debugging.

### S7 - Socket.IO disconnect (DEFERRED)
### S8 - Multi-container (DEFERRED)

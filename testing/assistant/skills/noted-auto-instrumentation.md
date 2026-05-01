# Skill: noted-auto-instrumentation

**Type:** skill (priority-1, auto-injects on `mlflow_experiment_in_context`)
**Source:** [data/skills/noted-auto-instrumentation/SKILL.md](../../../data/skills/noted-auto-instrumentation/SKILL.md)

## Purpose

Explains how MLflow runs are created in noted (via Run Manager; users never write `mlflow.start_run()`). Guards against the common anti-pattern of suggesting manual tracking code.

## Scenarios

### S1 - How does tracking work?
No tools; explain Run Manager flow.

### S2 - Reject manual start_run advice
No tools; explain nesting/competition risk; redirect to Run Manager.

### S3 - Free execution vs tracked
Individual cells have no MLflow overhead.

### S4 - Hydra linkage
`hydra_config_hash` param + per-run bundle artifact.

### S5 - DVC dataset tagging
Dataset hashes logged when selected in Run Manager.

### S6 - "Are there experiments?"
Check WORKSPACE CONTEXT; don't suggest manual code.

### S7 - Framework autologging detail (DEFERRED)
### S8 - Tag-based filtering (DEFERRED)

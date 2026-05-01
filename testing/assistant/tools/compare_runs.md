# Tool: compare_runs

**Type:** tool
**Tier:** read
**Domain:** mlflow / runs
**Handler:** [backend/app/managers/llm_tools.py `_tool_compare_runs`](../../../backend/app/managers/llm_tools.py)

## Purpose

Side-by-side comparison of two MLflow runs, showing metrics and params for both. Output uses Run A / Run B labels (A = first arg, B = second arg). Used after the Assistant has run_ids in hand (typically from `list_model_versions` or `get_experiment_runs`).

## Input schema

- `run_id_a` (required), `run_id_b` (required) - both must be FULL 32-char hashes.

## Output shape

```
Comparing runs:
  A: <run_name_a>   B: <run_name_b>
Metrics:
  val_mae   2.41   2.15
  ...
Parameters:
  ...
```

## Setup prerequisites

- Project: `noted-testing`. Sandbox runs from `stage_sandbox.py`.

## Scenarios

### S1 - Basic two-run comparison
Direct call. Conclusion grounded in actual values; do NOT swap A/B.

### S2 - Champion vs challenger
T1: `list_model_versions`. T2: `compare_runs` reusing run_ids.

### S3 - Same run twice
Degenerate; deltas all zero; do not fabricate.

### S4 - Nonexistent run
Report tool error; suggest verifying run_id.

### S5 - Truncated run_ids
Ask for full ids; or `list_model_versions` to recover; do not pad.

### S6 - Best of three
Pairwise comparison strategy; or ask user which two to compare; no auto-deploy.

### S7 - Non-overlapping metric sets (DEFERRED)
### S8 - Cross-experiment compare (DEFERRED)

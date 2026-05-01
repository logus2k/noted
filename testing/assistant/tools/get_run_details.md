# Tool: get_run_details

**Type:** tool
**Tier:** read
**Domain:** mlflow / runs
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_run_details`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns the full record for a single MLflow run: status, start/end times, metrics, params, tags, and a classified artifact tree (Models / Images / Charts / Files) plus MLflow 3.x Logged Models. This is the primary tool for "what did this run produce?" and the entry to `list_run_artifacts` (drill-down) or `compare_runs` (between runs).

## Input schema

- `run_id` (required, string) - MLflow run ID (32-char hex).

## Output shape

```
Run: <run_name> (ID: <run_id>)
Status: FINISHED
Metrics:
  val_mae: 2.15
  ...
Parameters:
  target_mean: 9.099239278235567
  ...
Tags: ...
Artifacts: Models (1), Images (3), Charts (2), Files (5)
```

## Setup prerequisites

- Project: `noted-testing`
- Sandbox runs created by `stage_sandbox.py` (run_ids hardcoded in scenarios are stable across recreates).

## Scenarios

### S1 - Basic by-id detail
**Expected:** `get_run_details` only; no `list_run_artifacts`.

### S2 - Specific metric query
**User request:** "what's the val_mae for run X?" → cite verbatim from result.

### S3 - Params for inverse-transform
**User request:** "what target_mean and target_std were used in run X?" → report and mention inverse-transform context.

### S4 - Artifacts overview
**Expected:** summary counts; no `list_run_artifacts`.

### S5 - Nonexistent run_id
**Expected:** report tool error; do not fabricate.

### S6 - Multi-turn drill-down
**Turn 1:** `get_run_details(run_id=X)`.
**Turn 2:** "what's inside model/ directory?" → `list_run_artifacts(run_id=X, path="model")`.

### S7 - Truncated run_id
**Expected:** if tool errors, ask for full 32-char id; never fabricate.

### S8 - Comparison setup
**Turn 1+2:** two `get_run_details` calls; suggest `compare_runs` as cleaner path next.

### S9 - FAILED run with stack trace (DEFERRED)
Needs a pre-staged failed run.

### S10 - 1000+ artifacts run (DEFERRED)
Volume scenario.

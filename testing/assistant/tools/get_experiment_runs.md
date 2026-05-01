# Tool: get_experiment_runs

**Type:** tool
**Tier:** read
**Domain:** mlflow / runs
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_experiment_runs`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists recent MLflow runs in a named experiment. The Assistant uses this as the entry point for any "what runs are there?" / "did anything fail?" / "what's the latest?" question. From a run row, drill via `get_run_details` for metrics/params; never enumerate every run when a count or summary suffices.

## Input schema

- `experiment_name` (required, string) - MLflow experiment name.

## Output shape

```
Recent runs in 'noted-testing' (5):
  - run_name (run_id=ad190b73...) [FINISHED] start=2026-04-20T22:13Z
  ...
```

## Setup prerequisites

- Project: `noted-testing`
- The `noted-testing` experiment exists with a few runs (created by `stage_sandbox.py`).

## Scenarios

### S1 - Basic listing
**User request:** "what runs are in the noted-testing experiment?" → `get_experiment_runs(experiment_name="noted-testing")`. No `get_run_details`.

### S2 - Find named run
**User request:** "is there a run called 'baseline-eval' in noted-testing?" → `get_experiment_runs`; if absent, report and list actuals.

### S3 - Latest run
**User request:** "what's the latest run in noted-testing?" → first row from output; no `get_run_details`.

### S4 - Failed-run identification
**User request:** "did anything fail recently in noted-testing?" → scan for status=FAILED.

### S5 - Nonexistent experiment
**User request:** "list runs in the absent-experiment-xyz experiment" → tool returns error; report it; do not fabricate.

### S6 - Workspace inference
**User request:** "show me the recent runs" → infer experiment from project_id (`noted-testing`).

### S7 - Multi-turn drill-down
**Turn 1:** "what runs are in noted-testing?" → `get_experiment_runs`.
**Turn 2:** "give me details for the first one" → `get_run_details(run_id=...)` reusing the run_id from turn 1.

### S8 - Counts + summary
**User request:** "how many runs are in noted-testing?" → report count and status mix; do not enumerate all.

### S9 - Very-large run set (DEFERRED)
Synthetic-volume scenario.

### S10 - Failed-run-only experiment (DEFERRED)
Specialized fixture needed.

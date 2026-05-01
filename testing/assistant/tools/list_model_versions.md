# Tool: list_model_versions

**Type:** tool
**Tier:** read
**Domain:** mlflow / registry
**Handler:** [backend/app/managers/llm_tools.py `_tool_list_model_versions`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists all versions of a specific registered model, newest first, with each version's run_id and aliases. The Assistant uses this to (1) pick a version to deploy, (2) trace an alias to its run_id, and (3) feed run_ids into `compare_runs` / `get_run_details`. Run_ids in the output are FULL 32-char hashes (regression-guarded).

## Input schema

- `model_name` (required, string) - registered model name.

## Output shape

```
Versions of 'Sandbox Forecaster' (4):
  v4  run_id=94295f53427c4e4697b27f089eb32328  status=READY
  v3  run_id=87989ef24b5441c99bf0a7b0d58e559a  status=READY
  v2 [@staging]  run_id=8921d48aca9b4f328910bceb66778c7c  status=READY
  v1 [@champion]  run_id=ad190b73dd6147158fc27f1eda9f1637  status=READY
```

## Setup prerequisites

- Project: `noted-testing`
- `Sandbox Forecaster` registered with v1-v4 (created by `stage_sandbox.py`).

## Scenarios

### S1 - Basic listing
**User request:** "list versions of Sandbox Forecaster"
**Expected tool calls:** `list_model_versions(model_name="Sandbox Forecaster")` (exactly once)
**Expected answer focus:** report v1-v4 with aliases; FULL run_ids; do not call get_run_details.

### S2 - Latest version
**User request:** "what's the latest version of Sandbox Forecaster?"
**Expected:** identify v4; do NOT auto-deploy.

### S3 - Run_id behind alias
**User request:** "what's the run_id for the @champion of Sandbox Forecaster?"
**Expected:** locate v1 (champion-aliased) and report its FULL run_id.

### S4 - Stale alias check
**User request:** "does the @staging alias still point at v2?"
**Expected:** confirm/deny from tool output; never assume.

### S5 - Nonexistent model
**User request:** "what versions does GBM Forecaster have?"
**Expected:** report not in registry; do not fabricate.

### S6 - Ambiguous (no model named)
**User request:** "show me all the versions"
**Expected:** ASK for model_name; calling list_registered_models alongside is acceptable.

### S7 - Multi-turn: list then compare
**Turn 1:** "list versions of Sandbox Forecaster" → `list_model_versions`.
**Turn 2:** "compare v1 and v2 metrics" → `compare_runs` with run_ids from turn 1; no re-list.

### S8 - Run_id of currently-deployed version
**Setup:** Sandbox Forecaster v1 deployed.
**User request:** "what's the run_id for the version we just deployed?"
**Expected:** infer v1, report run_id; `get_serving_status` is an equally-acceptable path.

### S9 - Model with 100+ versions (DEFERRED)
Synthetic-volume scenario; out of scope.

### S10 - Versioned-only-runs (DEFERRED)
Specialty case requiring custom fixture.

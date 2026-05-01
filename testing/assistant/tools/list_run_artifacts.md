# Tool: list_run_artifacts

**Type:** tool
**Tier:** read
**Domain:** mlflow / runs / artifacts
**Handler:** [backend/app/managers/llm_tools.py `_tool_list_run_artifacts`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists the contents of a specific path inside a run's artifact tree. Returns one level at a time. Used to drill into subdirectories (`model`, `model/data`, `model/metadata`) after `get_run_details` shows the path exists.

## Input schema

- `run_id` (required, string) - MLflow run ID.
- `path` (optional, string, default `""`) - artifact path; empty = root.

## Output shape

```
Artifacts at 'model/' for run X:
  - MLmodel
  - conda.yaml
  - requirements.txt
  - python_model.pkl
  - data/
```

## Setup prerequisites

- Project: `noted-testing`. Sandbox runs from `stage_sandbox.py`.

## Scenarios

### S1 - Root listing
"what's at the root of run X's artifacts?" → `list_run_artifacts(run_id=X)`.

### S2 - Drill into model/
"what's inside model/?" → `list_run_artifacts(run_id=X, path="model")`.

### S3 - Deeper (model/data)
`path="model/data"` → contents at that level.

### S4 - Wrong path
Tool errors / empty; report; do not fabricate.

### S5 - Multi-turn details then drill
T1: `get_run_details`. T2: "drill into model/" → `list_run_artifacts`.

### S6 - Find specific file
"does it have MLmodel?" → list `model/`, check.

### S7 - Deeply-nested artifacts (DEFERRED)
Volume scenario.

### S8 - Large artifact set (DEFERRED)
Volume scenario.

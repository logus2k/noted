# Tool: register_model

**Type:** tool
**Tier:** write (requires user confirmation; platform shows dialog automatically)
**Domain:** mlflow / registry
**Handler:** [backend/app/managers/llm_tools.py `_tool_register_model`](../../../backend/app/managers/llm_tools.py)

## Purpose

Registers a run's model artifact into the MLflow Model Registry under a given name. Required first step before `deploy_model` can reference a model by version. Returns the new version number.

## Input schema

- `run_id` (required, FULL 32-char), `model_name` (required), `artifact_path` (optional, default `"model"`).

## Setup prerequisites

- A run with a logged model exists (Sandbox runs from `stage_sandbox.py`).

## Scenarios

### S1 - Register from existing run
Direct call; no auto-deploy.

### S2 - Reuse model_name
Appends new version; no warning about overwrite.

### S3 - Custom artifact_path
Pass `artifact_path="best_model"`.

### S4 - Multi-turn register then promote
T1: register → version N. T2: "make it champion" → `set_model_alias`.

### S5 - Missing model_name
Ask; do NOT pick.

### S6 - Bad run_id
Tool errors; report; no fabrication.

### S7 - Concurrent (DEFERRED)
### S8 - Large artifact (DEFERRED)

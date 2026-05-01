# Tool: set_model_alias

**Type:** tool
**Tier:** write (requires user confirmation)
**Domain:** mlflow / registry / alias
**Handler:** [backend/app/managers/llm_tools.py `_tool_set_model_alias`](../../../backend/app/managers/llm_tools.py)

## Purpose

Moves an alias (e.g. `champion`, `staging`) to point at a specific version of a registered model. In MLflow 3.x, aliases are movable pointers — promoting reassigns rather than deletes/creates.

## Input schema

- `model_name`, `version`, `alias` (all required).

## Setup prerequisites

- Registered model with target version exists.

## Scenarios

### S1 - Set @champion to new version
Direct call; alias moves; no auto-deploy.

### S2 - Set new alias name
Custom alias; works the same.

### S3 - Move alias to itself (no-op)
Succeeds; report gracefully.

### S4 - Bad version
Tool errors; suggest list_model_versions.

### S5 - Multi-turn promote then deploy
T1: `set_model_alias`. T2: "deploy champion" → `deploy_model(alias="champion")`.

### S6 - Concurrent (DEFERRED)
### S7 - Alias on deleted version (DEFERRED)

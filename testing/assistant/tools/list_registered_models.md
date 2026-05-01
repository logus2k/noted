# Tool: list_registered_models

**Type:** tool
**Tier:** read (no confirmation required)
**Domain:** mlflow / registry
**Handler:** [backend/app/managers/llm_tools.py `_tool_list_registered_models`](../../../backend/app/managers/llm_tools.py)
**MCP definition:** [backend/app/mcp/tools.py](../../../backend/app/mcp/tools.py)

## Purpose

Lists all models in the MLflow Model Registry plus the alias mapping for each (e.g. `@champion -> v7`). Zero arguments; one MLflow API call. The Assistant uses this to discover model_name values before any write tool that takes one (`register_model`, `set_model_alias`, `deploy_model`), and to answer "what's registered?" questions without sending the user to the UI.

## Input schema

- No arguments.

## Output shape

```
Registered models (2):
  - Sandbox Forecaster (@champion -> v1)
  - Jena Weather Forecaster (no aliases)
```

## Setup prerequisites

- Project: `noted-testing`
- The `Sandbox Forecaster` registered model must exist (created by `stage_sandbox.py`).

## Scenarios

### S1 - Basic listing
**User request:** "what models are in the registry?"
**Expected tool calls:** `list_registered_models` (exactly once)
**Forbidden:** `list_model_versions`, `get_serving_status`, `deploy_model`
**Expected answer focus:** lists the models present plus their current alias mappings; no fabrication.

### S2 - Discover model_name for a write tool
**User request:** "I want to deploy a model but I don't remember the exact name"
**Expected tool calls:** `list_registered_models`
**Forbidden:** `deploy_model` (cannot pick on user's behalf)
**Expected answer focus:** list options; suggest the next step but wait for the user to choose.

### S3 - Find which model carries @champion
**User request:** "which model has the @champion alias?"
**Expected tool calls:** `list_registered_models` (the alias map is already in this output - do NOT also call `list_model_versions`)
**Expected answer focus:** identify the model_name and the version that @champion currently points at.

### S4 - Aliasless models surfaced
**User request:** "are there any models without an alias?"
**Expected tool calls:** `list_registered_models`
**Expected answer focus:** identify models whose entry shows "no aliases".

### S5 - Specific model exists
**User request:** "is Sandbox Forecaster registered?"
**Expected tool calls:** `list_registered_models`
**Forbidden:** `list_model_versions` (not asked for versions)
**Expected answer focus:** confirm presence + mention current aliases if any.

### S6 - Specific model doesn't exist
**User request:** "is GBM Forecaster registered?"
**Expected tool calls:** `list_registered_models`
**Expected answer focus:** report not present; offer the actual registry contents as alternatives.

### S7 - Pre-flight before register_model
**User request:** "I'm about to register a model from a run - is the name 'Sandbox Forecaster' already taken?"
**Expected tool calls:** `list_registered_models`
**Forbidden:** `register_model` (no explicit confirmation to act yet)
**Expected answer focus:** confirm the name exists; explain re-registering appends a new version, not overwrites.

### S8 - Multi-turn: discover then act
**Setup:** serving idle.
**Turn 1:** "what models can I deploy?" → `list_registered_models` only.
**Turn 2:** "deploy the champion of Sandbox Forecaster" → `deploy_model(model_name="Sandbox Forecaster", alias="champion")` only; does not re-list.

### S9 - Empty registry (DEFERRED)
Requires a destructive registry wipe; skip until a `wipe_registered_models` fixture exists.

### S10 - Concurrent registration (DEFERRED)
Requires multi-process orchestration; not in scope for the harness.

# Tool: get_serving_status

**Type:** tool
**Tier:** read (no confirmation required)
**Domain:** mlflow
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_serving_status`](../../../backend/app/managers/llm_tools.py)
**MCP definition:** [backend/app/mcp/tools.py](../../../backend/app/mcp/tools.py)

## Purpose

Reports the current state of the `noted-serving` container: whether a model is loaded, which model and version, the resolved alias, framework, and the originating run_id. Single endpoint call to `GET /health`, zero input args, fast (sub-second). It's the Assistant's authoritative answer to "is a model deployed?" / "what's currently serving?" and exists so the model never defers to "check the UI" for that question.

## Input schema

- No arguments.

## Output shape (abridged)

Human-readable text with fields, e.g.:

```
Serving status: ready
Loaded model: Sandbox Forecaster
  Version: 1
  Alias: @champion
  Framework: keras
  Produced by run: 374b5c9a629d4c7fbd7127beb47ad6fa
The model is ready to accept prediction requests at POST /api/serving/predict.
```

Alternative states: `idle` / `loading` / `error`, each with their own specific fields.

## Setup prerequisites

Varies per scenario. Baseline:
- Project: `noted-testing`
- `noted-serving` container is up and reachable (verify before running the suite)

## Scenarios

### S1 - Ready state, deployed model
**Setup:** a model is deployed (`Sandbox Forecaster @champion` loaded)
**User request:** "is the model deployed?"
**Expected tool calls:** `get_serving_status` (exactly once)
**Forbidden tool calls:** `list_registered_models`, `get_run_details`, `deploy_model`
**Expected answer focus:** confirm it's deployed, report the model name, version, alias. Do not suggest the user check the UI.

### S2 - Idle state
**Setup:** no model deployed (harness calls unload before the scenario)
**User request:** "anything running on the serving container?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `deploy_model` (do not auto-deploy)
**Expected answer focus:** report idle / no model loaded. May mention `deploy_model` as the next step if the user wants to load one.

### S3 - Loading state
**Setup:** a deploy was just started (harness kicks off `deploy_model` and calls this scenario mid-load)
**User request:** "how's the deploy going?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `deploy_model`
**Expected answer focus:** status=loading, current phase (resolving / downloading / loading_model), target model+version. Do not claim the deploy is complete. Do not suggest canceling.

### S4 - Error state
**Setup:** a prior deploy failed (harness pre-stages an error - e.g. bad model_name that failed to resolve)
**User request:** "what went wrong with the deploy?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `deploy_model` without user direction to retry
**Expected answer focus:** report status=error + the error string + the attempted model/version. Do not invent reasons not present in the response.

### S5 - Serving container down (infra failure)
**Setup:** harness stops the `noted-serving` container before this scenario
**User request:** "is the model deployed?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `deploy_model` (it would also fail with the same connection error)
**Expected answer focus:** report that noted-serving is unreachable and identify it as an infrastructure issue. Do not invent model state; do not advise a full Docker restart unless the user asks.

### S6 - Contextless query with MLflow run open
**Setup:** active MLflow run in context (mlflow-serving skill auto-injects)
**User request:** "what's deployed?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `list_model_versions`, `list_registered_models`, `get_experiment_runs`
**Expected answer focus:** report the loaded model (or idle). The presence of the active run in context must NOT distract the model into fetching run-related info.

### S7 - Is this the run behind the deploy?
**Setup:** deployed = `Sandbox Forecaster v1` (run `374b5c9a...`), active run in context = a DIFFERENT run
**User request:** "is the model I'm looking at deployed?"
**Expected tool calls:** `get_serving_status` (then reasoning based on run_id comparison)
**Forbidden tool calls:** `deploy_model`
**Expected answer focus:** compare the active_run_id to the serving status's `run_id`. Explicitly say "no, the deployed model was produced by a different run" and quote the relevant run_id fragments for clarity.

### S8 - Natural language variations
**Setup:** default ready state
**User request variations (run each as its own scenario or judge collapsed):**
  - "what model is serving predictions?"
  - "show me the serving state"
  - "which version is loaded?"
  - "is something deployed right now?"
**Expected tool calls:** `get_serving_status` in each case
**Forbidden tool calls:** variance across the four shouldn't matter - none of them warrant a different tool
**Expected answer focus:** current serving status. Failure modes: the model declining, asking the user to clarify, or reaching for `list_registered_models` instead.

### S9 - Follow-up stay-in-context
**Setup:** default ready state
**Turn 1 user request:** "is a model deployed?"
**Turn 1 expected tool calls:** `get_serving_status`
**Turn 1 forbidden tool calls:** `deploy_model`
**Turn 2 user request:** "and its framework?"
**Turn 2 expected tool calls:** none (framework was in the Turn 1 response)
**Turn 2 forbidden tool calls:** `get_serving_status` (second call would be redundant - the persisted transcript already has it per Fix 4)
**Turn 2 expected answer focus:** quote the framework directly from the prior tool result

### S10 - Do not hallucinate the answer
**Setup:** default ready state, but harness deploys a *specific* model with known fields (e.g. `Sandbox Forecaster` v2 with framework=keras and a known run_id)
**User request:** "what's deployed?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** answering without calling the tool
**Expected answer focus:** the answer must quote the exact version and run_id from the tool result. If the model answers "Sandbox Forecaster v1" when v2 is actually loaded, that's a FAIL on the answer axis.

### S11 - Do not re-fetch on stale context
**Setup:** a prior turn in this conversation already called `get_serving_status` (no deploys/unloads since)
**User request:** "confirm it's still up"
**Expected tool calls:** `get_serving_status` is ACCEPTABLE here because the user asked for re-confirmation
**Forbidden tool calls:** none specific, but the model should not avoid the tool if the user explicitly asks for a freshness check
**Expected answer focus:** report the same status (or change, if the world changed). This scenario inverts S9 to prove the model CAN re-call when asked explicitly.

### S12 - Prefer this tool over `list_registered_models` for "is deployed" questions
**Setup:** default ready state with 3 registered models in the registry
**User request:** "is Sandbox Forecaster currently deployed?"
**Expected tool calls:** `get_serving_status` (not `list_registered_models` - the registry listing would show the model exists in the registry, which is NOT the same as being loaded into serving)
**Forbidden tool calls:** `list_registered_models`, `list_model_versions`
**Expected answer focus:** confirm whether THIS specific model is the one loaded, not just whether it exists in the registry.

### S13 - Workflow: status -> deploy -> status
**Setup:** default idle state
**Turn 1 user request:** "what's the current serving state?"
**Turn 1 expected tool calls:** `get_serving_status`
**Turn 1 forbidden tool calls:** `deploy_model`
**Turn 1 expected answer focus:** idle / nothing loaded
**Turn 2 user request:** "deploy the champion of Sandbox Forecaster"
**Turn 2 expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="champion")`
**Turn 2 forbidden tool calls:** `get_serving_status` before the deploy (we already know it's idle from Turn 1)
**Turn 3 user request:** "verify"
**Turn 3 expected tool calls:** `get_serving_status`
**Turn 3 forbidden tool calls:** `deploy_model` again
**Turn 3 expected answer focus:** report the now-loaded state; quote model name + version.

### S14 - Natural language sleight-of-hand
**Setup:** idle state
**User request:** "serve me Sandbox Forecaster"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="champion")` if the skill auto-injects and the model interprets "serve" as "deploy"; OTHERWISE `get_serving_status` + ask the user to clarify
**Forbidden tool calls:** calling `deploy_model` without knowing a version or alias (ambiguous; would need the user's pick or default to @champion)
**Expected answer focus:** either deploy the champion (if assuming default) OR ask which version. Do not silently fabricate a version.
**Notes:** This is intentionally fuzzy to exercise the procedural-hygiene axis of the judge.

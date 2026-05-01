# Tool: deploy_model

**Type:** tool
**Tier:** write (requires user confirmation via the platform's approval panel)
**Domain:** mlflow
**Handler:** [backend/app/managers/llm_tools.py `_tool_deploy_model`](../../../backend/app/managers/llm_tools.py)
**MCP definition:** [backend/app/mcp/tools.py](../../../backend/app/mcp/tools.py)

## Purpose

Deploys a registered MLflow model into the `noted-serving` container so it can serve predictions at `POST /api/serving/predict`. Accepts either a specific version number or an alias. Streams the `/load` NDJSON progress events and returns the terminal state (`ready` or `error`). Takes 10-60 seconds end-to-end (artifact download + framework load). Because it is a write-tier tool, the platform shows the user a confirmation dialog BEFORE the tool executes.

## Input schema

- `model_name` (string, required) - registered model name in the MLflow Model Registry (e.g. `"Sandbox Forecaster"`).
- `version` (string, optional) - specific version number (e.g. `"7"`).
- `alias` (string, optional) - alias to resolve at deploy time (e.g. `"champion"`, `"staging"`).
- Exactly one of `version` or `alias` must be supplied.

## Output shape (abridged)

Success:
```
Deploy succeeded.
  Model: Sandbox Forecaster
  Version: 3
  Alias: @champion
  Framework: keras
  From run: 374b5c9a629d4c7fbd7127beb47ad6fa
  Parameters: 2,145,688
The model is now loaded and ready to accept prediction requests at POST /api/serving/predict.
```

Failure:
```
Deploy failed: <error text>
```

## Setup prerequisites

Baseline:
- Project: `noted-testing`
- The sandbox must contain a registered model `Sandbox Forecaster` with:
  - Version 1 aliased as `@champion`
  - Version 2 aliased as `@staging`
  - Version 3 (no alias)
  - Version 4 "poisoned" to fail load (e.g. pins a framework version not in the baseline image) - used for error-path scenarios
- `noted-serving` container up
- For single-scenario isolation, the harness should call `POST /api/serving/unload` before each scenario so state is deterministic

## Scenarios

### S1 - Deploy by explicit version
**Setup:** idle serving
**User request:** "deploy version 3 of Sandbox Forecaster"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="3")`
**Forbidden tool calls:** `list_registered_models`, `list_model_versions`, asking "are you sure?"
**Expected answer focus:** brief pre-call intent, deploy succeeds, final message confirms v3 is loaded. After success, suggest verifying with `get_serving_status` or trying a prediction.

### S2 - Deploy by alias
**Setup:** idle serving, @champion -> v1
**User request:** "deploy the champion"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="champion")`
**Forbidden tool calls:** `list_model_versions` (no need; alias resolution happens server-side)
**Expected answer focus:** confirm load complete; include the resolved version in the answer (from the tool's response).

### S3 - Missing required arg: model_name omitted
**Setup:** idle serving, user's request is ambiguous
**User request:** "deploy the champion"
**Context twist:** zero registered models exist (harness wipes the registry for this scenario)
**Expected tool calls:** `list_registered_models` (discover that nothing exists), then explain to the user
**Forbidden tool calls:** `deploy_model` (can't deploy nothing)
**Expected answer focus:** inform the user there are no registered models; suggest `register_model` from a run first. Do not call `deploy_model` with a fabricated name.

### S4 - Multiple candidates, user must pick
**Setup:** idle serving, THREE registered models exist (`Sandbox Forecaster`, `Traffic Predictor`, `SalesModel`), each with @champion
**User request:** "deploy the champion"
**Expected tool calls:** `list_registered_models` (then ask the user which one)
**Forbidden tool calls:** `deploy_model` without the user specifying a model_name
**Expected answer focus:** present the three options and ask which to deploy. Do not pick arbitrarily.

### S5 - Replace currently-deployed model
**Setup:** Sandbox Forecaster v1 currently deployed
**User request:** "switch to v3"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="3")` (the platform handles the implicit unload+reload)
**Forbidden tool calls:** an explicit `POST /api/serving/unload` call (there is no such tool surfaced; the replacement happens atomically via /load)
**Expected answer focus:** confirm v3 is now loaded, mention that v1 was displaced.

### S6 - Version does not exist
**Setup:** Sandbox Forecaster has versions 1-3 only
**User request:** "deploy version 99"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="99")` (tool will surface the error)
**Forbidden tool calls:** none critical; `list_model_versions` beforehand is ACCEPTABLE as a defensive check
**Expected answer focus:** report the deploy failure, quote the error, suggest listing versions or picking an existing one.

### S7 - Load-time failure (framework pin mismatch)
**Setup:** Sandbox Forecaster v4 pins a framework version not in the serving baseline
**User request:** "deploy version 4"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="4")`
**Forbidden tool calls:** `deploy_model` retrying the same version multiple times; suggesting the user edit the model's requirements file without approval
**Expected answer focus:** report `Deploy failed: <ImportError>`, explain the baseline-image constraint, link to the worker-subprocess refactor as the planned fix. Do not silently retry.

### S8 - Serving container down
**Setup:** harness stops noted-serving before the scenario
**User request:** "deploy the champion"
**Expected tool calls:** `deploy_model(...)` (which surfaces a ConnectionError)
**Forbidden tool calls:** proactively starting the container (not a tool we have)
**Expected answer focus:** report unreachable, explain that noted-serving is down; do not advise restarting without asking.

### S9 - Logged Model id as version (anti-pattern guard)
**Setup:** active run in context with a Logged Model id like `m-79bedbd9fb5f4b03af54fb61b715d62a`
**User request:** "deploy the logged model m-79bedbd9fb5f4b03af54fb61b715d62a"
**Expected tool calls:** `register_model(run_id=..., model_name=...)` FIRST, then `deploy_model` with the resulting numeric version
**Forbidden tool calls:** `deploy_model(version="m-79bedbd9...")` - the Registry rejects non-numeric versions, and this is the exact anti-pattern prior sessions hit
**Expected answer focus:** explain the Logged Model id vs Registry version distinction, register first, then deploy.

### S10 - Deploy then verify (workflow)
**Setup:** idle serving
**Turn 1 user request:** "deploy the champion of Sandbox Forecaster"
**Turn 1 expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="champion")`
**Turn 1 forbidden tool calls:** `get_serving_status` BEFORE the deploy (nothing to see yet)
**Turn 1 expected answer focus:** confirm success; suggest verifying with get_serving_status OR trying a prediction
**Turn 2 user request:** "confirm it"
**Turn 2 expected tool calls:** `get_serving_status`
**Turn 2 forbidden tool calls:** `deploy_model` again
**Turn 2 expected answer focus:** confirm the model is loaded; quote name + version.

### S11 - Deploy-then-test (workflow into invoke_model)
**Setup:** idle serving
**Turn 1 user request:** "deploy the @staging version"
**Turn 1 expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="staging")`
**Turn 1 forbidden tool calls:** `invoke_model`, `get_serving_schema`
**Turn 2 user request:** "test it"
**Turn 2 expected tool calls:** `invoke_model` (no data for smoke test) OR `get_serving_schema` + `invoke_model(data=...)`
**Turn 2 forbidden tool calls:** `deploy_model` again; handing the user a Python script
**Turn 2 expected answer focus:** real prediction output from the tool result.

### S12 - Do not ask "are you sure?"
**Setup:** idle serving
**User request:** "deploy version 2"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="2")` (with a BRIEF intent statement beforehand; the platform's approval panel handles the actual confirmation)
**Forbidden tool calls:** an extra assistant turn where the model asks "are you sure you want me to deploy?" before firing the tool
**Expected answer focus:** intent + tool call. The confirmation dialog is the user's chance to veto; the model must not re-prompt.

### S13 - Both version and alias supplied
**Setup:** idle serving
**User request:** "deploy Sandbox Forecaster version 2 as @champion"
**Expected interpretation:** the user wants to deploy v2 AND label it as champion. Two distinct intents.
**Expected tool calls:** `set_model_alias(model_name="Sandbox Forecaster", version="2", alias="champion")`, then `deploy_model(model_name="Sandbox Forecaster", version="2")` OR `deploy_model(..., alias="champion")`
**Forbidden tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="2", alias="champion")` - the tool accepts EITHER version OR alias, not both (per input schema). Also do not skip the alias promotion step.
**Expected answer focus:** promote to @champion + deploy; final state confirms both.

### S14 - Regression guard: confirmation panel not blocking
**Setup:** idle serving, user has set the frontend to auto-accept write tool calls (or harness simulates approval)
**User request:** "deploy version 3"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="3")` - fires, returns success
**Forbidden tool calls:** the model hanging indefinitely waiting for confirmation (the tool call surface should include the approval round trip within the turn)
**Expected answer focus:** success message after the approve-then-load cycle.
**Notes:** This scenario is mainly harness-level; it ensures the judge has the full tool result and doesn't mis-flag the intermediate "pending_action" frame as a failure.

### S15 - Idempotency
**Setup:** Sandbox Forecaster v3 currently deployed
**User request:** "deploy version 3"
**Expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", version="3")` - the tool will happily reload the same version (it's idempotent at the serving level); OR the model may check `get_serving_status` first and skip if already deployed
**Forbidden tool calls:** none critical
**Expected answer focus:** either confirm v3 is already loaded (if skipped) or redeploy and confirm. Either behavior is acceptable; the judge should flag only if the model invents a different version number or error.

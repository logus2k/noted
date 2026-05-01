# Skill: mlflow-serving

**Type:** skill
**File:** [data/skills/mlflow-serving/SKILL.md](../../../data/skills/mlflow-serving/SKILL.md)
**Auto-inject triggers:** `mlflow_run_in_context`
**Priority:** 1
**Max tokens:** 600

## Purpose

This skill teaches the Assistant the full deploy + invoke workflow for MLflow-registered models in noted: how to promote a run into the Registry, how to deploy to noted-serving, how to verify status, how to test predictions using the native tools (`invoke_model`, `get_serving_schema`), and how to invoke from external clients. It covers the critical distinction between a run's Logged Model id (`m-...`) and a Registry version number, and the inverse-transform requirement for scaled regression targets.

## Setup prerequisites

Unless a scenario says otherwise:

- Project: `noted-testing`
- The sandbox must contain:
  - A registered model named `Sandbox Forecaster` with at least versions v1 (champion alias), v2, v3
  - A finished run under experiment `noted-testing` whose tags include `target_mean` and `target_std` (to exercise inverse transform)
  - Another run that is *not yet registered* (used to test "register a run's model" scenarios)
- Active run in context (`active_run_id` set) so the skill auto-injects via the `mlflow_run_in_context` trigger
- Skill loaded into the model's context (auto-injection per the trigger above)

For scenarios that require a deployed model, the harness should deploy `Sandbox Forecaster @champion` before starting, unless the scenario explicitly tests the deploy action itself.

## Scenarios

### S1 - Check what is deployed
**Setup:** default. A model IS currently deployed.
**User request:** "is there a model deployed right now?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `list_registered_models`, `deploy_model`
**Expected answer focus:** confirm the model name, version, alias, framework, and originating run_id. Do not tell the user to check the UI.

### S2 - Check status when nothing is loaded
**Setup:** default, but harness unloads before the scenario (no model deployed).
**User request:** "is there a model deployed right now?"
**Expected tool calls:** `get_serving_status`
**Forbidden tool calls:** `deploy_model`, `list_registered_models`
**Expected answer focus:** report idle / no model loaded; suggest `deploy_model` as the next step if the user wants one loaded. Do not volunteer to deploy without being asked.

### S3 - Deploy a specific version
**Setup:** default, v3 is not currently deployed
**User request:** "deploy version 3 of Sandbox Forecaster"
**Expected tool calls:** `deploy_model` with `model_name="Sandbox Forecaster"`, `version="3"`
**Forbidden tool calls:** `list_registered_models`, `list_model_versions`, asking "are you sure?" (the platform handles confirmation)
**Expected answer focus:** a short pre-call sentence describing the intent is fine ("I'll deploy v3 now"); no post-confirmation question. After success, suggest verifying with `get_serving_status` or trying a prediction.

### S4 - Deploy via alias
**Setup:** default, Sandbox Forecaster has `@staging` alias on v2
**User request:** "deploy the staging version of Sandbox Forecaster"
**Expected tool calls:** `deploy_model` with `model_name="Sandbox Forecaster"`, `alias="staging"`
**Forbidden tool calls:** `list_model_versions`, `get_run_details`
**Expected answer focus:** intent statement + deploy. Do not convert alias to a numeric version manually - let the serving container resolve.

### S5 - Deploy "the best one" - full chain from a run
**Setup:** default, active run in context, `target_mean`/`target_std` logged, run's model not yet registered
**User request:** "deploy the best model from this run"
**Expected tool calls (in order):** `list_registered_models` (discover model_name candidate), `register_model` (produces version N), `deploy_model` (using the new version N). If there's ambiguity about which registered model to attach to, ask the user once before registering.
**Forbidden tool calls:** calling `deploy_model` with a Logged Model id (`m-...`) as `version` - this is the critical anti-pattern the skill exists to prevent
**Expected answer focus:** explain each step briefly ("registering as v4 ... now deploying v4"). Final message confirms deployed state.

### S6 - Guard against the Logged Model id anti-pattern
**Setup:** default, active run in context with a Logged Model artifact (id like `m-79bedbd9...`)
**User request:** "deploy the logged model with id m-79bedbd9fb5f4b03af54fb61b715d62a"
**Expected tool calls:** `register_model` (register the run's model first), then `deploy_model` with the resulting numeric version
**Forbidden tool calls:** `deploy_model(model_name=..., version="m-79bedbd9...")` - this would be rejected by the Registry
**Expected answer focus:** explain the distinction between Logged Model id and Registry version, perform the registration, then deploy.

### S7 - Promote to @champion as part of deploying
**Setup:** default, `register_model` just produced v5 (or harness pre-stages the state)
**User request:** "register this run's model, make it champion, then deploy"
**Expected tool calls (in order):** `register_model`, `set_model_alias` with `alias="champion"`, `deploy_model` with `alias="champion"`
**Forbidden tool calls:** `deploy_model` using the numeric version when the skill recommends the alias path for self-documentation
**Expected answer focus:** short narration of each step; final answer confirms @champion now points at vN and is loaded.

### S8 - Invoke via tool (smoke test)
**Setup:** default, `Sandbox Forecaster @champion` already deployed (tensor model, input shape e.g. (1, 120, 16))
**User request:** "run a smoke test against the deployed model"
**Expected tool calls:** `invoke_model` with no `data` arg (relies on the auto-synthesized zeros payload)
**Forbidden tool calls:** generating a Python/curl script for the user to run; calling `invoke_model` with a handcrafted payload when a smoke test was requested
**Expected answer focus:** report predictions + output shape. A predictions preview is fine.

### S9 - Invoke with realistic values
**Setup:** default, `Sandbox Forecaster @champion` deployed
**User request:** "create a sample request with realistic values and test it"
**Expected tool calls:** `get_serving_schema` (to confirm the shape), then `invoke_model(data=<nested list of realistic floats matching the schema's input_shape>)`
**Forbidden tool calls:** generating a Python/curl script; passing `data` as a stringified JSON literal (the tool should forward a real list)
**Expected answer focus:** report predictions + optionally offer inverse-transform if the run has `target_mean`/`target_std`. No scripts handed back to the user.

### S10 - Inverse transform when asked
**Setup:** default, a prediction has been obtained (scaled values); the active run's params contain `target_mean` and `target_std`
**User request:** "convert those back to degrees Celsius"
**Expected tool calls:** possibly `get_run_details` for the relevant run (if the params weren't already fetched); no new `invoke_model`
**Forbidden tool calls:** a second `invoke_model` call (the scaled predictions are already in-context from the previous turn)
**Expected answer focus:** apply `y_real = y_scaled * target_std + target_mean`, show both the scaled and real-unit values. Quote the exact `target_mean` / `target_std` from the run (no invented numbers).

### S11 - External-client integration question
**Setup:** default
**User request:** "how would I hit the prediction endpoint from my own Python script running outside noted?"
**Expected tool calls:** none (this is a documentation-style request)
**Forbidden tool calls:** `invoke_model` (user asked HOW to invoke from their own code, not to run one now)
**Expected answer focus:** give the external URL pattern (`POST http://<host>:8123/api/serving/predict`), show a JSON body shape matching the model's input_format (pick tensor vs dataframe_records vs dataframe_split based on the currently deployed model), include a short `requests` snippet. Do not use `invoke_model`.

### S12 - Wrong payload shape diagnosis
**Setup:** default, deployed tensor model expects shape (1, 120, 16)
**User request:** "why did my POST to /predict return a 500 with 'AttributeError string has no get'?"
**Expected tool calls:** `get_serving_schema` (optional, to confirm the expected shape)
**Forbidden tool calls:** `invoke_model`, `deploy_model`
**Expected answer focus:** explain that a stringified JSON ended up where a list/dict was expected. Recommend passing a real JSON array or using `invoke_model` (which now auto-decodes stringified arrays). Should not suggest restarting the serving container.

### S13 - Registered-model discovery
**Setup:** default, multiple registered models exist
**User request:** "which models are available in the registry?"
**Expected tool calls:** `list_registered_models`
**Forbidden tool calls:** `deploy_model`
**Expected answer focus:** list model names with their current aliases (e.g. `@champion -> v1`). Do not invent models.

### S14 - Version comparison before deploying
**Setup:** default, Sandbox Forecaster has v1 (champion), v2, v3
**User request:** "is v2 worth deploying over the champion?"
**Expected tool calls (in order):** `list_model_versions` (to get run_ids per version), `get_run_details` on the run behind v2, `get_run_details` on the run behind v1 (the champion). Both run_ids must be the full 32-char hash (regression guard for the earlier truncation bug).
**Forbidden tool calls:** `deploy_model` (user asked for a comparison, not a deploy)
**Expected answer focus:** compare the primary metric (MAE or equivalent from the run context), recommend keep/swap. Do not auto-deploy.

### S15 - Constraint awareness (framework pins)
**Setup:** default
**User request:** "my model's requirements.txt pins torch==2.3 but the serving container has torch 2.4. what happens?"
**Expected tool calls:** none
**Forbidden tool calls:** `deploy_model`
**Expected answer focus:** explain that the baseline serving image is a fixed superset; pins outside it will fail at load time with an ImportError (not silently succeed). Point to the worker-subprocess serving refactor as the eventual fix. Do not invent a per-model venv feature that does not exist yet.

### S16 - Workflow: deploy then immediately invoke
**Setup:** default, nothing currently deployed, Sandbox Forecaster @champion exists
**Turn 1 user request:** "deploy the champion"
**Turn 1 expected tool calls:** `deploy_model(model_name="Sandbox Forecaster", alias="champion")`
**Turn 1 forbidden tool calls:** `invoke_model`, `get_serving_schema`
**Turn 1 expected answer focus:** confirm deploy succeeded
**Turn 2 user request:** "now test it"
**Turn 2 expected tool calls:** `invoke_model` (with no `data` for smoke test), OR `get_serving_schema` followed by `invoke_model` with a realistic payload
**Turn 2 forbidden tool calls:** handing the user a Python script
**Turn 2 expected answer focus:** actual predictions from the deployed model
**Notes:** This tests that tool-turn persistence (Fix 4) keeps the context between turns so the model doesn't re-deploy or ask "what model?" on Turn 2.

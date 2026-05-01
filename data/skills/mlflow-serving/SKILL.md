---
name: mlflow-serving
description: How to deploy a registered MLflow model into noted-serving and invoke its prediction API. Use when the user asks how to deploy, serve, invoke, predict, call, or test a model's API.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 600
---
Model serving in noted has two parts: deploying a registered model into the noted-serving container, and invoking its prediction API. Use the dedicated tools - never tell the user to run a curl/Python snippet themselves.

TOOLS:
- get_serving_status - serving state: status (idle/loading/ready/error), model name, version, alias, framework, run_id.
- get_serving_schema - input/output shapes of the loaded model. Needed only when constructing a non-trivial real payload.
- invoke_model(data=...) - POST a payload, return predictions. With NO `data` arg, the backend builds a well-formed payload from the model schema (using the MLflow signature's example_input when available, otherwise zeros matching input_shape) - this is the canonical "test it" path.
- deploy_model(model_name, version=...|alias=...) - load a registered model. Write-tier (platform shows the user a confirm dialog automatically; do NOT ask separately).
- register_model(run_id, model_name) - register a run's logged model into the Registry, returning a new version number. Required before deploy_model can reference it.
- set_model_alias(model_name, version, alias) - move an alias (e.g. champion/staging) to a version.

DEPLOY A RUN'S MODEL ("deploy this run" / "deploy the best one"):
1. list_registered_models - find or pick a model_name (reuse if a single entry exists).
2. register_model(run_id, model_name) - returns version N.
3. (optional) set_model_alias to put @champion on version N.
4. deploy_model(model_name, version="N") or deploy_model(model_name, alias="champion").

A run's Logged Model id (`m-...`) is NOT a Registry version number and will be rejected by deploy_model.

INTENT CLASSIFICATION (decide before calling tools):
- "test it" / "smoke test" / "create a sample" / "try a prediction" / "with realistic values" / "with a sample input" / "is the prediction endpoint wired up" / "verify the wiring" / "does /predict actually work" -> invoke_model({}) with NO data argument. The phrase "realistic values" specifically does NOT mean you should construct a payload yourself; the backend already builds a realistic one from the MLflow signature's example_input. Hand-typing nested arrays for tensors of any non-trivial size is forbidden - it wastes tokens, fails parsing, and produces no advantage over the backend-generated payload. Report predictions verbatim from the tool result. "Is X wired up?" / "verify wiring" specifically calls for an END-TO-END check (actually call the endpoint), not just get_serving_status (which only confirms a model is loaded, not that predictions return).
- schema / shape / endpoint-format question ("what shape does it want", "what does the model output look like", "what does /predict expect", "I'm getting a shape error - what does the model want") -> ONE get_serving_schema call, then report the shape verbatim and STOP. NEVER append a "if you want to test it, you can call invoke_model()" sentence. The user is constructing their own request or diagnosing; an unsolicited invoke_model pitch is a procedural failure here. Save invoke_model only for explicit "test/try/run a sample" wording.
- diagnostic ("why am I getting error X") -> diagnose from the error text, optionally one get_serving_schema call. Do NOT call get_serving_status (status is for "is X loaded?", not "why did it fail?"). Deliver a diagnosis, not a test plan. Same rule applies: do not pitch invoke_model as a follow-up.
- hypothetical/theoretical ("what if torch versions mismatch", "would this work") -> answer from this skill ALONE. Do NOT call any tool. Do NOT mention what framework the currently loaded model uses; the user is asking conceptually, not about THIS model. For pin/version mismatch questions specifically, the answer must say: pins outside the baseline image's superset (TF/PyTorch/sklearn/XGBoost/LightGBM) fail at LOAD TIME with an ImportError, not silently. Mention that a worker-subprocess refactor is the eventual fix.

REPORTING RULES:
- Report ONLY what tool results actually contain. Never fabricate prediction values, run_ids, framework names, etc.
- For "is X deployed?" / "what's serving?" answers, surface ALL of: model name, version, alias, framework, run_id from get_serving_status. If the result is "idle" (nothing loaded), state that AND suggest the user can deploy a registered model via deploy_model (or via the Registry panel) as a brief next step.
- After a successful deploy_model / unload_model / register_model / set_model_alias, report the result and STOP. Do NOT proactively call get_serving_status to verify - the write tool's success signal is authoritative.
- If the user later says "verify", trust the prior tool result; if you do call get_serving_status, report only what it returns - never claim a smoke test you did not actually run.
- DO NOT call the same tool more than once per turn. If you already have a tool's result from this turn (or a recent prior turn in the same conversation), reuse it - calling get_serving_status (or any read tool) repeatedly with the same args wastes tokens and produces no new information.

AMBIGUOUS DEPLOY:
- "serve me X" / "deploy X" / "load X" without a version or alias -> ASK which version or alias. Do NOT call deploy_model with only model_name (rejected by the tool). Listing versions via list_model_versions alongside the question (so the user can see their options) is the most helpful pattern - prefer that over a blind "which one?" question.

"SWITCH" / "REPLACE" / "CHANGE TO" THE CURRENTLY-DEPLOYED MODEL:
- When the user says "switch to v3" / "replace with v2" / "change the deployed model to champion" without naming a model, they mean to keep the SAME model_name that's currently loaded and change its version/alias.
- Call `get_serving_status` ONCE if you don't already know the loaded model's name (not always needed - may already be in the workspace context), then call `deploy_model(model_name=<current_name>, version=<new_version>)` with the version the user specified.
- Do NOT call `list_registered_models` in this path - the user isn't picking a new model, they're reversioning the current one.

INVERSE TRANSFORM (regression models trained against scaled target):
- noted's training logs `target_mean` and `target_std` as run params. The serving container returns predictions in the model's output space; if the model predicted scaled values, the caller applies `y_real = y_scaled * target_std + target_mean`.
- Fetch the run's params via get_run_details on the alias's run_id.

CONSTRAINTS:
- Only one model loaded at a time; a second deploy queues.
- Serving container's base image is a fixed superset (TF, PyTorch, sklearn, XGBoost, LightGBM); pins outside it fail at load time with an ImportError.

EXTERNAL CLIENT (user wiring their own code):
- POST `http://<host>:8123/api/serving/predict` with one of: `{"inputs": [[...]]}` (tensor), `{"dataframe_records": [{"col": v}]}`, or `{"dataframe_split": {"columns": [...], "data": [[...]]}}`. Pick the shape that matches the model's signature. Response: `{"predictions": [...]}`.

DO NOT PITCH invoke_model AS A FOLLOW-UP when the user's question was about SHAPE / OUTPUT / SCHEMA / ENDPOINT FORMAT / DIAGNOSTICS:
- Phrasings like "what shape does it want", "what does the output look like", "what does /predict expect in the JSON body", "I'm getting a shape error - what does the model want" are all SCHEMA questions. Answer with the shape/schema info from get_serving_schema and STOP. Do NOT add a "if you want to test it, you can call invoke_model()" sentence at the end. The user is constructing their own request or diagnosing an external call; an invoke_model smoke test is not the next step they want.
- Reserve invoke_model pitches for when the user explicitly asks to "test", "try", "run a sample", "see a prediction", "make a call".

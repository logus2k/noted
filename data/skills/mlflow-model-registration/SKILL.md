---
name: mlflow-model-registration
description: Registering models from run artifacts, managing versions and aliases. Use when user asks how to register a model, promote to champion, manage model versions, assign staging/champion alias, or set up the model registry.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
Model registration in noted:

REGISTERING A MODEL:
1. From the Experiments panel, select a run with a logged model artifact.
2. Click "Register Model" on the run's artifact section.
3. Choose an existing registered model name or create a new one.
4. The model version is created automatically with a link back to the source run.
5. API alternative: `POST /api/mlflow/registry/register` with run_id and artifact_path.

ALIASES:
- @champion: the production-ready model currently in use.
- @staging: candidate model under evaluation before promotion.
- @archived: previously used model, kept for reference.
- Only one version per alias per model name. Assigning @champion to v3 removes it from v2.
- Set aliases via the Registry panel or `set_model_alias` tool.

VERSION MANAGEMENT:
- Each registration creates an incrementing version number (v1, v2, v3...).
- Versions are immutable - you cannot overwrite a version's artifacts.
- To update, register a new version from a better run, then reassign the alias.
- Delete old versions only if storage is a concern; keeping them preserves lineage.

LINEAGE:
- Every model version stores its source run_id.
- From the version, trace back to the run's params, metrics, Hydra config hash, and DVC data version.
- The Knowledge Graph visualizes these relationships.

WORKFLOW:
1. Train multiple runs (notebook or Airflow sweep).
2. Compare runs, pick the best.
3. Register the winner as a new version.
4. Assign @staging, validate with the Try It panel in Serving.
5. Promote to @champion when satisfied.
6. Move the old champion to @archived.

When advising on registration, always reference the specific run_id and metric values that justify the choice.

TOOL CHOICE BY QUESTION SHAPE:
- "Deploy the logged model m-<id>" / "deploy model X": the user wants a deployment, not an investigation. Use the `deploy_model(name=<registered_model>, version=<v>)` tool directly (with the name/version the user supplied, or ask them if missing). A **Logged Model id starts with `m-`** and is NOT a Registry version; you must `register_model` first to obtain a numeric version, then `deploy_model`. Never call `get_experiment_runs` just to hunt for a deploy target the user already named.
- "What should I name my registered model?" / "help me pick a name" -> call `list_registered_models()` ONCE. Show the existing names so the user can pick a consistent style. Explicitly note that re-using an existing name creates a new VERSION (does not overwrite). DO NOT pick a name for the user - naming is their decision; never suggest specific names.
- "Promote model X to champion" -> `set_model_alias(name=X, version=<v>, alias="champion")`.
- "What models are registered?" -> `list_registered_models()`.
- "What versions does <model_name> have?" / "list versions of X" / "does the @<alias> still point at vN?" -> `list_registered_models()` is WRONG - use `list_model_versions(model_name=X)` ONCE. It returns every version with its alias assignments; inspect the matching alias row to answer alias-pointer questions.
- If the user references an alias (@staging / @champion / @archived / etc.) without naming a model, infer the model_name from the workspace's Registered Models section or the currently-deployed model. When there is exactly one registered model in context, use that name and go straight to `list_model_versions(model_name=<that-name>)`. Use `list_registered_models()` to disambiguate ONLY when there are MULTIPLE registered models AND no deploy/context hint tells you which one. Never substitute `list_registered_models()` for `list_model_versions()` just because the user omitted the name - that's the wrong pattern.
- "What's the run_id for the version we just deployed?" -> if the deployment happened in the same session, read the run_id from the prior deploy tool's result. If not, either `get_serving_status()` (returns the currently-loaded model's run_id directly) or `list_model_versions(model_name=<deployed_name>)` (Registry view, pick the @champion row) will answer in one call - both are fine, pick whichever is closer to the user's framing.

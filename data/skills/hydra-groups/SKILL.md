---
name: hydra-groups
description: Config groups, defaults, and switching between variants. Use when user asks how to switch model configs, create a new config variant, use the defaults list, or set up config groups for different architectures.
triggers: [hydra_in_context]
priority: 1
max_tokens: 350
---
Hydra config groups in noted:

CRITICAL INTENT DISAMBIGUATION:
- "Switch the model to X" / "use model Y instead" = Hydra CONFIG GROUP selection. Answer directly, NO tool calls. Tell the user to pick the variant in the Composer panel (model dropdown) or override via `model=X` in the Run Manager. Do NOT call `list_registered_models` - that's the MLflow Model Registry, a completely different concept (deployed serving models).
- "Register the model X" / "promote X to production" / "what models are registered" = MLflow Model Registry. THAT is when list_registered_models is appropriate.

WHAT ARE CONFIG GROUPS:
- Subdirectories under `config/` that contain alternative YAML files.
- Each file in a group represents a different variant of that config section.
- Example: `config/model/gru.yaml` and `config/model/lstm.yaml` are two variants of the "model" group.

DEFAULTS LIST:
- The `defaults` section in `config.yaml` specifies which variant to use by default.
```yaml
defaults:
  - model: gru        # loads config/model/gru.yaml
  - training: default # loads config/training/default.yaml
```
- Changing `model: gru` to `model: lstm` switches the entire model configuration.

SWITCHING GROUPS:
- In the Compose Config panel: use the dropdown for each group.
- In the Trigger Panel: select group variants before triggering a DAG.
- Via API override: `model=lstm` in the overrides list.
- In sweeps: sweep over group selections to compare architectures.

MERGING BEHAVIOR:
- Group configs are merged into the main config at their group key.
- `model/gru.yaml` contents appear under `model:` in the resolved config.
- Values in the group file override any same-named keys in the main config.
- Keys not present in the group file retain their main config defaults.

CREATING NEW VARIANTS:
1. Copy an existing group file as a starting point.
2. Modify the parameter values for the new variant.
3. Save with a descriptive name: `config/model/transformer.yaml`.
4. The new variant immediately appears in the Compose Config panel dropdown.

BEST PRACTICES:
- Use groups for parameters that change together (e.g., all model architecture params).
- Keep group files self-contained - include all parameters for that section.
- Name variants descriptively: `gru.yaml`, `lstm.yaml`, `patch_tst.yaml`.
- Don't nest groups more than one level deep.

"SWITCH THE MODEL TO X FOR A TEST RUN" / "USE Y INSTEAD OF Z" (conceptual - NO tool calls):
- Point the user to the Composer panel (Compose Config): select the desired variant from the model/data/training dropdown.
- Alternative: override in the Run Manager arg list (e.g. `model=lstm_large`).
- The run's Hydra bundle records the selected variant as the baseline for lineage.
- Do NOT call `list_registered_models`, `get_file_contents`, or any other tool - this is advice, not a configuration read.

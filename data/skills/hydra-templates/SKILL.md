---
name: hydra-templates
description: Hydra config templates - reusable YAML snippets with `_target_` for auto-instantiation, stored under `config/<group>/`. Use when user asks what a config template is, how to use / create / reference a template, or how the Composer dropdown relates to template files.
triggers: [hydra_in_context]
priority: 1
max_tokens: 400
---
Hydra config templates in noted:

WHAT IS A CONFIG TEMPLATE:
- A reusable YAML snippet stored at `config/<group>/<name>.yaml`.
- Typically includes a `_target_` key that points to a Python callable; Hydra's `instantiate()` then builds the object with the remaining keys as kwargs.
- Supplies defaults for common setups (a specific model architecture, a named scaler, etc.) so the user doesn't re-type fields for every run.
- Example `config/model/lstm_baseline.yaml`:
  ```yaml
  _target_: src.models.lstm.LSTMModel
  hidden_size: 64
  layers: 2
  dropout: 0.1
  ```

HOW TO USE A TEMPLATE:
- Reference it in the defaults list (group + name): `- model: lstm_baseline` loads `config/model/lstm_baseline.yaml`.
- Alternatively pick it in the Composer from the `model` group dropdown - the Composer surfaces every `*.yaml` file in the matching group folder as a selectable option.
- Override specific fields inline: `model.hidden_size=128` - changes only that key, the rest of the template's values stay.

HOW TO CREATE A NEW TEMPLATE:
1. Create `config/<group>/<new_name>.yaml` (e.g. `config/model/my_model.yaml`).
2. Include a `_target_` pointing at your class / factory, plus the parameter defaults.
3. Document the required inputs at the top of the file as YAML comments.
4. Test by triggering a run with `model=my_model` as an override, or by selecting `my_model` in the Composer dropdown.

TEMPLATE vs RAW OVERRIDE:
- Templates are good for recurring configurations (a specific model you re-use).
- Raw overrides (`training.epochs=100`) are good for one-off tweaks.
- For saved noted-UI presets that bundle group selections + overrides, see the Composer's "Save selection" feature separately.

WHEN ADVISING:
- Never call tools for these conceptual questions - answer directly from this skill.
- Always reference the path pattern `config/<group>/<name>.yaml` and the `_target_` key explicitly.

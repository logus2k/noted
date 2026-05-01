---
name: hydra-composition
description: Composing Hydra configs with overrides, groups, and hash tracking. Use when user asks how to compose a config, override parameters, use config groups, check a config hash, or understand Hydra config resolution.
triggers: [hydra_in_context]
priority: 1
max_tokens: 350
---
Hydra configuration in noted:

BASICS:
- Config files live in the project's `config/` folder (YAML format).
- Main file: `config.yaml` defines defaults for all parameters.
- Config groups: subdirectories like `model/gru.yaml`, `model/lstm.yaml` allow switching entire parameter sets.

COMPOSITION:
- Compose via the Compose Config panel or API: `POST /api/hydra/compose`.
- Overrides use dotted-key notation: `model.type=LSTM`, `training.epochs=100`.
- Group selections: `model: gru` loads `config/model/gru.yaml` and merges it.
- Result: fully resolved config dict + YAML string + SHA-256 hash.

HASH TRACKING:
- Every composed config gets a unique SHA-256 hash.
- This hash appears in MLflow runs and Airflow DAG runs for lineage.
- Same config inputs = same hash (deterministic).
- Changing any value produces a different hash.

TEMPLATES:
- Save named presets via the Templates section in Compose Config.
- Templates store group selections + overrides for quick recall.
- Team members can share templates for reproducible experiments.

WHEN ADVISING:
- Reference config keys with dotted notation: `training.learning_rate`, not "learning rate".
- Suggest changes in terms of the config structure, not raw values.
- For new parameters, suggest where to add them in the YAML hierarchy.

"SHOW ME THE RESOLVED CONFIG" / "WHAT'S THE CURRENT CONFIG":
- Call `get_hydra_config` to fetch the composed config for the current project (defaults merged with group selections and overrides). Render the returned YAML / dict in the answer.
- Do NOT try to stitch this together from `config/config.yaml` + group files manually - the tool does the composition exactly as the runtime does.

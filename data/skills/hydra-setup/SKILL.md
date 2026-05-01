---
name: hydra-setup
description: Setting up Hydra config structure for a new project. Use when user asks how to initialize Hydra, create a config directory, set up config.yaml, organize config groups, or start a new project configuration.
triggers: [hydra_in_context]
priority: 1
max_tokens: 350
---
Setting up Hydra configuration in a noted project:

DIRECTORY STRUCTURE:
```
project/
  config/
    config.yaml          # main config (defaults + base params)
    model/
      gru.yaml           # model group: GRU variant
      lstm.yaml          # model group: LSTM variant
    training/
      default.yaml       # training hyperparameters
    data/
      default.yaml       # data processing parameters
```

MAIN CONFIG (config.yaml):
```yaml
defaults:
  - model: gru
  - training: default
  - data: default

project:
  name: my_experiment
  seed: 42
```

GROUP CONFIG (model/gru.yaml):
```yaml
type: GRU
hidden_size: 128
num_layers: 2
dropout: 0.1
```

SETUP STEPS:
1. Create the `config/` directory in the project root.
2. Create `config.yaml` with defaults and top-level parameters.
3. Create subdirectories for each config group (model, training, data).
4. Add YAML files for each variant within groups.
5. Verify in noted: the Compose Config panel should detect the config directory.

KEY RULES:
- The main file must be named `config.yaml`.
- Group directory names become the group keys in the defaults list.
- File names within groups become the selectable options.
- All YAML keys use snake_case.
- Use dotted notation for overrides: `model.hidden_size=256`.

COMPOSE CONFIG PANEL:
- Once config/ exists, the panel shows group selectors and override fields.
- Composing produces a resolved config + SHA-256 hash.
- The hash is tracked in MLflow runs for reproducibility.

Start with a flat config.yaml and add groups only when you have multiple variants to switch between.

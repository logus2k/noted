---
name: hydra-sweep-design
description: Designing hyperparameter sweep configs using Hydra. Use when user asks how to set up a hyperparameter sweep, tune learning rate, design a grid search with Hydra, or plan a systematic parameter exploration.
triggers: [hydra_in_context]
priority: 1
max_tokens: 400
---
Designing hyperparameter sweeps with Hydra in noted:

SWEEP VIA TRIGGER PANEL:
- Open the Trigger Panel for the target DAG.
- Toggle "Sweep" mode.
- Enter comma-separated values for parameters to sweep.
- Example: `training.learning_rate: 0.01, 0.001, 0.0001`.
- The preview table shows all parameter combinations.

PARAMETER SELECTION:
- Use Hydra dotted-key notation: `model.hidden_size`, `training.batch_size`.
- Sweep 2-3 parameters at a time to keep combinations manageable.
- Total runs = product of all parameter value counts (3 x 3 = 9 runs).

DESIGN STRATEGY:
1. Phase 1 - Coarse search: wide range, few values.
   `training.learning_rate: 0.1, 0.01, 0.001, 0.0001`
2. Phase 2 - Refined search: narrow range around the best from Phase 1.
   `training.learning_rate: 0.005, 0.002, 0.001, 0.0005`
3. Phase 3 - Architecture comparison: sweep config groups.
   `model: gru, lstm, transformer` (sweeps entire model configs).

GROUP SWEEPS:
- Sweep over config groups by entering group variant names.
- This replaces the entire config section for each variant.
- Combine with parameter sweeps: model group x learning rate.

CONFIG HASH TRACKING:
- Each sweep combination produces a unique Hydra config hash.
- All runs in a sweep share a `_sweep_id` tag for grouping.
- After the sweep, compare runs in the Experiments panel sorted by primary metric.

PRACTICAL LIMITS:
- Aim for 10-20 runs per sweep, max 50.
- Estimate total training time before launching: runs x avg_duration.
- If > 50 combinations, split into multiple focused sweeps.

AFTER THE SWEEP:
- Use `get_experiment_runs` or the Experiments panel to view results.
- Sort by the primary metric to identify the best configuration.
- Register the winning run's model to the Registry.

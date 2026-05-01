---
name: airflow-sweep-strategy
description: Designing parameter sweeps and grid search strategies. Use when user asks how to set up a sweep, choose hyperparameters to tune, plan a grid search, or decide how many runs to include in a sweep.
triggers: [airflow_in_context]
priority: 1
max_tokens: 350
---
When helping design parameter sweeps:

STRATEGY:
1. Start COARSE: few values, wide range. Example: learning_rate [0.01, 0.001, 0.0001].
2. Then REFINE: narrow range around the best. Example: learning_rate [0.002, 0.001, 0.0005].
3. Keep total combinations manageable: aim for 10-20 runs, max 50.

PARAMETER PRIORITY (sweep the most impactful first):
1. Learning rate (almost always the most impactful)
2. Model architecture/size (hidden units, layers)
3. Batch size
4. Regularization (dropout, weight decay)
5. Data preprocessing choices (window size, features)

NOTED-SPECIFIC:
- Use the Sweep panel in the Trigger Panel (not manual triggering).
- Enter comma-separated values per parameter.
- The preview table shows all combinations before submitting.
- All sweep runs get a shared `_sweep_id` tag for grouping.
- Parameters come from Hydra config - suggest values using Hydra config key names.

SWEEP RESULT ANALYSIS:
- After the sweep completes, call `get_experiment_runs` with `filter_tag="_sweep_id=<id>"` to fetch ONLY that sweep's runs (not every run in the experiment).
- Sort the returned runs by the primary metric to identify the best combo.
- For a side-by-side comparison of the top 2, use `compare_runs(run_id_a, run_id_b)`.

COMMON MISTAKES:
- Too many parameters at once (3^5 = 243 runs). Sweep 2-3 parameters at a time.
- Range too narrow (only 10% variation). Start with order-of-magnitude differences.
- Ignoring training cost. Estimate total GPU hours before launching.

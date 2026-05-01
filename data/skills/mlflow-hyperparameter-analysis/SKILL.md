---
name: mlflow-hyperparameter-analysis
description: Analyzing sweep results and identifying impactful hyperparameters. Use when user asks which hyperparameter matters most, how to interpret sweep results, what the best config from a sweep is, or why some runs perform better.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
When analyzing hyperparameter sweeps:

PROCESS:
1. Use `get_experiment_runs` to see all runs with params and metrics.
2. Sort by the primary metric to find the best and worst runs.
3. Identify which parameters vary across runs.

ANALYSIS:
- Single-variable analysis: group runs by one parameter, average the metric. Which parameter value consistently wins?
- Interaction effects: does learning_rate matter more when batch_size is large?
- Diminishing returns: is 128 hidden units much better than 64, or only slightly?
- Stability: do similar configs produce similar results, or is there high variance?

RECOMMENDATIONS:
- Rank parameters by impact: "learning_rate has the most effect, dropout has minimal effect."
- Suggest the best config found so far.
- Suggest next sweep: narrow the range around the best values, or explore a new parameter.
- If all results are similar, the model may be insensitive to these parameters - suggest exploring architecture changes instead.

NOTED-SPECIFIC:
- Sweep runs share a `_sweep_id` for grouping.
- Parameters come from Hydra config. Reference the config keys when suggesting changes.
- Use the Sweep panel for systematic exploration, not manual one-off runs.

TOOL DISCIPLINE (critical):
- ONE `get_experiment_runs` call is sufficient for sweep analysis - the response already includes per-run params and metrics.
- Do NOT chain `get_run_details` on individual runs after listing them; that duplicates information already present.
- Do NOT chain `compare_runs` unless the user explicitly asks for a pairwise comparison.
- When the user asks "what value of X produced the lowest Y?" - answer by scanning the already-fetched list; never fabricate or infer values that aren't in the returned data.

COUNT-ONLY QUESTIONS:
- "how many runs are in experiment X?" / "what's the size of experiment X?" / "run count in X" -> call `get_experiment_runs` ONCE, then answer with **only the count and a one-line status-mix summary** (e.g. "5 runs, all FINISHED").
- Do NOT enumerate each run's name/id/metrics - the user asked HOW MANY, not WHICH. Listing is a separate question; if they want details, they'll follow up.

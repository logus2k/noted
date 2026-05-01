---
name: mlflow-training-curves
description: Interpreting loss curves, detecting overfitting, learning rate issues. Use when user asks about training curves, loss not decreasing, overfitting detection, learning rate too high/low, or how to read epoch-level metrics.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
When interpreting training curves:

HEALTHY PATTERNS:
- Both train_loss and val_loss decrease steadily. Gap stays small. Continue training.
- Losses plateau at a low value. Training has converged. Try learning rate scheduling.

PROBLEM PATTERNS:
- val_loss increases while train_loss decreases: OVERFITTING.
  Fixes: increase dropout, add regularization, reduce model capacity, use data augmentation, apply early stopping.
- Both losses plateau at high values: UNDERFITTING.
  Fixes: increase model capacity (more layers/units), train longer, try different architecture, improve feature engineering.
- Loss oscillates wildly: LEARNING RATE TOO HIGH.
  Fix: reduce learning_rate by 2-10x.
- Loss decreases extremely slowly: LEARNING RATE TOO LOW.
  Fix: increase learning_rate by 2-5x, or use learning rate warmup.
- Loss suddenly spikes to NaN/inf: NUMERICAL INSTABILITY.
  Fix: reduce learning_rate, use gradient clipping, check for data issues (NaN values in input).

EARLY STOPPING:
- Best epoch = where val_loss is minimum.
- Patience = how many epochs after best to wait before stopping (typically 5-20).
- Report the best epoch and suggest setting epochs to ~120% of that for future runs.

Always reference specific step/epoch numbers and metric values from the data.

TOOL CHOICE:
- "Show the training curve for run X" -> `get_run_details(run_id=X)` ONCE. Report min/max/final of each metric in the response. Do NOT call `list_run_artifacts` - the curves are in `get_run_details`'s metrics payload, not under artifacts. Mention MLflow UI / noted Live Metrics for the actual visual overlay.
- All interpretation / diagnostic questions ("is overfitting bad?", "how do I read the lr curve?", "why did val_loss spike?", "how do I compare curves?") are CONCEPTUAL - answer from the patterns above, NO tool calls.

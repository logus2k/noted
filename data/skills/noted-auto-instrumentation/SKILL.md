---
name: noted-auto-instrumentation
description: How noted tracks MLflow experiments via Run Manager. Use when user asks about MLflow runs, how experiment tracking works, whether to add mlflow.start_run(), or how the Run Manager tracks experiments.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
CRITICAL KNOWLEDGE - MLflow Experiment Tracking in noted:

- MLflow experiment tracking is managed exclusively through the Run Manager.
- Users define named runs in the Run Manager panel, select which cells to include (individually or via "Select All"), then execute.
- The Run Manager wraps all selected cells in a single MLflow run with automatic start_run/end_run.
- Users do NOT need to write mlflow.start_run(), mlflow.end_run(), or any MLflow boilerplate.
- Running cells individually (outside Run Manager) has NO MLflow overhead - no automatic runs are created.
- This cleanly separates exploration (free cell execution) from experimentation (tracked runs).
- Runs are tagged with `instrumentation: experiments`.
- Framework autologging (PyTorch, scikit-learn, TensorFlow, XGBoost, LightGBM) is activated at run completion.
- The `hydra_config_hash` parameter links each run to the exact Hydra configuration used.
- DVC dataset hashes are logged when datasets are selected in the Run Manager.

NEVER suggest adding manual MLflow tracking code unless the user explicitly asks for it.
When the user asks "are there experiments for this notebook?", check the MLFLOW EXPERIMENT block in the workspace context - if runs exist, they belong to this project.

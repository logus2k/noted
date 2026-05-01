---
name: mlflow-snapshots
description: Mid-training model snapshots (intermediate checkpoints) logged as Logged Models in MLflow 3.x. Use when user asks what a snapshot is, how many checkpoints a run has, how to resume from a checkpoint, or how noted's autolog captures them.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
MLflow snapshots in noted:

WHAT IS A SNAPSHOT:
- A snapshot is a mid-training model checkpoint persisted as an MLflow Logged Model (the first-class model entity introduced in MLflow 3.x).
- Each snapshot represents the model weights + metadata at a specific epoch / step during a single run.
- noted's autologging captures these automatically for supported frameworks (Keras, PyTorch Lightning, etc.) when `early_stopping.restore_best_weights=True` or when explicit checkpoint callbacks fire.
- Snapshots enable: resuming training from a best epoch, comparing models at different stages, A/B testing checkpoints before promotion.

LOGGED MODEL IDS:
- Each snapshot has an id of the form `m-<hex>`. These are NOT Registry version numbers (those are simple integers like v1, v2 under a registered model name).
- To deploy a snapshot, you must first `register_model(source="runs:/<run_id>/<artifact_path>", name=<registry_name>)` to mint a Registry version, then `deploy_model(name=<registry_name>, version=<v>)`.

FINDING A RUN'S SNAPSHOTS:
- Call `get_run_details(run_id=X)`. The response classifies artifacts; look at the **Logged Models** count.
- count == 1 -> only the final model (no mid-training snapshots).
- count > 1 -> additional entries are intermediate checkpoints. Each can be inspected / registered / deployed independently.

AUTOLOG BEHAVIOR:
- Run Manager wraps your training call in `mlflow.start_run()` + framework-specific autolog.
- For Keras: every callback that saves weights (ModelCheckpoint, EarlyStopping with restore_best_weights) creates a Logged Model.
- For PyTorch Lightning: every `trainer.save_checkpoint` call creates one.

WHEN ADVISING:
- Differentiate clearly: Logged Model id (`m-...`) -> checkpoint entity, Registry version (integer) -> production pointer. The user often confuses them.
- For conceptual "what is X" questions, answer directly from this skill - no tool calls.
- For "how many checkpoints does run X have" questions, call `get_run_details(run_id=X)` ONCE and read the Logged Models count.

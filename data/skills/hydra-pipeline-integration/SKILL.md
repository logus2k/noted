---
name: hydra-pipeline-integration
description: How Hydra configuration flows into Airflow DAG parameters. Use when user asks how config reaches the DAG, how parameters are passed to Airflow, how the config hash is tracked, or how Hydra and Airflow connect.
triggers: [hydra_in_context]
priority: 1
max_tokens: 350
---
Hydra-Airflow integration in noted:

CONFIG FLOW:
1. User composes a Hydra config (via Compose panel or templates).
2. In the DAG Trigger Panel, "Load Hydra Config" fetches the composed config.
3. Nested Hydra keys are flattened to match DAG param names:
   - model.type -> model_type
   - model.units1 -> units1
   - training.epochs -> epochs
   - training.learning_rate -> learning_rate
   - training.batch_size -> batch_size
4. The SHA-256 config hash is included as `hydra_config_hash` param.
5. DAG tasks read all values from params, not from hardcoded defaults.

LINEAGE:
- The config hash in the DAG run links back to the exact Hydra config.
- This hash also appears in the MLflow run (via Run Manager or Airflow pipeline).
- Full chain: Hydra config hash -> Airflow run conf -> MLflow run params.

WHEN ADVISING:
- Hyperparameter changes should be made in Hydra config, not in DAG params.
- DAG Param defaults should mirror Hydra config defaults (single source of truth).
- For sweeps, vary Hydra config values via the Sweep panel.
- When creating new DAGs, always include `hydra_config_hash` as a param.

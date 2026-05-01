---
name: ml-workflow-guidance
description: General ML best practices adapted to noted's workflow. Use when user asks how to start a new experiment, what the ML workflow is, best practices for training, how to avoid common ML mistakes, or how to structure an ML project.
triggers: [workspace_active]
priority: 1
max_tokens: 400
---
ML workflow guidance for noted:

RECOMMENDED WORKFLOW:
1. DATA: Load and explore data in notebook cells. Track large files with DVC.
2. PREPROCESS: Clean, transform, feature engineer. Version processed data with DVC.
3. CONFIGURE: Set up Hydra config with model architecture and training params.
4. EXPERIMENT: Define runs in Run Manager. Execute and monitor in Metrics Panel.
5. ANALYZE: Compare runs in Experiments panel. Use leaderboard to rank.
6. ITERATE: Adjust Hydra config based on results. Run sweeps for systematic search.
7. REGISTER: Best model goes to Registry with @champion alias.
8. SERVE: Load model in serving container. Test with Try It panel.
9. PIPELINE: Automate the workflow as an Airflow DAG for scheduled retraining.

EXPERIMENT DESIGN:
- Start simple: baseline model with default params.
- Change one thing at a time to understand impact.
- Use sweeps for systematic exploration (2-3 params, 10-20 runs).
- Track everything - use the Run Manager to create MLflow runs with full lineage.

COMMON MISTAKES:
- Training on all data (no validation/test split). Use Hydra config for split ratios.
- Not versioning data. Track with DVC before starting experiments.
- Comparing runs trained on different data versions. Check DVC hashes in lineage.
- Over-tuning on validation set. Keep test set truly held out.
- Not setting random seeds. Include seed in Hydra config for reproducibility.

METRICS:
- Regression: MAE, RMSE, R2. Lower MAE/RMSE = better, higher R2 = better.
- Classification: accuracy, precision, recall, F1. Choose based on class balance.
- Always report on the TEST set, not validation.

CROSS-FILE / PROJECT-WIDE QUESTIONS:
- When the user asks for a summary that spans many files ("how does this project train and evaluate models", "give me an overview of the codebase", "what's the data pipeline across files", "trace the flow from X to Y across the project"), DO NOT walk the files yourself with list_files + get_file_contents - that fills the main context with raw source code for what should be a summary. Use `run_agent(agent_name="notebook-explorer", task="<the user's question, restated as a concrete research goal>")`. The subagent reads the files in its own context and returns a compact summary.
- Direct exploration (list_files / get_file_contents) is for targeted reads when the user names a specific file or you already know exactly which file holds the answer.

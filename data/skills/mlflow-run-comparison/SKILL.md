---
name: mlflow-run-comparison
description: How to compare two MLflow runs - metrics diff, param diff, trade-offs. Use when user asks to compare two runs, which run is better, what changed between runs, or how to evaluate run differences.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 400
---
When comparing MLflow runs:

RUN_ID VALIDATION (BEFORE ANY TOOL CALL):
- MLflow run_ids are 32-character lowercase hex strings (e.g. `ad190b73dd6147158fc27f1eda9f1637`).
- If the user provides a shorter string (prefix like `ad190b73`), it is NOT a valid run_id - MLflow will return `RESOURCE_DOES_NOT_EXIST`.
- When the user gives a truncated id: ASK them for the full 32-character run_id, or offer `get_experiment_runs` / `list_model_versions` to look up the full id from a prefix.
- NEVER pad or fabricate the missing characters. NEVER call `compare_runs`, `get_run_details`, or any run_id-accepting tool with a prefix - the call will fail and waste the user's time.

PROCESS:
1. Use the `compare_runs` tool with both full 32-char run IDs.
2. Focus on parameters that DIFFER (marked with * in the comparison output).
3. Calculate relative improvement: (new - old) / old * 100%.

ANALYSIS FRAMEWORK:
- Primary metric: identify which metric matters most for the task (e.g., val_MAE for regression, val_accuracy for classification).
- Trade-offs: better accuracy but longer training? More parameters but marginal improvement?
- Statistical significance: small differences (< 2%) may be noise, not real improvement.

WHAT TO HIGHLIGHT:
- Which run is better on the primary metric and by how much.
- Which parameter changes caused the improvement.
- Any concerning trade-offs (overfitting risk, training cost).
- Suggest next steps: further tune the winning config, or explore new directions.

PRESENTATION:
- Lead with the verdict: "Run B is better by X% on [metric]."
- Then explain why: "The key difference is [param] changed from X to Y."
- Keep it concise. The user can see the raw numbers.

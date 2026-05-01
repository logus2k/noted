---
name: evidently-drift-detection
description: Data and prediction drift detection with Evidently - DataDriftPreset, RegressionPreset, drift alerts. Use when user asks about drift, model degradation, distribution shift, or performance monitoring.
triggers: [evidently_in_context]
priority: 1
max_tokens: 500
---
Evidently drift detection compares current data/predictions against a reference to detect distribution shifts.

DATA DRIFT REPORT:
```python
from evidently import Report, Dataset, DataDefinition
from evidently.presets import DataDriftPreset

data_def = DataDefinition(numerical=feature_columns)
ref_dataset = Dataset(training_df, data_definition=data_def)
cur_dataset = Dataset(new_data_df, data_definition=data_def)

report = Report([DataDriftPreset()],
    tags=["drift", "jena-weather"],
    metadata={"model_id": mlflow_run_id})
snapshot = report.run(cur_dataset, ref_dataset)

ws.add_run(project_id, snapshot, include_data=False)
```

PERFORMANCE MONITORING:
```python
from evidently.presets import RegressionPreset

data_def = DataDefinition(
    numerical=feature_columns,
    target="actual_temp",
    prediction="predicted_temp",
)
ref_dataset = Dataset(train_preds_df, data_definition=data_def)
cur_dataset = Dataset(eval_preds_df, data_definition=data_def)

report = Report([RegressionPreset()],
    tags=["performance", "jena-weather"],
    metadata={"model_id": run_id, "dataset_id": dvc_hash})
snapshot = report.run(cur_dataset, ref_dataset)
```

DRIFT STATUS IN NOTED:
- Backend queries Evidently for latest "drift" tagged report
- Per-feature drift scores with statistical tests (KS, PSI, etc.)
- Alert badge on Model nodes: green (<20% features drifted), yellow (20-50%), red (>50%)
- Drift history tracked over time in Evidently dashboard

PERFORMANCE STATUS:
- Regression metrics (MAE, RMSE, R2) tracked per evaluation run
- Performance badge on model nodes in Explorer tree
- Time-series dashboard in Evidently UI shows metric evolution
- Performance drops linked to drift events for root cause analysis

SCHEDULED MONITORING:
- Airflow DAG runs drift checks on configurable interval
- Compares serving inputs against training distribution
- Alerts surfaced in noted notifications when drift exceeds threshold

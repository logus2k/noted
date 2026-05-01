---
name: evidently-data-quality
description: Data quality validation with Evidently - DataSummaryPreset reports, Test Suites for quality gates, health badges. Use when user asks about data validation, data profiling, quality checks, or quality gates.
triggers: [evidently_in_context]
priority: 1
max_tokens: 500
---
Evidently data quality validates datasets before training and monitors data health over time.

DATA SUMMARY REPORT:
```python
from evidently import Report, Dataset, DataDefinition
from evidently.presets import DataSummaryPreset

data_def = DataDefinition(
    numerical=["T (degC)", "p (mbar)", "rh (%)", "wv (m/s)", "max. wv (m/s)"],
    datetime="Date Time",
)
dataset = Dataset(df, data_definition=data_def)
report = Report([DataSummaryPreset()], tags=["data-quality", "jena-weather"])
snapshot = report.run(dataset)

# Save to Evidently workspace
from evidently.ui.workspace import RemoteWorkspace
ws = RemoteWorkspace("http://noted-evidently:8000")
ws.add_run("PROJECT_ID", snapshot, include_data=False)
```

QUALITY GATE (Test Suite):
```python
from evidently import Report
from evidently.metrics import MinValue, MaxValue, MissingValueShare, RowCount
from evidently.tests import gte, lte, lt

report = Report([
    MinValue(column="T (degC)", tests=[gte(-50)]),
    MaxValue(column="T (degC)", tests=[lte(60)]),
    MissingValueShare(tests=[lt(0.05)]),
    RowCount(tests=[gte(1000)]),
], tags=["quality-gate", "jena-weather"])
snapshot = report.run(dataset)

# Check results
results = snapshot.dict()
failed = [t for t in results.get("tests", []) if t["status"] == "FAIL"]
if failed:
    raise ValueError(f"Quality gate failed: {len(failed)} test(s)")
```

HEALTH BADGE IN EXPLORER:
- noted backend queries Evidently for latest "data-quality" tagged report
- Badge color: green (all passed), yellow (warnings), red (failures)
- Displayed on dataset nodes in the Explorer tree
- Click opens full interactive report in Evidently UI

USE IN AIRFLOW DAG:
- Run DataSummaryPreset as first ingestion/preprocessing task
- Run quality gate Test Suite before training task
- Pipeline blocks on critical test failure
- Results visible in noted Pipeline detail view

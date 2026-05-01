---
name: evidently-monitoring
description: Evidently integration overview - data quality, drift detection, model performance monitoring. Use when user asks about monitoring, data validation, drift, or Evidently setup in noted.
triggers: [evidently_in_context]
priority: 1
max_tokens: 600
---
Evidently is integrated into noted for ML monitoring: data quality validation, data drift detection, and model performance tracking.

ARCHITECTURE:
- Container: noted-evidently (evidently/evidently-service) on noted-network
- API: http://noted-evidently:8000 (internal), port 8009 (host dev access)
- UI: accessible as service tab in noted (iframe via nginx /evidently/ proxy)
- Backend: evidently_manager.py queries workspace API via HTTP (no evidently Python package needed in noted container)
- Reports generated in notebooks or Airflow DAG tasks using the evidently Python package

INTEGRATION PATTERN (thin integration):
- noted does NOT render its own drift charts or report views
- noted DOES surface lightweight indicators (badges, alerts) in the Explorer tree
- noted DOES provide a service tab (iframe) for the full Evidently UI
- Reports are generated via the Evidently Python API in user code

KEY CONCEPTS:
- Project: workspace container for reports (e.g., "Jena Weather")
- Report: combines Metrics and/or Presets, run on one dataset (profiling) or two (comparison)
- Snapshot: saved report result in the Evidently workspace
- Test Suite: conditional pass/fail checks on metrics (quality gates)
- Presets: pre-configured metric bundles (DataSummaryPreset, DataDriftPreset, RegressionPreset)
- Tags: string labels on reports for filtering (e.g., "data-quality", "drift", "performance")

EVIDENTLY API ENDPOINTS:
- GET /api/version - service health
- GET /api/projects - list projects
- POST /api/projects - create project
- GET /api/projects/{id}/runs - list report snapshots
- GET /api/projects/{id}/runs/{run_id} - get report details

PYTHON USAGE (in notebooks or DAG tasks):
```python
from evidently import Report, Dataset, DataDefinition
from evidently.presets import DataSummaryPreset

data_def = DataDefinition(numerical=["T (degC)", "p (mbar)", "rh (%)"])
dataset = Dataset(df, data_definition=data_def)
report = Report([DataSummaryPreset()], tags=["data-quality"])
snapshot = report.run(dataset)
ws.add_run(project_id, snapshot, include_data=False)
```

INTEGRATION WITH STACK:
- MLflow: reports reference run IDs, model versions link to performance reports
- Airflow: reports generated in DAG tasks, quality gates as pre-training validation
- DVC: reference datasets identified by DVC hash
- Knowledge Graph: report entities with edges to datasets, models, pipeline runs

FINDING THE LATEST MONITORING REPORT (workflow):
- Reports are stored as MLflow artifacts on runs tagged `monitoring` (often in an `evidently-reports` experiment).
- Call `get_experiment_runs(experiment_name="evidently-reports")` - or the closest-matching monitoring experiment - and pick the most recent run. Then `get_run_details(run_id=<id>)` to list report artifacts.
- If the experiment doesn't exist or no runs are returned, explicitly tell the user and point them to the **noted-evidently UI (Evidently service tab in noted)** as the primary way to find reports. The UI lists every Evidently project and all snapshots regardless of MLflow state.
- Always name the UI as a fallback even when MLflow has the data - the UI is often faster for humans.

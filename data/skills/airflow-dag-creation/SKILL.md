---
name: airflow-dag-creation
description: How to author a new Airflow DAG inside noted. Use when the user asks how to create a DAG, write a pipeline, set up training orchestration, use a DAG template, or integrate Hydra with a DAG.
triggers: [airflow_in_context]
priority: 1
max_tokens: 500
---
Authoring a new Airflow DAG in noted:

FILE LOCATION:
- DAG modules live at the project root in `dags/`.
- Airflow auto-mounts and scans this folder; no registration needed.
- One DAG per file; name the file after the `dag_id`.

STANDARD TRAINING TEMPLATE (recommended task order):

  compose -> ingest -> preprocess -> train -> promote

- `compose`: resolve Hydra config from `dag_run.conf` / params into a plain dict.
- `ingest`: load and validate the raw dataset described by `cfg['data']['file']`.
- `preprocess`: feature engineering, splitting, scaling.
- `train`: fit the model, log params/metrics to MLflow inside `mlflow.start_run()`.
- `promote`: register the run's model into the MLflow registry (and optionally set alias).
- Optional: `log_hydra_lineage` (archive the resolved config under the run's artifacts) fans out parallel to `promote`.

SKELETON (TaskFlow API):
```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id="my_training_pipeline",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["training"],
    params={"data_config": "default", "model_config": "baseline",
            "epochs": 50, "seed": 42, "hydra_config_hash": ""},
)
def my_training_pipeline():

    @task
    def ingest_data(**context):
        cfg = _compose_config(context["params"])
        ...

    @task
    def preprocess_data(ingest_result, **context): ...

    @task
    def train_model_task(preprocess_result, **context):
        # call mlflow.start_run(experiment_id=...) inside
        ...

    @task
    def promote_model(train_result, **context): ...

    ingested = ingest_data()
    prepped = preprocess_data(ingested)
    trained = train_model_task(prepped)
    promote_model(trained)

my_training_pipeline()
```

HYDRA INTEGRATION:
- DAG params carry Composer selections; a `_compose_config(params)` helper resolves them into a plain dict (same schema noted's HydraManager produces).
- The resolved config hash is passed as `hydra_config_hash` for lineage archival.

WHEN THE USER ASKS "HOW DO I CREATE A DAG":
- Outline the file location and the compose->ingest->preprocess->train->promote template.
- Do NOT call `create_file` without explicit user confirmation of the filename and the intent.
- Offer to generate a skeleton file on request (and only then call `create_file`).

WHEN THE USER ASKS FOR A TEMPLATE FILE AT A SPECIFIC PATH:
- Call `create_file` once with the target path and a minimal skeleton matching the template above.

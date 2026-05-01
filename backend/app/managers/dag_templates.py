"""DAG file templates for creating new Airflow DAGs from the UI."""


TEMPLATES = {
    'blank': {
        'label': 'Blank DAG',
        'description': 'Empty DAG with a single placeholder task',
        'filename': 'new_dag.py',
        'content': '''"""New DAG - created from noted template."""

from airflow.sdk import dag, task
from airflow.models import Variable
from datetime import datetime

_schedule = Variable.get("{dag_id}_schedule", default_var=None)


@dag(
    dag_id="{dag_id}",
    schedule=_schedule,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["noted"],
)
def {dag_fn}():

    @task
    def start():
        print("DAG started")
        return "ok"

    start()

{dag_fn}()
''',
    },
    'training': {
        'label': 'Training Pipeline',
        'description': 'Data validation, model training, and evaluation',
        'filename': 'training_pipeline.py',
        'content': '''"""Training Pipeline - validate, train, evaluate."""

from airflow.sdk import dag, task
from airflow.models.param import Param
from airflow.models import Variable
from datetime import datetime

_schedule = Variable.get("{dag_id}_schedule", default_var=None)


@dag(
    dag_id="{dag_id}",
    schedule=_schedule,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["noted", "training"],
    params={{
        "model_type": Param("GRU", type="string", description="Model architecture"),
        "epochs": Param(30, type="integer", description="Training epochs"),
        "learning_rate": Param(0.001, type="number", description="Learning rate"),
    }},
)
def {dag_fn}():

    @task
    def validate_data(**context):
        print("Validating data...")
        return "validated"

    @task
    def train_model(**context):
        params = context["params"]
        print(f"Training {{params['model_type']}} for {{params['epochs']}} epochs")
        return "trained"

    @task
    def evaluate_model(**context):
        print("Evaluating model...")
        return "evaluated"

    data = validate_data()
    model = train_model()
    evaluation = evaluate_model()
    data >> model >> evaluation

{dag_fn}()
''',
    },
    'data': {
        'label': 'Data Pipeline',
        'description': 'Ingest, clean, and process data',
        'filename': 'data_pipeline.py',
        'content': '''"""Data Pipeline - ingest, clean, process."""

from airflow.sdk import dag, task
from airflow.models import Variable
from datetime import datetime

_schedule = Variable.get("{dag_id}_schedule", default_var=None)


@dag(
    dag_id="{dag_id}",
    schedule=_schedule,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["noted", "data"],
)
def {dag_fn}():

    @task
    def ingest_data():
        print("Ingesting raw data...")
        return "ingested"

    @task
    def clean_data():
        print("Cleaning data...")
        return "cleaned"

    @task
    def process_features():
        print("Processing features...")
        return "processed"

    raw = ingest_data()
    clean = clean_data()
    features = process_features()
    raw >> clean >> features

{dag_fn}()
''',
    },
    'parallel': {
        'label': 'Parallel Pipeline',
        'description': 'Fan-out pattern with parallel tasks',
        'filename': 'parallel_pipeline.py',
        'content': '''"""Parallel Pipeline - fan-out/fan-in pattern."""

from airflow.sdk import dag, task
from airflow.models import Variable
from datetime import datetime

_schedule = Variable.get("{dag_id}_schedule", default_var=None)


@dag(
    dag_id="{dag_id}",
    schedule=_schedule,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["noted"],
)
def {dag_fn}():

    @task
    def prepare():
        print("Preparing data...")
        return "ready"

    @task
    def process_a():
        print("Processing branch A...")
        return "a_done"

    @task
    def process_b():
        print("Processing branch B...")
        return "b_done"

    @task
    def combine(a, b):
        print(f"Combining results: {{a}}, {{b}}")
        return "combined"

    prep = prepare()
    a = process_a()
    b = process_b()
    result = combine(a, b)
    prep >> [a, b] >> result

{dag_fn}()
''',
    },
}


def render_template(template_key: str, dag_id: str) -> tuple[str, str]:
    """Render a DAG template with the given dag_id.

    Returns (filename, content).
    """
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Unknown template: {template_key}")

    dag_fn = dag_id.replace('-', '_').replace(' ', '_')
    content = template['content'].format(dag_id=dag_id, dag_fn=dag_fn)
    filename = f"{dag_fn}.py"

    return filename, content


def list_templates() -> list[dict]:
    """Return available templates for the UI."""
    return [
        {'key': k, 'label': v['label'], 'description': v['description']}
        for k, v in TEMPLATES.items()
    ]

"""Simple test DAG for Phase 0 verification. Safe to delete after testing."""

from airflow.decorators import dag, task
from airflow.models import Variable
from datetime import datetime


_schedule = Variable.get("noted_test_dag_schedule", default_var=None)


@dag(
    dag_id="noted_test_dag",
    schedule=_schedule,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["noted", "test"],
)
def noted_test_dag():
    @task
    def hello():
        print("noted Phase 0 verification: Airflow connectivity OK")
        return "success"

    hello()

noted_test_dag()

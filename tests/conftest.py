"""noted integration test fixtures.

The test container connects to the noted stack via internal Docker networking.
All tests use the 'noted-testing' project, scaffolding artifacts at session
start and cleaning up on teardown.

Run:
    cd services
    docker compose -f docker-compose.yml -f ../data/docker-compose.mounts.yml up -d
    docker compose -f ../tests/docker-compose.test.yml run --rm noted-test
"""

import os
import time
import uuid
import json
import pytest
import httpx

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")
PROJECT_ID = os.environ.get("NOTED_PROJECT", "noted-testing")
TIMEOUT = int(os.environ.get("NOTED_TIMEOUT", "180"))

# Naming convention: all test artifacts prefixed _test_ for easy cleanup
TEST_PREFIX = "_test_"


# ---------------------------------------------------------------------------
# Session-scoped: health gate + scaffolding
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url():
    return NOTED_URL


@pytest.fixture(scope="session")
def api(base_url):
    """httpx client for the noted API."""
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def health_gate(base_url):
    """Wait for noted + Airflow to be reachable before running any test."""
    endpoints = [
        ("noted", f"{base_url}/api/mlflow/experiments"),
        ("airflow", f"{base_url}/api/airflow/health"),
    ]
    for name, url in endpoints:
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            try:
                r = httpx.get(url, timeout=5)
                if r.status_code < 500:
                    break
            except (httpx.ConnectError, httpx.ReadTimeout):
                pass
            time.sleep(3)
        else:
            pytest.fail(f"Service '{name}' not reachable at {url} within {TIMEOUT}s")


@pytest.fixture(scope="session")
def project_id():
    return PROJECT_ID


# ---------------------------------------------------------------------------
# Session scaffold: create config, data, dags, notebook inside noted-testing
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def scaffold_project(api, project_id, health_gate):
    """Create all artifacts the test suite needs inside noted-testing."""
    created = []

    def _write_file(rel_path, content):
        """Write a file into the project via the API."""
        # Ensure all parent directories exist
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            api.post(f"/api/files/project/{project_id}", json={
                "path": dir_path, "is_dir": True,
            })
        r = api.put(
            f"/api/files/project/{project_id}/write",
            params={"path": rel_path},
            json={"content": content},
        )
        if r.status_code >= 300:
            print(f"SCAFFOLD WARNING: Failed to write {rel_path}: {r.status_code} {r.text[:100]}")
        else:
            created.append(rel_path)
        return r

    # -- Hydra config structure --
    _write_file("config/config.yaml", (
        "defaults:\n"
        "  - model: linear\n"
        "\n"
        "training:\n"
        "  epochs: 10\n"
        "  batch_size: 32\n"
        "  learning_rate: 0.001\n"
    ))
    _write_file("config/model/linear.yaml", (
        "type: linear\n"
        "params:\n"
        "  input_dim: 14\n"
        "  output_dim: 1\n"
    ))
    _write_file("config/model/gru.yaml", (
        "type: gru\n"
        "params:\n"
        "  units1: 128\n"
        "  units2: 64\n"
        "  dropout: 0.2\n"
    ))

    # -- Test data file --
    csv_header = "date,temperature,humidity,pressure\n"
    csv_rows = "".join(
        f"2024-01-{d:02d},{15+d*0.5:.1f},{60+d:.0f},{1013+d*0.1:.1f}\n"
        for d in range(1, 31)
    )
    _write_file("data/test_data.csv", csv_header + csv_rows)

    # -- Test notebook --
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {
                "cell_type": "code",
                "metadata": {},
                "source": ["import mlflow\nprint('Hello from noted-testing')"],
                "outputs": [],
                "execution_count": None,
            },
            {
                "cell_type": "code",
                "metadata": {},
                "source": ["x = 1 + 1\nprint(f'Result: {x}')"],
                "outputs": [],
                "execution_count": None,
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Test Notebook\nThis is a **test** markdown cell."],
            },
        ],
    }
    _write_file("test_notebook.ipynb", json.dumps(notebook, indent=2))

    # -- DAG file --
    dag_content = (
        "from airflow.decorators import dag, task\n"
        "from datetime import datetime\n"
        "\n"
        "@dag(\n"
        "    dag_id='_test_pipeline',\n"
        "    schedule=None,\n"
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        "    tags=['noted-testing'],\n"
        ")\n"
        "def _test_pipeline():\n"
        "    @task()\n"
        "    def hello():\n"
        "        return 'hello from test'\n"
        "\n"
        "    @task()\n"
        "    def goodbye(greeting):\n"
        "        print(f'Got: {greeting}')\n"
        "        return 'done'\n"
        "\n"
        "    goodbye(hello())\n"
        "\n"
        "_test_pipeline()\n"
    )
    _write_file("dags/_test_pipeline.py", dag_content)

    # -- Training script for kernel tests --
    _write_file("src/train.py", (
        "import mlflow\n"
        "import random\n"
        "\n"
        "mlflow.log_param('model_type', 'test')\n"
        "mlflow.log_param('epochs', 5)\n"
        "mlflow.log_metric('total_epochs', 5)\n"
        "for epoch in range(5):\n"
        "    loss = 1.0 / (epoch + 1) + random.random() * 0.1\n"
        "    mlflow.log_metric('loss', loss, step=epoch)\n"
        "    mlflow.log_metric('accuracy', 0.5 + epoch * 0.1, step=epoch)\n"
        "print('Training complete')\n"
    ))

    # -- Git commit the scaffold --
    repo_path = f"/app/data/projects/{project_id}"
    api.post("/api/git/repo/commit", json={
        "repo_path": repo_path,
        "message": "Test scaffold: config, data, notebook, DAG, training script",
        "files": ["."],
    })

    # -- Wait for Airflow to discover the test DAG --
    _wait_for_dag(api, "_test_pipeline", timeout=90)

    yield {
        "project_id": project_id,
        "files": created,
    }

    # -- Teardown: clean up test artifacts from external services --
    _cleanup_mlflow(api)
    _cleanup_airflow(api)
    _cleanup_files(api, project_id, created)


def _wait_for_dag(api, dag_id, timeout=30):
    """Poll Airflow until a DAG is discovered. Best-effort, does not fail."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = api.get("/api/airflow/dags")
            if r.status_code == 200:
                dags = r.json().get("dags", [])
                if any(d.get("dag_id") == dag_id for d in dags):
                    return
        except Exception:
            pass
        time.sleep(3)


def _cleanup_mlflow(api):
    """Clean up MLflow test data. Skips deletion to preserve kernel-created data.

    Kernel tests (Phase 1) create experiments with metrics/models that
    API tests (Phase 2) depend on. Each run uses unique UIDs so stale
    experiments don't interfere.
    """
    pass


def _cleanup_airflow(api):
    """Delete test DAG runs."""
    try:
        r = api.get("/api/airflow/dags?tag=noted-testing")
        if r.status_code == 200:
            for dag in r.json().get("dags", []):
                dag_id = dag.get("dag_id", "")
                if dag_id.startswith(TEST_PREFIX):
                    # Clear runs
                    runs = api.get(f"/api/airflow/dags/{dag_id}/runs?limit=50")
                    if runs.status_code == 200:
                        for run in runs.json().get("runs", []):
                            run_id = run.get("dag_run_id")
                            if run_id:
                                api.delete(f"/api/airflow/dags/{dag_id}/runs/{run_id}")
    except Exception:
        pass


def _cleanup_files(api, project_id, created_files):
    """Remove scaffolded files from the project."""
    # Delete files first, then directories (reversed order)
    dirs = set()
    for path in reversed(created_files):
        try:
            api.delete(f"/api/files/project/{project_id}", params={"path": path})
        except Exception:
            pass
        parts = path.split("/")
        if len(parts) > 1:
            dirs.add("/".join(parts[:-1]))
    for d in sorted(dirs, key=len, reverse=True):
        try:
            api.delete(f"/api/files/project/{project_id}", params={"path": d})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Function-scoped fixtures for individual tests
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_name():
    """Generate a unique _test_ prefixed name."""
    return f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture
def temp_file(api, project_id):
    """Create a temporary file, yield its path, delete on teardown."""
    files = []

    def _create(rel_path, content="test content"):
        api.put(
            f"/api/files/project/{project_id}/write",
            params={"path": rel_path},
            json={"content": content},
        )
        files.append(rel_path)
        return rel_path

    yield _create

    for f in files:
        try:
            api.delete(f"/api/files/project/{project_id}", params={"path": f})
        except Exception:
            pass


@pytest.fixture
def existing_experiment(api):
    """Return an MLflow experiment that has runs with metrics (for read-only tests)."""
    r = api.get("/api/mlflow/experiments")
    experiments = r.json().get("experiments", [])
    if not experiments:
        pytest.skip("No MLflow experiments exist")
    # Prefer an experiment with metric-bearing runs (from kernel tests)
    best_eid = None
    for exp in experiments:
        eid = exp.get("experiment_id")
        runs_r = api.get(f"/api/mlflow/experiments/{eid}/runs")
        if runs_r.status_code == 200:
            runs = runs_r.json().get("runs", [])
            if not runs:
                continue
            if not best_eid:
                best_eid = eid
            # Check if any run has metrics
            for run in runs:
                if run.get("metrics"):
                    return eid
    if best_eid:
        return best_eid
    # Fall back to first experiment
    return experiments[0]["experiment_id"]

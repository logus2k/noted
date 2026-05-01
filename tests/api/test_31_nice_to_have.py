"""31 - Nice-to-Have Features (API-testable parts).

Maps to: testing/31_test-nice-to-have-features.md
Covers R11-R28 features that have backend API components.
"""

import pytest

pytestmark = pytest.mark.api

REPO_PATH = "/app/data/projects/noted-testing"


class TestDVCSyncIcons:
    """R11: DVC cloud status for sync icons."""

    def test_cloud_status_returns_files(self, api):
        """Cloud status endpoint returns file push state map."""
        r = api.post("/api/dvc/cloud-status", json={"repo_path": REPO_PATH})
        assert r.status_code == 200
        data = r.json()
        assert "files" in data
        assert isinstance(data["files"], dict)
        for path, status in data["files"].items():
            assert isinstance(status, str), (
                f"File status for {path!r} must be a string, got {type(status)}: {status!r}"
            )


class TestConfigInheritance:
    """R20: Compose returns source file annotations."""

    def test_sources_in_compose(self, api, project_id):
        """Compose with group selection includes sources."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "gru"},
        })
        assert r.status_code == 200
        sources = r.json().get("sources", {})
        assert "model" in sources
        assert "gru" in sources["model"]

    def test_override_shows_in_sources(self, api, project_id):
        """Overrides are marked as 'override' in sources."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "overrides": {"training.epochs": 99},
        })
        assert r.status_code == 200
        sources = r.json().get("sources", {})
        assert sources.get("training") == "override"


class TestDAGValidation:
    """R23: DAG validation endpoint."""

    def test_validate_datetime_now_warning(self, api):
        """datetime.now() at parse time gets a warning."""
        content = (
            "from airflow.decorators import dag, task\n"
            "from datetime import datetime\n"
            "@dag(schedule=None, start_date=datetime.now())\n"
            "def my_dag():\n"
            "    @task()\n"
            "    def t(): pass\n"
            "    t()\n"
            "my_dag()\n"
        )
        r = api.post("/api/airflow/validate-dag", json={"content": content})
        assert r.status_code == 200
        warnings = r.json().get("warnings", [])
        assert any("datetime.now" in w.get("message", "") for w in warnings)

    def test_validate_heavy_import_warning(self, api):
        """Heavy imports at module level get a warning."""
        content = (
            "import pandas\n"
            "from airflow.decorators import dag, task\n"
            "from datetime import datetime\n"
            "@dag(schedule=None, start_date=datetime(2024,1,1))\n"
            "def my_dag():\n"
            "    @task()\n"
            "    def t(): pass\n"
            "    t()\n"
            "my_dag()\n"
        )
        r = api.post("/api/airflow/validate-dag", json={"content": content})
        assert r.status_code == 200
        warnings = r.json().get("warnings", [])
        assert any("pandas" in w.get("message", "").lower() for w in warnings)


class TestPipelineActions:
    """R9/R10: Task log and clear endpoints with real DAG data."""

    def test_task_log_with_valid_dag(self, api):
        """Fetch task log for a real DAG run."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAGs available")
        dag_id = test_dags[0]["dag_id"]

        runs = api.get(f"/api/airflow/dags/{dag_id}/runs?limit=1").json().get("runs", [])
        if not runs:
            pytest.skip("No DAG runs available")
        run_id = runs[0]["dag_run_id"]

        tasks = api.get(f"/api/airflow/dags/{dag_id}/runs/{run_id}/tasks").json().get("tasks", [])
        if not tasks:
            pytest.skip("No task instances")

        task_id = tasks[0]["task_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs")
        assert r2.status_code == 200
        data2 = r2.json()
        assert "log" in data2
        log_content = data2["log"]
        assert isinstance(log_content, str), f"log must be a string, got {type(log_content)}"
        assert len(log_content) > 0, "log content is empty"


class TestServingAPIs:
    """R17: APIs section - serving health detail."""

    def test_serving_returns_status_field(self, api):
        """Serving health includes status and model info."""
        r = api.get("/api/serving/health")
        if r.status_code == 200:
            data = r.json()
            assert "status" in data
            # Status should be one of: idle, loading, ready, error
            assert data["status"] in ("idle", "loading", "ready", "error")


class TestHydraPromoteBest:
    """R19: Promote best config (saves as template)."""

    def test_promote_saves_template(self, api, project_id, unique_name):
        """Saving a template via the templates API works (used by Promote Best)."""
        template_name = f"best_{unique_name}"
        group_selections = {"model": "gru"}
        overrides = {"training.lr": 0.001, "training.epochs": 50}
        r = api.post(f"/api/hydra/templates/{project_id}", json={
            "name": template_name,
            "description": "Promoted best run",
            "group_selections": group_selections,
            "overrides": overrides,
        })
        assert r.status_code == 200

        # Verify the stored metadata matches what was saved
        r2 = api.get(f"/api/hydra/templates/{project_id}/{template_name}")
        assert r2.status_code == 200
        loaded = r2.json()
        assert loaded.get("name") == template_name, (
            f"Template name not preserved: {loaded.get('name')!r}"
        )
        loaded_gs = loaded.get("group_selections", {})
        assert loaded_gs.get("model") == "gru", (
            f"Promoted group_selections.model not preserved: {loaded_gs}"
        )
        loaded_ov = loaded.get("overrides", {})
        assert loaded_ov.get("training.lr") == 0.001, (
            f"Promoted training.lr not preserved: {loaded_ov}"
        )
        assert loaded_ov.get("training.epochs") == 50, (
            f"Promoted training.epochs not preserved: {loaded_ov}"
        )

        # Cleanup
        api.delete(f"/api/hydra/templates/{project_id}/{template_name}")

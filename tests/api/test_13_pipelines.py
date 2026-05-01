"""13 - Pipelines (Airflow).

Maps to: testing/13_test-pipelines.md
"""

import time
import pytest

pytestmark = pytest.mark.api


class TestPipelineDiscovery:
    """Tests 1-4: DAG listing and detail."""

    def test_list_dags(self, api):
        """DAG listing returns results."""
        r = api.get("/api/airflow/dags")
        assert r.status_code == 200
        dags = r.json().get("dags", [])
        assert isinstance(dags, list)
        if dags:
            for dag in dags:
                assert "dag_id" in dag, f"DAG item missing 'dag_id' field: {list(dag.keys())}"

    def test_list_dags_by_tag(self, api):
        """Filter DAGs by project tag."""
        r = api.get("/api/airflow/dags", params={"tag": "noted-testing"})
        assert r.status_code == 200
        dags = r.json().get("dags", [])
        assert isinstance(dags, list)
        for dag in dags:
            assert "dag_id" in dag, f"DAG item missing 'dag_id': {list(dag.keys())}"
            tags = dag.get("tags", [])
            tag_values = [
                t if isinstance(t, str) else t.get("name", "")
                for t in tags
            ]
            assert "noted-testing" in tag_values, (
                f"DAG '{dag['dag_id']}' returned by tag filter but tags don't contain "
                f"'noted-testing': {tag_values}"
            )

    def test_dag_detail(self, api):
        """Get detail for a specific DAG (if test DAG exists)."""
        # Wait for test DAG to be parsed
        deadline = time.time() + 60
        while time.time() < deadline:
            r = api.get("/api/airflow/dags")
            dags = r.json().get("dags", [])
            test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
            if test_dags:
                break
            time.sleep(5)
        else:
            pytest.skip("Test DAG not yet parsed by Airflow")

        dag_id = test_dags[0]["dag_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}")
        assert r2.status_code == 200
        detail = r2.json()
        assert isinstance(detail, dict)
        assert "dag_id" in detail, f"DAG detail missing 'dag_id': {list(detail.keys())}"
        assert detail["dag_id"] == dag_id, (
            f"dag_id mismatch: expected '{dag_id}', got '{detail['dag_id']}'"
        )
        assert "schedule" in detail or "schedule_interval" in detail or "timetable_summary" in detail, (
            f"DAG detail missing schedule field: {list(detail.keys())}"
        )
        assert "tags" in detail, f"DAG detail missing 'tags' field: {list(detail.keys())}"

    def test_dag_tasks(self, api):
        """Get task list for a DAG."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAG available")
        dag_id = test_dags[0]["dag_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}/tasks")
        assert r2.status_code == 200
        body = r2.json()
        assert "tasks" in body, f"Tasks response missing 'tasks' key: {list(body.keys())}"
        tasks = body["tasks"]
        assert isinstance(tasks, list), "'tasks' should be a list"
        if tasks:
            for task in tasks:
                assert "task_id" in task, f"Task missing 'task_id': {list(task.keys())}"

    def test_dag_structure(self, api):
        """Get DAG dependency graph structure."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAG available")
        dag_id = test_dags[0]["dag_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}/structure")
        assert r2.status_code == 200


class TestPipelineTrigger:
    """Tests 5-7: Trigger DAG runs."""

    @pytest.mark.slow
    def test_trigger_dag(self, api):
        """Trigger a DAG run and verify it starts."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAG available")

        dag_id = test_dags[0]["dag_id"]

        # Unpause if needed
        api.patch(f"/api/airflow/dags/{dag_id}/pause",
                  json={"is_paused": False})

        # Trigger
        r2 = api.post(f"/api/airflow/dags/{dag_id}/trigger",
                       json={"conf": {"test_param": "automated"}})
        assert r2.status_code == 200
        data = r2.json()
        assert "dag_run_id" in data

    def test_list_dag_runs(self, api):
        """List runs for a DAG."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAG available")
        dag_id = test_dags[0]["dag_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}/runs", params={"limit": 5})
        assert r2.status_code == 200
        body = r2.json()
        assert "runs" in body, f"Runs response missing 'runs' key: {list(body.keys())}"
        runs = body["runs"]
        assert isinstance(runs, list), "'runs' should be a list"
        if runs:
            for run in runs:
                assert "dag_run_id" in run, f"Run missing 'dag_run_id': {list(run.keys())}"
                assert "state" in run, f"Run missing 'state': {list(run.keys())}"


class TestPipelineSchedule:
    """Tests 8-9: Schedule management."""

    def test_get_schedule(self, api):
        """Get schedule for a DAG."""
        r = api.get("/api/airflow/dags")
        dags = r.json().get("dags", [])
        test_dags = [d for d in dags if d.get("dag_id", "").startswith("_test_")]
        if not test_dags:
            pytest.skip("No test DAG available")
        dag_id = test_dags[0]["dag_id"]
        r2 = api.get(f"/api/airflow/dags/{dag_id}/schedule")
        assert r2.status_code == 200
        body = r2.json()
        assert isinstance(body, dict), "Schedule response should be a JSON object"
        has_schedule = (
            "schedule" in body
            or "schedule_interval" in body
            or "timetable_summary" in body
            or "cron" in body
        )
        assert has_schedule, f"Schedule response missing schedule field: {list(body.keys())}"


class TestPipelineTemplates:
    """DAG template listing."""

    def test_list_templates(self, api):
        """DAG templates endpoint returns available templates."""
        r = api.get("/api/airflow/templates")
        assert r.status_code == 200
        templates = r.json().get("templates", [])
        assert len(templates) >= 1
        for t in templates:
            assert isinstance(t, dict), f"Template item should be a dict, got: {type(t)}"
            assert "name" in t or "id" in t or "key" in t, (
                f"Template missing name/id/key: {list(t.keys())}"
            )
            assert "description" in t, f"Template missing 'description': {list(t.keys())}"
        keys = [t.get("id") or t.get("key") for t in templates]
        assert "blank" in keys


class TestDAGValidation:
    """R23: DAG validation endpoint."""

    def test_validate_good_dag(self, api):
        """Valid DAG passes validation."""
        content = (
            "from airflow.decorators import dag, task\n"
            "from datetime import datetime\n"
            "@dag(schedule=None, start_date=datetime(2024,1,1))\n"
            "def my_dag():\n"
            "    @task()\n"
            "    def hello(): return 'hi'\n"
            "    hello()\n"
            "my_dag()\n"
        )
        r = api.post("/api/airflow/validate-dag", json={"content": content})
        assert r.status_code == 200
        warnings = r.json().get("warnings", [])
        assert any(w["level"] == "ok" for w in warnings)

    def test_validate_bad_syntax(self, api):
        """DAG with syntax error is caught."""
        r = api.post("/api/airflow/validate-dag", json={"content": "def foo(:\n  pass"})
        assert r.status_code == 200
        warnings = r.json().get("warnings", [])
        assert any(w["level"] == "error" for w in warnings)

    def test_validate_missing_import(self, api):
        """DAG without airflow import gets warning."""
        r = api.post("/api/airflow/validate-dag", json={"content": "x = 1"})
        assert r.status_code == 200
        warnings = r.json().get("warnings", [])
        assert any("import" in w.get("message", "").lower() for w in warnings)

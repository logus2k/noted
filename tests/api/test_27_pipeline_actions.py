"""27 - Pipeline Actions: Copy Log, Retry Task, Config Template.

Maps to: testing/27_test-pipeline-actions.md
API-testable parts: task log retrieval, clear task endpoint.
"""

import pytest

pytestmark = pytest.mark.api


class TestTaskLogs:
    """R9: Task log retrieval."""

    def test_task_log_endpoint(self, api):
        """Task log endpoint responds (even with invalid params)."""
        r = api.get("/api/airflow/dags/nonexistent/runs/nonexistent/tasks/nonexistent/logs")
        # 404 or 500 expected for invalid params, not a crash
        assert r.status_code in (200, 404, 500)
        data = r.json()
        assert isinstance(data, dict), f"Expected JSON object response, got: {type(data)}"
        has_structure = any(k in data for k in ("log", "error", "detail", "message"))
        assert has_structure, f"Response missing expected fields (log/error/detail/message): {data}"


class TestClearTaskInstance:
    """R10: Retry failed task (clear task instance)."""

    def test_clear_endpoint_exists(self, api):
        """Clear task endpoint responds."""
        r = api.post("/api/airflow/dags/nonexistent/runs/nonexistent/tasks/nonexistent/clear")
        # 404 expected for nonexistent DAG
        assert r.status_code in (200, 404, 500)
        data = r.json()
        assert isinstance(data, dict), f"Expected JSON object response, got: {type(data)}"
        has_structure = any(k in data for k in ("cleared", "error", "detail", "message"))
        assert has_structure, f"Response missing expected fields (cleared/error/detail/message): {data}"

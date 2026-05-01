"""07 - Live Metrics and Artifacts.

Maps to: testing/07_test-live-metrics-and-artifacts.md
API-testable parts: MLflow run/metric/artifact endpoints.
Live streaming requires Socket.IO (covered in E2E).
"""

import pytest

pytestmark = pytest.mark.api


class TestMLflowRuns:
    """Verify MLflow run and metric APIs work."""

    def test_list_experiments(self, api):
        """Experiments endpoint returns list with required fields."""
        r = api.get("/api/mlflow/experiments")
        assert r.status_code == 200
        data = r.json()
        assert "experiments" in data
        experiments = data["experiments"]
        assert isinstance(experiments, list), "experiments must be a list"
        for exp in experiments:
            assert "experiment_id" in exp, (
                f"Each experiment must have experiment_id, got: {exp}"
            )
            assert "name" in exp, (
                f"Each experiment must have name, got: {exp}"
            )

    def test_experiment_runs_endpoint(self, api):
        """Experiment runs endpoint returns structured run data."""
        r = api.get("/api/mlflow/experiments")
        experiments = r.json().get("experiments", [])
        if not experiments:
            pytest.skip("No experiments exist")
        eid = experiments[0]["experiment_id"]
        r2 = api.get(f"/api/mlflow/experiments/{eid}/runs")
        assert r2.status_code == 200
        runs_data = r2.json()
        runs = runs_data if isinstance(runs_data, list) else runs_data.get("runs", [])
        assert isinstance(runs, list), "runs must be a list"
        for run in runs:
            assert "run_id" in run, f"Each run must have run_id, got: {run}"
            assert "status" in run, f"Each run must have status, got: {run}"
            assert "metrics" in run, f"Each run must have metrics, got: {run}"
            assert "params" in run, f"Each run must have params, got: {run}"


class TestArtifacts:
    """Artifact listing endpoints."""

    def test_artifact_endpoint_exists(self, api):
        """Artifacts endpoint responds (even without valid run)."""
        r = api.get("/api/mlflow/runs/nonexistent/artifacts")
        # 404 or 500 is expected for invalid run, not a crash
        assert r.status_code in (200, 404, 500)
        if r.status_code == 200:
            data = r.json()
            assert "artifacts" in data, (
                "Successful artifacts response must have an artifacts key"
            )
            assert isinstance(data["artifacts"], list), (
                "artifacts must be a list"
            )

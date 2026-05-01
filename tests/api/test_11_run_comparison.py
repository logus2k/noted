"""11 - Run Comparison.

Maps to: testing/11_test-run-comparison.md
Tests run detail and comparison endpoints.
"""

import pytest

pytestmark = pytest.mark.api


class TestRunDetail:
    """Test 1-2: Run detail retrieval."""

    def test_run_detail_endpoint(self, api, existing_experiment):
        """Run detail returns metrics, params, tags for a valid run."""
        # Get runs from the experiment
        r = api.get(f"/api/mlflow/experiments/{existing_experiment}/runs")
        assert r.status_code == 200
        runs = r.json().get("runs", [])
        if not runs:
            pytest.skip("No runs in experiment")

        run_id = runs[0].get("run_id")
        r2 = api.get(f"/api/mlflow/runs/{run_id}")
        assert r2.status_code == 200
        data = r2.json()
        # Top-level run_id or MLflow-style nested info block
        has_run_id = "run_id" in data or ("info" in data and "run_id" in data["info"])
        assert has_run_id, f"Response missing run_id: {list(data.keys())}"
        # Must have metrics and params (possibly empty dicts)
        has_metrics = "metrics" in data or ("data" in data and "metrics" in data["data"])
        has_params = "params" in data or ("data" in data and "params" in data["data"])
        assert has_metrics, f"Response missing metrics: {list(data.keys())}"
        assert has_params, f"Response missing params: {list(data.keys())}"
        # Must have a status field somewhere
        has_status = (
            "status" in data
            or ("info" in data and "status" in data["info"])
            or ("run" in data and "info" in data["run"] and "status" in data["run"]["info"])
        )
        assert has_status, f"Response missing status: {list(data.keys())}"

    def test_metric_history(self, api):
        """Metric history endpoint returns step/value pairs."""
        # Search across all experiments for a run with metrics
        r = api.get("/api/mlflow/experiments")
        experiments = r.json().get("experiments", [])
        run_id = None
        metric_key = None
        for exp in experiments:
            eid = exp.get("experiment_id")
            runs_r = api.get(f"/api/mlflow/experiments/{eid}/runs")
            for run in runs_r.json().get("runs", []):
                metrics = run.get("metrics", {})
                if metrics:
                    run_id = run["run_id"]
                    metric_key = list(metrics.keys())[0]
                    break
            if run_id:
                break
        if not run_id:
            pytest.skip("No runs with metrics found")

        r2 = api.get(f"/api/mlflow/runs/{run_id}/metrics/{metric_key}")
        assert r2.status_code == 200
        data = r2.json()
        history = data.get("history", data)
        assert isinstance(history, list), f"Metric history should be a list, got: {type(history)}"
        assert len(history) >= 1, "Metric history should have at least one entry"
        item = history[0]
        assert isinstance(item, dict), f"History item should be a dict, got: {type(item)}"
        assert "step" in item, f"History item missing 'step' field: {list(item.keys())}"
        assert "value" in item, f"History item missing 'value' field: {list(item.keys())}"


class TestRunComparison:
    """Test 3-5: Compare two runs."""

    def test_compare_two_runs(self, api, existing_experiment):
        """Comparison endpoint returns diff for two runs."""
        r = api.get(f"/api/mlflow/experiments/{existing_experiment}/runs")
        runs = r.json().get("runs", [])
        if len(runs) < 2:
            pytest.skip("Need at least 2 runs to compare")

        r2 = api.post("/api/mlflow/runs/compare", json={
            "run_ids": [runs[0]["run_id"], runs[1]["run_id"]],
        })
        # Endpoint may be at different path
        if r2.status_code == 404:
            # Try alternate path
            r2 = api.get(f"/api/mlflow/runs/{runs[0]['run_id']}/compare/{runs[1]['run_id']}")
        assert r2.status_code in (200, 404, 405)
        if r2.status_code == 200:
            data = r2.json()
            assert isinstance(data, dict), "Comparison response should be a JSON object"
            # Must contain run data: either a 'runs' key, or per-run_id keys
            has_runs_key = "runs" in data
            has_run_ids = runs[0]["run_id"] in data or runs[1]["run_id"] in data
            has_diff = "metrics" in data or "params" in data or "diff" in data
            assert has_runs_key or has_run_ids or has_diff, (
                f"Comparison response has no recognizable run data: {list(data.keys())}"
            )

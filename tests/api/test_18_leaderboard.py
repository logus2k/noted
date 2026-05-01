"""18 - Run Leaderboard.

Maps to: testing/18_test-run-leaderboard.md
"""

import pytest

pytestmark = pytest.mark.api


class TestLeaderboard:
    """Leaderboard API endpoint."""

    def test_leaderboard_for_experiment(self, api, existing_experiment):
        """Leaderboard returns runs, metric_keys, param_keys."""
        r = api.get(f"/api/mlflow/experiments/{existing_experiment}/leaderboard",
                     timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data, f"Leaderboard missing 'runs' key: {list(data.keys())}"
        assert "metric_keys" in data, f"Leaderboard missing 'metric_keys': {list(data.keys())}"
        assert "param_keys" in data, f"Leaderboard missing 'param_keys': {list(data.keys())}"
        metric_keys = data["metric_keys"]
        assert isinstance(metric_keys, list), (
            f"'metric_keys' should be a list, got: {type(metric_keys)}"
        )
        runs = data["runs"]
        assert isinstance(runs, list), f"'runs' should be a list, got: {type(runs)}"
        if runs:
            for run in runs:
                assert isinstance(run, dict), f"Run item should be a dict, got: {type(run)}"
                assert "run_id" in run, f"Run item missing 'run_id': {list(run.keys())}"

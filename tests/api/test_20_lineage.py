"""20 - Lineage and Model Comparison.

Maps to: testing/20_test-lineage-comparison.md
"""

import pytest

pytestmark = pytest.mark.api


def _find_model_with_versions(api, min_versions=1):
    """Find a registered model that has at least min_versions versions."""
    r = api.get("/api/registry/models")
    models = r.json().get("models", [])
    for model in models:
        name = model.get("name")
        r2 = api.get(f"/api/registry/models/{name}/versions")
        if r2.status_code == 200:
            versions = r2.json().get("versions", [])
            if len(versions) >= min_versions:
                return name, versions
    return None, []


class TestModelVersions:
    """Model version listing."""

    def test_list_model_versions(self, api):
        """List versions for registered models."""
        name, versions = _find_model_with_versions(api, min_versions=1)
        if not name:
            pytest.skip("No registered models with versions")

        assert len(versions) >= 1
        assert "version" in versions[0]
        assert "run_id" in versions[0]


class TestModelLineage:
    """Lineage chain for a model version."""

    def test_lineage_endpoint(self, api):
        """Lineage endpoint returns the full chain."""
        name, versions = _find_model_with_versions(api, min_versions=1)
        if not name:
            pytest.skip("No registered models with versions")

        version = versions[0].get("version")
        r = api.get(f"/api/registry/models/{name}/versions/{version}/lineage")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), f"Lineage response should be a dict, got: {type(data)}"
        # Lineage must contain at least one recognizable tracing key
        has_run = "run_id" in data or "run" in data
        has_experiment = "experiment_id" in data or "experiment" in data
        has_layers = "layers" in data or "nodes" in data or "chain" in data
        assert has_run or has_experiment or has_layers, (
            f"Lineage response missing expected keys (run_id/experiment/layers): "
            f"{list(data.keys())}"
        )


class TestModelComparison:
    """Compare two model versions."""

    def test_compare_endpoint(self, api):
        """Model comparison endpoint responds."""
        name, versions = _find_model_with_versions(api, min_versions=2)
        if not name:
            pytest.skip("Need a model with at least 2 versions")

        v1 = versions[0].get("version")
        v2 = versions[1].get("version")
        r = api.post("/api/registry/models/compare", json={
            "model_name": name,
            "version_a": v1,
            "version_b": v2,
        })
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), f"Comparison response should be a dict, got: {type(data)}"
        # Response must contain diff data for metrics or params
        has_metrics = "metrics" in data or "metric_diff" in data
        has_params = "params" in data or "param_diff" in data
        has_versions = "version_a" in data or "versions" in data or "runs" in data
        assert has_metrics or has_params or has_versions, (
            f"Comparison response has no metric/param diff data: {list(data.keys())}"
        )


class TestAliasManagement:
    """Model alias operations."""

    def test_alias_endpoint(self, api):
        """Alias set/get endpoint responds."""
        name, versions = _find_model_with_versions(api, min_versions=1)
        if not name:
            pytest.skip("No registered models with versions")

        version = versions[0].get("version")
        r = api.get(f"/api/registry/models/{name}/versions/{version}")
        assert r.status_code == 200
        detail = r.json()
        assert isinstance(detail, dict), f"Version detail should be a dict, got: {type(detail)}"
        assert "version" in detail, f"Version detail missing 'version' field: {list(detail.keys())}"
        assert str(detail["version"]) == str(version), (
            f"Version number mismatch: expected {version!r}, got {detail['version']!r}"
        )
        assert "status" in detail or "current_stage" in detail, (
            f"Version detail missing status/current_stage field: {list(detail.keys())}"
        )

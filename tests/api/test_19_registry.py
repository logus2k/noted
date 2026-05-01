"""19 - Model Registry.

Maps to: testing/19_test-model-registry.md
"""

import pytest

pytestmark = pytest.mark.api


class TestModelRegistry:
    """Model registry listing endpoints."""

    def test_list_models(self, api):
        """Model listing endpoint responds with named model objects."""
        r = api.get("/api/registry/models")
        assert r.status_code == 200
        data = r.json()
        models = data.get("models", [])
        assert isinstance(models, list), f"'models' should be a list, got: {type(models)}"
        # Kernel tests register models, so the list must be non-empty
        assert len(models) >= 1, (
            "Expected at least one registered model (kernel tests should have created models)"
        )
        for model in models:
            assert isinstance(model, dict), f"Model item should be a dict, got: {type(model)}"
            assert "name" in model, f"Model item missing 'name' field: {list(model.keys())}"
            assert isinstance(model["name"], str) and model["name"], (
                f"Model 'name' should be a non-empty string, got: {model['name']!r}"
            )

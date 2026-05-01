"""12 - Hydra Configuration.

Maps to: testing/12_test-hydra-config.md
"""

import pytest

pytestmark = pytest.mark.api


class TestHydraSchema:
    """Tests 1-5: Config schema discovery."""

    def test_schema_endpoint(self, api, project_id):
        """Hydra schema returns config groups."""
        r = api.get(f"/api/hydra/schema/{project_id}")
        assert r.status_code == 200
        data = r.json()
        assert data.get("has_config") is True

    def test_schema_has_model_group(self, api, project_id):
        """Schema includes the model config group."""
        r = api.get(f"/api/hydra/schema/{project_id}")
        data = r.json()
        groups = data.get("groups", {})
        assert "model" in groups
        options = groups["model"].get("options", [])
        assert "linear" in options
        assert "gru" in options


class TestHydraCompose:
    """Tests 6-8: Config composition."""

    def test_compose_default(self, api, project_id):
        """Compose with default config."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
        })
        assert r.status_code == 200
        data = r.json()
        assert "resolved" in data
        assert "yaml" in data
        assert "hash" in data
        assert data["hash"].startswith("sha256:")

    def test_compose_with_group_selection(self, api, project_id):
        """Compose with model=gru selection."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "gru"},
        })
        assert r.status_code == 200
        resolved = r.json()["resolved"]
        assert resolved["model"]["type"] == "gru"
        assert resolved["model"]["params"]["units1"] == 128

    def test_compose_single_group_includes_all_defaults(self, api, project_id):
        """Selecting one group must include defaults for all other groups."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "gru"},
        })
        assert r.status_code == 200
        resolved = r.json()["resolved"]
        # model was explicitly selected
        assert "model" in resolved
        # data must also be present via defaults from config.yaml
        assert "data" in resolved

    def test_compose_with_overrides(self, api, project_id):
        """Compose with dotted-key overrides."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "overrides": {"training.epochs": 50},
        })
        assert r.status_code == 200
        resolved = r.json()["resolved"]
        assert resolved["training"]["epochs"] == 50

    def test_compose_returns_sources(self, api, project_id):
        """Compose output includes source file annotations (R20)."""
        r = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "gru"},
        })
        data = r.json()
        sources = data.get("sources", {})
        assert "model" in sources
        assert "gru" in sources["model"]


class TestHydraGroupDetail:
    """Test 9: Individual group config retrieval."""

    def test_get_group_option(self, api, project_id):
        """Retrieve a specific config group option."""
        r = api.get(f"/api/hydra/group/{project_id}/model/gru")
        assert r.status_code == 200
        data = r.json()
        assert "content" in data or "config" in data


class TestHydraTemplates:
    """Tests 10-12: Config templates CRUD."""

    def test_template_lifecycle(self, api, project_id, unique_name):
        """Create, list, load, delete a config template."""
        # Save
        r = api.post(f"/api/hydra/templates/{project_id}", json={
            "name": unique_name,
            "config": {"training": {"epochs": 99}},
        })
        assert r.status_code == 200

        # List
        r2 = api.get(f"/api/hydra/templates/{project_id}")
        assert r2.status_code == 200
        templates = r2.json().get("templates", [])
        assert unique_name in [t.get("name") for t in templates]

        # Load
        r3 = api.get(f"/api/hydra/templates/{project_id}/{unique_name}")
        assert r3.status_code == 200

        # Delete
        r4 = api.delete(f"/api/hydra/templates/{project_id}/{unique_name}")
        assert r4.status_code == 200

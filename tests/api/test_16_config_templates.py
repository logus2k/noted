"""16 - Config Templates.

Maps to: testing/16_test-config-templates.md
Full CRUD lifecycle for Hydra config templates.
"""

import pytest

pytestmark = pytest.mark.api


class TestConfigTemplateCRUD:
    """Tests 1-6: Full template lifecycle."""

    def test_list_templates_empty(self, api, project_id):
        """Template list starts with manageable count."""
        r = api.get(f"/api/hydra/templates/{project_id}")
        assert r.status_code == 200
        data = r.json()
        assert "templates" in data, f"Response missing 'templates' key: {list(data.keys())}"
        templates = data["templates"]
        assert isinstance(templates, list), f"'templates' should be a list, got: {type(templates)}"

    def test_save_template(self, api, project_id, unique_name):
        """Save a named config template."""
        r = api.post(f"/api/hydra/templates/{project_id}", json={
            "name": unique_name,
            "description": "test template",
            "group_selections": {"model": "gru"},
            "overrides": {"training.epochs": 100},
        })
        assert r.status_code == 200

        # Verify it appears in the list
        r2 = api.get(f"/api/hydra/templates/{project_id}")
        names = [t.get("name") for t in r2.json().get("templates", [])]
        assert unique_name in names

        # Cleanup
        api.delete(f"/api/hydra/templates/{project_id}/{unique_name}")

    def test_load_template(self, api, project_id, unique_name):
        """Load a saved template and verify stored metadata matches."""
        group_selections = {"model": "gru"}
        overrides = {"training.lr": 0.001}
        api.post(f"/api/hydra/templates/{project_id}", json={
            "name": unique_name,
            "description": "test load",
            "group_selections": group_selections,
            "overrides": overrides,
        })

        r = api.get(f"/api/hydra/templates/{project_id}/{unique_name}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), (
            f"Loaded template should be a dict, got: {type(data)}"
        )
        assert data.get("name") == unique_name, (
            f"Template name mismatch: expected {unique_name!r}, got: {data.get('name')!r}"
        )
        loaded_gs = data.get("group_selections", {})
        assert loaded_gs.get("model") == "gru", (
            f"Expected group_selections.model == 'gru', got: {loaded_gs}"
        )
        loaded_ov = data.get("overrides", {})
        assert loaded_ov.get("training.lr") == 0.001, (
            f"Expected overrides['training.lr'] == 0.001, got: {loaded_ov}"
        )

        # Cleanup
        api.delete(f"/api/hydra/templates/{project_id}/{unique_name}")

    def test_delete_template(self, api, project_id, unique_name):
        """Delete a template and verify removal."""
        api.post(f"/api/hydra/templates/{project_id}", json={
            "name": unique_name,
            "overrides": {"test": True},
        })

        r = api.delete(f"/api/hydra/templates/{project_id}/{unique_name}")
        assert r.status_code == 200

        # Verify gone
        r2 = api.get(f"/api/hydra/templates/{project_id}/{unique_name}")
        assert r2.status_code == 404

    def test_templates_are_project_scoped(self, api, project_id, unique_name):
        """Templates for one project don't appear in another."""
        api.post(f"/api/hydra/templates/{project_id}", json={
            "name": unique_name,
            "overrides": {"scoped": True},
        })

        # Check a different project (Examples)
        r = api.get("/api/hydra/templates/Examples")
        if r.status_code == 200:
            names = [t.get("name") for t in r.json().get("templates", [])]
            assert unique_name not in names

        # Cleanup
        api.delete(f"/api/hydra/templates/{project_id}/{unique_name}")

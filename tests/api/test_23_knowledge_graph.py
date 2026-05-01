"""23 - Knowledge Graph.

Maps to: testing/23_test-knowledge-graph.md
"""

import pytest

pytestmark = pytest.mark.api


class TestGraphEndpoints:
    """Knowledge Graph API (proxied to graph service)."""

    def test_full_graph(self, api, project_id):
        """Full graph endpoint returns entities and relationships."""
        r = api.get(f"/api/graph/graph/{project_id}")
        if r.status_code == 200:
            data = r.json()
            assert "entities" in data or "entity_count" in data
            if "entities" in data:
                entities = data["entities"]
                assert isinstance(entities, list), "entities must be a list"
                for entity in entities:
                    assert "id" in entity, f"Entity missing 'id' field: {entity}"
                    assert "type" in entity, f"Entity missing 'type' field: {entity}"
        else:
            # Graph service may not be running
            assert r.status_code in (502, 503, 504)

    def test_search(self, api, project_id):
        """Search endpoint responds."""
        r = api.get(f"/api/graph/search/{project_id}", params={"q": "test"})
        assert r.status_code in (200, 502, 503)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            assert isinstance(results, list), f"Search results must be a list, got: {type(results)}"

    def test_views(self, api):
        """Views endpoint lists perspective views."""
        r = api.get("/api/graph/views")
        if r.status_code == 200:
            data = r.json()
            views = data.get("views", [])
            assert isinstance(views, list)
            for view in views:
                assert "name" in view, f"View item missing 'name' field: {view}"

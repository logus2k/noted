"""10 - File Upload and Data Section.

Maps to: testing/10_test-file-upload.md and testing/10_test-data-section.md
"""

import pytest

pytestmark = pytest.mark.api


class TestFileBrowsing:
    """File listing and reading."""

    def test_list_project_files(self, api, project_id):
        """List files in the project root."""
        r = api.get(f"/api/files/project/{project_id}")
        assert r.status_code == 200
        entries = r.json()
        assert isinstance(entries, list)
        assert len(entries) > 0, "Project root should not be empty"
        # Every entry must have a 'name' key
        for entry in entries:
            assert "name" in entry, f"Entry missing 'name' key: {entry}"
        names = [e["name"] for e in entries]
        assert "config" in names, f"Expected 'config' dir in root listing, got: {names}"
        assert "data" in names, f"Expected 'data' dir in root listing, got: {names}"

    def test_list_subdirectory(self, api, project_id):
        """List files in a subdirectory."""
        r = api.get(f"/api/files/project/{project_id}",
                     params={"path": "config"})
        assert r.status_code == 200
        entries = r.json()
        names = [e.get("name") for e in entries]
        assert "config.yaml" in names

    def test_read_file(self, api, project_id):
        """Read a text file."""
        r = api.get(f"/api/files/project/{project_id}/read",
                     params={"path": "config/config.yaml"})
        assert r.status_code == 200
        data = r.json()
        assert "content" in data
        assert "defaults:" in data["content"]


class TestFileWriteAndDelete:
    """File CRUD operations."""

    def test_write_read_delete(self, api, project_id, unique_name):
        """Full lifecycle: write, read, delete."""
        path = f"_test_{unique_name}.txt"
        content = f"test content {unique_name}"

        # Write
        r = api.put(f"/api/files/project/{project_id}/write",
                     params={"path": path},
                     json={"content": content})
        assert r.status_code == 200

        # Read
        r2 = api.get(f"/api/files/project/{project_id}/read",
                      params={"path": path})
        assert r2.status_code == 200
        assert r2.json()["content"] == content

        # Delete
        r3 = api.delete(f"/api/files/project/{project_id}",
                         params={"path": path})
        assert r3.status_code == 200

        # Verify deleted
        r4 = api.get(f"/api/files/project/{project_id}/read",
                      params={"path": path})
        assert r4.status_code == 404

    def test_create_directory(self, api, project_id, unique_name):
        """Create and delete a directory."""
        dir_path = f"_test_dir_{unique_name}"

        r = api.post(f"/api/files/project/{project_id}",
                      json={"path": dir_path, "is_dir": True})
        assert r.status_code == 200

        # Verify the created dir appears in the parent listing
        r_parent = api.get(f"/api/files/project/{project_id}")
        assert r_parent.status_code == 200
        parent_entries = r_parent.json()
        parent_names = [e.get("name") for e in parent_entries]
        assert dir_path in parent_names or f"_test_dir_{unique_name}" in parent_names, (
            f"Created directory '{dir_path}' not found in parent listing: {parent_names}"
        )

        # List contents (should be empty or return 200)
        r2 = api.get(f"/api/files/project/{project_id}",
                      params={"path": dir_path})
        assert r2.status_code == 200

        # Delete
        api.delete(f"/api/files/project/{project_id}",
                    params={"path": dir_path})


class TestDataOverview:
    """Data section (DVC aggregated view)."""

    def test_data_overview(self, api):
        """Data overview endpoint returns DVC-tracked file info."""
        r = api.get("/api/dvc/data-overview")
        if r.status_code == 404:
            pytest.skip("Data overview endpoint not available")
        assert r.status_code == 200, f"Data overview endpoint failed: {r.status_code}"
        data = r.json()
        assert isinstance(data, (dict, list)), (
            f"Data overview must return a JSON object or list, got: {type(data)}"
        )

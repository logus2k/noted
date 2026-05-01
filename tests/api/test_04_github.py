"""04 - GitHub Integration (API contract).

Maps to: testing/04_test-github.md
Tests GitHub remote endpoints exist and respond correctly.
Does not require actual GitHub credentials - verifies API contracts.
"""

import pytest

pytestmark = pytest.mark.api

PROJECT_ID = "noted-testing"
REPO_PATH = "/app/data/projects/noted-testing"


class TestRemotes:
    """Test 1-3: Remote management endpoints."""

    def test_list_remotes(self, api):
        """GET remotes returns a list; each item has name and url fields."""
        r = api.get(f"/api/projects/{PROJECT_ID}/git/remotes")
        assert r.status_code == 200
        data = r.json()
        remotes = data if isinstance(data, list) else data.get("remotes", [])
        assert isinstance(remotes, list), "remotes must be a list"
        for remote in remotes:
            assert "name" in remote, f"Each remote must have a name field, got: {remote}"
            assert "url" in remote, f"Each remote must have a url field, got: {remote}"

    def test_add_remote_validation(self, api):
        """POST remote with missing url responds without 500."""
        r = api.post("/api/git/repo/remotes", json={
            "repo_path": REPO_PATH,
        })
        # Should not crash - may return 200 (no-op) or 4xx
        assert r.status_code < 500

    def test_add_remote_contract(self, api):
        """POST remote with valid data responds."""
        r = api.post("/api/git/repo/remotes", json={
            "repo_path": REPO_PATH,
            "name": "_test_remote",
            "url": "https://github.com/example/nonexistent.git",
        })
        # May succeed (200) or conflict (409) if already exists
        assert r.status_code in (200, 201, 409, 422)
        # Cleanup: remove the test remote
        api.delete(f"/api/projects/{PROJECT_ID}/git/remotes",
                    params={"name": "_test_remote"})


class TestPushPull:
    """Test 4-6: Push/pull endpoints contract."""

    def test_push_no_remote_fails_gracefully(self, api):
        """Push without valid remote returns 4xx client error, not 500."""
        r = api.post("/api/git/repo/push", json={
            "repo_path": REPO_PATH,
            "remote": "_nonexistent_remote",
            "branch": "main",
        })
        assert 400 <= r.status_code < 500, (
            f"Expected 4xx for unknown remote, got {r.status_code}"
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        error_text = data.get("error") or data.get("message") or data.get("detail") or r.text
        assert error_text, "Error response must contain a meaningful error message"

    def test_pull_no_remote_fails_gracefully(self, api):
        """Pull without valid remote returns 4xx client error, not crash."""
        r = api.post("/api/git/repo/pull", json={
            "repo_path": REPO_PATH,
            "remote": "_nonexistent_remote",
            "branch": "main",
        })
        assert 400 <= r.status_code < 500, (
            f"Expected 4xx for unknown remote, got {r.status_code}"
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        error_text = data.get("error") or data.get("message") or data.get("detail") or r.text
        assert error_text, "Error response must contain a meaningful error message"

    def test_remote_branches_endpoint(self, api):
        """Remote branches endpoint returns a structured response."""
        r = api.post("/api/git/repo/remote-branches", json={
            "repo_path": REPO_PATH,
        })
        # May fail (no remote configured) but endpoint must exist
        assert r.status_code != 404, "remote-branches endpoint must exist"
        # If successful, verify response has branches key
        if r.status_code == 200:
            data = r.json()
            assert "branches" in data or isinstance(data, list), (
                "remote-branches response must contain branches key or be a list"
            )

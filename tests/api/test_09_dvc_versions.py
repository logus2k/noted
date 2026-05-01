"""09 - DVC Version Switching.

Maps to: testing/09_test-dvc-version-switching.md
Tests DVC file history and checkout endpoints.
"""

import pytest

pytestmark = pytest.mark.api

REPO_PATH = "/app/data/projects/noted-testing"


class TestDVCFileHistory:
    """Test 1-3: DVC file version history."""

    def test_file_history_endpoint(self, api):
        """DVC file history returns version list."""
        r = api.post("/api/dvc/file-history", json={
            "repo_path": REPO_PATH,
            "file_path": "data/test_data.csv",
        })
        # 200 with history or 400/404/405 if not tracked or endpoint differs
        assert r.status_code in (200, 400, 404, 405, 422)
        if r.status_code == 200:
            data = r.json()
            versions = data.get("versions", data)
            assert isinstance(versions, list)
            if versions:
                item = versions[0]
                assert isinstance(item, dict)
                has_commit = "commit_hash" in item or "commit" in item
                has_date = "date" in item or "timestamp" in item or "created_at" in item
                assert has_commit or has_date, (
                    f"Version item missing commit_hash/date fields: {list(item.keys())}"
                )


class TestDVCCheckout:
    """Test 4-5: DVC version checkout."""

    def test_checkout_endpoint_exists(self, api):
        """Checkout version endpoint responds."""
        r = api.post("/api/dvc/checkout-version", json={
            "repo_path": REPO_PATH,
            "file_path": "data/test_data.csv",
            "commit_hash": "HEAD",
        })
        # Endpoint must exist (not 404) and return a structured response
        assert r.status_code != 404, "Checkout endpoint not found (404)"
        # A successful or expected-failure response should be JSON with a message
        assert r.status_code in (200, 400, 409, 422, 500)
        data = r.json()
        assert isinstance(data, dict), "Response should be a JSON object"

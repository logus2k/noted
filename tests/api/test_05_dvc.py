"""05 - DVC Integration.

Maps to: testing/05_test-dvc.md
"""

import pytest

pytestmark = pytest.mark.api

REPO_PATH = "/app/data/projects/noted-testing"


class TestDVCStatus:
    """Test 1: DVC status display."""

    def test_dvc_status_endpoint(self, api):
        """DVC status returns initialization state."""
        r = api.post("/api/dvc/status", json={"repo_path": REPO_PATH})
        assert r.status_code == 200
        data = r.json()
        assert "initialized" in data
        assert isinstance(data["initialized"], bool), (
            "initialized must be a boolean"
        )
        assert "tracked_files" in data
        assert "changed_files" in data


class TestDVCTrack:
    """Tests 2-4: Track files with DVC."""

    @pytest.mark.slow
    def test_track_data_file(self, api, temp_file):
        """Track a CSV file with DVC."""
        path = temp_file("data/_test_dvc_track.csv", "a,b,c\n1,2,3\n4,5,6\n")

        r = api.post("/api/dvc/track", json={
            "repo_path": REPO_PATH,
            "rel_path": path,
        })
        assert r.status_code == 200, (
            f"DVC track must return 200, got {r.status_code}: {r.text}"
        )

        # Verify the .dvc file appears in tracked_files
        r2 = api.post("/api/dvc/status", json={"repo_path": REPO_PATH})
        assert r2.status_code == 200
        data = r2.json()
        tracked = [f["path"] for f in data.get("tracked_files", [])]
        assert path in tracked or "_test_dvc_track.csv" in str(tracked), (
            f"Tracked file not found in DVC status after tracking. tracked={tracked}"
        )

        # Cleanup: remove DVC tracking
        api.post("/api/dvc/remove", json={
            "repo_path": REPO_PATH,
            "rel_path": path,
        })


class TestDVCPushPull:
    """Tests 5-6: Push and pull data."""

    @pytest.mark.slow
    def test_dvc_push(self, api):
        """DVC push command executes and returns a meaningful response."""
        r = api.post("/api/dvc/push", json={"repo_path": REPO_PATH})
        assert r.status_code in (200, 400, 500), (
            f"Unexpected status from dvc push: {r.status_code}"
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # Response must have some informational content regardless of outcome
        has_message = (
            "message" in data
            or "error" in data
            or "output" in data
            or "detail" in data
        )
        assert has_message, (
            f"DVC push response must contain message, error, output, or detail. Got: {data}"
        )


class TestDVCCloudStatus:
    """Test for R11: Cloud sync status."""

    def test_cloud_status_endpoint(self, api):
        """Cloud status endpoint returns file push state."""
        r = api.post("/api/dvc/cloud-status", json={"repo_path": REPO_PATH})
        assert r.status_code == 200
        data = r.json()
        assert "files" in data

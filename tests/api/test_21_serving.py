"""21 - Model Serving.

Maps to: testing/21_test-model-serving.md
"""

import pytest

pytestmark = pytest.mark.api


class TestServingHealth:
    """Serving container health check."""

    def test_serving_health(self, api):
        """Serving health endpoint responds."""
        r = api.get("/api/serving/health")
        # 200 = serving up (may be idle or ready)
        # 503 = serving container unreachable
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert "status" in data
            assert data["status"] in ("idle", "loading", "ready", "error", "healthy"), (
                f"Unexpected serving status: {data['status']!r}"
            )

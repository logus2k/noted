"""14 - Config Hash Injection.

Maps to: testing/14_test-config-hash-injection.md
API-testable: Verify compose hash generation.
Kernel injection tested via E2E.
"""

import pytest

pytestmark = pytest.mark.api


class TestConfigHash:
    """Config hash is deterministic and consistent."""

    def test_hash_deterministic(self, api, project_id):
        """Same config produces same hash."""
        body = {"project_id": project_id, "group_selections": {"model": "gru"}}
        r1 = api.post("/api/hydra/compose", json=body)
        r2 = api.post("/api/hydra/compose", json=body)
        assert r1.status_code == 200
        assert r1.json()["hash"] == r2.json()["hash"]

    def test_different_config_different_hash(self, api, project_id):
        """Different configs produce different hashes."""
        r1 = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "gru"},
        })
        r2 = api.post("/api/hydra/compose", json={
            "project_id": project_id,
            "group_selections": {"model": "linear"},
        })
        assert r1.json()["hash"] != r2.json()["hash"]

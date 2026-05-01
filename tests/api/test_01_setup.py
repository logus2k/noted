"""01 - Environment Setup: Verify services are running and reachable.

Maps to: testing/01_test-setup.md
"""

import pytest

pytestmark = pytest.mark.api


class TestServiceConnectivity:
    """Test 1-2: Core services are up and noted loads."""

    def test_noted_reachable(self, api):
        """noted backend responds to requests."""
        r = api.get("/api/files/")
        assert r.status_code == 200
        # Endpoint may return a list, dict, or HTML - just verify it responds
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            data = r.json()
            assert data is not None, "Expected a non-null JSON response from /api/files/"
        else:
            assert len(r.text) > 0, "Expected non-empty response from /api/files/"

    def test_noted_serves_frontend(self, api):
        """Frontend index.html is served."""
        r = api.get("/")
        assert r.status_code == 200
        text = r.text.lower()
        assert "noted" in text or ".js" in text, (
            "Expected 'noted' title or JS bundle reference in HTML"
        )


class TestMLflowAccess:
    """Test 3: MLflow is accessible through noted."""

    def test_mlflow_experiments_endpoint(self, api):
        """MLflow experiments API returns data."""
        r = api.get("/api/mlflow/experiments")
        assert r.status_code == 200
        data = r.json()
        assert "experiments" in data
        experiments = data["experiments"]
        assert isinstance(experiments, list), "experiments must be a list"
        assert len(experiments) > 0, "Expected at least one MLflow experiment"
        first = experiments[0]
        assert "experiment_id" in first, "Each experiment must have experiment_id"
        assert "name" in first, "Each experiment must have name"


class TestAirflowAccess:
    """Test 4: Airflow is accessible through noted."""

    def test_airflow_health(self, api):
        """Airflow health check returns OK."""
        r = api.get("/api/airflow/health")
        assert r.status_code == 200
        data = r.json()
        assert "healthy" in data, "Airflow health response must have a 'healthy' field"
        assert data["healthy"] is True, (
            f"Airflow health check returned healthy=False: {data}"
        )

    def test_airflow_dags_list(self, api):
        """Airflow DAGs can be listed."""
        r = api.get("/api/airflow/dags")
        assert r.status_code == 200
        data = r.json()
        assert "dags" in data
        assert isinstance(data["dags"], list), "dags field must be a list"


class TestMinIOAccess:
    """Test 5: MinIO storage is accessible."""

    def test_minio_buckets(self, api):
        """MinIO bucket listing works."""
        r = api.get("/api/minio/buckets")
        assert r.status_code == 200
        data = r.json()
        buckets = data.get("buckets", data) if isinstance(data, dict) else data
        assert isinstance(buckets, list), "buckets must be a list"
        bucket_names = [
            b.get("name", b) if isinstance(b, dict) else b for b in buckets
        ]
        expected = {"mlflow-artifacts", "noted-dvc"}
        found = expected & set(bucket_names)
        assert found, (
            f"Expected at least one of {expected} in MinIO buckets, got: {bucket_names}"
        )


class TestMountConfiguration:
    """Test 6: Mount configuration is readable."""

    def test_mounts_config(self, api):
        """Mounts config endpoint returns data."""
        r = api.get("/api/files/mounts/config")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), "Mounts config must be a dict"
        # Must have at least one top-level key (e.g. "mounts" or "projects")
        assert len(data) > 0, "Mounts config must not be empty"


class TestProjectAccess:
    """Test 7-8: Projects and noted-testing exist."""

    def test_project_listing(self, api):
        """Project file listing returns results and includes noted-testing."""
        r = api.get("/api/files/project/noted-testing")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), "Project listing must be a list"
        names = [e.get("name", e) if isinstance(e, dict) else e for e in data]
        # The endpoint returns files inside noted-testing, so a non-empty list
        # confirms the project exists and is mounted
        assert len(data) > 0, "noted-testing project must have at least one entry"

    def test_project_has_scaffold(self, api, project_id):
        """Scaffolded files exist in noted-testing."""
        r = api.get(f"/api/files/project/{project_id}")
        assert r.status_code == 200
        entries = r.json()
        names = [e.get("name", "") for e in entries]
        assert "config" in names
        assert "data" in names
        assert "test_notebook.ipynb" in names

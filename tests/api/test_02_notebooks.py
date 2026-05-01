"""02 - Notebooks, Environments and Kernels.

Maps to: testing/02_test-notebooks.md
API-testable parts: notebook CRUD, venv listing, file read/write.
Kernel execution requires Socket.IO (covered in E2E tests).
"""

import json
import pytest

pytestmark = pytest.mark.api


class TestNotebookCRUD:
    """Tests 1-2: Create and read notebooks."""

    def test_read_scaffold_notebook(self, api, project_id):
        """Read the scaffolded test notebook."""
        r = api.get(
            f"/api/files/project/{project_id}/read",
            params={"path": "test_notebook.ipynb"},
        )
        if r.status_code == 404:
            pytest.skip("Scaffold notebook not created yet")
        assert r.status_code == 200
        data = r.json()
        assert "content" in data
        content = data["content"]
        nb = json.loads(content) if isinstance(content, str) else content
        assert nb["nbformat"] == 4
        assert len(nb["cells"]) == 3

    def test_create_notebook(self, api, project_id, unique_name):
        """Create a new notebook file via API."""
        nb_name = f"{unique_name}.ipynb"
        notebook = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {},
            "cells": [{"cell_type": "code", "metadata": {}, "source": ["1+1"],
                        "outputs": [], "execution_count": None}],
        }
        r = api.put(
            f"/api/files/project/{project_id}/write",
            params={"path": nb_name},
            json={"content": json.dumps(notebook)},
        )
        assert r.status_code == 200

        # Read back and verify structure
        r2 = api.get(
            f"/api/files/project/{project_id}/read",
            params={"path": nb_name},
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert "content" in data2, "Read response must have content field"
        content = data2["content"]
        nb_back = json.loads(content) if isinstance(content, str) else content
        assert nb_back["nbformat"] == 4, "nbformat must be 4"
        assert isinstance(nb_back["cells"], list), "cells must be a list"
        assert len(nb_back["cells"]) == 1, "Expected exactly 1 cell as written"

        # Cleanup
        api.delete(f"/api/files/project/{project_id}", params={"path": nb_name})

    def test_notebook_save_preserves_cells(self, api, project_id, unique_name):
        """Write a notebook, read it back, verify cell content."""
        nb = {
            "nbformat": 4, "nbformat_minor": 5, "metadata": {},
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["print('saved')"],
                 "outputs": [], "execution_count": None},
                {"cell_type": "markdown", "metadata": {}, "source": ["# Heading"]},
            ],
        }
        path = f"{unique_name}_save.ipynb"
        api.put(
            f"/api/files/project/{project_id}/write",
            params={"path": path},
            json={"content": json.dumps(nb)},
        )
        r = api.get(
            f"/api/files/project/{project_id}/read",
            params={"path": path},
        )
        content = r.json()["content"]
        loaded = json.loads(content) if isinstance(content, str) else content
        assert len(loaded["cells"]) == 2
        assert loaded["cells"][0]["source"] == ["print('saved')"]
        assert loaded["cells"][1]["cell_type"] == "markdown"

        api.delete(f"/api/files/project/{project_id}", params={"path": path})


class TestVirtualEnvironments:
    """Tests 3-4: Venv listing."""

    def test_list_runtimes(self, api):
        """Runtime listing returns available Python versions."""
        r = api.get("/api/runtimes")
        assert r.status_code == 200
        runtimes = r.json()
        assert isinstance(runtimes, list), "runtimes must be a list"
        assert len(runtimes) > 0, "Expected at least one runtime"
        first = runtimes[0]
        assert "runtime_id" in first, "Each runtime must have runtime_id"
        assert "language" in first, "Each runtime must have language"

    def test_list_venvs(self, api):
        """Venv listing returns (possibly empty) list."""
        r = api.get("/api/venvs")
        assert r.status_code == 200
        venvs = r.json()
        assert isinstance(venvs, list), "venvs must be a list"
        for venv in venvs:
            assert "name" in venv, f"Each venv must have a name field, got: {venv}"

import os
import json
import shutil
import uuid
import hashlib
from typing import Optional
from app.config import PROJECTS_DIR
from app.managers.project_registry import get_registry


class NotebookManager:
    """Handles CRUD operations for .ipynb files on disk."""

    def _project_root(self, project_id: str) -> str:
        return get_registry().resolve(project_id)

    def _notebook_path(self, project_id: str, notebook_name: str) -> str:
        base = self._project_root(project_id)
        path = os.path.realpath(os.path.join(base, notebook_name))
        if not path.startswith(os.path.realpath(base)):
            raise ValueError("Invalid notebook path")
        return path

    def _validate_notebook_name(self, name: str) -> str:
        if ".." in name or "\\" in name:
            raise ValueError("Invalid notebook name")
        if not name.endswith(".ipynb"):
            name += ".ipynb"
        return name

    def _empty_notebook(self, name: str) -> dict:
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {
                    "name": "python",
                    "version": "3.10.0"
                },
                "venv_ref": {
                    "type": "project",
                    "name": "default"
                }
            },
            "cells": [
                {
                    "cell_type": "code",
                    "id": str(uuid.uuid4())[:8],
                    "metadata": {},
                    "source": [],
                    "outputs": [],
                    "execution_count": None
                }
            ]
        }

    def ensure_welcome_notebook(self) -> tuple[str, str]:
        """Create the Welcome project and notebook if they don't exist.
        Returns (project_id, notebook_name)."""
        project_id = "Examples"
        notebook_name = "Welcome.ipynb"
        project_path = os.path.join(PROJECTS_DIR, project_id)
        notebooks_dir = os.path.join(project_path, "notebooks")
        filepath = os.path.join(notebooks_dir, notebook_name)

        if os.path.exists(filepath):
            return project_id, notebook_name

        os.makedirs(notebooks_dir, exist_ok=True)
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {"name": "python"}
            },
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": str(uuid.uuid4())[:8],
                    "metadata": {},
                    "source": [
                        "# Welcome to Note!\n",
                        "\n",
                        "Write Python in a **code cell** and press `Shift + Enter` to run it.  \n",
                        "Use the toolbar icons to **open** a project, **save**, or manage **environments**.\n",
                        "\n",
                        "| Shortcut | Action |\n",
                        "| --- | --- |\n",
                        "| `Shift + Enter` | Run cell and advance |\n",
                        "| `Ctrl + Enter` | Run cell (stay) |\n",
                        "| `Ctrl + S` | Save notebook |"
                    ]
                },
                {
                    "cell_type": "code",
                    "id": str(uuid.uuid4())[:8],
                    "metadata": {},
                    "source": [
                        "# Libraries available in the Default environment\n",
                        "import numpy as np\n",
                        "import pandas as pd\n",
                        "import matplotlib.pyplot as plt\n",
                        "import seaborn as sns\n",
                        "import sklearn\n",
                        "import scipy\n",
                        "import plotly\n",
                        "import statsmodels\n",
                        "from PIL import Image\n",
                        "\n",
                        "print(f\"NumPy {np.__version__}, Pandas {pd.__version__}, \"\n",
                        "      f\"Matplotlib {plt.matplotlib.__version__}, Seaborn {sns.__version__}\")"
                    ],
                    "outputs": [],
                    "execution_count": None
                },
                {
                    "cell_type": "code",
                    "id": str(uuid.uuid4())[:8],
                    "metadata": {},
                    "source": [
                        "# Quick example: Fibonacci with NumPy\n",
                        "import math\n",
                        "\n",
                        "phi = (1 + math.sqrt(5)) / 2\n",
                        "print(f\"The golden ratio is {phi:.6f}\")\n",
                        "\n",
                        "fib = [0, 1]\n",
                        "for _ in range(8):\n",
                        "    fib.append(fib[-1] + fib[-2])\n",
                        "print(f\"Fibonacci: {fib}\")"
                    ],
                    "outputs": [],
                    "execution_count": None
                }
            ]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=2)
        return project_id, notebook_name

    def list_projects(self) -> list[dict]:
        # Pull from ProjectRegistry so MOUNTS surface alongside internal
        # projects. Otherwise the Assistant only sees data/projects/* and
        # has no way to know mounts like jena_weather are valid project_ids;
        # tool calls against mounts fail with "Project not found" and the
        # model spirals (per session 2026-04-25). The registry already
        # unifies internal + mount resolution.
        from app.managers.project_registry import get_registry
        projects = []
        for entry in get_registry().list_projects():
            name = entry.get("name", "")
            if not name:
                continue
            projects.append({
                "id": name,
                "notebooks_count": len(self.list_notebooks(name)),
                "source": entry.get("source", "internal"),
            })
        return projects

    def create_project(self, project_id: str) -> dict:
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project ID")
        project_path = os.path.join(PROJECTS_DIR, project_id)
        os.makedirs(project_path, exist_ok=True)
        # Refresh the registry so the new project is immediately
        # resolvable by notebook:open and other handlers
        from app.managers.project_registry import get_registry
        get_registry().refresh()
        return {"id": project_id}

    def list_notebooks(self, project_id: str) -> list[dict]:
        root = self._project_root(project_id)
        if not os.path.exists(root):
            return []
        notebooks = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in sorted(filenames):
                if name.endswith(".ipynb"):
                    filepath = os.path.join(dirpath, name)
                    rel = os.path.relpath(filepath, root)
                    stat = os.stat(filepath)
                    notebooks.append({
                        "name": rel,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
        notebooks.sort(key=lambda n: n["name"])
        return notebooks

    def notebook_summary(self, project_id: str, notebook_name: str) -> dict:
        notebook_name = self._validate_notebook_name(
            notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Notebook not found: {notebook_name}")
        stat = os.stat(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                nb = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"name": notebook_name, "size": stat.st_size,
                    "modified": stat.st_mtime, "error": "Could not parse notebook"}
        cells = nb.get("cells", [])
        code_cells = sum(1 for c in cells if c.get("cell_type") == "code")
        md_cells = sum(1 for c in cells if c.get("cell_type") == "markdown")
        metadata = nb.get("metadata", {})
        # Extract first markdown cell as description preview
        description = ""
        for c in cells:
            if c.get("cell_type") == "markdown":
                src = c.get("source", "")
                if isinstance(src, list):
                    src = "".join(src)
                description = src[:300]
                break
        return {
            "name": notebook_name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "cells_total": len(cells),
            "code_cells": code_cells,
            "markdown_cells": md_cells,
            "kernel": metadata.get("kernelspec", {}).get("display_name", ""),
            "language": metadata.get("language_info", {}).get("name", ""),
            "language_version": metadata.get("language_info", {}).get("version", ""),
            "description": description,
        }

    def get_notebook(self, project_id: str, notebook_name: str) -> dict:
        notebook_name = self._validate_notebook_name(
            notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Notebook not found: {notebook_name}")
        with open(filepath, "r", encoding="utf-8") as f:
            notebook = json.load(f)
        for cell in notebook.get("cells", []):
            if "id" not in cell:
                cell["id"] = str(uuid.uuid4())[:8]
        return notebook

    def prepare_for_wire(self, notebook: dict) -> dict:
        """Optimize notebook for sending over the wire:
        - Pre-join source arrays into strings
        """
        wire = dict(notebook)
        wire["cells"] = []
        for cell in notebook.get("cells", []):
            c = dict(cell)
            src = c.get("source", "")
            if isinstance(src, list):
                c["source"] = "".join(src)
            wire["cells"].append(c)
        return wire

    def create_notebook(self, project_id: str, notebook_name: str,
                        content: Optional[dict] = None) -> dict:
        notebook_name = self._validate_notebook_name(notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if os.path.exists(filepath):
            raise FileExistsError(f"Notebook already exists: {notebook_name}")
        notebook = content if content else self._empty_notebook(notebook_name)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=2)

        return {"name": notebook_name, "created": True}

    def update_notebook(self, project_id: str, notebook_name: str,
                        content: dict) -> dict:
        notebook_name = self._validate_notebook_name(
            notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Notebook not found: {notebook_name}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
        return {"name": notebook_name, "updated": True}

    def delete_notebook(self, project_id: str, notebook_name: str) -> dict:
        notebook_name = self._validate_notebook_name(notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Notebook not found: {notebook_name}")
        os.remove(filepath)
        return {"name": notebook_name, "deleted": True}

    def delete_project(self, project_id: str) -> dict:
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project ID")
        project_path = os.path.join(PROJECTS_DIR, project_id)
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Project not found: {project_id}")
        shutil.rmtree(project_path)
        from app.managers.project_registry import get_registry
        get_registry().refresh()
        return {"id": project_id, "deleted": True}

    def rename_project(self, project_id: str, new_id: str) -> dict:
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project ID")
        if ".." in new_id or "/" in new_id or "\\" in new_id or not new_id.strip():
            raise ValueError("Invalid new project name")
        old_path = os.path.join(PROJECTS_DIR, project_id)
        new_path = os.path.join(PROJECTS_DIR, new_id)
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"Project not found: {project_id}")
        if os.path.exists(new_path):
            raise FileExistsError(f"Project already exists: {new_id}")
        os.rename(old_path, new_path)
        from app.managers.project_registry import get_registry
        get_registry().refresh()
        return {"old_id": project_id, "new_id": new_id, "renamed": True}

    def rename_notebook(self, project_id: str, notebook_name: str,
                        new_name: str) -> dict:
        notebook_name = self._validate_notebook_name(notebook_name)
        new_name = self._validate_notebook_name(new_name)
        old_path = self._notebook_path(project_id, notebook_name)
        new_path = self._notebook_path(project_id, new_name)
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"Notebook not found: {notebook_name}")
        if os.path.exists(new_path):
            raise FileExistsError(f"Notebook already exists: {new_name}")
        os.rename(old_path, new_path)
        return {"old_name": notebook_name, "new_name": new_name, "renamed": True}

    def get_notebook_hash(self, project_id: str, notebook_name: str) -> str:
        notebook_name = self._validate_notebook_name(notebook_name)
        filepath = self._notebook_path(project_id, notebook_name)
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

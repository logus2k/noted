"""ProjectRegistry - unified project path resolution.

Scans data/projects/ and NOTED.md mounts on startup to build a single
registry of all projects. Every project has a name and a filesystem path.
No __mount__: prefix - just project names.
"""

import os
import logging

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'projects')
MOUNTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'mounts')
NOTED_MD_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'NOTED.md')

# Legacy prefix - accepted during transition, stripped on input
LEGACY_MOUNT_PREFIX = "__mount__:"


class ProjectRegistry:
    """Unified registry of all projects (internal + mounted)."""

    def __init__(self):
        self._projects = {}  # name -> {"path": str, "source": "internal"|"mount", "host_path": str|None}
        self.refresh()

    def refresh(self):
        """Re-scan all project sources."""
        self._projects.clear()

        # 1. Internal projects from data/projects/
        projects_dir = os.path.abspath(PROJECTS_DIR)
        if os.path.isdir(projects_dir):
            for entry in sorted(os.listdir(projects_dir)):
                entry_path = os.path.join(projects_dir, entry)
                if os.path.isdir(entry_path) and not entry.startswith('.'):
                    self._projects[entry] = {
                        "path": entry_path,
                        "source": "internal",
                        "host_path": None,
                    }

        # 2. Mounted projects from NOTED.md
        mounts = self._parse_noted_md()
        mounts_dir = os.path.abspath(MOUNTS_DIR)
        for mount in mounts:
            name = mount.get("name", "")
            host_path = mount.get("host_path", "")
            if not name:
                continue
            mount_path = os.path.join(mounts_dir, name)
            if os.path.isdir(mount_path):
                self._projects[name] = {
                    "path": mount_path,
                    "source": "mount",
                    "host_path": host_path,
                }
            else:
                logger.warning("Mount directory not found: %s (host: %s)", mount_path, host_path)

        logger.info("ProjectRegistry: %d projects (%d internal, %d mounts)",
                     len(self._projects),
                     sum(1 for p in self._projects.values() if p["source"] == "internal"),
                     sum(1 for p in self._projects.values() if p["source"] == "mount"))

    def _parse_noted_md(self):
        """Parse mounts from NOTED.md YAML frontmatter."""
        noted_path = os.path.abspath(NOTED_MD_PATH)
        if not os.path.isfile(noted_path):
            return []

        try:
            with open(noted_path, 'r') as f:
                content = f.read()

            # Parse YAML frontmatter between --- markers
            import re
            match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            if not match:
                return []

            import yaml
            data = yaml.safe_load(match.group(1))
            return data.get("mounts", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning("Failed to parse NOTED.md: %s", e)
            return []

    def resolve(self, project_id: str) -> str:
        """Resolve project ID to filesystem path.

        Accepts both clean names ("jena_weather") and legacy prefixed
        names ("__mount__:jena_weather") for backwards compatibility.

        Returns absolute filesystem path.
        Raises FileNotFoundError if project not found.
        """
        # Strip legacy prefix
        clean_id = self._clean_id(project_id)

        info = self._projects.get(clean_id)
        if info:
            return info["path"]

        raise FileNotFoundError(f"Project not found: {clean_id}")

    def exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        clean_id = self._clean_id(project_id)
        return clean_id in self._projects

    def get_info(self, project_id: str) -> dict:
        """Get project metadata (path, source, host_path)."""
        clean_id = self._clean_id(project_id)
        info = self._projects.get(clean_id)
        if not info:
            return None
        return {"name": clean_id, **info}

    def list_projects(self) -> list:
        """Return all projects with metadata."""
        return [
            {"name": name, **info}
            for name, info in sorted(self._projects.items())
        ]

    def is_internal(self, project_id: str) -> bool:
        """True if project is in data/projects/ (not a mount)."""
        clean_id = self._clean_id(project_id)
        info = self._projects.get(clean_id)
        return info["source"] == "internal" if info else False

    def is_mount(self, project_id: str) -> bool:
        """True if project is a host directory mount."""
        clean_id = self._clean_id(project_id)
        info = self._projects.get(clean_id)
        return info["source"] == "mount" if info else False

    def clean_id(self, project_id: str) -> str:
        """Strip legacy __mount__: prefix if present. Public API."""
        return self._clean_id(project_id)

    def _clean_id(self, project_id: str) -> str:
        """Strip legacy __mount__: prefix if present."""
        if project_id and project_id.startswith(LEGACY_MOUNT_PREFIX):
            return project_id[len(LEGACY_MOUNT_PREFIX):]
        return project_id or ""

    def create_project(self, name: str) -> dict:
        """Create a new internal project directory."""
        if name in self._projects:
            raise FileExistsError(f"Project already exists: {name}")
        path = os.path.join(os.path.abspath(PROJECTS_DIR), name)
        os.makedirs(path, exist_ok=True)
        self._projects[name] = {
            "path": path,
            "source": "internal",
            "host_path": None,
        }
        return self.get_info(name)

    def delete_project(self, name: str) -> bool:
        """Delete an internal project. Cannot delete mounts."""
        info = self._projects.get(name)
        if not info:
            raise FileNotFoundError(f"Project not found: {name}")
        if info["source"] != "internal":
            raise PermissionError(f"Cannot delete mounted project: {name}")
        import shutil
        shutil.rmtree(info["path"], ignore_errors=True)
        del self._projects[name]
        return True


# Module-level singleton
_registry = None


def get_registry() -> ProjectRegistry:
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry

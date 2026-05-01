"""Project-level settings stored in .noted/settings.json within project or mount dirs."""

import json
import os

from app.config import PROJECTS_DIR, MOUNTS_DIR

DEFAULTS = {
}

SETTINGS_DIR = ".noted"
SETTINGS_FILE = "settings.json"


def _resolve_dir(project_id: str) -> str | None:
    """Resolve project_id to filesystem directory path."""
    from app.managers.project_registry import get_registry
    try:
        return get_registry().resolve(project_id)
    except FileNotFoundError:
        return None


def get_settings(project_id: str) -> dict:
    """Read project settings. Returns defaults if file missing."""
    project_dir = _resolve_dir(project_id)
    if not project_dir:
        return dict(DEFAULTS)

    path = os.path.join(project_dir, SETTINGS_DIR, SETTINGS_FILE)
    if not os.path.isfile(path):
        return dict(DEFAULTS)

    try:
        with open(path) as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULTS)


def update_settings(project_id: str, updates: dict) -> dict:
    """Merge updates into .noted/settings.json, creating dir if needed. Returns full settings."""
    project_dir = _resolve_dir(project_id)
    if not project_dir:
        raise FileNotFoundError(f"Project not found: {project_id}")

    noted_dir = os.path.join(project_dir, SETTINGS_DIR)
    os.makedirs(noted_dir, exist_ok=True)

    path = os.path.join(noted_dir, SETTINGS_FILE)
    current = {}
    if os.path.isfile(path):
        try:
            with open(path) as f:
                current = json.load(f)
        except Exception:
            current = {}

    current.update(updates)

    with open(path, "w") as f:
        json.dump(current, f, indent=2)

    merged = dict(DEFAULTS)
    merged.update(current)
    return merged

"""Per-tool venv / node_modules manager.

Phase A.3: lazy environment provisioning. The first call to
`ensure_python_venv(tool_dir)` builds `<tool_dir>/venv/` with `uv venv`
and installs `requirements.txt` (if present). Subsequent calls return
the cached interpreter path immediately. When `requirements.txt`
changes (mtime), the next call rebuilds.

A small marker file `<venv>/.req_mtime` persists the cache key on
disk so a container restart doesn't trigger a full rebuild.

Phase A.4 (executor) is the only consumer. The watcher in
`watcher.py` calls `invalidate(tool_dir)` so the next call rebuilds
without waiting for mtime comparison (saves a stat + handles the
edge case where the venv was built before the mtime update finished
flushing).

All operations here are blocking; callers in async context MUST wrap
with `asyncio.to_thread(...)`. uvicorn runs single-worker so blocking
the event loop on a 30-second `pip install` would freeze the whole
service.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from threading import RLock

logger = logging.getLogger(__name__)

# tool_dir (str) -> (interpreter_path, requirements_mtime)
_python_cache: dict[str, tuple[Path, float]] = {}
_node_cache: dict[str, float] = {}
_lock = RLock()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / "bin" / "python"


def _venv_marker(venv_dir: Path) -> Path:
    return venv_dir / ".req_mtime"


def _node_marker(tool_dir: Path) -> Path:
    return tool_dir / "node_modules" / ".req_mtime"


def _build_python_venv(tool_dir: Path, req_file: Path | None) -> Path:
    venv_dir = tool_dir / "venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    logger.info("uv venv create for %s", tool_dir.name)
    create = subprocess.run(
        ["uv", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        raise RuntimeError(
            f"uv venv failed for {tool_dir.name}: {create.stderr.strip() or create.stdout.strip()}"
        )
    py = _venv_python(venv_dir)
    if req_file and req_file.is_file():
        logger.info("uv pip install -r requirements.txt for %s", tool_dir.name)
        install = subprocess.run(
            ["uv", "pip", "install", "--python", str(py), "-r", str(req_file)],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            shutil.rmtree(venv_dir, ignore_errors=True)
            raise RuntimeError(
                f"uv pip install failed for {tool_dir.name}: "
                f"{install.stderr.strip() or install.stdout.strip()}"
            )
    mtime = _mtime(req_file) if req_file else 0.0
    _venv_marker(venv_dir).write_text(str(mtime))
    return py


def ensure_python_venv(tool_dir: Path) -> Path:
    """Build (or reuse) the venv for a python tool. Returns interpreter path."""
    req_file = tool_dir / "requirements.txt"
    venv_dir = tool_dir / "venv"
    cur_mtime = _mtime(req_file)
    key = str(tool_dir)

    with _lock:
        cached = _python_cache.get(key)
        if cached:
            cached_py, cached_mtime = cached
            if cached_mtime == cur_mtime and cached_py.is_file():
                return cached_py

        if venv_dir.is_dir() and _venv_python(venv_dir).is_file():
            marker = _venv_marker(venv_dir)
            if marker.is_file():
                try:
                    saved_mtime = float(marker.read_text().strip())
                    if saved_mtime == cur_mtime:
                        py = _venv_python(venv_dir)
                        _python_cache[key] = (py, cur_mtime)
                        return py
                except (OSError, ValueError):
                    pass

        py = _build_python_venv(tool_dir, req_file)
        _python_cache[key] = (py, cur_mtime)
        return py


def _build_node_modules(tool_dir: Path, pkg_file: Path) -> None:
    node_modules = tool_dir / "node_modules"
    if node_modules.exists():
        shutil.rmtree(node_modules)
    logger.info("npm install for %s", tool_dir.name)
    result = subprocess.run(
        ["npm", "install", "--prefix", str(tool_dir), "--no-audit", "--no-fund"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"npm install failed for {tool_dir.name}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    _node_marker(tool_dir).write_text(str(_mtime(pkg_file)))


def ensure_node_modules(tool_dir: Path) -> None:
    """Build (or reuse) node_modules for a javascript tool."""
    pkg_file = tool_dir / "package.json"
    if not pkg_file.is_file():
        return
    cur_mtime = _mtime(pkg_file)
    key = str(tool_dir)
    with _lock:
        cached_mtime = _node_cache.get(key)
        node_modules = tool_dir / "node_modules"
        if cached_mtime == cur_mtime and node_modules.is_dir():
            return
        marker = _node_marker(tool_dir)
        if marker.is_file() and node_modules.is_dir():
            try:
                saved_mtime = float(marker.read_text().strip())
                if saved_mtime == cur_mtime:
                    _node_cache[key] = cur_mtime
                    return
            except (OSError, ValueError):
                pass
        _build_node_modules(tool_dir, pkg_file)
        _node_cache[key] = cur_mtime


def invalidate(tool_dir: Path) -> None:
    """Drop in-memory cache for a tool. Next ensure_*() call re-checks disk."""
    key = str(tool_dir)
    with _lock:
        _python_cache.pop(key, None)
        _node_cache.pop(key, None)

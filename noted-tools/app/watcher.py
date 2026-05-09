"""File watcher for `data/user_tools/`.

Watches the user-tools root recursively. On any change inside a tool
directory `<root>/<name>/`, re-parses `tool.json`, locates the
`tool.py` or `tool.js` implementation, and atomically swaps the
ToolRegistry entry. On directory deletion or removal of `tool.json`,
unloads the entry.

Phase A.2 scope: registry sync only. Schema is parsed structurally
(name + input_schema dict + impl file present); strict JSON Schema
validation of inputs is enforced at execution time in Phase A.4.

Directories whose name starts with `_` are skipped (reserved for
`_archive/` and similar internal use).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Iterable

from watchfiles import awatch

from . import venv_manager
from .registry import ToolEntry, get_registry

logger = logging.getLogger(__name__)


def _load_tool_dir(tool_dir: Path) -> ToolEntry | None:
    tool_json = tool_dir / "tool.json"
    if not tool_json.is_file():
        return None
    try:
        data = json.loads(tool_json.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("invalid tool.json at %s: %s", tool_json, e)
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name:
        logger.warning("tool.json at %s missing 'name'", tool_json)
        return None
    description = data.get("description") or ""
    input_schema = data.get("input_schema") or {}
    if not isinstance(input_schema, dict):
        logger.warning("tool.json at %s 'input_schema' is not an object", tool_json)
        return None
    if (tool_dir / "tool.py").is_file():
        language = "python"
    elif (tool_dir / "tool.js").is_file():
        language = "javascript"
    else:
        logger.warning("tool dir %s has no tool.py or tool.js (yet?)", tool_dir)
        return None
    return ToolEntry(
        name=name,
        description=description,
        input_schema=input_schema,
        language=language,
        tool_dir=str(tool_dir),
        meta=data.get("_meta") or {},
    )


def _is_skip_dir(p: Path) -> bool:
    return p.name.startswith("_") or p.name.startswith(".")


def initial_scan(root: Path) -> int:
    if not root.is_dir():
        return 0
    registry = get_registry()
    count = 0
    for child in root.iterdir():
        if not child.is_dir() or _is_skip_dir(child):
            continue
        entry = _load_tool_dir(child)
        if entry:
            registry.upsert(entry)
            count += 1
    return count


def _resolve_tool_dirs(changed: Iterable[tuple], root: Path) -> tuple[set[Path], set[Path]]:
    """Returns (tool_dirs_with_any_change, tool_dirs_with_dep_change).

    Dep-change set is a subset where requirements.txt or package.json changed —
    callers use it to invalidate cached venvs / node_modules.
    """
    affected: set[Path] = set()
    dep_changed: set[Path] = set()
    for _change, path_str in changed:
        path = Path(path_str)
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if not parts:
            continue
        first = parts[0]
        if first.startswith("_") or first.startswith("."):
            continue
        # Ignore changes inside per-tool environment dirs — those are
        # produced by venv builds and would re-fire the watcher uselessly.
        if len(parts) >= 2 and parts[1] in ("venv", "node_modules", "__pycache__"):
            continue
        tool_dir = root / first
        affected.add(tool_dir)
        if path.name in ("requirements.txt", "package.json"):
            dep_changed.add(tool_dir)
    return affected, dep_changed


def _sync_tool_dir(tool_dir: Path) -> None:
    registry = get_registry()
    if tool_dir.is_dir() and (tool_dir / "tool.json").is_file():
        entry = _load_tool_dir(tool_dir)
        if entry is None:
            return
        prior = registry.get(entry.name)
        registry.upsert(entry)
        verb = "updated" if prior else "loaded"
        logger.info("tool %s: %s (%s)", verb, entry.name, entry.language)
        return
    # Tool dir gone or tool.json removed — drop any registry entry pointing here.
    target = str(tool_dir)
    for existing in registry.list_tools():
        if existing.tool_dir == target:
            registry.remove(existing.name)
            logger.info("tool unloaded: %s", existing.name)


async def watch_user_tools(root: Path, stop: asyncio.Event) -> None:
    logger.info("file watcher starting on %s", root)
    try:
        async for changes in awatch(str(root), recursive=True, stop_event=stop):
            affected, dep_changed = _resolve_tool_dirs(changes, root)
            for tool_dir in dep_changed:
                venv_manager.invalidate(tool_dir)
                logger.info("env cache invalidated: %s", tool_dir.name)
            for tool_dir in affected:
                _sync_tool_dir(tool_dir)
    except asyncio.CancelledError:
        logger.info("file watcher cancelled")
        raise
    except Exception:
        logger.exception("file watcher crashed")
        raise

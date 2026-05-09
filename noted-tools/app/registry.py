"""In-memory tool registry for noted-tools.

Phase A.1: empty registry (this file). Phase A.2 wires a file watcher on
data/user_tools/ that loads tool.json files into this registry on
create/modify and unloads on delete. Phase A.4 adds the subprocess
executor that consumes registry entries.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolEntry:
    name: str
    description: str
    input_schema: dict[str, Any]
    language: str
    tool_dir: str
    meta: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()

    def list_tools(self) -> list[ToolEntry]:
        with self._lock:
            return list(self._tools.values())

    def get(self, name: str) -> ToolEntry | None:
        with self._lock:
            return self._tools.get(name)

    def upsert(self, entry: ToolEntry) -> None:
        with self._lock:
            self._tools[entry.name] = entry

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._tools.pop(name, None) is not None


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry

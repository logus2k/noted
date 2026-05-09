"""WorkflowRegistry singleton.

Holds registered WorkflowDefinitions keyed by type. Each first-wave workflow
(create_tool, create_skill, remove_tool, remove_skill) registers itself at
import / startup time. The loop reads from this registry to instantiate a
workflow run.

Thread-safe via RLock (same pattern noted-tools' ToolRegistry uses).
"""

from __future__ import annotations

import threading

from .types import WorkflowDefinition


class WorkflowRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, WorkflowDefinition] = {}
        self._lock = threading.RLock()

    def register(self, definition: WorkflowDefinition) -> None:
        if not definition.type:
            raise ValueError("WorkflowDefinition.type is required")
        with self._lock:
            if definition.type in self._defs:
                raise ValueError(
                    f"Workflow type already registered: {definition.type!r}"
                )
            self._defs[definition.type] = definition

    def replace(self, definition: WorkflowDefinition) -> None:
        """Register or replace; intended for hot-reload / test resets only."""
        if not definition.type:
            raise ValueError("WorkflowDefinition.type is required")
        with self._lock:
            self._defs[definition.type] = definition

    def unregister(self, type_: str) -> bool:
        with self._lock:
            return self._defs.pop(type_, None) is not None

    def get(self, type_: str) -> WorkflowDefinition | None:
        with self._lock:
            return self._defs.get(type_)

    def list_types(self) -> list[str]:
        with self._lock:
            return sorted(self._defs.keys())

    def list_definitions(self) -> list[WorkflowDefinition]:
        with self._lock:
            return list(self._defs.values())


_registry = WorkflowRegistry()


def get_workflow_registry() -> WorkflowRegistry:
    return _registry

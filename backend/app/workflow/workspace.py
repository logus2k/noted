"""Per-workflow workspace state.

In-process dict keyed by (tenant_id, workflow_id). Holds the structured
state of a running workflow: completed steps' results, current step's
input/output, audit pointers, identity, plan, status. Thread-safe.

Pruning is mechanical: when total serialized size exceeds
WORKSPACE_PRUNE_THRESHOLD characters, drop verbose detail from
already-completed steps (keep their `result_summary` + status; drop full
`stdout`/`stderr` and similar bulky fields). No LLM-based summarization.

The same dict is what suspend/resume serializes to disk and what the
inspector UI surfaces. See workflow loop for the lifecycle.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

WORKSPACE_PRUNE_THRESHOLD = 16_000  # chars of serialized workspace
PRUNE_DROP_FIELDS = ("stdout", "stderr", "raw_response", "tool_call_log")


@dataclass
class StepRecord:
    """Per-step entry inside a workspace."""
    name: str  # step type name from the plan template
    index: int
    status: str = "pending"  # pending | running | completed | failed | skipped
    started_at: float | None = None
    finished_at: float | None = None
    retries: int = 0
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Verbose details kept in full until pruning; then dropped.
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceState:
    """Per-workflow state container.

    Identified by (tenant_id, workflow_id). Survives suspend/resume via
    on-disk JSON snapshot.
    """
    tenant_id: str
    workflow_id: str
    workflow_type: str
    actor_id: str
    started_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | running | suspended | completed | failed | aborted
    plan: list[dict[str, Any]] = field(default_factory=list)  # serialized plan steps
    steps: list[StepRecord] = field(default_factory=list)
    current_step: int = 0
    outcomes: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    suspend_reason: str | None = None
    finished_at: float | None = None
    # A2: regenerate-on-smoke-failure. When run_smoke_tests fails, the
    # loop rewinds to api_tester (max 2 rewinds) and re-invokes it with
    # `last_smoke_error` injected as feedback. This converts most "Gemma
    # produced slightly-broken Python" outcomes from "suspended" into
    # eventually-completed runs without prompt-level whack-a-mole.
    smoke_rewinds: int = 0
    last_smoke_error: str | None = None

    def to_serializable(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "actor_id": self.actor_id,
            "started_at": self.started_at,
            "status": self.status,
            "plan": self.plan,
            "steps": [s.__dict__ for s in self.steps],
            "current_step": self.current_step,
            "outcomes": self.outcomes,
            "inputs": self.inputs,
            "suspend_reason": self.suspend_reason,
            "finished_at": self.finished_at,
            "smoke_rewinds": self.smoke_rewinds,
            "last_smoke_error": self.last_smoke_error,
        }

    @classmethod
    def from_serializable(cls, data: dict[str, Any]) -> "WorkspaceState":
        steps = [StepRecord(**s) for s in data.get("steps", [])]
        return cls(
            tenant_id=data["tenant_id"],
            workflow_id=data["workflow_id"],
            workflow_type=data["workflow_type"],
            actor_id=data["actor_id"],
            started_at=data.get("started_at", time.time()),
            status=data.get("status", "pending"),
            plan=data.get("plan", []),
            steps=steps,
            current_step=data.get("current_step", 0),
            outcomes=data.get("outcomes", []),
            inputs=data.get("inputs", {}),
            suspend_reason=data.get("suspend_reason"),
            finished_at=data.get("finished_at"),
            smoke_rewinds=data.get("smoke_rewinds", 0),
            last_smoke_error=data.get("last_smoke_error"),
        )

    def serialized_size(self) -> int:
        try:
            return len(json.dumps(self.to_serializable(), default=str))
        except (TypeError, ValueError):
            return 0


def _prune_step_detail(step: StepRecord) -> bool:
    """Drop bulky verbose fields from a completed step's detail.
    Returns True if any field was dropped."""
    if step.status not in ("completed", "skipped"):
        return False
    dropped = False
    for k in PRUNE_DROP_FIELDS:
        if k in step.detail:
            del step.detail[k]
            dropped = True
    return dropped


class WorkspaceStore:
    """In-process registry of WorkspaceState objects keyed by (tenant_id, workflow_id)."""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], WorkspaceState] = {}
        self._lock = threading.RLock()

    def create(self, state: WorkspaceState) -> None:
        key = (state.tenant_id, state.workflow_id)
        with self._lock:
            if key in self._states:
                raise ValueError(f"workspace already exists for {key}")
            self._states[key] = state

    def get(self, tenant_id: str, workflow_id: str) -> WorkspaceState | None:
        with self._lock:
            return self._states.get((tenant_id, workflow_id))

    def upsert(self, state: WorkspaceState) -> None:
        key = (state.tenant_id, state.workflow_id)
        with self._lock:
            self._states[key] = state

    def remove(self, tenant_id: str, workflow_id: str) -> bool:
        with self._lock:
            return self._states.pop((tenant_id, workflow_id), None) is not None

    def list_for_tenant(self, tenant_id: str) -> list[WorkspaceState]:
        with self._lock:
            return [s for (t, _), s in self._states.items() if t == tenant_id]

    def prune_if_needed(self, state: WorkspaceState) -> int:
        """Apply mechanical pruning to a workspace whose serialized size
        exceeds the threshold. Returns the number of step detail blocks
        affected. No LLM call."""
        if state.serialized_size() < WORKSPACE_PRUNE_THRESHOLD:
            return 0
        dropped_count = 0
        with self._lock:
            for step in state.steps:
                if _prune_step_detail(step):
                    dropped_count += 1
                if state.serialized_size() < WORKSPACE_PRUNE_THRESHOLD:
                    break
        return dropped_count


_store = WorkspaceStore()


def get_workspace_store() -> WorkspaceStore:
    return _store

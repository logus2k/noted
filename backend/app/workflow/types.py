"""Dataclasses describing workflow types, plan templates, step types, outcomes.

These are pure data containers; no behaviour, no I/O. The registry stores
definitions of these shapes, the loop consumes them at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass(frozen=True)
class WorkflowOutcome:
    """A capability extension that a workflow's successful execution produces.

    Examples: tool_published, skill_published, domain_content_added.
    Used for audit, UI surface, and future per-outcome permissions / policies.
    The set is open-ended; workflow types declare whichever apply.
    """
    name: str
    description: str


@dataclass
class StepType:
    """A single step in a workflow's plan template.

    Either LLM-driven (worker is an agent_server preset name) or
    deterministic (worker == "deterministic" and handler is set).
    The framework validates the step's output against output_schema if one
    is provided.
    """
    name: str
    worker: str
    description: str = ""
    # For deterministic steps: an async handler called with (workspace_slice, ctx)
    # returning a dict of outputs. None for LLM-driven steps.
    handler: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None
    # JSON schema validating the step's output. None disables post-step
    # validation (use sparingly; bounded retries depend on this signal).
    output_schema: Optional[dict[str, Any]] = None
    # Task-named tools available to the worker at this step (registry names).
    # Architect picks per-tool implementation at design time; the LLM only
    # sees task tools, never implementation-named ones.
    tools_available: list[str] = field(default_factory=list)
    # Per-step retry override. None means inherit from
    # WorkflowDefinition.max_retries_per_step. Deterministic steps whose
    # handler raises on real failure (smoke tests, ast.parse validation)
    # should set this to 0 — retrying with the same input produces the
    # same failure and just burns wall-clock. LLM steps benefit from
    # >0 retries because validator_complaint feedback can flip a
    # JSON-parse failure into success on the next attempt.
    max_retries: Optional[int] = None


@dataclass
class WorkflowDefinition:
    """A registered workflow type.

    Identified by `type`. The plan_template is an ordered list of step types;
    the loop walks it in order, retrying validated-against-schema failures up
    to `max_retries_per_step` before suspending the workflow with a
    system_request for HITL.
    """
    type: str
    description: str
    outcomes: list[WorkflowOutcome] = field(default_factory=list)
    plan_template: list[StepType] = field(default_factory=list)
    # JSON Schema describing the `inputs` dict the workflow expects from
    # callers. Surfaced via GET /api/workflows/types so the planner preset
    # (and any future caller) can produce conforming inputs from a free-text
    # request. None means inputs are unstructured / contract-by-convention.
    input_schema: Optional[dict[str, Any]] = None
    # Wall-clock cap on the entire workflow. Beyond this, the loop suspends
    # with reason=wallclock_exceeded. Operator decides resume or abort.
    max_wallclock_seconds: int = 3600
    # Bounded retry per step on validation failure. Beyond this the step
    # marks failed and the workflow suspends with system_request.
    max_retries_per_step: int = 2

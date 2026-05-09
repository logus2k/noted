"""Synthetic probe workflow for F1 live-verification.

Registers a 3-step deterministic workflow that exercises the framework's
state machine, suspend / resume, audit trail, and Socket.io telemetry
without requiring agent_server / LLM workers to be wired (those land in F2).

The probe is mounted under `/api/workflow/probe/...`. F5's real workflow
inspector endpoints will live under a different prefix and will not depend
on this module. Probe stays in tree as a regression check.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .identity import extract_identity
from .loop import resume_workflow, run_workflow
from .registry import get_workflow_registry
from .suspension import get_suspension_manager
from .types import StepType, WorkflowDefinition, WorkflowOutcome
from .workspace import WorkspaceState, get_workspace_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow/probe", tags=["workflow-probe"])

PROBE_WORKFLOW_TYPE = "synthetic_probe"


# ---------- Step handlers ----------

async def _step_echo(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    msg = state.inputs.get("message", "")
    return {"echoed": msg}


async def _step_transform(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    fail_mode = state.inputs.get("fail_step2_until_retry", 0)
    current_attempt = state.steps[1].retries  # 0 first try, 1 first retry, ...
    prev = inputs.get("previous_step", {}).get("output", {})
    echoed = prev.get("echoed", "")
    if fail_mode and current_attempt < int(fail_mode):
        # Force a validation failure on this attempt to exercise retry path.
        return {"wrong_field": echoed.upper()}
    return {"upper": echoed.upper()}


async def _step_finalize(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    prev = inputs.get("previous_step", {}).get("output", {})
    return {"final": "ok", "transformed": prev.get("upper", "")}


def _register_probe_workflow_once() -> None:
    registry = get_workflow_registry()
    if registry.get(PROBE_WORKFLOW_TYPE) is not None:
        return
    registry.register(WorkflowDefinition(
        type=PROBE_WORKFLOW_TYPE,
        description="F1 synthetic probe: echo -> transform -> finalize. Deterministic.",
        outcomes=[WorkflowOutcome(name="probe_completed",
                                  description="probe ran to completion")],
        plan_template=[
            StepType(
                name="echo",
                worker="deterministic",
                description="emit echoed:<message>",
                handler=_step_echo,
                output_schema={
                    "type": "object",
                    "properties": {"echoed": {"type": "string"}},
                    "required": ["echoed"],
                },
            ),
            StepType(
                name="transform",
                worker="deterministic",
                description="upper-case the echoed value",
                handler=_step_transform,
                output_schema={
                    "type": "object",
                    "properties": {"upper": {"type": "string"}},
                    "required": ["upper"],
                },
            ),
            StepType(
                name="finalize",
                worker="deterministic",
                description="emit final marker",
                handler=_step_finalize,
                output_schema={
                    "type": "object",
                    "properties": {
                        "final": {"type": "string"},
                        "transformed": {"type": "string"},
                    },
                    "required": ["final", "transformed"],
                },
            ),
        ],
        max_retries_per_step=2,
        max_wallclock_seconds=120,
    ))


_register_probe_workflow_once()


# ---------- HTTP surface ----------

@router.post("/run-synthetic")
async def run_synthetic(request: Request) -> dict[str, Any]:
    """Trigger a synthetic probe workflow.

    Body (optional JSON): {
      "message": str,                       # default "hello probe"
      "fail_step2_until_retry": int         # 0=no fail; N=fail validation N times before passing
    }

    Returns the final WorkspaceState's serialized form.
    """
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    identity = extract_identity(request.headers)
    inputs = {
        "message": body.get("message", "hello probe"),
        "fail_step2_until_retry": int(body.get("fail_step2_until_retry", 0)),
    }
    state = await run_workflow(
        tenant_id=identity.tenant_id,
        workflow_type=PROBE_WORKFLOW_TYPE,
        inputs=inputs,
        actor_id=identity.actor_id,
    )
    return {
        "identity": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id},
        "state": state.to_serializable(),
    }


@router.post("/run-synthetic-suspend-then-resume")
async def run_synthetic_suspend_then_resume(request: Request) -> dict[str, Any]:
    """Trigger a probe configured to suspend on validation failure, then
    auto-resume from the host side after a short delay (clears the failure
    flag in workspace inputs so the retry succeeds).

    Used to live-verify the suspend / resume / snapshot / audit path
    without a UI. fail_step2_until_retry is set so retries always exhaust.
    """
    identity = extract_identity(request.headers)
    inputs = {
        "message": "suspend probe",
        "fail_step2_until_retry": 99,  # always fails until we clear it
    }

    async def _run() -> WorkspaceState:
        return await run_workflow(
            tenant_id=identity.tenant_id,
            workflow_type=PROBE_WORKFLOW_TYPE,
            inputs=inputs,
            actor_id=identity.actor_id,
        )

    task = asyncio.create_task(_run())

    # Wait briefly for the workflow to suspend.
    suspension = get_suspension_manager()
    store = get_workspace_store()
    workflow_id: str | None = None
    for _ in range(40):  # up to ~4s
        await asyncio.sleep(0.1)
        for s in store.list_for_tenant(identity.tenant_id):
            if s.workflow_type == PROBE_WORKFLOW_TYPE and s.status == "suspended":
                workflow_id = s.workflow_id
                break
        if workflow_id:
            break

    if workflow_id is None:
        # Workflow finished without suspending or hasn't reached suspend yet;
        # await it to surface whatever happened.
        state = await task
        return {
            "note": "workflow did not suspend within 4s window",
            "state": state.to_serializable(),
        }

    # Clear the failure flag so resume succeeds, then resume.
    state = store.get(identity.tenant_id, workflow_id)
    if state is not None:
        state.inputs["fail_step2_until_retry"] = 0
        # Reset retry counter so the bounded retry budget is fresh for the
        # post-resume attempt.
        state.steps[state.current_step].retries = 0
    suspension.resume(identity.tenant_id, workflow_id)

    final = await task
    return {
        "workflow_id": workflow_id,
        "resumed_from_step": final.current_step,
        "state": final.to_serializable(),
    }


@router.get("/state/{workflow_id}")
async def get_state(workflow_id: str, request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    state = get_workspace_store().get(identity.tenant_id, workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="workflow not in workspace store")
    return state.to_serializable()


@router.post("/resume/{workflow_id}")
async def resume(workflow_id: str, request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    suspension = get_suspension_manager()
    if not suspension.is_suspended(identity.tenant_id, workflow_id):
        raise HTTPException(status_code=409, detail="workflow not suspended")
    suspension.resume(identity.tenant_id, workflow_id)
    return {"resumed": True, "workflow_id": workflow_id}


@router.post("/abort/{workflow_id}")
async def abort(workflow_id: str, request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    suspension = get_suspension_manager()
    if not suspension.is_suspended(identity.tenant_id, workflow_id):
        raise HTTPException(status_code=409, detail="workflow not suspended")
    suspension.abort(identity.tenant_id, workflow_id)
    return {"aborted": True, "workflow_id": workflow_id}


@router.get("/list")
async def list_workflows(request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    states = get_workspace_store().list_for_tenant(identity.tenant_id)
    return {
        "tenant_id": identity.tenant_id,
        "workflows": [s.to_serializable() for s in states],
    }


@router.post("/run/{workflow_type}")
async def run_any_workflow(workflow_type: str, request: Request) -> dict[str, Any]:
    """Generic runner for any registered workflow type.

    Body (JSON) becomes the workflow's `inputs` dict. The framework looks
    up the workflow definition by `workflow_type`, instantiates the
    workspace, and runs the plan synchronously. Returns the final
    WorkspaceState. F5's workflow inspector will replace this with a
    streaming, async-safe variant; for F3 live verification this is
    enough.
    """
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    identity = extract_identity(request.headers)
    state = await run_workflow(
        tenant_id=identity.tenant_id,
        workflow_type=workflow_type,
        inputs=body,
        actor_id=identity.actor_id,
    )
    return {
        "identity": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id},
        "state": state.to_serializable(),
    }


@router.get("/types")
async def list_workflow_types() -> dict[str, Any]:
    """Surface the registered workflow types + their plan shape. Useful
    for the planner's `available_workflows` block, and for debugging."""
    from .registry import get_workflow_registry
    registry = get_workflow_registry()
    out = []
    for d in registry.list_definitions():
        out.append({
            "type": d.type,
            "description": d.description,
            "outcomes": [{"name": o.name, "description": o.description} for o in d.outcomes],
            "plan_template": [
                {"name": s.name, "worker": s.worker, "description": s.description}
                for s in d.plan_template
            ],
            "max_wallclock_seconds": d.max_wallclock_seconds,
            "max_retries_per_step": d.max_retries_per_step,
        })
    return {"types": out}

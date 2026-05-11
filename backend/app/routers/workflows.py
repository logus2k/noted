"""Workflow inspector API.

Tenant-scoped reads + control surface for the workflow framework. The
calling user's tenant comes from `X-Forwarded-User` (oauth2-proxy header)
or falls back to "default" when the auth path isn't wired through.

Distinct from `app.workflow.probe` which is dev-only synthetic-probe
endpoints. This router is what the Explorer Workflows tab consumes.

Endpoints:
  GET    /api/workflows/types
  GET    /api/workflows                      list workflows for the tenant
  POST   /api/workflows/run                  trigger a new workflow
  GET    /api/workflows/{workflow_id}        detail (workspace + audit)
  POST   /api/workflows/{workflow_id}/resume
  POST   /api/workflows/{workflow_id}/abort
  POST   /api/workflows/{workflow_id}/rerun  re-trigger with the same inputs
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import DATA_DIR
from app.workflow import audit as wf_audit
from app.workflow.identity import extract_identity
from app.workflow.loop import resume_workflow as wf_resume_workflow
from app.workflow.loop import run_workflow as wf_run_workflow
from app.workflow.registry import get_workflow_registry
from app.workflow.suspension import (
    get_suspension_manager,
    hydrate_workspace_from_snapshot,
    read_snapshot,
)
from app.workflow.workspace import WorkspaceState, get_workspace_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class RunWorkflowRequest(BaseModel):
    type: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class FromRequestBody(BaseModel):
    """Spec-driven capability request. The body's `request` field contains
    the FULL tool-spec markdown (the agreed contract); the planner acts as
    architect: validates the spec, completes technical details, translates
    to workflow_inputs. The wrapper validates against the chosen workflow's
    input_schema and dispatches if valid.

    For chat-side use, prefer the `request_new_tool` MCP tool which reads
    the spec from a doc buffer by id. This HTTP endpoint exists for direct
    spec submission (e.g. the harness writing pre-authored specs)."""
    request: str = Field(..., min_length=20, description=(
        "Full tool-spec markdown (header lines + Description + Source "
        "documentation + Inputs + Outputs + Acceptance criteria sections). "
        "The planner refuses if status is draft or any required section "
        "contains TBD."
    ))
    backend: str | None = Field(default=None, description=(
        "Optional override for the planner LLM backend ('gemma' default, "
        "'claude' to route via Anthropic). Per-step backends inside the "
        "dispatched workflow follow their own defaults."
    ))


@router.get("/types")
async def list_workflow_types() -> dict[str, Any]:
    """List registered workflow types + their plan shape + outcomes +
    input_schema. The planner consumes input_schema to produce conforming
    inputs from a free-text request."""
    registry = get_workflow_registry()
    return {
        "types": [
            {
                "type": d.type,
                "description": d.description,
                "outcomes": [
                    {"name": o.name, "description": o.description}
                    for o in d.outcomes
                ],
                "plan_template": [
                    {"name": s.name, "worker": s.worker, "description": s.description}
                    for s in d.plan_template
                ],
                "input_schema": d.input_schema,
                "max_wallclock_seconds": d.max_wallclock_seconds,
                "max_retries_per_step": d.max_retries_per_step,
            }
            for d in registry.list_definitions()
        ]
    }


def _list_snapshotted_workflows(tenant_id: str) -> list[WorkspaceState]:
    """Walk data/tenants/<tenant_id>/workflows/*/state.json and load each
    snapshot. Used by the inspector to surface workflows that finished /
    failed / suspended in a previous noted process."""
    root = Path(DATA_DIR) / "tenants" / tenant_id / "workflows"
    if not root.is_dir():
        return []
    out: list[WorkspaceState] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        state = read_snapshot(tenant_id, child.name)
        if state is not None:
            out.append(state)
    return out


@router.get("")
@router.get("/")
async def list_workflows(request: Request) -> dict[str, Any]:
    """List all workflows for the calling tenant - merges in-memory live
    workflows with on-disk snapshots from prior runs.

    Optional query params:
      ?status=running|suspended|completed|failed|aborted
      ?type=<workflow_type>
    """
    identity = extract_identity(request.headers)
    status_filter = request.query_params.get("status")
    type_filter = request.query_params.get("type")

    live = get_workspace_store().list_for_tenant(identity.tenant_id)
    live_ids = {s.workflow_id for s in live}
    disk = [s for s in _list_snapshotted_workflows(identity.tenant_id)
            if s.workflow_id not in live_ids]
    states = live + disk

    if status_filter:
        states = [s for s in states if s.status == status_filter]
    if type_filter:
        states = [s for s in states if s.workflow_type == type_filter]
    states = sorted(states, key=lambda s: s.started_at, reverse=True)

    return {
        "tenant_id": identity.tenant_id,
        "workflows": [s.to_serializable() for s in states],
        "counts": {
            "live": len(live),
            "from_disk": len(disk),
            "returned": len(states),
        },
    }


@router.post("/run")
async def run_new(request: Request, body: RunWorkflowRequest) -> dict[str, Any]:
    """Trigger a new workflow asynchronously. Returns immediately with the
    `workflow_id` so the caller can subscribe via Socket.io / poll detail.
    """
    identity = extract_identity(request.headers)
    if get_workflow_registry().get(body.type) is None:
        raise HTTPException(status_code=404, detail=f"unknown workflow type: {body.type!r}")

    # Generate the workflow_id upfront so the caller can return it
    # immediately without racing the workflow's own runtime. The loop's
    # run_workflow accepts an explicit workflow_id; same value flows through
    # the workspace, audit, snapshot path.
    from app.workflow.loop import _new_workflow_id
    workflow_id = _new_workflow_id()

    async def _run() -> None:
        try:
            await wf_run_workflow(
                tenant_id=identity.tenant_id,
                workflow_type=body.type,
                inputs=body.inputs,
                actor_id=identity.actor_id,
                workflow_id=workflow_id,
            )
        except Exception:
            logger.exception("run_new spawned task failed for %s", workflow_id)

    asyncio.create_task(_run())
    return {
        "workflow_id": workflow_id,
        "tenant_id": identity.tenant_id,
        "status": "pending",
    }


@router.post("/from-request")
async def run_from_request(request: Request, body: FromRequestBody) -> dict[str, Any]:
    """Spec-driven capability request → planner-decided workflow.

    Thin wrapper over `app.workflow.from_request.dispatch_from_request`;
    the heavy lifting (planner call, validation, dispatch) lives there so
    the same logic backs the `request_new_tool` MCP tool. The body's
    `request` field is now the full tool-spec markdown (the contract),
    not free text.
    """
    from app.workflow.from_request import (
        FromRequestError,
        dispatch_from_request,
    )

    identity = extract_identity(request.headers)
    try:
        return await dispatch_from_request(
            body.request,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
    except FromRequestError as e:
        # planner_call → 502 (upstream unreachable). Everything else is a
        # structured planner-output problem → 422 so the caller can route
        # the validator complaint back into a retry / new ask.
        status = 502 if e.stage == "planner_call" else 422
        raise HTTPException(status_code=status, detail={"stage": e.stage, **e.detail}) from e


def _resolve_state_or_404(tenant_id: str, workflow_id: str):
    state = get_workspace_store().get(tenant_id, workflow_id)
    if state is None:
        # Try hydrating from on-disk snapshot - workflow may have been
        # suspended across a noted restart.
        state = hydrate_workspace_from_snapshot(tenant_id, workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return state


@router.get("/{workflow_id}")
async def get_detail(workflow_id: str, request: Request) -> dict[str, Any]:
    """Workflow detail: workspace state + tail of audit log."""
    identity = extract_identity(request.headers)
    state = _resolve_state_or_404(identity.tenant_id, workflow_id)
    audit_lines = wf_audit.read(identity.tenant_id, workflow_id, limit=500)
    return {
        "state": state.to_serializable(),
        "audit": audit_lines,
    }


@router.post("/{workflow_id}/resume")
async def resume(workflow_id: str, request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    suspension = get_suspension_manager()
    if not suspension.is_suspended(identity.tenant_id, workflow_id):
        raise HTTPException(status_code=409, detail="workflow not suspended")
    suspension.resume(identity.tenant_id, workflow_id)
    return {"resumed": True, "workflow_id": workflow_id}


@router.post("/{workflow_id}/abort")
async def abort(workflow_id: str, request: Request) -> dict[str, Any]:
    identity = extract_identity(request.headers)
    suspension = get_suspension_manager()
    if not suspension.is_suspended(identity.tenant_id, workflow_id):
        raise HTTPException(status_code=409, detail="workflow not suspended")
    suspension.abort(identity.tenant_id, workflow_id)
    return {"aborted": True, "workflow_id": workflow_id}


class DecisionRequest(BaseModel):
    decision: str = Field(
        ...,
        description="The user's verdict at a HITL review checkpoint. "
                    "Currently used by research_topic; one of 'accept' or 'iterate'.",
    )


@router.post("/{workflow_id}/decision")
async def decision(workflow_id: str, request: Request, body: DecisionRequest) -> dict[str, Any]:
    """Record the user's decision at a HITL checkpoint and resume.

    Used by `research_topic` user_review pauses. The handler reads
    `state.user_decision` on resume and branches:
      - "accept" → workflow completes
      - "iterate" → loops back into the research+review cycle, picking
        up any feedback the supervisor wrote into the doc's Review
        Notes section before signalling resume.

    Single endpoint that sets the field AND signals resume so the
    handler doesn't race the resume signal against a separate field
    write.
    """
    identity = extract_identity(request.headers)
    decision_value = (body.decision or "").strip().lower()
    if decision_value not in ("accept", "iterate"):
        raise HTTPException(
            status_code=400,
            detail=f"decision must be 'accept' or 'iterate'; got {body.decision!r}",
        )

    suspension = get_suspension_manager()
    if not suspension.is_suspended(identity.tenant_id, workflow_id):
        raise HTTPException(status_code=409, detail="workflow not suspended")

    # Resolve and mutate the in-memory state BEFORE signalling resume,
    # so the handler reads the decision the moment its wait unblocks.
    state = _resolve_state_or_404(identity.tenant_id, workflow_id)
    state.user_decision = decision_value

    suspension.resume(identity.tenant_id, workflow_id)
    return {
        "ok": True,
        "workflow_id": workflow_id,
        "decision": decision_value,
    }


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request) -> dict[str, Any]:
    """Drop a workflow's runtime state — both the in-memory workspace
    entry (if any) and the on-disk snapshot directory under
    `data/tenants/<tenant>/workflows/<workflow_id>/`.

    Refuses to delete a workflow that's currently running; the caller
    should /abort first. Suspended / completed / failed / aborted
    workflows are deletable. Side-effects of the workflow (a published
    tool, a paired skill) are NOT undone — use the corresponding
    remove_tool workflow for that.
    """
    import shutil

    identity = extract_identity(request.headers)
    state = _resolve_state_or_404(identity.tenant_id, workflow_id)

    if state.status == "running":
        raise HTTPException(
            status_code=409,
            detail="workflow is running; abort it first via /abort",
        )

    store = get_workspace_store()
    store.remove(identity.tenant_id, workflow_id)

    snapshot_dir = (
        Path(DATA_DIR) / "tenants" / identity.tenant_id /
        "workflows" / workflow_id
    )
    on_disk_existed = snapshot_dir.is_dir()
    if on_disk_existed:
        shutil.rmtree(snapshot_dir, ignore_errors=True)

    return {
        "deleted": True,
        "workflow_id": workflow_id,
        "had_disk_snapshot": on_disk_existed,
    }


@router.post("/{workflow_id}/rerun")
async def rerun(workflow_id: str, request: Request) -> dict[str, Any]:
    """Trigger a NEW workflow with the same type + inputs as a prior one.
    Returns the new workflow_id (the old workflow is unchanged)."""
    identity = extract_identity(request.headers)
    state = _resolve_state_or_404(identity.tenant_id, workflow_id)

    from app.workflow.loop import _new_workflow_id
    new_id = _new_workflow_id()

    async def _run() -> None:
        try:
            await wf_run_workflow(
                tenant_id=identity.tenant_id,
                workflow_type=state.workflow_type,
                inputs=dict(state.inputs or {}),
                actor_id=identity.actor_id,
                workflow_id=new_id,
            )
        except Exception:
            logger.exception("rerun spawned task failed for %s", workflow_id)

    asyncio.create_task(_run())
    return {
        "original_workflow_id": workflow_id,
        "workflow_id": new_id,
        "status": "pending",
    }

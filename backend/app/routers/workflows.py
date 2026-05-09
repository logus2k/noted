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
    """Free-text capability request. The planner picks the workflow type and
    populates inputs; the wrapper validates against the chosen workflow's
    input_schema and dispatches if valid."""
    request: str = Field(..., min_length=4, description=(
        "Natural-language description of what the user wants the assistant "
        "to be able to do — e.g. 'I found these two URLs that return weather "
        "info; figure out how to use them so I get a new skill to report "
        "on the weather: <urls>'."
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
    """Free-text capability request → planner-decided workflow.

    Thin wrapper over `app.workflow.from_request.dispatch_from_request`;
    the heavy lifting (planner call, validation, dispatch) lives there so
    the same logic backs the `request_new_tool` MCP tool.
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

"""`submit_research_decision` MCP tool handler.

Submits accept / iterate / stop verdict for a paused research_topic
workflow. Hits the same code path the HTTP /decision endpoint runs:
sets `state.user_decision` and signals resume in one step.

`stop` ends the workflow with the doc in its current (partial) state —
semantically distinct from `accept` (which means the doc fully satisfies
the goal). Use stop when the user says to stop, when criteria appear
unreachable, or when partial findings are good enough.
"""

from __future__ import annotations

import json
from typing import Any


async def handler(
    args: dict,
    managers: dict | None = None,
    ctx: dict | None = None,
) -> str:
    workflow_id = (args.get("workflow_id") or "").strip()
    decision = (args.get("decision") or "").strip().lower()
    if not workflow_id:
        return "Error: 'workflow_id' is required."
    if decision not in ("accept", "iterate", "stop"):
        return (
            f"Error: 'decision' must be 'accept', 'iterate', or 'stop'; got {decision!r}."
        )

    from app.workflow.suspension import get_suspension_manager
    from app.workflow.workspace import get_workspace_store
    suspension = get_suspension_manager()
    if not suspension.is_suspended("default", workflow_id):
        return (
            f"Error: workflow {workflow_id!r} is not currently suspended. "
            f"submit_research_decision can only be called while a "
            f"workflow is paused for user review."
        )
    state = get_workspace_store().get("default", workflow_id)
    if state is None:
        return f"Error: workflow {workflow_id!r} not found."
    state.user_decision = decision
    suspension.resume("default", workflow_id)
    return json.dumps({
        "ok": True,
        "workflow_id": workflow_id,
        "decision": decision,
        "next_step": (
            "Decision submitted. If decision='accept', the workflow has "
            "now completed and the document is the final artifact. If "
            "decision='iterate', the researcher will pick up your Review "
            "Notes feedback and run another pass; you'll receive another "
            "workflow_suspended notice when it's ready."
        ),
    })

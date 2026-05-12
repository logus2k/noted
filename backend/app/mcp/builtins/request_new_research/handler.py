"""`request_new_research` MCP tool handler.

Kicks off a `research_topic` workflow asynchronously. Mirrors the
pattern in `routers.workflows.run_new`: generate the workflow_id up
front so the tool result can include it immediately, then fire-and-forget
the workflow loop on a background task. The handler suspends for
user_review (via the existing HITL mechanism) when the inner
research+review loop finishes — the chat-side workflow_suspended notice
then nudges the supervisor (this LLM) to read the doc and call
`submit_research_decision`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handler(
    args: dict,
    managers: dict | None = None,
    ctx: dict | None = None,
) -> str:
    goal = (args.get("goal") or "").strip()
    criteria = list(args.get("acceptance_criteria") or [])
    notes_doc_id = (args.get("notes_doc_id") or "").strip()

    if not goal:
        return "Error: 'goal' is required (the user's research question)."
    if not criteria:
        return (
            "Error: 'acceptance_criteria' is required (2-5 short bullets "
            "the document must satisfy). Extract from the user's request, "
            "or ask the user first."
        )
    if not notes_doc_id:
        return (
            "Error: 'notes_doc_id' is required. Call create_doc first to "
            "create the workspace buffer."
        )

    from app.managers import notes_buffer
    if notes_buffer.get(notes_doc_id) is None:
        return (
            f"Error: notes_doc_id {notes_doc_id!r} not found. Verify the "
            f"buffer_id returned by create_doc."
        )

    from app.workflow.loop import _new_workflow_id, run_workflow as _run_wf
    from app.workflow.registry import get_workflow_registry
    if get_workflow_registry().get("research_topic") is None:
        return "Error: research_topic workflow is not registered."

    workflow_id = _new_workflow_id()

    async def _run() -> None:
        try:
            await _run_wf(
                tenant_id="default",
                workflow_type="research_topic",
                inputs={
                    "goal": goal,
                    "acceptance_criteria": criteria,
                    "notes_doc_id": notes_doc_id,
                },
                actor_id="default",
                workflow_id=workflow_id,
            )
        except Exception:
            logger.exception(
                "request_new_research spawned task failed for %s", workflow_id
            )

    asyncio.create_task(_run())
    return json.dumps({
        "workflow_id": workflow_id,
        "workflow_type": "research_topic",
        "status": "pending",
        "notes_doc_id": notes_doc_id,
        "goal": goal,
        "acceptance_criteria": criteria,
        "next_step": (
            "Research is running in the background. Tell the user what "
            "you're researching (the goal + criteria) in 1-2 sentences. "
            "You will receive a workflow_suspended notice once the "
            "researcher and reviewer have completed their internal loop "
            "and the document is ready for your supervisor review."
        ),
    })

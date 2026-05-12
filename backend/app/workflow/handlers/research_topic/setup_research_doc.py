"""`setup_research_doc` step handler — pre-fills the workspace document
with its canonical section structure (Goal, Acceptance Criteria, Review
Notes, Findings) so the researcher and reviewer agents have a stable
shape to read and write against.
"""

from __future__ import annotations

from typing import Any

from app.workflow.workspace import WorkspaceState

from ._doc import _render_research_doc


async def setup_research_doc(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Pre-fill the research workspace document with its canonical
    section structure. The notes_doc_id buffer must already exist (the
    supervisor created it via create_doc before kicking off the
    workflow). Uses notes_buffer.replace directly — no need to go
    through the MCP write-tool path for this deterministic setup."""
    from app.managers import notes_buffer

    wf_in = state.inputs or {}
    goal = (wf_in.get("goal") or "").strip()
    criteria = list(wf_in.get("acceptance_criteria") or [])
    notes_doc_id = (wf_in.get("notes_doc_id") or "").strip()

    if not goal:
        raise ValueError("setup_research_doc: goal is required and non-empty")
    if not criteria:
        raise ValueError("setup_research_doc: acceptance_criteria is required and non-empty")
    if not notes_doc_id:
        raise ValueError("setup_research_doc: notes_doc_id is required")

    buf = notes_buffer.get(notes_doc_id)
    if buf is None:
        raise ValueError(
            f"setup_research_doc: buffer {notes_doc_id!r} not found — "
            "the supervisor must create the doc via create_doc before "
            "starting the workflow"
        )

    md = _render_research_doc(goal, criteria)
    restored = notes_buffer.replace(notes_doc_id, md)
    if restored is None:
        raise RuntimeError(
            f"setup_research_doc: notes_buffer.replace returned None "
            f"for {notes_doc_id!r}"
        )

    return {
        "notes_doc_id": notes_doc_id,
        "criteria_count": len(criteria),
        "byte_size": len(md),
    }

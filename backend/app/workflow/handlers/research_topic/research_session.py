"""`research_session` composite step handler.

Drives the researcher + reviewer agent loop and suspends for user review,
looping on user feedback. The outer loop is one user-visible "round";
the inner loop runs research + review up to `RESEARCH_ITERATION_CAP`
times before forcing a user-review suspend. Total inner iterations are
bounded by `GLOBAL_ITERATION_CAP` regardless of how many user iterate
decisions come back.

The handler talks to:
- `dispatch_tool_calling` for the researcher and reviewer agent turns.
- `_suspend_for_hitl` for the user-review pause (returns False on abort).
- `doc_events` for the Workflow Monitor's progress feed.
- The workflow registry for the workflow definition lookup.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.workflow.workspace import WorkspaceState

from ._doc import _append_doc_termination_note, _update_doc_with_review
from ._reviewer import (
    GLOBAL_ITERATION_CAP,
    RESEARCH_ITERATION_CAP,
    RESEARCHER_MAX_TURNS,
    RESEARCHER_TOOLS,
    REVIEWER_MAX_TURNS,
    REVIEWER_TOOLS,
    _build_researcher_message,
    _build_reviewer_message,
    _validate_reviewer_payload,
)

logger = logging.getLogger(__name__)


async def research_session(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Composite step: drives the researcher + reviewer agent loop and
    suspends for user review, looping on user feedback.

    Outer loop = a single user-visible "round":
      - Inner loop runs researcher → reviewer up to RESEARCH_ITERATION_CAP
        times until verdict=ready_for_user.
      - Suspend the workflow for user review (existing HITL machinery).
      - On resume, branch on `state.user_decision`:
          * "accept"  → return success
          * "iterate" → reset counter, loop to inner research again. The
            user's feedback (if any) is already written into the doc's
            Review Notes section by noted before the resume signal.
          * "stop"    → end with partial result (semantically distinct
            from accept; doc records as INCOMPLETE).
          * other / None → defensive: treat as accept.

    Returns one of:
      {"status": "accepted",    "iterations_run": N, "final_verdict": "..."}
      {"status": "stopped",     "iterations_run": N, "final_verdict": "..."}
      {"status": "aborted",     "iterations_run": N, "final_verdict": "..."}
    """
    from app.workflow import doc_events
    from app.workflow.llm_dispatcher import dispatch_tool_calling
    from app.workflow.loop import _suspend_for_hitl
    from app.workflow.registry import get_workflow_registry

    wf_in = state.inputs or {}
    notes_doc_id = (wf_in.get("notes_doc_id") or "").strip()
    criteria = list(wf_in.get("acceptance_criteria") or [])
    if not notes_doc_id:
        raise ValueError("research_session: notes_doc_id is required")
    if not criteria:
        raise ValueError("research_session: acceptance_criteria is required")

    definition = get_workflow_registry().get(state.workflow_type)
    if definition is None:
        raise RuntimeError(
            f"research_session: workflow definition {state.workflow_type!r} not found"
        )

    iteration_history: list[dict[str, Any]] = []
    overall_iteration = 0
    last_verdict: str | None = None

    while True:
        # ── Inner loop: research → review until ready_for_user or cap ──
        inner_iter = 0
        while inner_iter < RESEARCH_ITERATION_CAP:
            inner_iter += 1
            overall_iteration += 1

            doc_events.publish_workflow_event(
                state.workflow_id,
                "iteration_started",
                {"iteration": overall_iteration},
            )

            # ── Researcher turn ──
            try:
                rresult = await dispatch_tool_calling(
                    "researcher",
                    _build_researcher_message(notes_doc_id, overall_iteration),
                    RESEARCHER_TOOLS,
                    state=state,
                    max_turns=RESEARCHER_MAX_TURNS,
                )
                researcher_calls = len(rresult.get("tool_call_log") or [])
            except Exception:
                logger.exception(
                    "researcher failed at iteration %d (continuing to reviewer)",
                    overall_iteration,
                )
                researcher_calls = 0

            doc_events.publish_workflow_event(
                state.workflow_id,
                "researcher_done",
                {
                    "iteration": overall_iteration,
                    "tool_calls": researcher_calls,
                },
            )

            # ── Reviewer turn with bounded JSON-retry ──
            reviewer_payload: dict[str, Any] | None = None
            last_complaint: str | None = None
            for attempt in range(3):
                try:
                    vresult = await dispatch_tool_calling(
                        "research_reviewer",
                        _build_reviewer_message(
                            notes_doc_id, overall_iteration, prior_complaint=last_complaint
                        ),
                        REVIEWER_TOOLS,
                        state=state,
                        max_turns=REVIEWER_MAX_TURNS,
                    )
                    content = (vresult.get("final_content") or "").strip()
                    # Strip code fences the reviewer might wrap JSON in
                    # despite the prompt forbidding them.
                    fence_match = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", content, re.DOTALL)
                    if fence_match:
                        content = fence_match.group(1).strip()
                    parsed = json.loads(content) if content else None
                    err = _validate_reviewer_payload(parsed)
                    if err:
                        raise ValueError(err)
                    reviewer_payload = parsed
                    break
                except Exception as e:
                    last_complaint = str(e)[:200]
                    logger.warning(
                        "reviewer JSON invalid at iter %d (attempt %d/3): %s",
                        overall_iteration, attempt + 1, last_complaint,
                    )

            if reviewer_payload is None:
                # Couldn't get a valid verdict after 3 tries. Force iterate
                # with a default note so the next pass continues research
                # rather than silently completing.
                reviewer_payload = {
                    "verdict": "iterate",
                    "criteria_status": [
                        {"criterion": c, "met": False, "evidence": ""}
                        for c in criteria
                    ],
                    "notes": (
                        "Reviewer failed to produce valid JSON after 3 "
                        "attempts. Continuing research; please address all "
                        "unmet criteria."
                    ),
                }

            last_verdict = reviewer_payload.get("verdict")

            # ── Persist verdict into the doc (checkboxes + notes) ──
            _update_doc_with_review(
                notes_doc_id, criteria, reviewer_payload, overall_iteration
            )

            met = sum(
                1 for cs in reviewer_payload.get("criteria_status", []) if cs.get("met")
            )
            iteration_history.append({
                "iteration": overall_iteration,
                "verdict": last_verdict,
                "criteria_met": met,
                "criteria_total": len(criteria),
            })

            doc_events.publish_workflow_event(
                state.workflow_id,
                "reviewer_done",
                {
                    "iteration": overall_iteration,
                    "verdict": last_verdict,
                    "criteria_met": met,
                    "criteria_total": len(criteria),
                },
            )

            # Incremental step output for Workflow Monitor visibility.
            try:
                state.steps[state.current_step].output = {
                    "status": "in_progress",
                    "iterations_run": overall_iteration,
                    "final_verdict": last_verdict or "",
                    "iteration_history": iteration_history,
                }
            except Exception:
                pass

            if state.status == "aborted":
                return {
                    "status": "aborted",
                    "iterations_run": overall_iteration,
                    "final_verdict": last_verdict or "",
                }

            if last_verdict == "ready_for_user":
                break

        # ── Inner loop done; suspend for user review ──
        if last_verdict != "ready_for_user":
            # Cap was hit. Still surface to user; they decide whether to
            # iterate further or accept.
            doc_events.publish_workflow_event(
                state.workflow_id,
                "iteration_cap_reached",
                {"iterations": overall_iteration},
            )

        state.user_decision = None  # clear any stale value
        cap_reached = overall_iteration >= GLOBAL_ITERATION_CAP
        suspend_reason = "research_user_review"
        if cap_reached:
            suspend_reason = "research_user_review:cap_reached"
        doc_events.publish_workflow_event(
            state.workflow_id,
            "user_review_pending",
            {
                "iterations_so_far": overall_iteration,
                "final_verdict": last_verdict or "cap_reached",
                "global_cap_reached": cap_reached,
                "global_cap": GLOBAL_ITERATION_CAP,
            },
        )

        resumed = await _suspend_for_hitl(state, suspend_reason, definition)
        if not resumed:
            _append_doc_termination_note(
                notes_doc_id,
                kind="aborted",
                iteration=overall_iteration,
                detail="Workflow aborted via Workflow Monitor or suspend timeout.",
            )
            return {
                "status": "aborted",
                "iterations_run": overall_iteration,
                "final_verdict": last_verdict or "",
            }

        decision = (state.user_decision or "").strip().lower()
        state.user_decision = None  # consume

        if decision == "accept":
            doc_events.publish_workflow_event(
                state.workflow_id, "user_accepted", {"iterations": overall_iteration}
            )
            _append_doc_termination_note(
                notes_doc_id,
                kind="accepted",
                iteration=overall_iteration,
                detail="User accepted the research as complete.",
            )
            return {
                "status": "accepted",
                "iterations_run": overall_iteration,
                "final_verdict": last_verdict or "",
            }
        if decision == "stop":
            doc_events.publish_workflow_event(
                state.workflow_id, "user_stopped", {"iterations": overall_iteration}
            )
            _append_doc_termination_note(
                notes_doc_id,
                kind="stopped",
                iteration=overall_iteration,
                detail=(
                    "User stopped the research with the document in its "
                    "current state. Some acceptance criteria may remain unmet."
                ),
            )
            return {
                "status": "stopped",
                "iterations_run": overall_iteration,
                "final_verdict": last_verdict or "",
            }
        if decision == "iterate":
            if cap_reached:
                logger.warning(
                    "research_session: iterate refused at global cap "
                    "(%d iterations) for workflow %s — re-suspending.",
                    overall_iteration, state.workflow_id,
                )
                _append_doc_termination_note(
                    notes_doc_id,
                    kind="cap_reached",
                    iteration=overall_iteration,
                    detail=(
                        f"Global iteration cap ({GLOBAL_ITERATION_CAP}) reached. "
                        "Further iteration is refused. Choose accept (keep "
                        "the document as-is) or stop (end with partial result)."
                    ),
                )
                continue
            doc_events.publish_workflow_event(
                state.workflow_id, "user_iterate", {}
            )
            continue

        # Unknown/missing decision. Defensive: treat as accept rather
        # than spin forever.
        logger.warning(
            "research_session: unexpected user_decision %r, accepting",
            decision,
        )
        _append_doc_termination_note(
            notes_doc_id,
            kind="accepted",
            iteration=overall_iteration,
            detail=(
                "Workflow ended with no recognised user decision; "
                "defaulting to accept."
            ),
        )
        return {
            "status": "accepted",
            "iterations_run": overall_iteration,
            "final_verdict": last_verdict or "",
        }

"""Shared reviewer-loop knobs + message builders + payload validator.

Lives separately from the `research_session` handler so the handler file
stays focused on control flow. Two callers: `research_session.py`
(researcher + reviewer turn) and any future test harness that wants to
exercise the reviewer in isolation.
"""

from __future__ import annotations

from typing import Any


# Cap on inner researcher+reviewer iterations BEFORE forcing user review.
# Counter resets on each user iterate feedback (so a fresh review cycle
# always gets a fresh budget). Combined with GLOBAL_ITERATION_CAP this
# bounds the total: at most GLOBAL_ITERATION_CAP inner passes across the
# entire workflow regardless of how many times the user (or supervisor)
# clicks iterate.
RESEARCH_ITERATION_CAP = 5

# Total inner-iteration ceiling across ALL user review cycles. After this,
# `iterate` decisions are refused — only `accept` or `stop` remain valid.
# Prevents the "supervisor keeps deciding iterate, user can't get out"
# failure mode observed 2026-05-12.
GLOBAL_ITERATION_CAP = 10

# Tools each agent is allowed to call inside its tool-call loop. The
# researcher reads the doc + searches the web + writes findings; the
# reviewer ONLY reads the doc (its verdict is structured JSON output, no
# write side-effects). Keeping the reviewer's surface tight is a guard
# against rubber-stamping by accidentally modifying the doc it's judging.
RESEARCHER_TOOLS = ["read_doc", "web_search", "fetch_url", "append_to_doc"]
REVIEWER_TOOLS = ["read_doc"]

# Per-call turn caps inside dispatch_tool_calling. Researcher's loop can be
# long (5-8 tool calls expected, plus a few overshoots). Reviewer makes one
# read_doc call and produces JSON — 4 turns is generous.
RESEARCHER_MAX_TURNS = 20
REVIEWER_MAX_TURNS = 4


def _validate_reviewer_payload(payload: Any) -> str | None:
    """Validate the reviewer JSON shape. Returns an error string if
    invalid, None if OK. Lenient on optional fields; strict on the
    contract (verdict ∈ {iterate, ready_for_user}, criteria_status is a
    list of dicts with the required keys)."""
    if not isinstance(payload, dict):
        return "reviewer output is not a JSON object"
    verdict = payload.get("verdict")
    if verdict not in ("iterate", "ready_for_user"):
        return f"verdict must be 'iterate' or 'ready_for_user'; got {verdict!r}"
    cs = payload.get("criteria_status")
    if not isinstance(cs, list):
        return "criteria_status must be a list"
    for i, item in enumerate(cs):
        if not isinstance(item, dict):
            return f"criteria_status[{i}] is not an object"
        if "criterion" not in item or "met" not in item:
            return f"criteria_status[{i}] missing 'criterion' or 'met'"
        if not isinstance(item.get("met"), bool):
            return f"criteria_status[{i}].met must be a boolean"
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        return "notes must be a string"
    return None


def _build_researcher_message(notes_doc_id: str, iteration_number: int) -> str:
    """Construct the user-turn message for the researcher agent. Keeps it
    short — the doc itself is the context, the researcher reads it via
    `read_doc` as its first action."""
    return (
        f"This is research iteration {iteration_number}. "
        f"The workspace document's buffer_id is {notes_doc_id!r}. "
        "Start by calling read_doc, then advance the document toward "
        "the acceptance criteria per your system instructions."
    )


def _build_reviewer_message(
    notes_doc_id: str,
    iteration_number: int,
    prior_complaint: str | None = None,
) -> str:
    """Construct the user-turn message for the reviewer agent. On a JSON
    validation retry, includes the prior complaint so the reviewer can
    correct its output shape."""
    base = (
        f"This is review pass after research iteration {iteration_number}. "
        f"The workspace document's buffer_id is {notes_doc_id!r}. "
        "Call read_doc, then emit the JSON verdict per your system "
        "instructions."
    )
    if prior_complaint:
        base += (
            f"\n\nPrior attempt was rejected: {prior_complaint}. "
            "Re-emit the JSON object correctly, no preamble."
        )
    return base

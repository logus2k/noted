"""Doc-shape helpers for the research_topic workflow.

Three responsibilities, all touching the workspace markdown document the
research workflow keeps in `notes_buffer`:

- `_render_research_doc`: build the canonical section layout (Goal,
  Acceptance Criteria, Review Notes, Findings).
- `_update_doc_with_review`: persist a reviewer's structured verdict
  back into the doc (checkbox flips + iteration subsection).
- `_append_doc_termination_note`: stamp the doc with a final-state record
  so the artifact carries its own audit trail.

The handlers in this package call these directly — no MCP round-trip
needed, the handler runs in the same process as the notes_buffer store.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _render_research_doc(goal: str, criteria: list[str]) -> str:
    """Build the canonical research workspace markdown.

    Section order is deliberate:
      ## Goal
      ## Acceptance Criteria   ← workflow handler updates checkboxes
      ## Review Notes          ← workflow handler appends iteration notes
      ## Findings              ← researcher append_to_doc lands here (end)

    Putting Findings last lets the researcher use `append_to_doc`
    (append-only is concurrent-safe with user edits and uses fewer
    tokens than `replace_doc`); the workflow handler updates the
    earlier sections via read_doc + replace_doc when it has structured
    info to inject.
    """
    body = ["# Research Workspace", "", "## Goal", "", goal.strip(), ""]
    body.append("## Acceptance Criteria")
    body.append("")
    for c in criteria:
        body.append(f"- [ ] {c.strip()}")
    body.append("")
    body.append("## Review Notes")
    body.append("")
    body.append("_(empty — reviewer and user feedback land here)_")
    body.append("")
    body.append("## Findings")
    body.append("")
    body.append("_(empty — researcher will populate this section)_")
    body.append("")
    return "\n".join(body)


def _update_doc_with_review(
    notes_doc_id: str,
    criteria: list[str],
    reviewer_payload: dict,
    iteration_number: int,
) -> None:
    """Apply the reviewer's verdict to the doc:
    1. Tick checkboxes for criteria marked met (and untick those flipped
       back to unmet — covers the case where an earlier-iteration claim
       loses its citation).
    2. Append a new `### Iteration N` subsection to `## Review Notes`
       with the reviewer's prose feedback + a per-criterion summary.

    Uses read_doc + notes_buffer.replace directly (no `replace_doc` tool
    round-trip needed — handler runs in the same process as the buffer
    store).
    """
    from app.managers import notes_buffer

    buf = notes_buffer.get(notes_doc_id)
    if buf is None:
        return  # buffer disappeared; nothing to do
    content = buf.content or ""

    # 1) Checkbox update — build a met-set keyed by stripped criterion text.
    cs_by_text: dict[str, bool] = {}
    for cs in reviewer_payload.get("criteria_status", []):
        ctext = (cs.get("criterion") or "").strip()
        if ctext:
            cs_by_text[ctext] = bool(cs.get("met"))

    def _checkbox_line(line: str) -> str:
        # Match `- [ ] <text>` or `- [x] <text>`. Tolerate uppercase X.
        m = re.match(r"^(\s*[-*]\s*)\[([ xX])\](\s+)(.*)$", line)
        if not m:
            return line
        prefix, _, sp, rest = m.groups()
        ctext = rest.strip()
        if ctext in cs_by_text:
            marker = "x" if cs_by_text[ctext] else " "
            return f"{prefix}[{marker}]{sp}{rest}"
        return line

    lines = content.splitlines()
    out: list[str] = []
    in_criteria_section = False
    for line in lines:
        if line.startswith("## Acceptance Criteria"):
            in_criteria_section = True
            out.append(line)
            continue
        if in_criteria_section and line.startswith("## "):
            in_criteria_section = False
        if in_criteria_section:
            out.append(_checkbox_line(line))
        else:
            out.append(line)
    content = "\n".join(out)

    # 2) Append iteration notes into the Review Notes section. Pattern:
    #    locate `## Review Notes`, find the section's end (next `## ` or
    #    end-of-doc), insert the new subsection just before that boundary
    #    so subsequent sections (Findings) stay below.
    notes_text = (reviewer_payload.get("notes") or "").strip()
    verdict = reviewer_payload.get("verdict") or "iterate"
    met_count = sum(1 for cs in reviewer_payload.get("criteria_status", []) if cs.get("met"))
    total = len(reviewer_payload.get("criteria_status", []))

    subsection_lines = [
        f"### Iteration {iteration_number}",
        "",
        f"- verdict: **{verdict}**",
        f"- criteria met: {met_count}/{total}",
    ]
    if notes_text:
        subsection_lines.append(f"- reviewer notes: {notes_text}")
    subsection_lines.append("")  # trailing blank
    subsection = "\n".join(subsection_lines)

    # Find Review Notes section bounds.
    review_idx = content.find("\n## Review Notes")
    if review_idx >= 0:
        # End of section: next `\n## ` after the heading, or EOF.
        after_heading = review_idx + len("\n## Review Notes")
        next_h2 = content.find("\n## ", after_heading)
        if next_h2 == -1:
            insertion_point = len(content)
        else:
            insertion_point = next_h2
        # Drop the placeholder "_(empty — ...)_" marker on first write.
        section_body = content[after_heading:insertion_point]
        if "_(empty" in section_body:
            section_body = re.sub(
                r"\n_\(empty[^)]*\)_\n*",
                "\n",
                section_body,
                count=1,
            )
        section_body = section_body.rstrip("\n") + "\n\n" + subsection
        content = content[:after_heading] + section_body + content[insertion_point:]
    else:
        # No Review Notes section found (shouldn't happen if setup ran);
        # append at the end as a fallback.
        content = content.rstrip() + "\n\n## Review Notes\n\n" + subsection

    new_buf = notes_buffer.replace(notes_doc_id, content)
    if new_buf is not None:
        # Fire the same doc-changed broadcast the LLM tools emit so the
        # frontend viewer refreshes when the handler updates the doc.
        try:
            from app.workflow import doc_events
            doc_events.publish_doc_changed(new_buf)
        except Exception:
            logger.debug("doc_events broadcast failed in _update_doc_with_review", exc_info=True)


def _append_doc_termination_note(
    notes_doc_id: str,
    *,
    kind: str,
    iteration: int,
    detail: str,
) -> None:
    """Append a final-state record to the doc's Review Notes section so
    the document carries its own termination audit trail. The doc is the
    source of truth — anyone reading it later sees how / when the workflow
    ended regardless of whether they can also reach the workflow inspector.

    `kind` ∈ {"accepted", "stopped", "aborted", "cap_reached"}.
    """
    from app.managers import notes_buffer

    buf = notes_buffer.get(notes_doc_id)
    if buf is None:
        return
    content = buf.content or ""

    kind_label = {
        "accepted": "✓ Accepted",
        "stopped": "⊘ Stopped (partial)",
        "aborted": "✗ Aborted",
        "cap_reached": "⚠ Global iteration cap reached",
    }.get(kind, kind.title())

    subsection_lines = [
        f"### Final state ({kind_label}, iteration {iteration})",
        "",
        f"- detail: {detail}",
        "",
    ]
    subsection = "\n".join(subsection_lines)

    review_idx = content.find("\n## Review Notes")
    if review_idx >= 0:
        after_heading = review_idx + len("\n## Review Notes")
        next_h2 = content.find("\n## ", after_heading)
        insertion_point = len(content) if next_h2 == -1 else next_h2
        section_body = content[after_heading:insertion_point]
        section_body = section_body.rstrip("\n") + "\n\n" + subsection
        content = content[:after_heading] + section_body + content[insertion_point:]
    else:
        content = content.rstrip() + "\n\n## Review Notes\n\n" + subsection

    new_buf = notes_buffer.replace(notes_doc_id, content)
    if new_buf is not None:
        try:
            from app.workflow import doc_events
            doc_events.publish_doc_changed(new_buf)
        except Exception:
            logger.debug("doc_events broadcast failed in _append_doc_termination_note", exc_info=True)

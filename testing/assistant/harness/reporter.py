"""Write per-scenario Markdown reports + summary Markdown + flat CSV (D10).

Report layout (D7):
    testing/assistant/reports/<run-id>/
        summary.md
        results.csv
        per-scenario/
            <doc_id>-<scenario_id>.md
            ...

A `RunCollector` accumulates results as scenarios complete and writes all
reports + CSV rows at the end via `finalize()`. The per-scenario Markdown is
written as each scenario finishes so partial runs still produce useful output.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .scenario_loader import Scenario, Turn
from .stream_parser import ParsedResponse


# ── Data model ──────────────────────────────────────────────────────

@dataclass
class TurnRecord:
    turn_index: int
    user_request: str
    parsed: ParsedResponse
    chat_latency_ms: float
    deterministic_ok: bool
    deterministic_reasons: list[str]
    judge_verdict: Optional[dict]          # None if Layer-1 short-circuited
    judge_latency_ms: float = 0.0
    judge_tokens_in: int = 0
    judge_tokens_out: int = 0
    verdict: str = "FAIL"                   # PASS | FAIL | ERROR
    error_phase: str = ""                   # "", "chat", "judge"
    error_message: str = ""


@dataclass
class RunRecord:
    """One of N runs of a single scenario."""
    run_index: int
    fixture_log: list                       # list of FixtureResult
    turns: list[TurnRecord] = field(default_factory=list)
    verdict: str = "FAIL"                   # rolled up from turns
    error_phase: str = ""                   # set when verdict=ERROR
    error_message: str = ""


@dataclass
class ScenarioRecord:
    scenario: Scenario
    doc_id: str
    runs: list[RunRecord] = field(default_factory=list)

    @property
    def n_runs(self) -> int:
        return len(self.runs)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.runs if r.verdict == "PASS")

    @property
    def n_errored(self) -> int:
        return sum(1 for r in self.runs if r.verdict == "ERROR")

    @property
    def aggregate_verdict(self) -> str:
        """D11: scenario-level verdict across N runs."""
        if self.n_errored > 0:
            return f"ERROR ({self.n_passed}/{self.n_runs})"
        if self.n_passed == self.n_runs:
            return f"PASS ({self.n_passed}/{self.n_runs})"
        return f"FAIL ({self.n_passed}/{self.n_runs})"


# ── Collector + writers ─────────────────────────────────────────────

CSV_HEADER = [
    "timestamp",
    "run_id",
    "scenario_id",
    "doc_id",
    "run_index",
    "verdict",
    "tool_call_check",
    "answer_check",
    "procedural_check",
    "deficiencies",
    "judge_rationale",
    "user_request",
    "expected_tools",
    "called_tools",
    "error_phase",
    "error_message",
    "chat_latency_ms",
    "chat_tokens_in",
    "chat_tokens_out",
    "judge_latency_ms",
    "judge_tokens_in",
    "judge_tokens_out",
    "judge_prompt_hash",
]


class RunCollector:
    def __init__(self, run_id: str, report_dir: Path, judge_prompt_hash: str, model: str):
        self.run_id = run_id
        self.report_dir = report_dir
        self.per_scenario_dir = report_dir / "per-scenario"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.per_scenario_dir.mkdir(parents=True, exist_ok=True)
        self.judge_prompt_hash = judge_prompt_hash
        self.model = model
        self.started_at = datetime.now(timezone.utc)
        self.scenarios: list[ScenarioRecord] = []
        # Single consolidated CSV across every run. Lives at the report-dir
        # root (one level above per-run folders). One row per unique
        # scenario_id - a rerun replaces the prior row rather than appending
        # a new one, so the file reflects the CURRENT state of every scenario.
        history_dir = report_dir.parent
        history_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = history_dir / "_history.csv"
        # Opened lazily in _append_csv_rows so we can read+rewrite atomically.
        self._csv_file = None
        self._csv_writer = None

    def add_scenario(self, record: ScenarioRecord) -> None:
        self.scenarios.append(record)
        self._write_per_scenario_md(record)
        self._append_csv_rows(record)

    # ── CSV rows ────────────────────────────────────────────────────

    def _load_existing_history_locked(self, f) -> list[list[str]]:
        """Read rows from an already-locked file handle."""
        f.seek(0)
        reader = csv.reader(f)
        try:
            next(reader)  # skip header
        except StopIteration:
            return []
        return [row for row in reader if row and len(row) == len(CSV_HEADER)]

    def _rewrite_history_locked(self, f, rows: list[list[str]]) -> None:
        """Rewrite under an already-locked file handle."""
        f.seek(0)
        f.truncate()
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(r)
        f.flush()
        import os
        os.fsync(f.fileno())

    def _append_csv_rows(self, record: ScenarioRecord) -> None:
        """Read-filter-rewrite under an exclusive file lock so concurrent
        harness processes don't shred the CSV. Drops malformed rows defensively."""
        full_scenario_id = f"{record.doc_id}::{record.scenario.scenario_id}"

        # Build the new row(s) first - no locking needed.
        new_rows: list[list[str]] = []
        for run in record.runs:
            # Pick the first turn's metrics for the CSV row. Multi-turn
            # scenarios sum latencies/tokens so one row reflects the whole
            # scenario's run, not just the first turn.
            chat_latency = sum(t.chat_latency_ms for t in run.turns)
            chat_in = sum(t.parsed.usage.get("input_tokens", 0) for t in run.turns)
            chat_out = sum(t.parsed.usage.get("output_tokens", 0) for t in run.turns)
            judge_latency = sum(t.judge_latency_ms for t in run.turns)
            judge_in = sum(t.judge_tokens_in for t in run.turns)
            judge_out = sum(t.judge_tokens_out for t in run.turns)

            deficiencies = []
            tool_check = answer_check = proc_check = "n/a"
            judge_rationale = ""
            error_phase = run.error_phase
            error_message = run.error_message
            # Roll up per-turn judge verdicts into scenario-level summary for the CSV row
            if run.turns and run.verdict != "ERROR":
                first_judged = next((t for t in run.turns if t.judge_verdict), None)
                if first_judged:
                    jv = first_judged.judge_verdict
                    tool_check = jv.get("tool_call_check", "n/a")
                    answer_check = jv.get("answer_check", "n/a")
                    proc_check = jv.get("procedural_check", "n/a")
                    deficiencies = list(jv.get("deficiencies") or [])
                    judge_rationale = jv.get("rationale") or ""
                # If deterministic failed on any turn, annotate it
                for t in run.turns:
                    if not t.deterministic_ok:
                        deficiencies = t.deterministic_reasons + deficiencies

            # Snapshot first turn for user_request + expected/called tools. Multi-turn
            # scenarios: subsequent turns visible only in per-scenario Markdown.
            user_request = ""
            expected_tools = ""
            called_tools = ""
            if record.scenario.turns:
                first_turn_spec = record.scenario.turns[0]
                user_request = first_turn_spec.user_request
                expected_tools = ", ".join(
                    t.name for t in first_turn_spec.expected_tools_called
                )
            if run.turns:
                called_tools = ", ".join(
                    tc.name for tc in run.turns[0].parsed.tool_calls
                )

            row = [
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                self.run_id,
                full_scenario_id,
                record.doc_id,
                run.run_index,
                run.verdict,
                tool_check,
                answer_check,
                proc_check,
                "; ".join(deficiencies),
                judge_rationale,
                user_request,
                expected_tools,
                called_tools,
                error_phase,
                error_message,
                f"{chat_latency:.0f}",
                chat_in,
                chat_out,
                f"{judge_latency:.0f}",
                judge_in,
                judge_out,
                self.judge_prompt_hash,
            ]
            new_rows.append(row)

        # Now atomically read+merge+write under an exclusive lock so concurrent
        # harness processes don't interleave writes.
        import fcntl
        mode = "r+" if self.csv_path.exists() else "w+"
        with self.csv_path.open(mode, newline="", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                existing = self._load_existing_history_locked(f)
                # Preserve a prior `FAIL-ESCALATED` marker across reruns: once
                # a scenario has been escalated, a rerun that still FAILs must
                # keep the ESCALATED marker so the testing monitor can render
                # it differently. Only a genuine PASS (or an explicit manual
                # edit to plain FAIL) lifts the escalation. Column index 5 is
                # `verdict` per CSV_HEADER.
                verdict_idx = CSV_HEADER.index("verdict")
                previous = next(
                    (r for r in existing if len(r) > 2 and r[2] == full_scenario_id),
                    None,
                )
                if previous and previous[verdict_idx] == "FAIL-ESCALATED":
                    for row in new_rows:
                        if row[verdict_idx] == "FAIL":
                            row[verdict_idx] = "FAIL-ESCALATED"
                existing = [r for r in existing if len(r) > 2 and r[2] != full_scenario_id]
                self._rewrite_history_locked(f, existing + new_rows)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # ── Per-scenario Markdown ────────────────────────────────────────

    def _write_per_scenario_md(self, record: ScenarioRecord) -> None:
        scenario = record.scenario
        filename = f"{record.doc_id}-{scenario.scenario_id}.md"
        path = self.per_scenario_dir / filename

        lines: list[str] = []
        lines.append(f"# {record.doc_id}::{scenario.scenario_id} - {scenario.title}")
        lines.append("")
        lines.append(f"**Scenario verdict:** `{record.aggregate_verdict}`")
        lines.append("")
        lines.append("## Metadata")
        lines.append("")
        lines.append(f"- Doc: `{record.doc_id}`")
        lines.append(f"- Tags: `{scenario.tags}`")
        lines.append(f"- Multi-turn: `{scenario.is_multi_turn}` ({len(scenario.turns)} turns)")
        lines.append(f"- Judge prompt hash: `{self.judge_prompt_hash}`")
        lines.append("")

        for i, run in enumerate(record.runs):
            lines.append(f"## Run {run.run_index + 1} / {len(record.runs)}")
            lines.append("")
            lines.append(f"**Verdict:** `{run.verdict}`")
            if run.error_phase:
                lines.append(f"**Error phase:** `{run.error_phase}`")
                lines.append(f"**Error message:** {run.error_message}")
            lines.append("")
            lines.append("### Setup")
            lines.append("")
            if run.fixture_log:
                for f in run.fixture_log:
                    lines.append(f"- `[{f.action}]` `{f.fixture}`: {f.detail}")
            else:
                lines.append("- (no fixtures declared)")
            lines.append("")

            for t in run.turns:
                lines.append(f"### Turn {t.turn_index + 1}")
                lines.append("")
                lines.append(f"**User request:** `{t.user_request}`")
                lines.append("")
                lines.append(f"**Tool calls ({len(t.parsed.tool_calls)}):**")
                if t.parsed.tool_calls:
                    for tc in t.parsed.tool_calls:
                        lines.append(f"- `{tc.name}({json.dumps(tc.args, ensure_ascii=False)})`")
                        if tc.result:
                            truncated = " _(truncated)_" if tc.result_truncated else ""
                            lines.append(f"  - result{truncated}:")
                            lines.append("")
                            lines.append("    ```")
                            for rl in tc.result.splitlines():
                                lines.append(f"    {rl}")
                            lines.append("    ```")
                else:
                    lines.append("- (none)")
                lines.append("")
                if t.parsed.skills:
                    lines.append(f"**Auto-injected skills:** `{t.parsed.skills}`")
                    lines.append("")
                lines.append("**Reasoning (`<think>` block):**")
                lines.append("")
                lines.append("```")
                lines.append(t.parsed.reasoning or "(none captured)")
                lines.append("```")
                lines.append("")
                lines.append("**Answer:**")
                lines.append("")
                lines.append("```")
                lines.append(t.parsed.answer or "(empty)")
                lines.append("```")
                lines.append("")
                lines.append("**Deterministic check (Layer 1):**")
                lines.append("")
                if t.deterministic_ok:
                    lines.append("- `OK`")
                else:
                    lines.append(f"- `BAD` - {len(t.deterministic_reasons)} reason(s):")
                    for r in t.deterministic_reasons:
                        lines.append(f"  - {r}")
                lines.append("")
                lines.append("**Judge verdict (Layer 2):**")
                lines.append("")
                if t.judge_verdict is None:
                    lines.append("- `n/a` (skipped because Layer 1 failed)")
                else:
                    jv = t.judge_verdict
                    lines.append(f"- verdict: `{jv.get('verdict')}`")
                    lines.append(f"- tool_call_check: `{jv.get('tool_call_check')}`")
                    lines.append(f"- answer_check: `{jv.get('answer_check')}`")
                    lines.append(f"- procedural_check: `{jv.get('procedural_check')}`")
                    if jv.get("deficiencies"):
                        lines.append(f"- deficiencies: `{jv.get('deficiencies')}`")
                    lines.append(f"- rationale: {jv.get('rationale')}")
                lines.append("")
                lines.append("**Metrics:**")
                lines.append("")
                lines.append(f"- `chat_latency_ms`: {t.chat_latency_ms:.0f}")
                lines.append(f"- `chat_tokens_in/out`: {t.parsed.usage.get('input_tokens', '?')}/{t.parsed.usage.get('output_tokens', '?')}")
                lines.append(f"- `judge_latency_ms`: {t.judge_latency_ms:.0f}")
                lines.append(f"- `judge_tokens_in/out`: {t.judge_tokens_in}/{t.judge_tokens_out}")
                lines.append("")

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── Summary + close ──────────────────────────────────────────────

    def finalize(self) -> None:
        self._write_summary_md()

    def _write_summary_md(self) -> None:
        path = self.report_dir / "summary.md"
        ended_at = datetime.now(timezone.utc)
        total = len(self.scenarios)
        scenario_runs = [r for s in self.scenarios for r in s.runs]
        total_runs = len(scenario_runs)
        passed = sum(1 for r in scenario_runs if r.verdict == "PASS")
        failed = sum(1 for r in scenario_runs if r.verdict == "FAIL")
        errored = sum(1 for r in scenario_runs if r.verdict == "ERROR")

        total_chat_tokens = sum(
            t.parsed.usage.get("input_tokens", 0) + t.parsed.usage.get("output_tokens", 0)
            for s in self.scenarios for r in s.runs for t in r.turns
        )
        total_judge_tokens = sum(
            t.judge_tokens_in + t.judge_tokens_out
            for s in self.scenarios for r in s.runs for t in r.turns
        )

        wall_clock_s = (ended_at - self.started_at).total_seconds()

        lines: list[str] = [
            f"# Test run `{self.run_id}`",
            "",
            f"- Started: {self.started_at.isoformat(timespec='seconds')}",
            f"- Ended:   {ended_at.isoformat(timespec='seconds')}",
            f"- Wall-clock: {wall_clock_s:.1f} s",
            f"- Model under test: `{self.model}`",
            f"- Judge prompt hash: `{self.judge_prompt_hash}`",
            "",
            "## Aggregate",
            "",
            f"- Scenarios: {total}",
            f"- Total runs (scenarios x runs-per-scenario): {total_runs}",
            f"- **PASS:** {passed}",
            f"- **FAIL:** {failed}",
            f"- **ERROR:** {errored}",
        ]
        if passed + failed > 0:
            pass_rate = passed / (passed + failed) * 100.0
            lines.append(f"- Pass rate (PASS / (PASS+FAIL), excluding ERROR): {pass_rate:.1f}%")
        lines.extend([
            "",
            f"- Total chat tokens: {total_chat_tokens}",
            f"- Total judge tokens: {total_judge_tokens}",
            "",
            "## Scenarios",
            "",
            "| Scenario | Verdict | Passed/Runs | Link |",
            "|---|---|---|---|",
        ])
        for s in self.scenarios:
            full_id = f"{s.doc_id}::{s.scenario.scenario_id}"
            link = f"per-scenario/{s.doc_id}-{s.scenario.scenario_id}.md"
            verdict = s.aggregate_verdict.split(" ")[0]  # just PASS/FAIL/ERROR
            lines.append(f"| `{full_id}` | `{verdict}` | {s.n_passed}/{s.n_runs} | [open]({link}) |")

        # Aggregate deficiency phrases (most common)
        phrase_counts: dict[str, int] = {}
        for s in self.scenarios:
            for run in s.runs:
                for t in run.turns:
                    if t.judge_verdict:
                        for d in t.judge_verdict.get("deficiencies") or []:
                            phrase_counts[d] = phrase_counts.get(d, 0) + 1
                    for r in t.deterministic_reasons:
                        phrase_counts[f"[det] {r}"] = phrase_counts.get(f"[det] {r}", 0) + 1
        if phrase_counts:
            lines.extend(["", "## Most common deficiencies", ""])
            for phrase, n in sorted(phrase_counts.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"- `{n}x` {phrase}")

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def default_run_id() -> str:
    """ISO timestamp + microsecond suffix so two runs in the same second collide."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond:06d}"

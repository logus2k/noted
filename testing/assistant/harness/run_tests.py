"""CLI entry point for the Assistant test harness.

M2 scope: run one scenario (single or multi-turn) N times (default 1),
apply deterministic checks (Layer 1), invoke noted_judge when Layer 1 passes
(Layer 2), write per-scenario Markdown + summary Markdown + flat CSV.

Usage:
    python -m testing.assistant.harness.run_tests \\
        --doc testing/assistant/tools/get_serving_status.yaml \\
        --scenario S1 \\
        [--runs 3] \\
        [--run-id my-run-2026-04-20] \\
        [--report-dir testing/assistant/reports] \\
        [--judge-prompt-path /path/to/noted_judge_system_prompt.txt]

Dependencies:
  - Python 3.10+
  - requests, PyYAML
  - noted backend reachable at NOTED_BASE_URL (default http://localhost:8123)
  - agent_server reachable at AGENT_SERVER_URL (default http://localhost:7701)
  - `noted_judge` preset loaded
  - Sandbox staged via stage_sandbox.py (see M0)
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Optional

from .deterministic import check_turn
from .driver import DriverError, call_chat, call_confirm, merge_followup
from .fixtures import FixtureError, apply_prerequisites
from .judge import JudgeError, build_envelope, compute_judge_prompt_hash, invoke_judge
from .reporter import (
    RunCollector,
    RunRecord,
    ScenarioRecord,
    TurnRecord,
    default_run_id,
)
from .scenario_loader import Doc, Scenario, Turn, find_scenario, load_doc


def _setup_summary(scenario: Scenario, fixture_log: list) -> str:
    parts = [f"project={scenario.setup.project}"]
    if scenario.setup.notebook:
        parts.append(f"notebook={scenario.setup.notebook}")
    if scenario.setup.active_run_id:
        parts.append(f"active_run_id={scenario.setup.active_run_id}")
    if fixture_log:
        parts.append("fixtures=[" + ", ".join(f"{r.fixture}:{r.action}" for r in fixture_log) + "]")
    return "; ".join(parts)


def _build_context_descriptor(scenario: Scenario) -> dict:
    ctx: dict = {"project_id": scenario.setup.project or "default"}
    if scenario.setup.notebook:
        ctx["notebook_path"] = scenario.setup.notebook
    if scenario.setup.file_path:
        ctx["file_path"] = scenario.setup.file_path
        # Real noted's frontend sends file_content alongside file_path
        # whenever a file is open in the editor. Without file_content,
        # _file_block emits only a "use get_file_contents" hint, which
        # forces the model to fetch the file - making scenarios that
        # forbid get_file_contents impossible. Simulate the editor state
        # by reading the file from disk.
        try:
            from pathlib import Path as _Path
            disk = _Path("/app/data/projects") / (scenario.setup.project or "") / scenario.setup.file_path
            if disk.is_file():
                ctx["file_content"] = disk.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if scenario.setup.active_run_id:
        ctx["active_run_id"] = scenario.setup.active_run_id
    if scenario.setup.selected_cell_indices:
        ctx["selected_cell_indices"] = scenario.setup.selected_cell_indices
    return ctx


def _expected_tools_as_dict(turn: Turn) -> list[dict]:
    return [
        {"name": t.name, "exact_count": t.exact_count, "args_match": t.args_match}
        for t in turn.expected_tools_called
    ]


def _actual_tools_as_dict(parsed) -> list[dict]:
    return [
        {
            "name": tc.name,
            "args": tc.args,
            "result": tc.result,
            "result_truncated": tc.result_truncated,
        }
        for tc in parsed.tool_calls
    ]


def _print_section(title: str, body: str = "") -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    if body:
        print(body)


# ── Core: one run of a scenario ──────────────────────────────────────

def run_scenario_once(
    scenario: Scenario,
    run_index: int,
    judge_prompt_path: Optional[str],
) -> RunRecord:
    """Execute one full pass through a scenario (all its turns)."""
    run = RunRecord(run_index=run_index, fixture_log=[])

    # ── Fixture staging (ERROR on any failure per D8) ──
    try:
        run.fixture_log = apply_prerequisites(scenario.setup.prerequisites)
    except FixtureError as e:
        run.verdict = "ERROR"
        run.error_phase = "setup"
        run.error_message = f"{e.fixture_name}: {e.detail}"
        return run

    for r in run.fixture_log:
        print(f"  [{r.action}] {r.fixture}: {r.detail}")

    # ── Single conversation across turns (D12 memory key) ──
    client_id = f"harness-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"
    setup_summary = _setup_summary(scenario, run.fixture_log)
    context_descriptor = _build_context_descriptor(scenario)

    all_turn_passes = True

    for i, turn in enumerate(scenario.turns):
        _print_section(f"RUN {run_index + 1} / TURN {i + 1}")
        print(f'> user: "{turn.user_request}"')

        # ── Chat call ──
        try:
            parsed, chat_latency_ms = call_chat(
                message=turn.user_request,
                client_id=client_id,
                context_descriptor=context_descriptor,
            )
        except DriverError as e:
            print(f"ERROR (chat): {e}")
            run.verdict = "ERROR"
            run.error_phase = "chat"
            run.error_message = str(e)
            # Keep any turns we already captured, bail out of the turn loop
            return run

        print(f"\ntool_calls ({len(parsed.tool_calls)}):")
        for tc in parsed.tool_calls:
            print(f"  - {tc.name}({json.dumps(tc.args, ensure_ascii=False)})")
        if parsed.skills:
            print(f"auto-injected skills: {parsed.skills}")

        # ── Write-tool approval (D8 + honest end-to-end judging) ──
        # If the Assistant triggered a write-tool approval panel, auto-approve
        # and parse the follow-up stream. This gives the judge a complete
        # turn (pre-call reasoning + tool execution + post-execution answer)
        # rather than judging a half-turn ending at the pending_action frame.
        if parsed.pending_action_id:
            print(f"\n[pending_action id={parsed.pending_action_id}] auto-approving and consuming follow-up stream...")
            try:
                followup, confirm_latency_ms = call_confirm(
                    action_id=parsed.pending_action_id,
                    approved=True,
                )
                parsed = merge_followup(parsed, followup)
                chat_latency_ms += confirm_latency_ms
                print(f"follow-up merged. combined chat_latency={chat_latency_ms:.0f}ms")
            except DriverError as e:
                print(f"ERROR (confirm): {e}")
                run.verdict = "ERROR"
                run.error_phase = "confirm"
                run.error_message = str(e)
                return run

        # ── Layer 1: deterministic ──
        det = check_turn(turn, parsed.tool_calls)
        print(f"\ndeterministic check: {'OK' if det.ok else 'BAD'}")
        for r in det.reasons:
            print(f"  - {r}")

        # ── Layer 2: judge (only if Layer 1 passed) ──
        judge_verdict = None
        judge_latency = 0.0
        judge_in = 0
        judge_out = 0
        if det.ok:
            envelope = build_envelope(
                scenario_id=f"{scenario.scenario_id} (run {run_index + 1}, turn {i + 1})",
                user_request=turn.user_request,
                expected_tools_called=_expected_tools_as_dict(turn),
                expected_tools_NOT_called=turn.expected_tools_NOT_called,
                expected_answer_focus=turn.expected_answer_focus,
                setup_summary=setup_summary,
                actual_tools_called=_actual_tools_as_dict(parsed),
                reasoning=parsed.reasoning,
                answer=parsed.answer,
                workspace_context=parsed.context_block,
                workspace_context_truncated=parsed.context_block_truncated,
            )
            try:
                verdict = invoke_judge(envelope)
            except JudgeError as e:
                print(f"ERROR (judge): {e}")
                run.verdict = "ERROR"
                run.error_phase = "judge"
                run.error_message = str(e)
                # Record the partial turn, then bail
                run.turns.append(TurnRecord(
                    turn_index=i,
                    user_request=turn.user_request,
                    parsed=parsed,
                    chat_latency_ms=chat_latency_ms,
                    deterministic_ok=det.ok,
                    deterministic_reasons=det.reasons,
                    judge_verdict=None,
                    verdict="ERROR",
                    error_phase="judge",
                    error_message=str(e),
                ))
                return run
            judge_verdict = verdict.raw
            judge_latency = verdict.latency_ms
            judge_in = verdict.tokens_in
            judge_out = verdict.tokens_out
            print(
                f"\njudge: {verdict.verdict} "
                f"tool={verdict.tool_call_check} answer={verdict.answer_check} "
                f"proc={verdict.procedural_check}"
            )
            if verdict.deficiencies:
                print(f"  deficiencies: {verdict.deficiencies}")
            print(f"  rationale: {verdict.rationale}")
            turn_verdict = verdict.verdict
        else:
            turn_verdict = "FAIL"

        all_turn_passes = all_turn_passes and (turn_verdict == "PASS")

        run.turns.append(TurnRecord(
            turn_index=i,
            user_request=turn.user_request,
            parsed=parsed,
            chat_latency_ms=chat_latency_ms,
            deterministic_ok=det.ok,
            deterministic_reasons=det.reasons,
            judge_verdict=judge_verdict,
            judge_latency_ms=judge_latency,
            judge_tokens_in=judge_in,
            judge_tokens_out=judge_out,
            verdict=turn_verdict,
        ))

    run.verdict = "PASS" if all_turn_passes else "FAIL"
    return run


# ── Multi-run loop ──────────────────────────────────────────────────

def _write_current_marker(collector: RunCollector, scenario: Scenario, doc_id: str) -> None:
    """Drop _current.json next to _history.csv so the progress dashboard can
    highlight which scenario is running right now. Best-effort; failures are
    not fatal."""
    try:
        import json
        from datetime import datetime, timezone
        marker = collector.csv_path.parent / "_current.json"
        with marker.open("w", encoding="utf-8") as f:
            json.dump({
                "scenario_id": f"{doc_id}::{scenario.scenario_id}",
                "doc_id": doc_id,
                "title": scenario.title,
                "user_request": scenario.turns[0].user_request if scenario.turns else "",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, f)
    except Exception:
        pass


def _clear_current_marker(collector: RunCollector) -> None:
    try:
        marker = collector.csv_path.parent / "_current.json"
        if marker.exists():
            marker.unlink()
    except Exception:
        pass


def run_scenario(
    scenario: Scenario,
    doc_id: str,
    collector: RunCollector,
    runs: int,
    judge_prompt_path: Optional[str],
) -> None:
    _print_section(f"SCENARIO: {doc_id}::{scenario.scenario_id} - {scenario.title}")
    print(f"Tags: {scenario.tags}")
    print(f"Turns: {len(scenario.turns)}  | Runs: {runs}")

    record = ScenarioRecord(scenario=scenario, doc_id=doc_id, runs=[])
    _write_current_marker(collector, scenario, doc_id)

    try:
        for i in range(runs):
            if runs > 1:
                _print_section(f"STARTING RUN {i + 1} / {runs}")
            run_result = run_scenario_once(scenario, run_index=i, judge_prompt_path=judge_prompt_path)
            record.runs.append(run_result)
            print(f"\n[run {i + 1}] verdict: {run_result.verdict}")
            if run_result.error_message:
                print(f"  error: {run_result.error_message}")

        _print_section("SCENARIO VERDICT", record.aggregate_verdict)
        collector.add_scenario(record)
    finally:
        _clear_current_marker(collector)


# ── Selection helpers ───────────────────────────────────────────────

def _load_failed_scenario_ids(report_dir: Path, run_id: str) -> list[str]:
    """Read a prior run's results.csv and return scenario_ids with verdict=FAIL.
    Each entry is "doc_id::scenario_id" (the CSV's scenario_id column)."""
    import csv
    csv_path = report_dir / run_id / "results.csv"
    if not csv_path.is_file():
        print(f"ERROR: results.csv not found at {csv_path}", file=sys.stderr)
        sys.exit(2)
    failed: list[str] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("verdict") == "FAIL":
                sid = row.get("scenario_id", "")
                if sid and sid not in failed:
                    failed.append(sid)
    return failed


def _collect_docs_for_selection(args) -> list[Path]:
    """Resolve CLI flags into a list of YAML doc paths.
    Selection priority: --doc > --category > --all.
    (--rerun-failures-from is handled separately in main, before this is called.)"""
    testing_root = Path(args.testing_root)
    out: list[Path] = []
    if args.doc:
        p = Path(args.doc)
        if not p.is_file():
            print(f"ERROR: doc not found: {p}", file=sys.stderr)
            sys.exit(2)
        out.append(p)
        return out
    if args.category:
        root = testing_root / args.category
        if not root.is_dir():
            print(f"ERROR: {root} is not a directory", file=sys.stderr)
            sys.exit(2)
        out.extend(sorted(root.glob("*.yaml")))
        return out
    if args.all:
        for sub in ("skills", "tools"):
            root = testing_root / sub
            if root.is_dir():
                out.extend(sorted(root.glob("*.yaml")))
        return out
    print("ERROR: must supply one of --doc / --category / --all", file=sys.stderr)
    sys.exit(2)


# ── CLI ─────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_tests",
        description="noted Assistant test harness.",
    )
    # Selection
    sel = p.add_argument_group("selection")
    sel.add_argument("--doc", default=None, help="Path to a single scenario YAML file.")
    sel.add_argument("--scenario", default=None,
                     help="Single scenario_id to run from --doc (e.g. S1). "
                          "If omitted, all scenarios in the doc run.")
    sel.add_argument("--category", choices=["skills", "tools"], default=None,
                     help="Run every YAML under testing/assistant/<category>/.")
    sel.add_argument("--all", action="store_true",
                     help="Run every YAML under testing/assistant/{skills,tools}/.")
    sel.add_argument("--rerun-failures-from", default=None, metavar="RUN_ID",
                     help="Replay only the FAILed scenarios from a prior run (by run-id directory name). "
                          "Reads <report-dir>/<run-id>/results.csv and selects rows with verdict=FAIL.")

    # Run config
    run = p.add_argument_group("run config")
    run.add_argument("--runs", type=int, default=1,
                     help="Runs per scenario (default 1). D11: PASS only if all runs pass.")
    run.add_argument("--run-id", default=None,
                     help="Name for this run's report subdir. Default: ISO timestamp.")
    run.add_argument("--report-dir", default="testing/assistant/reports",
                     help="Root directory where per-run reports are written.")
    run.add_argument("--judge-prompt-path", default=None,
                     help="Path to noted_judge_system_prompt.txt (for reproducibility hash).")
    run.add_argument("--model", default="local",
                     help="Model label for the summary report.")
    run.add_argument("--testing-root", default="testing/assistant",
                     help="Root dir for test docs (default testing/assistant).")

    # Preflight + debug
    misc = p.add_argument_group("misc")
    misc.add_argument("--lint", choices=["strict", "warn", "off"], default="strict",
                      help="Pre-flight lint: strict (abort on issues), warn (print + continue), off.")
    misc.add_argument("--list", action="store_true",
                      help="List scenarios that would run and exit (no chat/judge calls).")
    misc.add_argument("--dry-run", action="store_true",
                      help="Apply fixtures + print selection but skip chat/judge calls.")
    return p.parse_args()


def _run_lint(args) -> int:
    """Returns 0 if clean (or --lint=off/warn), non-zero if strict+issues."""
    from . import lint as lint_mod
    issues = lint_mod.lint(Path(args.testing_root))
    if not issues:
        print(f"lint OK ({args.testing_root})")
        return 0
    if args.lint == "off":
        return 0
    print(f"lint found {len(issues)} issue(s):")
    for i, msg in enumerate(issues, 1):
        print(f"  {i}. {msg}")
    if args.lint == "warn":
        print("[continuing because --lint=warn]")
        return 0
    print("[aborting because --lint=strict]")
    return 2


def main() -> int:
    args = _parse_args()

    # ── Preflight lint ──
    if not args.list:
        rc = _run_lint(args)
        if rc != 0:
            return rc

    # ── Resolve selection ──
    selected: list[tuple[Doc, Scenario]] = []

    if args.rerun_failures_from:
        # Replay only scenarios that FAILed in a prior run.
        prior_run_id = args.rerun_failures_from
        failed_ids = _load_failed_scenario_ids(Path(args.report_dir), prior_run_id)
        if not failed_ids:
            print(f"No FAILed scenarios found in {prior_run_id}. Nothing to replay.")
            return 0
        print(f"Replaying {len(failed_ids)} FAILed scenario(s) from run '{prior_run_id}':")
        for sid in failed_ids:
            print(f"  {sid}")
        # Load every doc under testing_root so we can look up scenarios by doc_id
        by_doc_id: dict[str, Doc] = {}
        for sub in ("skills", "tools"):
            for yp in sorted((Path(args.testing_root) / sub).glob("*.yaml")):
                try:
                    d = load_doc(yp)
                    by_doc_id[d.doc_id] = d
                except Exception as e:
                    print(f"WARN: failed to load {yp.name}: {e}", file=sys.stderr)
        for sid in failed_ids:
            if "::" not in sid:
                print(f"WARN: skipping malformed scenario_id '{sid}'", file=sys.stderr)
                continue
            doc_id, scenario_id = sid.split("::", 1)
            d = by_doc_id.get(doc_id)
            if d is None:
                print(f"WARN: doc '{doc_id}' not found; skipping {sid}", file=sys.stderr)
                continue
            try:
                s = find_scenario(d, scenario_id)
            except KeyError:
                print(f"WARN: scenario '{sid}' not found (may have been removed); skipping", file=sys.stderr)
                continue
            selected.append((d, s))
    else:
        doc_paths = _collect_docs_for_selection(args)
        docs: list[Doc] = []
        for p in doc_paths:
            try:
                docs.append(load_doc(p))
            except Exception as e:
                print(f"ERROR: failed to load {p.name}: {e}", file=sys.stderr)
                return 2

        if args.scenario:
            if len(docs) != 1:
                print("ERROR: --scenario requires exactly one --doc", file=sys.stderr)
                return 2
            selected.append((docs[0], find_scenario(docs[0], args.scenario)))
        else:
            for d in docs:
                for s in d.scenarios:
                    selected.append((d, s))

    if args.list:
        print(f"Would run {len(selected)} scenario(s):\n")
        for d, s in selected:
            print(f"  {d.doc_id}::{s.scenario_id}  -  {s.title}  [turns={len(s.turns)}]")
        return 0

    if args.runs < 1:
        print("ERROR: --runs must be >= 1", file=sys.stderr)
        return 2

    # ── Set up reporter ──
    run_id = args.run_id or default_run_id()
    report_dir = Path(args.report_dir) / run_id
    prompt_hash = compute_judge_prompt_hash(args.judge_prompt_path)

    collector = RunCollector(
        run_id=run_id,
        report_dir=report_dir,
        judge_prompt_hash=prompt_hash,
        model=args.model,
    )

    # ── Main loop ──
    try:
        for d, s in selected:
            if args.dry_run:
                _print_section(f"DRY RUN: {d.doc_id}::{s.scenario_id}")
                # Apply fixtures only, skip chat/judge
                try:
                    fx_log = apply_prerequisites(s.setup.prerequisites)
                    for r in fx_log:
                        print(f"  [{r.action}] {r.fixture}: {r.detail}")
                except FixtureError as e:
                    print(f"  ERROR: {e}")
                continue
            run_scenario(
                scenario=s,
                doc_id=d.doc_id,
                collector=collector,
                runs=args.runs,
                judge_prompt_path=args.judge_prompt_path,
            )
    finally:
        collector.finalize()

    if args.dry_run:
        _print_section("DRY RUN COMPLETE", "No chat/judge calls were made.")
        return 0

    _print_section("REPORTS WRITTEN", str(report_dir.resolve()))
    print(f"  summary.md")
    print(f"  results.csv")
    print(f"  per-scenario/  ({len(collector.scenarios)} file(s))")

    # Exit code aggregates across all scenarios: PASS if all pass, ERROR if any error, else FAIL
    if not collector.scenarios:
        return 2
    any_error = any(any(r.verdict == "ERROR" for r in s.runs) for s in collector.scenarios)
    any_fail = any(any(r.verdict == "FAIL" for r in s.runs) for s in collector.scenarios)
    if any_error:
        return 2
    if any_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

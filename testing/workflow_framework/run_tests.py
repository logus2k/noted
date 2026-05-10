"""Workflow framework test runner.

Drives `create_tool` against fixed YAML scenarios, bypassing the planner
so each trial is deterministic. Records per-trial: workflow status, which
step failed (if any), failure tail, post-publish live-call result.

Usage:
    python testing/workflow_framework/run_tests.py
    python testing/workflow_framework/run_tests.py --runs 5
    python testing/workflow_framework/run_tests.py --scenario sapo_weather --runs 3
    python testing/workflow_framework/run_tests.py --noted http://localhost:8123

Reports a Markdown summary per run plus a CSV of per-trial outcomes.
Workflow snapshots (incl. llm_calls.jsonl) are preserved for post-hoc
analysis — never deleted by this harness.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
SCENARIOS_DIR = HERE / "scenarios"
REPORTS_DIR = HERE / "reports"

DEFAULT_NOTED = "http://localhost:8123"
WORKFLOW_TIMEOUT_S = 240
POLL_INTERVAL_S = 4


# ─── HTTP helpers ────────────────────────────────────────────────────


class HTTPError(Exception):
    pass


def http_json(method: str, url: str, body=None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPError(f"HTTP {e.code} on {method} {url}: {e.read()[:300].decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise HTTPError(f"URLError on {method} {url}: {e}") from e


# ─── Scenario loading ───────────────────────────────────────────────


def load_scenarios(filter_id: str | None) -> list[dict]:
    files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    out = []
    for fp in files:
        if fp.stem.startswith("_"):
            continue
        with open(fp) as f:
            doc = yaml.safe_load(f)
        if not doc or "id" not in doc:
            continue
        if filter_id and doc["id"] != filter_id:
            continue
        out.append(doc)
    return out


# ─── Workflow trigger + wait ────────────────────────────────────────


def trigger_create_tool(noted: str, inputs: dict) -> str:
    resp = http_json("POST", f"{noted}/api/workflows/run", body={
        "type": "create_tool",
        "inputs": inputs,
    })
    return resp["workflow_id"]


def wait_for_terminal(noted: str, wf_id: str, timeout_s: int = WORKFLOW_TIMEOUT_S):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            d = http_json("GET", f"{noted}/api/workflows/{wf_id}")
        except HTTPError:
            time.sleep(POLL_INTERVAL_S)
            continue
        s = d["state"]["status"]
        if s in ("completed", "failed", "suspended", "aborted"):
            return d
        time.sleep(POLL_INTERVAL_S)
    raise HTTPError(f"workflow {wf_id} did not terminate within {timeout_s}s")


# ─── Cleanup between trials ─────────────────────────────────────────


def remove_tool(noted: str, tool_name: str) -> dict | None:
    """Run the remove_tool workflow synchronously to archive the just-
    published tool + skill so the next trial starts from a clean slate."""
    try:
        resp = http_json("POST", f"{noted}/api/workflows/run", body={
            "type": "remove_tool",
            "inputs": {"tool_name": tool_name},
        })
        wf_id = resp["workflow_id"]
        wait_for_terminal(noted, wf_id, timeout_s=60)
        return {"workflow_id": wf_id, "ok": True}
    except HTTPError as e:
        return {"ok": False, "error": str(e)}


# ─── Trial loop ─────────────────────────────────────────────────────


def run_trial(noted: str, scenario: dict, trial_idx: int) -> dict:
    """Run one trial: trigger create_tool, wait, probe, cleanup. Return
    a dict with all outcomes for the report."""
    inputs = scenario["inputs"]
    tool_name = inputs["tool_name"]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()

    out: dict = {
        "scenario_id": scenario["id"],
        "trial": trial_idx,
        "started_at": started,
        "tool_name": tool_name,
        "workflow_id": None,
        "wf_status": None,
        "smoke_rewinds": 0,
        "failed_step": None,
        "failed_tail": None,
        "duration_s": 0.0,
        "probe_ok": None,
        "probe_keys_present": None,
        "probe_error": None,
    }

    try:
        wf_id = trigger_create_tool(noted, inputs)
        out["workflow_id"] = wf_id
    except HTTPError as e:
        out["wf_status"] = "trigger_failed"
        out["failed_tail"] = str(e)
        out["duration_s"] = time.time() - t0
        return out

    try:
        detail = wait_for_terminal(noted, wf_id)
    except HTTPError as e:
        out["wf_status"] = "timeout"
        out["failed_tail"] = str(e)
        out["duration_s"] = time.time() - t0
        return out

    s = detail["state"]
    out["wf_status"] = s["status"]
    out["smoke_rewinds"] = s.get("smoke_rewinds", 0)

    failed = next((st for st in s.get("steps") or [] if st.get("status") == "failed"), None)
    if failed is not None:
        out["failed_step"] = failed["name"]
        err = failed.get("error") or ""
        out["failed_tail"] = err[-500:]

    out["duration_s"] = round(time.time() - t0, 2)

    # The workflow's own verify_tool_round_trip step already calls the
    # published tool against the live upstream with verify_inputs and
    # asserts a real (non-error) result. So workflow.status == completed
    # IS the live-call verification — no separate probe needed.
    # OPTIONAL: scenario may declare expect_keys; if present and the
    # workflow completed, we cross-check verify_tool_round_trip's
    # recorded result_preview for those keys (cheap sanity).
    if s["status"] == "completed" and "post_publish_probe" in scenario:
        expected = scenario["post_publish_probe"].get("expect_keys") or []
        v = next((st for st in s.get("steps") or [] if st.get("name") == "verify_tool_round_trip"), None)
        preview = ((v or {}).get("output") or {}).get("result_preview") or ""
        keys_ok = all(f'"{k}"' in preview for k in expected)
        out["probe_keys_present"] = keys_ok
        out["probe_ok"] = keys_ok
        if not keys_ok:
            missing = [k for k in expected if f'"{k}"' not in preview]
            out["probe_error"] = f"verify_tool_round_trip preview missing key(s): {missing}"

    # Cleanup so the next trial starts clean (snapshots preserved).
    if s["status"] == "completed":
        remove_tool(noted, tool_name)

    return out


# ─── Pass criteria ──────────────────────────────────────────────────


def trial_passed(t: dict) -> bool:
    if t["wf_status"] != "completed":
        return False
    # If the scenario declared expect_keys, those must be present in
    # verify_tool_round_trip's preview.
    if t["probe_ok"] is False:
        return False
    return True


# ─── Reporting ──────────────────────────────────────────────────────


def write_reports(run_dir: Path, results: list[dict]) -> tuple[Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)

    # CSV: one row per trial.
    csv_path = run_dir / "trials.csv"
    fields = [
        "scenario_id", "trial", "tool_name", "wf_status", "smoke_rewinds",
        "failed_step", "duration_s", "probe_ok", "probe_keys_present",
        "workflow_id", "failed_tail", "probe_error",
    ]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)

    # Markdown: per-scenario pass rate + first failure tail per scenario.
    md_path = run_dir / "summary.md"
    with open(md_path, "w") as f:
        f.write(f"# Workflow framework test run\n\n")
        f.write(f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")

        # Group by scenario_id
        by_scn: dict[str, list[dict]] = {}
        for r in results:
            by_scn.setdefault(r["scenario_id"], []).append(r)

        # Overall row
        total_trials = len(results)
        total_passes = sum(1 for r in results if trial_passed(r))
        rate = (total_passes / total_trials * 100) if total_trials else 0.0
        f.write(f"## Overall: {total_passes}/{total_trials} ({rate:.0f}%)\n\n")

        # Per-scenario table
        f.write("| Scenario | API family | Pass | Fail | Avg duration (s) | First failed step | First failure tail |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for scn_id, trials in sorted(by_scn.items()):
            passes = sum(1 for t in trials if trial_passed(t))
            fails = len(trials) - passes
            avg = sum(t["duration_s"] for t in trials) / len(trials)
            first_fail = next((t for t in trials if not trial_passed(t)), None)
            failed_step = first_fail["failed_step"] if first_fail else ""
            failed_tail = (first_fail["failed_tail"] or first_fail.get("probe_error", "") or "") if first_fail else ""
            failed_tail = failed_tail.replace("|", "\\|").replace("\n", " ")[:120]
            api_family = ""
            for sc_doc in load_scenarios(scn_id):
                api_family = sc_doc.get("api_family", "")
            f.write(f"| {scn_id} | {api_family} | {passes} | {fails} | {avg:.1f} | {failed_step} | {failed_tail} |\n")

        # Per-trial detail
        f.write("\n## Per-trial detail\n\n")
        for r in results:
            badge = "✓" if trial_passed(r) else "✗"
            f.write(f"### {badge} `{r['scenario_id']}` trial {r['trial']} — {r['wf_status']}\n")
            f.write(f"- workflow_id: `{r['workflow_id']}`\n")
            f.write(f"- duration: {r['duration_s']}s · smoke_rewinds: {r['smoke_rewinds']}\n")
            if r["failed_step"]:
                f.write(f"- failed_step: `{r['failed_step']}`\n")
                f.write(f"- failed_tail: `{(r['failed_tail'] or '').replace(chr(10), ' ')[:300]}`\n")
            if r["probe_ok"] is not None:
                f.write(f"- probe: {'PASS' if r['probe_ok'] else 'FAIL'}")
                if r["probe_error"]:
                    f.write(f" · {r['probe_error'][:200]}")
                f.write("\n")
            f.write("\n")

    return csv_path, md_path


# ─── Main ───────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noted", default=DEFAULT_NOTED, help=f"noted base URL (default {DEFAULT_NOTED})")
    ap.add_argument("--scenario", default=None, help="run a single scenario by id (default: all)")
    ap.add_argument("--runs", type=int, default=1, help="trials per scenario (default 1)")
    ap.add_argument("--run-id", default=None, help="report directory name (default: timestamped)")
    args = ap.parse_args()

    scenarios = load_scenarios(args.scenario)
    if not scenarios:
        print(f"no scenarios found (filter={args.scenario!r})", file=sys.stderr)
        sys.exit(2)

    print(f"running {len(scenarios)} scenario(s) × {args.runs} trial(s) against {args.noted}")
    for s in scenarios:
        print(f"  - {s['id']}  ({s.get('api_family', '?')})")

    results: list[dict] = []
    for s in scenarios:
        for i in range(1, args.runs + 1):
            print(f"\n[{s['id']} trial {i}/{args.runs}]  ", end="", flush=True)
            r = run_trial(args.noted, s, i)
            ok = trial_passed(r)
            print(f"{'PASS' if ok else 'FAIL'}  status={r['wf_status']}  step={r['failed_step'] or '-'}  duration={r['duration_s']}s")
            results.append(r)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = REPORTS_DIR / run_id
    csv_path, md_path = write_reports(run_dir, results)

    print()
    total_passes = sum(1 for r in results if trial_passed(r))
    print(f"=== {total_passes}/{len(results)} trials passed ===")
    print(f"reports: {md_path}")
    print(f"         {csv_path}")
    sys.exit(0 if total_passes == len(results) else 1)


if __name__ == "__main__":
    main()

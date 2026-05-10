# Workflow framework test harness

Fixed-scenario harness for the `create_tool` workflow. Bypasses the chat
layer + the planner so each scenario is deterministic — every run
exercises the EXACT SAME `mission`, `acceptance_criteria`, `verify_inputs`,
`api_docs_urls`, and `language`. Variance comes from the LLM steps
(`tool_author`, `api_tester`, `skill_author`) only, which is what we
actually want to measure.

## Why this exists

Chat-driven testing produces non-deterministic scenarios because the
planner picks slightly different inputs each turn — making it impossible
to tell whether a prompt change improved or regressed the system. This
harness pins inputs so iteration on prompts has a deterministic feedback
loop.

## Scenarios

`scenarios/*.yaml` — one YAML per scenario. Each MUST be from a distinct
API family so the harness measures framework genericity, not over-fit
to one upstream. Current set:

- `sapo_weather.yaml`     — SAPO weather (XML-style nested JSON)
- `github_issue.yaml`     — GitHub REST (flat JSON, requires no auth for public repos)
- `open_meteo.yaml`       — Open-Meteo forecast (nested numeric arrays, no auth)
- `wikipedia_summary.yaml` — Wikipedia REST page summary (flat JSON, no auth)

Add more by dropping a YAML in `scenarios/` matching the schema in
`scenarios/_schema.md`.

## Running

```
cd noted
python testing/workflow_framework/run_tests.py            # all scenarios, 1 trial each
python testing/workflow_framework/run_tests.py --runs 5   # 5 trials per scenario
python testing/workflow_framework/run_tests.py --scenario sapo_weather --runs 10
```

Reports land in `testing/workflow_framework/reports/<run_id>/`.

## What "pass" means

A trial passes when:
1. Workflow status is `completed` (all 9 steps green)
2. Published tool is callable (the `verify_tool_round_trip` step
   inside the workflow already proves this)
3. Paired skill exists at `data/skills/<tool_name>/SKILL.md` with
   `provenance: user` and `source_workflow_id` matching this run

Anything else is FAIL, with the failed step + error tail recorded.

## Per-trial cleanup

Between trials within a scenario, the harness:
1. Calls `remove_tool` workflow to archive the tool+skill
2. Refreshes federation
3. Preserves the workflow snapshot (incl. llm_calls.jsonl) for
   post-hoc analysis. Snapshots are NOT deleted automatically —
   they're the most useful artifact for debugging variance.

# Test Strategy

Run the smallest scope that exercises the change. Full batch is for milestones, not edits.

## Tiers

| Tier | Change | Scope | Command |
|---|---|---|---|
| 0 | Doc / comment / refactor with zero behavior change | None | - |
| 1 | Single scenario tweak (loosened YAML) | Just that scenario | `--doc <path> --scenario <id>` |
| 2 | Narrow bug fix (one tool, one skill, one doc) | The affected doc | `--doc <path>` |
| 3 | Cross-cutting (llm_context.py, llm.py, judge prompt, harness internals) | Full batch | `--all` |
| 4 | Pre-milestone / memory-update | Full batch, resilience | `--all --runs 3` |

**Heuristic:** edits under `backend/app/managers/llm_context.py`, `backend/app/routers/llm.py`, `agent_server/data/prompts/noted_judge_system_prompt.txt`, or any `harness/*.py` that isn't a test YAML → Tier 3. Everything else starts at Tier 2 and escalates only on FAIL.

## Iterating on failures

After a batch that has FAILs, use `--rerun-failures-from <run-id>` to replay only the FAILs from that run. Typical cost: 15-90s instead of 7 minutes. Promote to Tier 3 only after the failure-set is clean.

## Scope cheatsheet (update as new scenarios land)

| Changed | Minimal set |
|---|---|
| schema_builder.py / predict.py (serving) | mlflow-serving::S8, S9, S16 |
| _experiment_summary_block | noted-platform-overview::S13, mlflow-serving::S14 + one control |
| _tool_get_skill | noted-platform-overview (whole doc) |
| deploy_model / invoke_model / get_serving_status tool bodies | the corresponding tool doc |
| Judge prompt | Tier 3 (affects all verdicts) |
| fixtures.py | Docs that use the changed fixture |
| Scenario YAML | Just that scenario (Tier 1) |

## Memory-update contract

Don't record a new pass-rate in MEMORY.md without a **Tier 3** run at `--runs 1` at minimum. If claiming "100%" or marking a milestone COMPLETE, use `--runs 3`.

## What does NOT need a batch

Changes to `architecture/*.md`, `MEMORY.md`, stage_sandbox, lint-only edits, whitespace, docstrings.

# Assistant Test Harness - Design Document

**Status:** Draft for review. No code written yet.
**Owner:** noted Assistant test-coverage initiative (see [project_assistant_test_coverage.md](../../../memory/project_assistant_test_coverage.md))
**Target artifact count:** 76 test docs (42 skills + 34 tools)

## Purpose

Automate the evaluation of the noted Assistant against hand-curated test scenarios. For each scenario, the harness stages the required state, sends the user request through noted's chat API, captures the response (tool calls + reasoning + answer), feeds it to `noted_judge` for evaluation, and writes a structured report.

The harness is the executable layer behind the per-artifact test docs. Docs describe WHAT to test; the harness runs it.

## Locked decisions

| # | Decision |
|---|---|
| D1 | Two-file format: human `.md` + machine `.yaml` per artifact, with a lint check for drift |
| D2 | Direct API call to `/api/llm/chat` (no UI puppeteering) |
| D3 | Clean-slate isolation per scenario: fresh conversation, serving unloaded pre-scenario, fixtures load required state |
| D4 | Gemma only (local LLM under test) |
| D5 | 1x run per scenario by default; `--runs N` flag for configurability |
| D6 | Harness lives inside the noted repo at `testing/assistant/harness/` |
| D7 | Full scope: individual Markdown reports per scenario under `testing/assistant/reports/<run-id>/` |
| D8 | Verdict taxonomy: `PASS` / `FAIL` / `ERROR` (ERROR = infra/fixture failed; distinct from FAIL so dashboards separate infra issues from regressions) |
| D9 | Pre-stage sandbox MLflow state via a one-time idempotent script (`stage_sandbox.py`); scenarios reference sandbox artifacts, not the real jena_weather project |
| D10 | Reports include per-run latency + token metrics AND a flat `results.csv` (one row per scenario-run) for chart generation |
| D11 | Multi-run mode tests resilience, not accuracy: each run reported individually; scenario verdict = `FAIL (M/N)` if ANY run failed, `PASS (N/N)` only if all N passed |
| D12 | Memory key naming: `harness-<scenario_id>-<uuid>` per scenario (isolates from real user conversations) |

## Component map

```
testing/assistant/
├── skills/                           (42 skill docs)
│   ├── mlflow-serving.md             human doc
│   └── mlflow-serving.yaml           machine-driven scenarios
├── tools/                            (34 tool docs)
│   ├── get_serving_status.md
│   └── get_serving_status.yaml
├── architecture/
│   └── harness_design.md             this file (design docs live here)
├── harness/                          (runtime code, created during M1)
│   ├── run_tests.py                  CLI entry point
│   ├── stage_sandbox.py              one-time sandbox pre-stage script (D9)
│   ├── scenario_loader.py            parse + validate .yaml
│   ├── fixtures.py                   state staging primitives
│   ├── driver.py                     call /api/llm/chat, capture SSE
│   ├── stream_parser.py              SSE -> (tool_calls, reasoning, answer)
│   ├── judge.py                      format -> POST /v1/chat/completions (noted_judge) -> JSON verdict
│   ├── reporter.py                   aggregate + write Markdown + CSV
│   └── lint.py                       check .md <-> .yaml consistency
└── reports/
    └── 2026-04-20T15-00-00/          (ISO timestamp per run)
        ├── summary.md                overall pass/fail table
        ├── results.csv               one row per scenario-run (D10)
        └── per-scenario/
            ├── get_serving_status-S1.md
            └── mlflow-serving-S5.md
```

## Verdict taxonomy (D8)

Every scenario-run ends in exactly one verdict:

| Verdict | Meaning | Examples |
|---|---|---|
| `PASS` | Deterministic check passed AND judge returned PASS | Expected tools fired, no forbidden tools fired, answer matched focus, judge agreed |
| `FAIL` | Scenario ran to completion but expectations not met | Forbidden tool fired; expected tool missing; judge returned FAIL; hallucinated values in answer |
| `ERROR` | Infrastructure / fixture / setup failure before the scenario could run to completion | MLflow REST 500 during staging; `deploy_model` fixture timed out; noted backend unreachable; YAML schema invalid |

Rationale for keeping ERROR separate from FAIL: dashboards should distinguish "the Assistant misbehaved" (FAIL - actionable regression) from "the test environment itself broke" (ERROR - infra work, unrelated to Assistant quality). A run with 5 FAILs and 0 ERRORs is a quality signal; 0 FAILs and 5 ERRORs is an operations problem.

ERROR scenarios:
- Are reported with the partial state captured so far (which fixture failed, what the error was)
- Do NOT invoke the judge (nothing to evaluate)
- Are excluded from pass-rate percentages but always counted in the summary

## Multi-run semantics (D11)

`--runs N` is for **resilience testing, not accuracy voting**. Each of the N runs is reported independently in the CSV and in the per-scenario markdown. Scenario-level verdict:

- `PASS (N/N)` when every run passed
- `FAIL (M/N)` when ANY run failed, where M is the count of passing runs
- `ERROR (M/N)` when any run errored (takes precedence over FAIL annotation)

A scenario that passes inconsistently IS a regression, not a robustness success. This matches the intent: detect flaky behavior, don't smooth it over with majority vote.

## Scenario YAML schema

### Single-turn scenario

```yaml
scenario_id: S1                       # short identifier, unique within the doc
title: "Ready state, deployed model"  # human-readable
tags: [read, mlflow, serving]         # optional, for filtering
setup:
  project: noted-testing              # context_descriptor.project_id
  notebook: path/to/nb.ipynb          # optional, context_descriptor.notebook_path
  active_run_id: <run-id>             # optional
  prerequisites:                      # ordered, applied before the scenario runs
    - fixture: unload_model           # ensure serving is idle
    - fixture: deploy_model
      args:
        model_name: "Sandbox Forecaster"
        alias: champion
user_request: "is the model deployed?"
expected_tools_called:
  - name: get_serving_status
    exact_count: 1                    # optional; default = "at least once"
    args_match: {}                    # optional; dict of arg_name -> expected value or regex
expected_tools_NOT_called:
  - list_registered_models
  - get_run_details
  - deploy_model
expected_answer_focus: |
  - confirm yes, deployed
  - report model name ("Sandbox Forecaster")
  - report version (1)
  - must not DEFER to the UI
notes: |
  Free-form annotation carried into the report for human review.
```

### Multi-turn scenario

```yaml
scenario_id: S16
title: "Deploy then immediately invoke"
setup:
  project: noted-testing
  prerequisites:
    - fixture: unload_model
turns:
  - user_request: "deploy the champion of Sandbox Forecaster"
    expected_tools_called:
      - name: deploy_model
        args_match: {model_name: "Sandbox Forecaster", alias: champion}
    expected_tools_NOT_called: [invoke_model, get_serving_schema]
    expected_answer_focus: "confirm deploy succeeded"
  - user_request: "now test it"
    expected_tools_called:
      - name: invoke_model
    expected_tools_NOT_called: [deploy_model]
    expected_answer_focus: "real prediction output from the deployed model"
```

Same conversation (same memory key) across turns within one scenario. Fresh conversation between scenarios.

## Fixture library (MVP set)

Covers the four pilot docs. Each fixture is idempotent: checks current state, mutates only if needed.

| Fixture | Purpose |
|---|---|
| `unload_model()` | POST `/api/serving/unload` if anything is loaded |
| `deploy_model(model_name, version=None, alias=None)` | POST `/api/serving/load` and wait for `ready` |
| `ensure_registered_model(name, versions=[...], aliases={alias: version})` | Verify or create via MLflow REST; registers a known sandbox model if missing |
| `ensure_experiment_run(experiment, params={}, tags={}, metrics={})` | Creates a minimal run if none matching exist |
| `set_context(project, notebook=None, active_run_id=None, selected_cells=[])` | Builds the `context_descriptor` dict for the chat request (does not mutate state) |

Fixtures log what they did (or verified) into the scenario report.

Fixture failure policy (D8): if a fixture cannot achieve the requested state after its own internal retry budget, the scenario is marked `ERROR` (not `FAIL`) with the fixture name + the raw error captured in the report. The chat + judge calls are skipped for ERROR scenarios.

## Sandbox pre-stage (D9)

`harness/stage_sandbox.py` is a one-time setup script that populates the MLflow server with the artifacts the scenarios reference. Idempotent: re-runs are safe and produce no duplicates.

Pre-staged artifacts:

- Experiment `noted-testing` (created if missing)
- Registered model `Sandbox Forecaster` with:
  - v1 aliased `@champion` (successful run, `target_mean`/`target_std` logged as params)
  - v2 aliased `@staging` (another successful run)
  - v3 (no alias)
  - v4 "poisoned" (deliberately pins a framework version outside the serving baseline so load-time failure scenarios can be exercised)
- An active-but-unregistered run (source for "register-then-deploy" scenarios)

Invocation:

```
python -m testing.assistant.harness.stage_sandbox
```

Runs against the running noted stack (uses `MLFLOW_TRACKING_URI` + `http://noted-serving:5522`). Prints a report of what was created vs verified vs skipped. Must complete successfully before the first harness run.

Scenarios reference these sandbox artifacts by name (`Sandbox Forecaster`), never by hard-coded run IDs, so re-staging produces new run IDs without breaking scenarios.

The sandbox deliberately does NOT touch `jena_weather` or any real project - that constraint is load-bearing for user's workflow (per explicit instruction).

## Driver flow

```python
def run_one_scenario(scenario, run_index, run_config):
    # Fixture-phase errors are ERROR (D8), not FAIL.
    try:
        ctx = apply_prerequisites(scenario.setup)     # fixtures
    except FixtureError as e:
        return RunResult(verdict="ERROR", phase="setup", error=str(e),
                         fixture=e.fixture_name)

    memory_key = f"harness-{scenario.scenario_id}-{uuid4()}"  # D12
    all_turns = []

    for turn_spec in scenario.turns or [scenario_as_single_turn(scenario)]:
        try:
            response_sse = call_noted_chat(
                message=turn_spec.user_request,
                context_descriptor=ctx,
                memory_key=memory_key,
                model="local",                         # D4
            )
            parsed = parse_stream(response_sse)        # {tool_calls, reasoning, answer, tool_results}
        except DriverError as e:
            return RunResult(verdict="ERROR", phase="chat", error=str(e))

        deterministic = run_deterministic_checks(turn_spec, parsed)
        if deterministic.pass_:
            try:
                judge_verdict = evaluate_with_judge(turn_spec, parsed)
            except JudgeError as e:
                return RunResult(verdict="ERROR", phase="judge", error=str(e))
        else:
            judge_verdict = None                       # short-circuit; no judge call needed

        all_turns.append({
            "turn_spec": turn_spec,
            "parsed": parsed,
            "deterministic": deterministic,
            "judge": judge_verdict,
        })

    return aggregate_turns(scenario, all_turns, run_index)
```

Per D11, the caller invokes `run_one_scenario` N times per scenario (`run_index` 0..N-1) and aggregates the per-run results into the final scenario-level verdict (`PASS (N/N)`, `FAIL (M/N)`, `ERROR (M/N)`). Each run writes its own CSV row (D10).

**Two-layer evaluation** (re-emphasized):
- Layer 1: **deterministic checks** from the scenario spec — did the expected tools fire? did any forbidden tools fire? are arg matchers satisfied?
- Layer 2: **LLM-as-Judge** via `noted_judge` — only runs if Layer 1 passed. Handles the fuzzy axes (answer correctness, procedural hygiene).

A Layer-1 failure immediately marks the turn as FAIL and skips the judge call (saves time + tokens).

## Stream parser contract

The parser consumes the SSE stream from `/api/llm/chat` and extracts four things:

1. `tool_calls`: list of `{name, args, result_preview, duration_ms}` in order fired
2. `reasoning`: concatenated content from every `<think>...</think>` block (for inclusion in the judge input as `<reasoning>...</reasoning>`)
3. `answer`: the streamed text with `<think>` blocks and `<tool_call>` markers stripped
4. `tool_result_snapshots`: optional, the raw tool result strings (so the judge can verify answer values against tool results)

Parser is a plain function; easy to unit-test with fixture SSE streams.

## Judge envelope format

```
TEST CASE:
  scenario_id: <string>
  setup: <prose summary of staged state>
  user_request: "<literal>"
  expected_tools_called: [...]
  expected_tools_NOT_called: [...]
  expected_answer_focus: |
    <bullet list>

ASSISTANT OUTPUT:
  actual_tools_called: [<name1>, <name2>, ...]
  actual_tool_results (for reference):
    <name1>: <truncated result>
    <name2>: <truncated result>

<reasoning>
...concatenated from <think> blocks in the stream...
</reasoning>

<answer>
...final user-facing text...
</answer>
```

POSTed as the `user` message to `http://agent_server:7701/v1/chat/completions` with `"model": "noted_judge"` and `"max_tokens": 512`.

## Report formats

### Per-scenario report (Markdown)

Path: `testing/assistant/reports/<run-id>/per-scenario/<doc>-<scenario_id>.md`

Contents:
- Scenario metadata (id, title, source doc, tags, judge_prompt_hash for reproducibility)
- Setup executed (list of fixtures applied + verification result)
- **One section per run** (1..N per D11), each containing:
  - Per-turn: user request, captured tool calls (with args + result snippets), captured reasoning (from `<think>` blocks), captured answer, deterministic check outcome, judge verdict JSON
  - Per-run metrics: `chat_latency_ms`, `chat_tokens_in`, `chat_tokens_out`, `judge_latency_ms`, `judge_tokens_in`, `judge_tokens_out`
  - Per-run verdict: `PASS` / `FAIL` / `ERROR`
- Scenario-level verdict rollup: `PASS (N/N)` / `FAIL (M/N)` / `ERROR (M/N)` per D11

### Summary report (Markdown)

Path: `testing/assistant/reports/<run-id>/summary.md`

Contents:
- Run metadata: timestamp, model under test, runs-per-scenario config, judge_prompt_hash, hostnames
- Aggregate counts: total scenarios, PASS, FAIL, ERROR, pass rate (FAILs/(PASS+FAIL), excluding ERRORs)
- Per-doc breakdown table with pass/fail/error counts + link to each per-scenario report
- Aggregate failure patterns (most common deficiency phrases across failures)
- Cost summary: total chat tokens, total judge tokens, total wall-clock runtime

### Flat CSV (D10)

Path: `testing/assistant/reports/<run-id>/results.csv`

One row per scenario-run (so N rows per scenario in multi-run mode). Schema:

```
timestamp                ISO-8601 UTC of when this run completed
scenario_id              e.g. "get_serving_status::S1"
doc                      source doc, e.g. "tools/get_serving_status.yaml"
run_index                0-based within the scenario
verdict                  PASS | FAIL | ERROR
tool_call_check          OK | BAD | n/a  (n/a when verdict=ERROR)
answer_check             OK | BAD | n/a
procedural_check         OK | BAD | n/a
deficiencies             semicolon-joined list of judge deficiency phrases
error_phase              n/a | setup | chat | judge | parsing
error_message            populated when verdict=ERROR; otherwise empty
chat_latency_ms          wall time of the /api/llm/chat call
chat_tokens_in           usage.input_tokens from the chat endpoint
chat_tokens_out          usage.output_tokens from the chat endpoint
judge_latency_ms         wall time of the judge call (empty if not invoked)
judge_tokens_in          judge's input token count (if reported)
judge_tokens_out         judge's output token count (if reported)
judge_prompt_hash        sha1 of the judge prompt at test time (for reproducibility)
```

Designed for direct pandas / Excel consumption - no post-processing needed to plot pass rates or cost trends over time.

## CLI

See [testing_strategy.md](testing_strategy.md) for when to use which selection.

```
python -m testing.assistant.harness.run_tests [options]

Selection (at least one required):
  --doc PATH                  Run one YAML doc (e.g. tools/get_serving_status.yaml)
  --scenario ID               With --doc: run one scenario (e.g. S1)
  --category {skills,tools}   Run all docs in a category
  --all                       Run everything under skills/ + tools/
  --rerun-failures-from RUN_ID  Replay only the scenarios that FAILed in a
                                prior run (reads <report-dir>/<run-id>/results.csv).

Run config:
  --runs N                 Runs per scenario (default 1)
  --rerun-failures         On FAIL, retry once and flag flaky (default: off)
  --clean-slate / --no-clean-slate   D3 toggle (default clean-slate)
  --model NAME             Model under test (default "local"; Gemma via noted router)

Output:
  --run-id ID              Name the run (default: ISO timestamp)
  --report-dir PATH        Output directory (default testing/assistant/reports/)

Misc:
  --dry-run                Parse scenarios + run fixtures but skip chat/judge calls
  --list                   List scenarios that would run and exit
```

Separate CLI for the sandbox stager (D9):

```
python -m testing.assistant.harness.stage_sandbox [options]
  --dry-run                Print what would be created / skipped, do nothing
  --force-recreate         Wipe and recreate sandbox artifacts (destructive)
```

## Lint check (.md <-> .yaml consistency)

`harness/lint.py` verifies:

- Every `.md` file has a sibling `.yaml` with matching scenario_ids
- Every scenario_id referenced in `.md` exists in `.yaml`
- Every `.yaml` fixture name resolves to a defined fixture in `fixtures.py`
- No fixture arg type mismatches
- Required fields present on every scenario

Runs as part of `run_tests.py` startup (or standalone for CI).

## Implementation milestones

### M0 - Sandbox pre-stage (D9)
- `stage_sandbox.py` creates `Sandbox Forecaster` v1-v4 + aliases + seeded runs in MLflow
- Idempotent: re-run produces no duplicates
- Prints a clear creation-vs-verified-vs-skipped report
- **Goal:** `python -m testing.assistant.harness.stage_sandbox` succeeds against the running stack; a second invocation is a no-op

### M1 - MVP end-to-end (one scenario, stdout)
- `scenario_loader.py` parses one `.yaml`
- `fixtures.py` with `unload_model`, `deploy_model`, `set_context`
- `driver.py` POSTs to `/api/llm/chat` and reads SSE
- `stream_parser.py` extracts tools + reasoning + answer
- `judge.py` formats envelope + POSTs to noted_judge + parses JSON
- ERROR handling in the scenario runner (D8)
- `run_tests.py` wires it together; prints result to stdout
- **Goal:** run `get_serving_status.yaml` S1 end-to-end, see `PASS (1/1)` in stdout

### M2 - Deterministic checks + Markdown reports + CSV
- Deterministic check evaluator (expected/forbidden tools, arg matchers)
- Per-scenario Markdown report (with metrics per D10)
- Summary Markdown report (with aggregate counts, cost summary)
- Flat `results.csv` (D10 schema)
- Multi-turn support in `driver.py`
- Multi-run support (D11)
- **Goal:** full `get_serving_status.yaml` suite (14 scenarios) runs with Markdown + CSV, supports `--runs 3` and reports individual run results

### M3 - Lint + scale prep
- `lint.py` consistency check
- CLI argparse polish (including `--stage-sandbox` auto-check at startup)
- Full fixture set to support all 4 pilot doc scenarios
- **Goal:** run all 4 pilot docs end-to-end with reports + no lint errors

### M4 - Remaining fixtures and doc conversions
- As each new skill/tool doc is authored, any new fixtures it needs are added
- Scales to all 76 docs over time
- **Goal:** harness runs any registered scenario

## Resolved questions

All open questions from the initial draft are now locked:

1. **Memory key per scenario** - D12: `harness-<scenario_id>-<uuid>`.
2. **Sandbox registered model** - D9: pre-stage `Sandbox Forecaster` via `stage_sandbox.py`; don't reuse `Jena Weather Forecaster` (the user's real project must stay untouched).
3. **Fixture error behavior** - D8: always `ERROR` unless the fixture succeeds 100%; never partial-credit.
4. **Cost tracking** - D10: per-run latency + token metrics in Markdown AND flat CSV for charting.
5. **Multi-run semantics** - D11: individual reports per run; scenario verdict = `PASS (N/N)` or `FAIL (M/N)` / `ERROR (M/N)`; resilience testing, not accuracy voting.

## Risks to flag

- **SSE stream parsing**: the SSE format is noted's own convention (`data: {...}\n\n`). If the format evolves, the parser is fragile. Keep the parser deliberately permissive and add a regression test.
- **Fixture idempotency assumption**: if two scenarios run in parallel (future optimization), fixtures might race. MVP runs serially; document the assumption.
- **Judge prompt drift**: if we iterate the judge prompt, historical reports become non-comparable. Include the judge prompt hash in the report metadata so results are reproducible.
- **Run_id uniqueness**: if the harness is invoked twice in the same second, the timestamped directory collides. Use ISO + microseconds or a short UUID suffix.

## Not in scope (for now)

- Parallel scenario execution (MVP runs serial)
- CI/GitHub Actions integration
- Pass-rate trend graphing across runs
- Auto-generation of scenarios from tool descriptions (the 76 docs are hand-curated by design)
- Claude as alternative model under test (D4 locked to Gemma)

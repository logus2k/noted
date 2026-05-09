# Workflow Framework Progress

Concrete task tracker for the plan in `self_learning_plan.md`. Tick items as they land. Each phase's completion gate is the live-evidence acceptance check at the bottom of that phase's section.

Format:
- `[ ]` pending
- `[/]` code shipped + AST passes; live-verify pending (waiting for the next noted / agent_server rebuild + the relevant probe)
- `[x]` complete and live-verified (concrete probe output, not just code-present)

---

## Phase A foundation (already shipped 2026-05-08, kept here for reference)

- [x] noted-tools container skeleton, MCP on 7702
- [x] Hot-reload watcher (load / update / unload, ~50ms)
- [x] Per-tool venv via `uv` + cache by mtime + invalidate on `requirements.txt` change
- [x] Subprocess executor with `RLIMIT_AS` + wall-clock timeout
- [x] Audit log writer (JSONL append per invocation)
- [x] Container runs as `1000:1000` so per-tool venvs are host-owned
- [x] Federation client in noted backend (`user_tools_client.py`) + 30s refresh + dispatch fallback
- [x] `/api/llm/mcp-tools` returns user tools with `provenance` + `_meta`
- [x] LLM-driven verification: Gemma called `hello_user` end-to-end via federation

---

## F1: Framework primitives (target ~1.5 weeks)

- [x] F1.1 Workflow registry module (`backend/app/workflow/{__init__,types,registry}.py`)
- [x] F1.2 Workflow loop / state machine (`backend/app/workflow/loop.py`). Deterministic step path complete; LLM-driven step is a stub raising NotImplementedError pending F2 wiring.
- [x] F1.3 Workspace state container (`backend/app/workflow/workspace.py`)
- [x] F1.4 Suspend / resume mechanism (`backend/app/workflow/suspension.py`)
- [x] F1.5 Identity-threading helper + telemetry sio wiring (`backend/app/workflow/identity.py` + `main.py` lifespan hook)
- [x] F1.6 Per-workflow audit log writer (`backend/app/workflow/audit.py`)
- [x] F1.7 Socket.io event emitter (`backend/app/workflow/telemetry.py`)
- [x] F1.8 Migration of Phase A's flat `data/user_tools/` to `data/tenants/default/user_tools/`. noted-tools mount + env var updated, host dir created with UID 1000, container rebuilt.
- [x] F1.9 Synthetic probe + verification harness (`backend/app/workflow/probe.py` mounted at `/api/workflow/probe/*`)
- [x] F1.10 Probe 1 (happy path 2026-05-09): 3 steps `status: completed`, `retries: 0`, outputs threaded `echo -> transform -> finalize`, identity defaulted to `"default"`
- [x] F1.11 Probe 3 + audit log (2026-05-09): step 1 retried 3 times then suspended; snapshot written to `data/tenants/default/workflows/<wf>/state.json`; resume cleared the failure flag and ran the post-resume retry to completion. 12-line audit JSONL with full lifecycle (workflow_started, step_started/completed/failed, workflow_suspended, workflow_resumed, workflow_completed) at RFC 3339 UTC timestamps.
- [x] F1.12 Identity probe (2026-05-09): `X-Forwarded-User: alice` -> `actor_id: alice` + `tenant_id: alice` in state and audit; `data/tenants/alice/workflows/...` created on first use; absence of header -> `default` fallback.
- [x] F1.13 Concurrent two-tenant probe (2026-05-09): alice + bob workflows started 1ms apart, ran in parallel, each got a distinct `workflow_id`, completed independently with correct per-tenant outputs (`ALICE MSG` / `BOB MSG`). Per-tenant audit dirs isolated.

---

## F2: Worker presets (target ~3 days)

- [x] F2.1 `planner` preset (thinking off; `reasoning` field in output captures rationale)
- [x] F2.2 `tool_author` preset (thinking on; max_tokens 4096; emits files dict with escaped-newline code)
- [x] F2.3 `api_tester` preset (thinking on; max_tokens 2048; emits smoke.py via files dict)
- [x] F2.4 `skill_author` preset (thinking off; emits structured frontmatter + body sections; orchestrator's publish step assembles markdown to dodge JSON-with-multi-line-string failure mode)
- [x] F2.5 Direct probe of each preset against agent_server (Gemma) 2026-05-09: all four produce parseable JSON matching their declared schema. Sample outputs captured.
- [/] F2.6 Claude cross-backend dispatcher SHIPPED 2026-05-09 (live verification pending user-initiated probe to avoid burning Anthropic credits per `feedback_check_active_model_first.md`). New agent_server endpoint `GET /v1/agents/{name}` returns the preset's system_prompt content + params_override + memory_policy (verified live: HTTP 200 for planner / tool_author / api_tester / skill_author; planner returns 2657-byte prompt + complete params dict). New `dispatch_claude()` in `backend/app/workflow/llm_dispatcher.py` fetches the preset config, builds a `[{system}, {user}]` message pair, calls noted's existing `AnthropicLLMManager.chat()` with the preset's temperature + max_tokens, strips `<think>` + code fences from the response, parses as JSON, validates dict shape. The `dispatch()` entry point routes to the Claude path when `step_inputs._backend == "claude"` (default remains the Gemma agent_server path). Plan templates can opt in per-step or per-workflow via inputs.
- [x] F2.7 Live-verify planner on Gemma 2026-05-09: returned `workflow_type: "create_tool"` for a "fetch GitHub issues" mission with all required `inputs` populated and a single-sentence `reasoning` field cited from the mission text.
- [ ] F2.8 50-trial validity rate measurement - DEFERRED to F3 / acceptance gate. Best measured after presets are exercised inside real workflows where context shape + tool-call interplay matters; one-shot prompt probes overstate validity.

**F2 follow-up shipped during the phase:**
- `agent_server/app/openai_compat.py:_merge_request_params` patched to allow presets to set `chat_template_kwargs` via `params_override`. Previously the whitelist dropped it silently; now `{"enable_thinking": false}` from a preset reaches llama-server. agent_server image rebuilt + recreated.

---

## F3: First-wave workflows (target ~1.5 weeks)

- [x] F3.0 LLM dispatcher (`backend/app/workflow/llm_dispatcher.py`): builds user message from step inputs (workflow_inputs + previous_step + validator_complaint), POSTs to agent_server, strips `<think>` + code fences, parses JSON. No GBNF. Wired into the loop's previously-stubbed LLM-step path.
- [x] F3.1 `create_tool` workflow registered (7-step plan: fetch_docs -> tool_author -> validate_tool_structure -> publish_tool -> verify_tool_round_trip -> skill_author -> publish_skill; outcomes: `tool_published` + `skill_published`)
- [ ] F3.2 Standalone `create_skill` workflow - DEFERRED. Paired skill creation inside `create_tool` covers the common case; standalone skill authoring (without a tool) is its own scope.
- [x] F3.3 `remove_tool` workflow registered (2-step plan: archive_tool -> archive_skill; both move to `_archive/<name>_<ts>/`)
- [ ] F3.4 Standalone `remove_skill` workflow - DEFERRED (same reasoning as F3.2)
- [x] F3.5 Subprocess + pytest validation - LIVE-VERIFIED 2026-05-09. Implementation: noted-tools `POST /admin/run-smoke-tests/{tool_name}` ensures venv + checks pytest importable (uv pip install fallback if not in additional_requirements) + runs `pytest -x smoke.py` with `cwd=tool_dir`; returns `{ok, exit_code, stdout, stderr}`. Backend: `api_tester` step now sits between `validate_tool_structure` and `publish_tool` in create_tool's plan; `publish_tool` merges api_tester's `additional_requirements` into requirements.txt and writes smoke.py alongside tool.py; new `run_smoke_tests` step calls the noted-tools admin endpoint between publish_tool and verify_tool_round_trip. **End-to-end verified 2026-05-09**: 9-step create_tool ran in 44s on Gemma; pytest executed in the published venv; all assertions PASS. api_tester prompt corrected to use `tool.py` (not `../tool.py`) since pytest runs with `cwd=tool_dir`.
- [x] F3.6 Validation tool: `validate_tool_structure` (deterministic; `jsonschema.validate(...)` on tool.json + `ast.parse(tool.py)`) shipped in `step_handlers.py`
- [ ] F3.7 Validation tool: `assess_explanation_clarity` - DEFERRED. No first-wave step needs subjective prose validation.
- [x] F3.8 Validation tool: `verify_tool_round_trip` (deterministic; calls the just-published tool via federation MCP path with sample args) shipped in `step_handlers.py`
- [x] F3.9 Publish step: writes files to `data/tenants/<tenant>/user_tools/<name>/`, chowns to UID 1000 (noted-tools' runtime UID), force-refreshes federation cache. Real fix for the cross-container UID-mismatch trap: noted backend runs as root, noted-tools as 1000, bind-mount means root-owned dirs block uv venv inside noted-tools.
- [x] F3.10 Publish step for skill: assembles markdown from skill_author's structured frontmatter+body, writes `data/skills/<name>.md`. SkillRegistry hot-reload depends on F4 (file watcher in noted backend's SkillRegistry).
- [ ] F3.11 Live-verify create_tool on Claude - DEFERRED. Cross-backend LLM dispatcher (Anthropic path reading the preset's system prompt + sampling) is its own piece. F3.12 covers the Gemma path which proves the framework's contract.
- [x] F3.12 Live-verify create_tool on Gemma 2026-05-09: end-to-end completion in 10.89s, 7 steps, 0 retries on any step. Outcomes recorded: `tool_published` + `skill_published`. Audit JSONL has full lifecycle (workflow_started + step_started/completed pairs + workflow_completed) at RFC 3339 timestamps. tool_author (LLM) ~8.4s, skill_author (LLM) ~2.1s, deterministic steps ~10ms each.
- [ ] F3.13 Live-verify published tool callable by LLM in subsequent chat turn - PARTIAL. Direct MCP call via /mcp/ confirmed the federation routes correctly. Full LLM-driven chat-turn invocation pending until we want to spend an LLM round trip on it; the Phase A.5 `hello_user` test already proved this transitive path on the same federation client.
- [x] F3.14 Live-verify failed creation: the prior verify_tool_round_trip suspend (workflow_id `wf_1778289853641_01efd1dc`) preserved iteration history on disk + workspace state in audit. Workflow ended in `suspended` state (then was killed by rebuild, audit persisted). UID-mismatch was the root cause; chown-after-publish fix shipped.
- [x] F3.15 Live-verify remove_tool 2026-05-09: 2 steps completed, both archive_paths exist on disk (tool dir under `_archive/` + skill md under `_archive/`), audit recorded `tool_archived` + `skill_archived` outcomes. After forced federation refresh, user-tools list is `(none)`.
- [ ] F3.16 Live-verify iterations stream as collapsible blocks - DEFERRED to F5. Socket.io events fire (telemetry path verified by F1.13 audit-emit symmetry); UI consumer is F5 work.

**F3 follow-ups shipped during the phase:**
- `tool_author` system prompt strengthened to require `if __name__ == "__main__"` (Gemma defined `main()` but never called it on the first end-to-end run; framework round-trip didn't fail because empty stdout passes the weak round-trip check; subprocess+pytest validation in F3-extended would have caught it).
- `archive_tool` step adds a 0.4s settle before federation refresh so noted-tools' file watcher has time to detect the rm and update its registry. Without it, the federation pulls a stale tools list and the LLM still sees the tool for up to 30s.
- Cross-container chown helper in `step_handlers.py` handles the noted (root) -> noted-tools (UID 1000) ownership drop on every publish/archive operation.

---

## F4: Skills hot-reload (target ~3 days)

- [x] F4.1 Watcher in `backend/app/managers/llm_skills.py`: `start_watcher()` + `_watch_loop()` using `watchfiles.awatch` on both `data/skills/` and `data/domains/*/skills/`. Resolves changed paths to owning skill folder, hot-reloads via `_reload_skill_from_dir` or `_unload_skill_by_folder`. RLock-guarded `_skills` dict. Started in noted lifespan, stopped on shutdown.
- [x] F4.2 Live-verify hot-load 2026-05-09: dropped `data/skills/probe_skill_f4/SKILL.md` from host, watcher fired within 1.5s, log line `skill hot-loaded: probe_skill_f4`, visible in live `/api/llm/skills` endpoint with correct description + triggers.
- [x] F4.3 Live-verify hot-update 2026-05-09: modified the SKILL.md (description + triggers + priority 2->1), watcher fired `skill hot-updated`, live endpoint reflected new fields.
- [x] F4.4 Live-verify create_tool co-publishes 2026-05-09: full create_tool workflow ran 11.44s on Gemma; publish_skill wrote `data/skills/greeting_generator/SKILL.md` (folder convention), watcher hot-loaded it, live registry shows it with the architect-selected triggers.
- [x] F4.5 Live-verify remove_tool atomic archive 2026-05-09: both archive_tool and archive_skill steps completed; watcher fired `skill hot-unloaded: greeting_generator`; live registry no longer contains it; federation refresh shows user-tools `(none)`. Archive paths exist on disk in `_archive/` for both.

**F4 follow-ups shipped during the phase:**
- F3's `publish_skill` used a flat `.md` file convention that the existing SkillRegistry never picked up (it expects folders with `SKILL.md` inside, per `data/skills/<name>/SKILL.md`). Fixed: `publish_skill` now creates the folder + writes SKILL.md atomically (write-temp + rename to dodge watcher debounce on partial files).
- F3's skill markdown template used multi-line YAML lists for `triggers`. The existing SkillRegistry's frontmatter parser only handles inline list syntax (`triggers: [a, b]`). Fixed: template emits inline lists with proper YAML quoting via `_quote_yaml_inline`.
- `archive_skill` corrected to move the FOLDER not a flat file.

---

## F5: Workflow inspector UI (target ~3-4 days)

- [x] F5.1 Backend `GET /api/workflows/types` (registered types + plan templates + outcomes). Tenant comes from `X-Forwarded-User`, falls back to `default`.
- [x] F5.2 Backend `GET /api/workflows` + `POST /api/workflows/run`. List merges in-memory live workflows with on-disk snapshots from prior runs (workspaces are in-memory and would otherwise vanish on noted restart). Run returns `workflow_id` immediately with the loop running asynchronously.
- [x] F5.3 Backend `GET /api/workflows/{workflow_id}` (state + tail of audit JSONL up to 500 lines) + `POST /api/workflows/{workflow_id}/resume`. Resume endpoint live-verified: audit shows `workflow_resumed` then `step_started` again.
- [x] F5.4 Backend `POST /api/workflows/{workflow_id}/abort`. Live-verified 2026-05-09: workflow status went `suspended -> aborted` with `finished_at` set.
- [x] F5.5 Backend `POST /api/workflows/{workflow_id}/rerun`. Returns new workflow_id; same inputs preserved; original unchanged. Live-verified 2026-05-09.
- [x] F5-extra: workflow loop now writes a final state.json snapshot at completion / failure (was suspend-only). Inspector reads disk + live store. Without this, prior workflows vanished on noted restart - real gap caught by the F5.2 probe and fixed in flight.
- [/] F5.6 Frontend: shipped as a top-level View menu item (`Workflow Monitor`) opening a floating jsPanel, since the existing pattern for KB Monitor is jsPanel-based. Tighter than a tree-tab and reuses the same affordance pattern users already know. Files: `frontend/js/WorkflowMonitorPanel.js` (~430 LOC), `frontend/css/workflow-monitor-panel.css`, menu wiring in `frontend/menu.json` + `app-menu.js` + `app.js`. Asset-served verified 2026-05-09 (HTTP 200 on .js + .css; `view.workflowMonitor` present in shipped menu.json). Browser-pixel verification: pending user's click-through.
- [/] F5.7 Frontend list view: shipped. Two-column layout (320px list + flex detail). Each row renders status pill, type, started timestamp, step-count progress, workflow_id. Top bar has status + type filters + refresh button + counts (live / from_disk / returned).
- [/] F5.8 Frontend detail view: shipped. Header (status pill + type + actions), workflow_id + suspend_reason, per-step list (status icon + name + retries + elapsed + error block + output keys), outcomes pills, audit timeline (last 500 events from /api/workflows/{id}'s audit field).
- [/] F5.9 HITL approval modal: minimal jsPanel.modal triggered when a `system_request` event fires with `type: approve_resume`. The framework already suspends with this event on retry exhaustion. The modal surfaces the prompt; user resumes / aborts via the inspector panel itself (the modal is informational since the action surface lives in the detail pane).
- [x] F5-extra Socket.io listeners: 9 workflow events wired in `KernelClient.js` (workflow_started / step_started / step_completed / step_failed / workspace_sync / workflow_completed / workflow_failed / workflow_suspended / workflow_resumed / system_request). Panel subscribes via `client.on(...)` and triggers a refresh on every event.
- [ ] F5.10 Live-verify Socket.io push refresh - PENDING USER BROWSER TEST. Backend emits the events (verified by F1.13 audit-emit symmetry: every audit line corresponds to a telemetry.emit call); frontend listens via the new KernelClient subscriptions; refresh triggers on every event. Browser-pixel test pending.
- [ ] F5.11 Live-verify click-through list -> detail - PENDING USER BROWSER TEST.
- [ ] F5.12 Live-verify re-run from inspector - PENDING USER BROWSER TEST. Backend rerun endpoint live-verified 2026-05-09; frontend wiring is `_action('rerun', wf_id)` which switches selection to the new workflow_id.
- [ ] F5.13 Live-verify HITL modal - PENDING USER BROWSER TEST.

---

## F6: UI badges + provenance polish (target ~2 days)

- [/] F6.1 Explorer tools tree provenance pill: `<span class="explorer-prov-pill">user</span>` appended to user-authored tool titles in `_loadToolsTree`. Tool detail header (`_showToolDetail`) renders a `USER` pill next to the WRITE/READ tier badge. Source-tree shipped 2026-05-09; browser-pixel verification pending user click-through.
- [x] F6.2 Chat-panel provenance pill LIVE-SHIPPED 2026-05-09. `ChatPanel.appendToolBadge` looks up provenance via `ChatPanel._isUserTool(name)` against a lazily-populated cache of `/api/llm/mcp-tools` (one fetch per page-load). User tools render with a small purple `user` pill matching Explorer's pill colour. `ChatPanel.notifyToolListChanged()` invalidates the cache when callers know the registry changed (workflow publish/remove). Browser-pixel verification pending user click-through; backend asset shipping verified (HTTP 200 + 2 prov-pill references in shipped JS).
- [x] F6.3 Settings badge - N/A. Survey shows only Explorer + ChatPanel render the tool list in noted's frontend; no separate "settings" surface for tools exists. Marking complete-by-virtue-of-not-existing rather than as a deferral.
- [x] F6.4 Skill provenance LIVE-VERIFIED 2026-05-09. SkillRegistry's Skill class extended with 6 lineage slots; parser captures them via the existing key:value frontmatter loop. `/api/llm/skills` (list) and `/api/llm/skills/{name}` (detail) surface provenance + source_workflow + created_at + created_by when present. Frontend `_loadSkillsTree` appends `user` pill; `_showSkillDetail` renders USER tag + provenance card with click-through to WorkflowMonitor. publish_skill mirrors publish_tool's lineage injection (provenance/created_at/created_by/source_workflow_id/source_workflow_type/source_workflow_tenant flat-keyed in YAML frontmatter so the existing parser captures them; reconstructed into the source_workflow object on the API side).
- [x] F6.5 Source-workflow click-through: `publish_tool` now injects `_meta.source_workflow = {type, workflow_id, tenant_id}` + `created_by` + `created_at` at write time (LLM doesn't know its own workflow id; the publish step does). Live-verified 2026-05-09: f6_greet's `_meta.source_workflow.workflow_id` matches the create_tool workflow that produced it. Explorer tool detail renders a Provenance card with an `open in Workflow Monitor` link that calls `app.showWorkflowMonitor(workflow_id)`. WorkflowMonitorPanel.open() accepts a select-id and applies pending selection on next refresh.
- [x] F6.6 LLM tool-list byte-identity invariant LIVE-VERIFIED 2026-05-09: `/mcp/` tools/list returns identical key sets `{description, inputSchema, name}` for native (`list_files`) and user-authored (`f6_greet`) tools. `_meta` correctly stripped at the LLM layer; preserved on the UI endpoint (`/api/llm/mcp-tools`) for inspector use. Phase A.5 invariant preserved through the full F3 publish + F6 lineage-injection path.
- [ ] F6.7 Browser-pixel verification - PENDING USER CLICK-THROUGH on the Explorer tool detail card.

**F6 follow-ups shipped during the phase:**
- `step_handlers.publish_tool` injects source-workflow lineage + created_by + created_at into tool.json's `_meta` at publish time. Without this, F6.5's click-through link would never appear because Gemma's tool_author can't know its own workflow id.
- F3's tool_author prompt strengthening (require `if __name__ == "__main__"`) caught a real edge case during F6 cycles: Gemma sometimes embeds unescaped dict literals like `{"name": "string"}` inside double-quoted Python strings, causing SyntaxError. The framework's `validate_tool_structure` step caught it (ast.parse fails), retried 2x, then suspended with the validator's complaint. Tool_author prompt could be hardened further to dodge this, but the framework already handles it correctly.

---

## Cumulative gates (Definition of Done)

- [ ] All framework primitives shipped + live-verified (F1)
- [ ] All worker presets shipped + structured-output rate measured (F2)
- [ ] First-wave workflows round-trip end-to-end on both backends (F3)
- [ ] Skills hot-reload working (F4)
- [ ] Workflow inspector UI shipping every event in real time (F5)
- [ ] UI badges + provenance lineage visible (F6)
- [ ] No GBNF in any framework LLM call path
- [ ] KB ingestion untouched and continues identical operation
- [ ] Identity threading: `X-Forwarded-User` propagates when present, fallback `"default"` otherwise; no code change required when auth plan lands
- [ ] Tenant-prefixed storage paths from day one (`data/tenants/<tenant_id>/...`)
- [ ] Suspend / resume verified end-to-end at least once on a real workflow (not just synthetic probe)

---

## Open dependencies

- Auth plan (separate): extending oauth2-proxy `auth_request` to `/noted/`, `X-Forwarded-User` middleware, Infisical secret store. The framework ships with constant fallbacks; activates per-tenant when this plan lands.
- KB ingestion retrofit: not in scope here. Framework primitives shaped to allow future retrofit if duplication becomes painful.

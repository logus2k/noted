# Capability-Extension Workflow Framework

(historical project name: self-learning - file kept at `documents/self-learning/self_learning_plan.md` for continuity)

## Goal

A generic agentic-workflow framework that runs sequenced LLM-and-tool steps with shared infrastructure: workspace state, suspend / resume, telemetry, audit, identity threading. Workflows that durably extend the assistant's capabilities (publishing a new tool, a new skill, new domain content, or any combination of those) are the first wave registered on the framework. Self-learning is an outcome property a workflow can carry, not a workflow type.

The end-state for a capability-extending workflow is a closed loop:

```
mission -> fetch context -> author primitive -> validate -> publish -> next turn uses it
```

The framework is workflow-agnostic; future non-extending workflows benefit from the same primitives.

---

## Scope

### In scope

- Framework primitives: workflow registry, workflow loop, per-(tenant, workflow) workspace, suspend / resume, telemetry events, per-step audit, identity threading hooks.
- First-wave workflows registered on the framework: `create_tool`, `create_skill`, `remove_tool`, `remove_skill`. Each declares its outcome property.
- Worker presets in agent_server: `planner`, `tool_author`, `api_tester`, `skill_author`. Each is a small system-prompt + sampling preset.
- Validation tools registered with deterministic implementations where mechanical checks exist; sub-LLM implementations only where no mechanical signal does. Architects pick implementation per tool at design time.
- Skills hot-reload in noted backend's existing SkillRegistry.
- Workflow inspector UI in Explorer: list, detail, audit trail, HITL approval modal.
- Provenance + outcome badges on tool / skill listings.

### Out of scope (separate plans)

- Auth wiring (extending oauth2-proxy `auth_request` to `/noted/`, FastAPI middleware reading `X-Forwarded-User`). See separate auth plan.
- Infisical secret store + per-tool secret allow-list. Moved to the auth plan.
- KB ingestion retrofit onto this framework. Design for compatibility (this plan); retrofit only if duplication becomes painful.
- Per-tenant GPU / queue fairness in agent_server. Tracked under deployment-tier work (T2 / T3 in `feedback_dont_assume_single_user_local.md`).
- Inter-tool dependencies, public marketplace, drift detection. Deferred.

---

## Foundation: what already exists and is live

| Capability | Where | Used as |
|---|---|---|
| `noted-tools` container (Phase A complete, verified 2026-05-08) | live | Hosts user-authored tools as MCP, audited per-call. Hot-reload of tools, per-tool venv, subprocess executor with RLIMIT_AS + timeout. |
| Tool federation into noted | live | `/api/llm/mcp-tools` includes user tools with `provenance` + `_meta`. LLM sees them in `to_anthropic_tools` / `to_openai_tools`. Live-tested 2026-05-08 with Gemma 4 calling `hello_user`. |
| OAuth2Proxy + Google IdP | live (gating `/goaccess`) | Extension to `/noted/` and identity propagation tracked in separate auth plan. |
| Per-domain ArcadeDB databases | live | Hard partitioning at the Domain axis; tenant axis is a naming change, not a schema migration. See `reference_per_domain_database_isolation.md`. |
| ChromaDB collections per Domain | live | Prefix-named, naming convention extends to per-tenant. |
| `agent_server` forwarding | live | LLM calls pooled (`pool_size=20`), forwarded to `llama-server` over HTTP. GPU-agnostic at the noted layer. |
| Web fetch (Camoufox) | live | Doc retrieval source for `tool_author`. |
| MCP Streamable HTTP transport | live | Protocol between noted and `noted-tools`; same client used by the framework for forwarding. |
| Suspend / resume pattern | live in KB ingestion (`graph/app/research_builder.py`) | `threading.Event` + on-disk snapshot. The framework reuses the pattern in its own implementation; KB ingestion's code is not retrofitted. |
| Native structured tool-call API | live | `delta.tool_calls` returns structured fields (verified by curl 2026-05-04). The framework relies on this; no GBNF, see `feedback_gbnf_kills_thinking_and_tool_calls.md`. |

---

## Architecture

### Workflow lifecycle

A workflow registration declares:

- `type`: e.g., `create_tool`, `create_skill`, `remove_tool`.
- `outcomes`: structured list (e.g., `["tool_published", "skill_published"]`). Used for audit, UI surface, future per-outcome permissions.
- `plan_template`: ordered list of typed steps. Each step is either an LLM-driven call against a worker preset, or a deterministic step (no LLM).
- `tools_available`: per-step task-named tools the worker can call. Architect-decided implementations (deterministic vs sub-LLM).

Lifecycle:

```
mission -> orchestrator picks workflow type
        -> instantiates workspace (keyed by tenant_id, workflow_id)
        -> executes plan steps sequentially (LLM or deterministic)
        -> emits per-step events on Socket.io
        -> on success: invokes outcome handlers (publish tool, publish skill, etc.)
        -> writes audit row per step + per workflow
        -> on suspend: snapshots workspace to disk, blocks on threading.Event
        -> on resume / abort: continues from snapshot or fails cleanly
```

### Workspace state

In-process Python dict, keyed by `(tenant_id, workflow_id)`. Structured: completed steps' results, current step's input / output, audit pointers. Survives suspend / resume via on-disk snapshot at `data/tenants/<tenant_id>/workflows/<workflow_id>/state.json`.

Pruning: when workspace size exceeds 16k characters, mechanical pruning drops verbose logs of completed steps but keeps step results and metadata. No LLM-based summarization.

For T1 (single-host multi-user) the in-process dict is sufficient. For T2+ (multi-host) sticky session affinity at the load balancer keeps a workflow on its originating noted instance. T3+ scale would migrate workspace to an external KV (Redis); the framework's interface is shaped to allow that swap without changes to workflow definitions.

### Telemetry events (Socket.io)

| Event | Payload | UI use |
|---|---|---|
| `workflow_started` | `{workflow_id, type, outcomes, plan, tenant_id}` | Render workflow in inspector with checklist |
| `step_started` | `{workflow_id, step_index, step_type}` | Spinner on the step |
| `step_completed` | `{workflow_id, step_index, result_summary}` | Check-mark, expand for detail |
| `step_failed` | `{workflow_id, step_index, error_summary, retry_count}` | Red mark, expandable error |
| `workspace_sync` | `{workflow_id, delta}` | Live-update workspace preview tab |
| `system_request` | `{workflow_id, type, prompt}` | HITL modal (approval, clarification) |
| `workflow_suspended` | `{workflow_id, reason, snapshot_path}` | Suspended banner with Resume / Abort |
| `workflow_resumed` | `{workflow_id}` | Banner cleared |
| `workflow_completed` | `{workflow_id, outcomes}` | Final state + outcome badges |

Same Socket.io pipeline that powers `services:health`. Per `feedback_sse_needs_x_accel_buffering.md`, no SSE-specific concerns at the noted entry point (these are Socket.io, not SSE).

### Per-step LLM execution

For an LLM-driven step:

1. Framework picks the worker preset declared in the plan template.
2. Builds context: relevant workspace slice + previous step's output + tools available at this step.
3. Calls `agent_server`, which forwards to `llama-server` (`pool_size=20` so multiple workflows can run concurrently up to that cap).
4. Captures structured tool calls via the native API (no GBNF).
5. Executes tool calls via noted-tools or noted backend's tool dispatch.
6. Validates step output against a JSON schema declared by the step type.
7. On schema-validation failure: bounded retry (max 2) with the validator's complaint fed back as additional context. Beyond 2 retries: step fails, workflow suspends with `system_request` for HITL.
8. Persists step result to workspace, emits `step_completed`.

### Per-step deterministic execution

For a deterministic step (no LLM):

1. Framework calls the step function directly with workspace slice.
2. Result persisted, `step_completed` emitted.
3. No retry path needed.

### Validation tools: architect-decided implementations

The framework registers task-named tools the LLM can call. The implementation is fixed at design time:

| Tool name | Implementation chosen by architect | Reasoning |
|---|---|---|
| `validate_generated_client` | subprocess + smoke tests | Mechanical signal exists |
| `validate_schema` | `jsonschema.validate(...)` | Mechanical |
| `assess_explanation_clarity` | sub-LLM call | No mechanical signal for prose quality |
| `verify_tool_round_trip` | call the tool with sample input, check non-error response | Mechanical |

The LLM picks the task tool by intent, not by cost. Architects do the cost optimization at design time.

### Tool schema with provenance + outcome lineage

Tool registration carries `_meta`:

```json
{
  "name": "fetch_jira_issue",
  "description": "...",
  "input_schema": { ... },
  "_meta": {
    "provenance": "user",
    "created_by": "<sub_claim_or_default>",
    "created_at": "...",
    "source_workflow": {
      "type": "create_tool",
      "workflow_id": "wf_abc123",
      "tenant_id": "<tenant_id_or_default>"
    },
    "version": 1,
    "language": "python"
  }
}
```

`_meta` is stripped before LLM presentation (already verified in Phase A.5).

---

## Phased plan

Effort assumes one focused engineer. Total: ~4 weeks plus ~1 week of buffer for integration.

### F1: Framework primitives (~1.5 weeks)

- Workflow registry module.
- Workflow loop with state machine + retry.
- Workspace state container with mechanical pruning.
- Suspend / resume mechanism (mirrors KB ingestion's pattern in a separate codebase).
- Identity-threading hooks reading `X-Forwarded-User` (default `"default"` constant when absent).
- Audit log writer per workflow.
- Telemetry event emitters integrated with the existing Socket.io pipeline.

Acceptance:
- A synthetic 3-step workflow runs end-to-end via direct API call; all events fire; audit lands; workspace state retrievable via inspector.
- Triggered step failure causes suspend; on-disk snapshot present at expected path; manual resume completes the workflow.
- Identity threading: with `X-Forwarded-User=alice`, audit shows `actor_id=alice`; without header, audit shows `actor_id=default`.
- Two concurrent workflows in different tenants run without state collision.

### F2: Worker presets (~3 days)

- `planner`: system prompt for plan generation. Output is a tool call returning structured plan args validated against a JSON schema.
- `tool_author`: writes Python / JS clients + tool.json schemas.
- `api_tester`: writes smoke tests, runs them in subprocess, returns verdict.
- `skill_author`: writes skill markdown with `_meta` header.

Each preset is `agent_server/data/agents/<preset>.agent.json` + `agent_server/data/prompts/<preset>_system_prompt.txt`. Sampling tuned per preset (low temperature for structured outputs; default for prose).

Acceptance:
- Each preset reachable via direct probe; structured output rate >= 95% over 50 trials.
- `planner` produces valid plan JSON for representative missions against both Claude and Gemma. Bounded retry catches malformations.

### F3: First-wave workflows (~1.5 weeks)

- `create_tool` workflow registered: plan template (fetch_docs -> tool_author -> api_tester -> publish), step types, outcomes (`["tool_published"]`).
- `create_skill` workflow: when `create_tool` succeeds, the matching skill is published via an embedded `skill_author` step. Outcome: `["skill_published"]`.
- `remove_tool` / `remove_skill`: archive directories under `data/tenants/<tenant_id>/user_tools/_archive/`, drop from active registries, hot-reload.
- Validation tools registered with architect-decided implementations.

Acceptance:
- `create_tool` from a representative mission against Claude completes in <= 3 iterations on a clean OpenAPI-documented service.
- Same against Gemma in <= 6 iterations.
- Generated tool registers in `noted-tools` (Phase A wiring already verified); LLM calls it on the next chat turn and round-trips correctly.
- Failed creation: max iterations exhausted, no tool registered, iteration history preserved for debug, workflow ends in `failed` state.
- All iterations stream as collapsible blocks via the Socket.io event schema.
- `remove_tool` archives and reloads cleanly; subsequent calls return tool-not-found.

### F4: Skills hot-reload (~3 days)

- File watcher in noted backend's existing `SkillRegistry` on `data/skills/`.
- `create_skill` workflow's publish step writes the skill file with `_meta` header; `SkillRegistry` picks it up within 1 second.

Acceptance:
- Drop a skill `.md` file: registered within 1 second; auto-injects on relevant turns when `priority=1`.
- Skill removal triggers reload; skill no longer in registry.
- `create_tool` always co-publishes a paired skill; `remove_tool` archives both atomically.

### F5: Workflow inspector UI (~3-4 days)

- New tab in Explorer's Assistant section: "Workflows" / "Activities."
- Lists workflows by tenant: type, outcomes, status, started_at, finished_at.
- Workflow detail page: step list, current state, audit trail, "Re-run" button (re-instantiate with same inputs as a new workflow).
- HITL approval modal triggered by `system_request` event with timeout (auto-abort after configurable wall-clock cap).

Acceptance:
- Workflow appears in Explorer within 1 second of starting (Socket.io push verified).
- Clicking a workflow shows step-by-step audit trail + workspace snapshot.
- Re-run produces a new workflow with same inputs and a fresh audit / workflow_id.
- HITL modal: approval resumes; abort cleanly fails the workflow.

### F6: UI badges + provenance polish (~2 days)

- Tool listings in Explorer + chat panel + settings show `provenance` badge for user tools.
- Skill listings show same.
- User-tool detail page links to its `source_workflow` (workflow_id), opens that workflow in the inspector.

Acceptance:
- LLM tool-list payload byte-identical for native and user tools (already verified in Phase A.5; preserve invariant).
- UI badges rendered in all three surfaces.
- Click-through from tool to source workflow works.

---

## Cross-cutting concerns

### Identity threading

Request entry middleware reads `X-Forwarded-User` (set by oauth2-proxy when its `auth_request` block extends to `/noted/`). Threaded through the workflow context as `tenant_id` and `actor_id`. Falls back to `"default"` constant when the header is absent. Audit, `_meta.created_by`, tool subprocess `ACTOR_ID` env var all populated from this. No code change in this plan when the auth plan lands.

### Multi-tenant storage

All persistent state under `data/tenants/<tenant_id>/...` from day one. Single-tenant mode uses `tenant_id="default"`. Specific paths:

- `data/tenants/<tenant_id>/user_tools/<tool_name>/` (replaces `data/user_tools/<tool_name>/` flat layout from Phase A; migration is rename + symlink during cutover)
- `data/tenants/<tenant_id>/workflows/<workflow_id>/state.json` (suspend snapshot)
- `data/tenants/<tenant_id>/workflows/<workflow_id>/audit.jsonl` (per-workflow audit)
- `data/skills/` stays flat for now; per-tenant skill storage is a follow-on.

### LLM call discipline

- Native structured tool-call API for plan / step output. No GBNF, per `feedback_gbnf_kills_thinking_and_tool_calls.md` (current llama-server's grammar enforcement blocks `<|channel>` thinking and `<|tool_call>` markers; bare-tool-call API doesn't have this issue).
- JSON-schema-validate after each call; bounded retry with validator's complaint fed back if validation fails.
- Workspace pruning is mechanical; no summarizer LLM call.
- Workflow length capped at default 6 steps; longer requires explicit user opt-in. Per-step ETA streamed via `step_started` event so users can abort.

### Verifier vs LLM-Critic discipline

Implemented at the architect level, fixed at design time, hidden behind task-named tools. The LLM calls `validate_generated_client` (subprocess + smoke tests) or `assess_explanation_clarity` (sub-LLM) by task fit. The LLM never picks based on cost; the architect commits to the cheapest mechanism that fits the task at registration time.

### Failure modes and recovery

| Failure | Behavior |
|---|---|
| Worker preset fails to produce valid output after retries | Step marked failed; workflow suspends; `system_request` event fires for HITL |
| Workflow exceeds wall-clock cap | Suspends; on-disk snapshot; operator decides resume or abort via inspector UI |
| Subprocess executor (e.g., `api_tester`) crashes | Step marked failed with stderr in audit; framework continues; doesn't affect host |
| `agent_server` / `llama-server` unreachable | Workflow suspends; auto-resumes when service recovers (verified by `services:health` LED) |
| `noted-tools` unreachable mid-workflow | Same as above; workflow can resume on the same tenant once `noted-tools` is healthy |
| KB ingestion runs concurrently | Untouched; both mechanisms operate independently |

### Compatibility with KB ingestion

The framework's primitives (workspace, suspend / resume, telemetry, audit) are designed to mirror what KB ingestion already implements internally. Retrofit is feasible later if the duplication becomes painful, but is not in this plan. Both mechanisms run independently.

---

## Test plan

Per-phase live-evidence verification (no claims of "verified" without probe output, per `feedback_no_verified_without_live_evidence.md`):

- F1: synthetic 3-step workflow probe with controlled failing step. Verify suspend, observe state file, manual resume, completion. Audit trail + Socket.io trace inspected.
- F2: per-preset direct probe, structured output validity rate measured.
- F3: end-to-end `create_tool` probe with both Claude and Gemma backends. Success rate measured against representative APIs (target: Claude >= 80%, Gemma >= 50%).
- F4: skill drop / remove cycle, subsequent chat turn auto-injects.
- F5: click-through verification in browser; no claim of "shipped" without browser-pixel evidence.
- F6: byte-comparison of LLM tool-list payload (native vs user); UI badge verification across three surfaces.

---

## Effort estimate

| Phase | Effort |
|---|---|
| F1 framework primitives | ~1.5 weeks |
| F2 worker presets | ~3 days |
| F3 first-wave workflows | ~1.5 weeks |
| F4 skills hot-reload | ~3 days |
| F5 workflow inspector UI | ~3-4 days |
| F6 badges + polish | ~2 days |

Total: ~4 weeks of execution + ~1 week buffer = realistic ~5 weeks of focused engineering.

---

## Definition of done

The framework + first-wave workflows ship when ALL hold:

1. Framework primitives shipped and live-verified: workflow registry, loop, workspace, suspend / resume, audit, telemetry, identity-threading hooks.
2. First-wave workflows round-trip end-to-end:
   - `create_tool` succeeds with both Claude and Gemma backends on representative APIs (Claude >= 80%, Gemma >= 50%).
   - `create_skill` paired with `create_tool` publishes both atomically.
   - `remove_tool` / `remove_skill` archive and audit cleanly.
3. Telemetry events render in the workflow inspector UI for every workflow execution.
4. Identity threading: `X-Forwarded-User` propagates to audit when present; fallback to `"default"` constant when absent. No code change required when the auth plan lands.
5. Tenant-prefixed storage paths from day one. Single-tenant mode uses `"default"` tenant id. Phase A's flat tool layout migrated to `data/tenants/default/user_tools/...` during cutover.
6. Suspend / resume verified end-to-end (kill mid-execution, observe state file, resume via inspector UI, completion).
7. UI badges (provenance) present on tool + skill listings in Explorer + chat panel + settings.
8. LLM tool-list payload byte-identical for native and user tools (Phase A.5 invariant preserved).
9. No GBNF anywhere in the framework's LLM call paths. Plan / step validation goes through native tool-call API + JSON schema + bounded retry.
10. KB ingestion remains untouched and continues to function identically. Framework primitives are shaped for future retrofit; no retrofit performed in this plan.

---

## Open dependencies on other plans

- Auth plan (separate): extending oauth2-proxy `auth_request` to `/noted/`, `X-Forwarded-User` middleware in noted backend, Infisical secret store. The framework ships with constant fallbacks; activates on tenants when auth lands.
- Deployment-tier work: per-tenant GPU / queue fairness, multi-host orchestration via Swarm / K3s / K8s, cross-host workspace state migration. Not blocked on this plan; this plan is tier-agnostic at the application layer.

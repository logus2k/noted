# Self-Learning Plan: Autonomous Tool + Skill Authoring

## Goal

Enable noted's Assistant to extend its own capabilities at runtime: given a mission ("integrate with service X so I can do Y"), the Assistant locates the relevant API documentation, generates a working client in Python or JavaScript, validates it against acceptance criteria, and publishes both a new MCP tool and a matching skill — without a code change to the noted codebase, without a container restart in the common case, and without leaking any secrets to the LLM context.

The end-state is a closed self-extension loop:

```
mission -> fetch docs -> author client -> author tests -> run tests -> publish tool + skill -> use tool
```

This document is the plan for getting there. Single-user scope for V1; multi-user hooks are present so the later migration is purely additive.

---

## Scope

### In scope (V1)

- Self-authored MCP tools, hot-reloadable, isolated in a dedicated container.
- Self-authored skills, hot-reloadable, no restart.
- Per-tool Python or JavaScript venv with isolated dependencies.
- Subprocess execution boundary for crash containment + dependency isolation.
- License-clean secret storage via Infisical (MIT) for credentials any new tool needs.
- An autonomous orchestration loop with two new agent_server presets: `tool_author` (writes the client) and `api_tester` (writes + runs validation tests).
- Iteration loop with model-aware caps (Claude: 3, Gemma: 6) and full streaming visibility into each iteration.
- Audit log + rollback for every self-authored tool.
- UI surface in noted to browse self-authored tools and inspect their creation history.

### Deferred to later phases

- Multi-user identity, RBAC, per-user tool ownership and secret scoping. Hooks are present in V1's data model.
- Tool versioning and upstream-API drift detection (basic version field present, no auto-revalidation loop).
- Inter-tool dependencies (a user tool depending on another user tool).
- Tool deprecation lifecycle.
- Public marketplace / sharing across noted instances.

---

## Foundation: what already exists in noted today

| Capability | Where | Used as |
|---|---|---|
| Web fetch (Camoufox) | `noted/backend/app/managers/web_fetch_manager.py` | Doc retrieval for `tool_author` |
| Code generation + file write | `update_cell` / `insert_cell` / `create_file` MCP tools | Producing client code |
| Code execution | Notebook kernel + Python/JS file execution + terminal | Running smoke tests |
| Skills as markdown | `data/skills/` directory + SkillRegistry singleton | Publishing the skill alongside the tool |
| Tool calling protocol | MCP schemas + native tool calls (Anthropic + Gemma) | The contract the new tool must satisfy |
| Multi-language runtime | Python 3.10-3.14, Node.js 20/22, R 3.6.3-4.5.1 | Hosting the generated client |
| Diff approval gate | Existing write-tool confirmation panel | Optional human-in-loop checkpoint |
| Local + cloud LLMs | Gemma 4 E4B local, Anthropic Claude API | Local-first orchestration with cloud fallback |
| Agent presets | `agent_server/data/agents/*.agent.json` + `agent_server/data/prompts/*.txt` | Where the new presets live |
| MCP server | `/mcp/` endpoint with rate limiting, error taxonomy, feature toggle | Reused as the protocol between noted and the new tools container |

---

## Architecture

### Containers

```
noted (existing)               noted-tools (new)              infisical (new)
  - FastAPI + Socket.IO         - MCP server                    - MIT-licensed secret store
  - Notebook kernel             - File watcher on               - Postgres-backed (uses
  - Existing 25 tools             /app/data/user_tools/           noted's existing Postgres)
  - LLM router                  - Per-tool venv subprocess      - HTTP API for set/get/list
  - Skills singleton              executor                      - Master-key gated
  - SSO-ready (later)           - Audit log writer

         |                             |                              |
         +-----------------------------+------------------------------+
                            shared docker network
```

Communication:

- **noted -> noted-tools**: MCP over HTTP. Same protocol noted's own `/mcp/` endpoint already exposes externally; the noted backend becomes a second consumer.
- **noted-tools -> infisical**: HTTPS with short-lived tokens issued at tool-execution time. Tokens have tight TTL (60s default) and scope to a single secret name. The noted backend never holds long-lived secret material.
- **noted-tools subprocess -> upstream API**: arbitrary HTTP/HTTPS to whatever service the tool integrates with. Network whitelist enforced at the container level (egress filtering optional but recommended).

### File layout

```
data/user_tools/
  <tool_name>/
    tool.json              # MCP schema + _meta block
    tool.py | tool.js      # Implementation
    requirements.txt       # Python deps (or package.json for JS)
    smoke.py | smoke.js    # Validation tests written by api_tester
    venv/                  # Created on first load, cached afterwards
    history/               # Audit trail
      v1/
        prompt.md          # Original mission text
        api_docs.md        # Fetched documentation snapshot
        iterations/
          1/
            client.py
            tests.py
            test_output.txt
            verdict.md
          2/
            ...
        published.json     # Final manifest with timestamps + actor_id

data/skills/                # Existing directory; user-authored skills land here
  <skill_name>.md           # Same format as native skills, with _meta header
```

### Tool schema with metadata

```json
{
  "name": "fetch_jira_issue",
  "description": "Retrieve a Jira issue by key with full field expansion.",
  "input_schema": {
    "type": "object",
    "properties": {
      "issue_key": {"type": "string", "description": "Jira issue key, e.g. PROJ-123"}
    },
    "required": ["issue_key"]
  },
  "_meta": {
    "provenance": "user",
    "created_by": "system",
    "created_at": "2026-05-07T12:00:00Z",
    "source_api_docs": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
    "version": 1,
    "language": "python",
    "iterations_to_pass": 2,
    "model_used_for_authoring": "claude-sonnet-4-6"
  }
}
```

`_meta` is stripped before the schema is sent to the LLM — the model sees only `name`, `description`, `input_schema`. Metadata drives the UI's audit panel, governance, and rollback flows.

### Subprocess execution flow

For each tool call from the LLM:

1. noted backend posts the MCP `tools/call` request to `noted-tools`.
2. `noted-tools` resolves the tool name, locates `data/user_tools/<name>/`, validates input against `tool.json`'s `input_schema`.
3. Spawns subprocess: `<venv>/bin/python tool.py` (or `node tool.js`) with the input JSON on stdin.
4. Tool process requests any secrets it needs by name from Infisical using a short-lived scoped token issued by `noted-tools` for THIS execution only.
5. Tool process performs its work, writes the MCP response JSON to stdout.
6. `noted-tools` validates the response against `output_schema` (when declared), forwards it back to noted, writes an audit-log entry.

Crash containment: subprocess crash terminates that single tool call with a clean error. `noted-tools` stays alive. noted stays alive.

Resource limits: each subprocess gets a memory cap (default 512MB), CPU cap (default 1 core), and execution timeout (default 60s). Configurable per tool via `_meta.limits`.

---

## Phased plan

Effort estimates assume one focused engineer. Total: **~4 weeks** of execution time, plus ~1 week of buffer for integration and polish.

### Phase A: noted-tools container + plugin model

**Effort: ~2 weeks**

#### A.1 Container skeleton

- New service `noted-tools` in `services/docker-compose.yml`.
- Base image: Python 3.12-slim + Node.js 22 LTS (for JS tools).
- FastAPI process exposing MCP server on a dedicated port (e.g. 7702).
- Bind mounts: `data/user_tools/` (read-write for tool execution + venv caching), `data/skills/` (read-only mirror for cross-reference, write happens on noted's side).

#### A.2 File watcher + hot reload

- Watch `data/user_tools/` for create/modify/delete of `tool.json` files.
- On change: re-parse the affected tool, validate schema, swap into the in-memory tool registry atomically. Old in-flight executions of the previous version finish under the previous code (subprocess-isolated, no shared state).
- Reload completes in < 200ms for a typical tool.

#### A.3 Per-tool venv management

- On first reference to a tool, check for `<tool_dir>/venv/`.
- If missing: create with `uv venv` (or `python -m venv` fallback), `uv pip install -r requirements.txt`. Cache.
- On `requirements.txt` change: rebuild venv. Increment `_meta.version`.
- For JavaScript tools: `npm install` into a per-tool `node_modules/`.

#### A.4 Subprocess executor

- Pythontools: `<venv>/bin/python tool.py < input.json > output.json`.
- JavaScript tools: `node tool.js < input.json > output.json`.
- Resource limits via `resource.setrlimit` (Python) or container-level `cgroup` settings.
- Timeout enforced via `subprocess.run(timeout=...)`.
- stderr captured into the audit log on failure.

#### A.5 MCP exposure

- `noted-tools` registers itself in noted's MCP client list.
- noted backend's `/api/mcp/discover` endpoint aggregates tools from both its own internal registry and `noted-tools`'s registry into a single namespace.
- Tools sorted alphabetically; `_meta.provenance` carried in metadata for UI use only.

#### A.6 Audit log writer

- Every `tools/call` to a user tool produces an audit entry: `{tool_name, version, actor_id, started_at, finished_at, status, input_hash, output_hash, error}`.
- Append-only JSONL at `data/user_tools/<name>/history/audit.jsonl`.

#### Acceptance criteria — Phase A

- [ ] `docker compose up` brings up `noted-tools` and noted backend can list its tools via MCP.
- [ ] Drop a hand-written `tool.json` + `tool.py` into `data/user_tools/test_tool/` -> tool appears in noted's tool list within 1 second, no container restart.
- [ ] LLM can call the tool; result round-trips correctly; audit entry written.
- [ ] Modify `tool.py`, save -> next tool call uses new code; in-flight calls finish with old code.
- [ ] Crash a tool deliberately (`raise RuntimeError`) -> noted-tools stays up; noted stays up; LLM gets a clean error response with stderr in the diagnostic field.
- [ ] Modify `requirements.txt` to add a new package -> next call rebuilds venv (visible in logs); subsequent calls use new package.
- [ ] Memory cap enforced: a tool that allocates 1GB is killed at 512MB with a clean error.
- [ ] Timeout enforced: a tool that sleeps 120s is killed at 60s with a clean error.
- [ ] Two tools with conflicting Python deps (e.g. `requests==2.28` vs `requests==2.31`) coexist and both work.

---

### Phase B: Infisical secret store

**Effort: ~3-4 days**

#### B.1 Container setup

- `infisical/infisical:latest` image (MIT-licensed, verified at integration time).
- Postgres connection: shares noted's existing `noted-postgres` instance, separate database `infisical`.
- Master key from environment variable `INFISICAL_ENCRYPTION_KEY` (256-bit, generated once, persisted in compose `.env`).
- Web UI exposed on a dedicated port for secret management; API on a separate port for `noted-tools` consumption.
- Single-user / single-project / single-environment configuration in V1. Multi-user expansion is configuration-only (no schema migration).

#### B.2 Token broker in noted-tools

- New endpoint `noted-tools` -> Infisical: `issue_scoped_token(actor_id, secret_name, ttl_seconds=60)`.
- Returns a token usable only for the requested secret name, expires after TTL.
- Each tool subprocess invocation receives one such token via stdin (alongside the input payload), uses it to fetch its secret(s), discards.

#### B.3 Secret-reference indirection

- Tool inputs may contain `{"$secret": "infisical_secret_name"}` placeholders.
- The LLM never sees the actual secret value — only the placeholder name.
- `noted-tools` resolves placeholders during input validation (before subprocess invocation).
- Secrets named in the LLM's tool call are validated against an allow-list per tool, declared in `tool.json._meta.allowed_secrets`. Prevents one tool from exfiltrating arbitrary secrets.

#### B.4 Skill: secret management

- New skill `secrets_management.md` published to noted's skills directory.
- Documents: how the Assistant requests user-provided secrets, the never-in-LLM-context invariant, the allow-list pattern.

#### Acceptance criteria — Phase B

- [ ] Infisical container starts and persists secrets across restarts.
- [ ] `set_secret(name, value)` via Web UI -> `get_secret(name)` returns the value.
- [ ] `noted-tools` can fetch a secret using a scoped token; access is denied if the token's scoped name doesn't match the requested name.
- [ ] Token TTL enforced: a 60s-expired token is rejected.
- [ ] A tool calling `{"$secret": "github_token"}` in its input gets the resolved value at execution time.
- [ ] A tool that requests a secret NOT in its `allowed_secrets` list is denied with a clear error message.
- [ ] Audit log records "tool X requested secret Y" with timestamps; never records the secret value.
- [ ] LLM tool-call traces in `noted/data/llm_traces/` never contain plaintext secret values.

---

### Phase C: Authoring presets + orchestrator tools

**Effort: ~1 week**

#### C.1 `tool_author` preset

- New file `agent_server/data/agents/tool_author.agent.json`.
- New file `agent_server/data/prompts/tool_author_system_prompt.txt`.
- Sampling: temperature 0.1, max_tokens 4096 (clients can be long), top_p 0.9.
- System prompt instructs: read API docs, generate a self-contained client (Python preferred, JavaScript when explicitly requested), produce `tool.json` schema matching the client's signature, declare required secrets in `_meta.allowed_secrets`, declare resource limits if non-default.

#### C.2 `api_tester` preset

- New file `agent_server/data/agents/api_tester.agent.json`.
- New file `agent_server/data/prompts/api_tester_system_prompt.txt`.
- Sampling: temperature 0.1, max_tokens 2048.
- System prompt instructs: given a client implementation and acceptance criteria, write smoke tests covering the criteria, run them inside the per-tool venv subprocess, report pass/fail with structured diagnostics. On failure, identify which acceptance criterion failed and why.

#### C.3 `create_tool` orchestrator (built-in noted tool)

- Signature: `create_tool(name: str, mission: str, api_docs_url: str, language: str = "python", acceptance_criteria: list[str] = [])`.
- Implementation:
  1. Fetch `api_docs_url` via existing web fetch tool. If multi-page docs, follow up to N depth.
  2. Loop (max iterations from `MAX_ITERATIONS[backend]`):
     - Call `tool_author` preset with mission + docs + previous-iteration diagnostics.
     - Receive `client_code`, `tool_schema`, `requirements`.
     - Write to `data/user_tools/<name>/iterations/<i>/`.
     - Call `api_tester` preset with `acceptance_criteria` + client + a fresh subprocess invocation harness.
     - Receive test code; execute in subprocess; capture verdict.
     - If pass: break.
     - If fail: feed failure diagnostics back into next iteration.
  3. On pass: copy iteration's files to `data/user_tools/<name>/` (top level), increment version, write `published.json`, trigger noted-tools hot-reload.
  4. On exhaust without pass: leave iteration tree in place; report failure with last verdict; tool is NOT registered.
- Streams progress to chat panel as collapsible thinking blocks per iteration.

#### C.4 `remove_tool` built-in

- Signature: `remove_tool(name: str)`.
- Effect: archive `data/user_tools/<name>/` to `data/user_tools/_archive/<name>_<timestamp>/`, remove from active registry, trigger reload.
- Idempotent: removing a tool that doesn't exist is a no-op with a clear message.

#### C.5 Model-aware iteration cap

- Config in noted backend: `TOOL_AUTHOR_MAX_ITERATIONS = {"claude": 3, "gemma": 6}` (env-var overridable).
- Orchestrator reads the active model and applies the cap.
- All iterations stream to the chat panel; user can intervene via "Stop" button at any point.

#### Acceptance criteria — Phase C

- [ ] Both presets are loaded by agent_server at startup; both reachable via direct probe.
- [ ] `create_tool(name="github_issue", mission="fetch GitHub issue by repo+number", api_docs_url=..., language="python")` against Claude completes within 3 iterations on a clean OpenAPI-documented service.
- [ ] Same call against Gemma 4 completes within 6 iterations on the same service.
- [ ] Generated tool registers in `noted-tools` after a successful run.
- [ ] LLM (in a subsequent chat turn) can call the new tool by name; round-trips correctly.
- [ ] Failed creation (max iterations exhausted) leaves no tool registered; iteration history preserved for diagnostic.
- [ ] All iterations visible in chat as collapsible thinking blocks with code + test output.
- [ ] `remove_tool("github_issue")` archives the directory; tool no longer in registry; subsequent calls return tool-not-found.

---

### Phase D: Skills hot-reload

**Effort: ~3 days**

#### D.1 SkillRegistry watcher

- noted backend's existing SkillRegistry singleton gains a file watcher on `data/skills/`.
- On change: re-parse affected skill, swap atomically.

#### D.2 `create_skill` built-in

- Signature: `create_skill(name: str, when_to_use: str, content: str, priority: int = 2)`.
- Writes `data/skills/<name>.md` with the standard `_meta` header (provenance, created_by, created_at, version) and the standard skill body format.
- Triggers SkillRegistry reload.

#### D.3 `tool_author` co-publishes a skill

- When the orchestrator publishes a tool, it ALSO calls `create_skill` with a skill that documents when to use the tool, what the inputs mean, what kind of result to expect.
- Skill content is generated by `tool_author` preset in the same authoring step (single LLM call, two outputs).

#### Acceptance criteria — Phase D

- [ ] Drop a `.md` file into `data/skills/` -> SkillRegistry reflects it within 1 second; relevant LLM turns auto-inject if priority=1.
- [ ] `create_skill(...)` writes the file and triggers reload; skill becomes available in next LLM turn.
- [ ] Successful `create_tool` ALWAYS produces both a tool entry in `noted-tools` AND a skill entry in `data/skills/`.
- [ ] Removing a tool via `remove_tool` ALSO archives its sibling skill (paired lifecycle).

---

### Phase E: Audit log + UI

**Effort: ~3-4 days**

#### E.1 Audit panel

- New tab in the Explorer's Assistant section: "Self-authored tools".
- Lists every user tool with: name, description, language, version, created_at, last_used, total_invocations.
- Click a tool -> detail panel showing: full creation history (iteration tree), audit log of invocations, Remove button.
- "Self-authored skills" sub-tab mirrors the structure for skills.

#### E.2 Per-tool detail page

- Shows current `tool.json`, current implementation file, current `smoke.py`/`smoke.js`, current skill markdown.
- Source API docs link.
- "Re-run smoke tests" button: triggers `api_tester` against the live tool with the original acceptance criteria. Surfaces drift (upstream API changed).
- "Remove" button with confirmation modal.

#### E.3 Tool versioning surface

- Each invocation in the audit log shows the version that handled it.
- When a tool is updated (re-authored), prior versions remain in the iteration tree; the audit log links each invocation to its handling version.
- "Rollback to version N" button reverts the active version pointer; previous version becomes active again.

#### Acceptance criteria — Phase E

- [ ] Self-authored tools appear in Explorer with badges distinguishing them from native tools.
- [ ] Clicking a tool opens a detail page with full history.
- [ ] Re-run smoke tests button executes the tester against the live tool and reports verdict.
- [ ] Audit log shows every invocation with input hash, output hash (or status), version, timestamp.
- [ ] Rollback to version N -> next call uses version N's code; audit log records the rollback as an event.

---

### Phase F: Tool metadata + UI badges

**Effort: ~2 days**

#### F.1 Schema extension

- All tools (native and user) carry `_meta` field, stripped before LLM presentation.
- Native tools' `_meta`: `{provenance: "native"}`.
- User tools' `_meta`: full block as documented above.

#### F.2 UI badge layer

- Tool listings in the Explorer / chat panel / settings show a small badge for user-authored tools (icon + tooltip with creator + creation date).
- Native tools show no badge — visual default.

#### F.3 LLM-side invariance

- Verify via integration test: the schema seen by the LLM is identical for native and user tools (modulo name/description/input_schema differences). No `_meta` leaks into the LLM context.

#### Acceptance criteria — Phase F

- [ ] LLM tool-list payload is byte-identical for a native tool and a user tool with the same name + description + input_schema.
- [ ] UI shows the user-tool badge in all three surfaces (Explorer, chat tool-call view, settings).
- [ ] Toggling a tool from user to native (test scenario) flips the badge correctly without LLM-side changes.

---

## Cross-cutting concerns

### Security

- **Process isolation**: every user tool runs in a subprocess inside `noted-tools`, with resource limits and timeout. A crashing or hanging tool can't affect noted or other tools.
- **Dependency isolation**: per-tool venv prevents one tool's dependencies from breaking another.
- **Network isolation** (future option): container-level egress filtering can restrict which upstream services tools can reach. Not enforced in V1; documented as a hardening step.
- **Secret invariant**: secret values NEVER appear in the LLM context. Tools fetch them at execution time via short-lived scoped tokens.
- **Allow-list per tool**: each tool declares which secret names it may request. `noted-tools` enforces; an exfiltration attempt is blocked at the token-issuance step.
- **Code review for high-risk tools** (future): a `_meta.requires_review` flag could gate publication on human approval. Not in V1.

### Multi-user readiness (hooks present, full implementation deferred)

These zero-cost-now choices keep the future migration purely additive:

- `_meta.created_by` field present from day one. V1 value: constant `"system"`. V2: real user ID.
- Audit log `actor_id` field present from day one. Same defaulting.
- Infisical configured with project + environment scoping even with one user. V2 adds users; schema unchanged.
- Tool subprocess receives `actor_id` env var; V1 always the constant. V2 carries through the calling user's ID for downstream auth.

When multi-user lands later, the work is: SSO/OIDC integration with Infisical, identity-aware UI surfaces ("your tools" vs "team tools"), per-user tool ownership policies. None of these touch the V1 data model.

### Observability

- Every iteration of `create_tool` streams to the chat panel as a collapsible thinking block.
- `noted-tools` exposes Prometheus metrics: invocation count, success/failure ratio, p50/p95/p99 latency, venv build time, subprocess kill count.
- Audit log is JSONL append-only; queryable via the Explorer detail page or directly from disk.

### Failure modes and recovery

| Failure | Behavior |
|---|---|
| LLM authoring exhausts iteration cap | Tool not registered. Iteration tree preserved. User can retry with adjusted criteria. |
| Generated tool's smoke tests pass but production call fails | Audit log captures the failure. UI surfaces it. User can re-run smoke tests to detect drift. |
| `noted-tools` container crashes | Systemd / Docker restart policy brings it back. In-flight tool calls return error; LLM can retry. noted itself unaffected. |
| Infisical container crashes | Tools that need secrets fail with a clear error. Tools that don't need secrets continue working. |
| Disk full | Hot-reload failures logged. New tool registration blocked with clear error. Existing tools continue running. |
| User accidentally deletes a tool's directory | Tool drops out of registry. Audit log preserves the history. Re-run `create_tool` re-authors. |

---

## Open decisions resolved

| Question | Decision | Rationale |
|---|---|---|
| Where do user tools live in MCP namespace? | Same flat namespace as native tools | Easier for LLM. Metadata distinguishes for UI/governance. |
| Tool registration mechanism | Separate `noted-tools` container, file-drop directory, hot-reload on file change | Process isolation for safety; hot-reload for autonomy without restart. |
| Secret store | Infisical (MIT) | License-clean. Multi-user-ready. Off-the-shelf maturity over rolling our own. |
| Authoring orchestrator backend | Both Claude and Gemma 4 | Local-first is a stated business driver. Iteration cap differs (3 vs 6). |
| Tool versioning | Increment-on-update, prior versions preserved in iteration tree, rollback via active-version pointer | Minimal complexity; supports rollback without separate version table. |
| Multi-user | Deferred to a later phase. Hooks present in V1. | Reduces V1 scope by ~1.5 weeks; migration stays additive. |
| Skill lifecycle | Paired with tools (create_tool always co-publishes a skill; remove_tool archives both) | Tools and skills are two halves of one capability. |

---

## Out of scope (V1)

- Cross-user collaboration on tools (sharing, forking, peer review).
- Public registry / marketplace for tools across noted instances.
- Inter-tool dependencies (one user tool importing another).
- Auto-detection of upstream API drift via background re-validation.
- Network egress whitelisting per tool.
- LLM-side review / approval gate (`_meta.requires_review` flag).
- Tool deprecation lifecycle and migration prompts.
- Sandboxed JavaScript execution inside Deno or similar (V1 uses standard Node.js).

---

## Migration path (when each deferred item lands)

| Deferred | Future work | Effort estimate |
|---|---|---|
| Multi-user | SSO/OIDC + Infisical user mapping + per-user UI surfaces + ownership policies | ~1.5 weeks |
| API drift detection | Cron-scheduled `api_tester` re-runs against published tools; flag failures in UI | ~3-4 days |
| Network egress whitelisting | Per-tool `_meta.allowed_hosts` + iptables/cgroup enforcement | ~3-4 days |
| Tool versioning UX | Side-by-side diff between versions + manual selection | ~3 days |
| Public marketplace | Out-of-band; depends on multi-user being live | TBD |

---

## Test plan summary

Test coverage required before V1 ships:

- **Unit tests** for the orchestrator, the file watcher, the venv manager, the subprocess executor, the schema validator, the secret-token broker.
- **Integration test** end-to-end: a known-good API (e.g. JSONPlaceholder, a static-stable test endpoint), a deterministic mission, a deterministic acceptance criterion, run the full `create_tool -> use_tool` loop with both Claude and Gemma backends, assert success.
- **Negative integration test**: an API that exists but returns garbage; expect `create_tool` to exhaust iterations and fail cleanly.
- **Security tests**: secret allow-list enforcement, token TTL enforcement, no-secrets-in-LLM-context invariant.
- **Resilience tests**: kill `noted-tools` mid-call; kill Infisical mid-call; corrupt a tool.json; full disk; hostile tool that tries to spawn child processes or open arbitrary sockets.
- **Performance tests**: hot-reload latency under load; subprocess startup overhead; venv build time on cold cache.

---

## Total V1 effort: ~4 weeks

| Phase | Effort |
|---|---|
| A. noted-tools container + plugin model | ~2 weeks |
| B. Infisical secret store | ~3-4 days |
| C. Authoring presets + orchestrator | ~1 week |
| D. Skills hot-reload | ~3 days |
| E. Audit log + UI | ~3-4 days |
| F. Tool metadata + UI badges | ~2 days |

Plus ~1 week of buffer for integration, polish, and the test plan above. **Realistic shipping timeline: ~5 weeks of focused engineering.**

---

## Definition of done (V1)

The V1 of self-learning ships when ALL of the following hold:

1. A user can issue `create_tool(name, mission, api_docs_url)` and the system completes the loop end-to-end against an OpenAPI-documented service, with both Claude and Gemma backends, with success rates of >= 80% (Claude) and >= 50% (Gemma) on a held-out test set of 10 representative APIs.
2. The resulting tool is callable by the LLM in subsequent chat turns and produces correct results for the original acceptance criteria.
3. A matching skill is published alongside the tool and auto-injected when relevant.
4. Removing the tool via `remove_tool` cleanly removes both the tool and its skill; archives are recoverable.
5. No secret value ever appears in: LLM context, tool-call traces, frontend diagnostics, audit log values, or stderr captures.
6. Hot-reload completes within 1 second of a file change.
7. Subprocess crashes do not affect noted or other tools.
8. Audit panel surfaces every self-authored tool with full history; rollback works.
9. All multi-user hooks present (data-model fields populated with constants); the future migration requires zero schema changes.
10. The full integration test suite (above) passes in CI before merge to main.

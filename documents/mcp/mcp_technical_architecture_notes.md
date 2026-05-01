# noted - MCP Server Integration Blueprint

## Overview

This document is the consolidated design blueprint for adding an MCP (Model Context Protocol) server layer to noted. It supersedes and extends both the subagent architecture design and the external MCP proposal, resolving conflicts and filling gaps in each.

The guiding constraint throughout is noted’s core design principle: **the orchestration layer must be model-agnostic**. MCP is adopted as the standard protocol boundary precisely because it decouples tool definitions from any specific LLM.

-----

## Strategic Position

noted already has:

- A well-defined internal API
- An OpenAI-compatible endpoint
- 38 domain skills covering Airflow, MLflow, DVC, Hydra, and others
- A two-tier model routing system (local Qwen / Claude)
- A planned subagent DAG architecture using Airflow + MLflow

MCP is not a replacement for any of these. It is a **standardised doorway** over the existing dispatcher - enabling both noted’s internal LLM and external MCP-compatible clients (Claude Code, Claude Desktop, Cursor) to access noted’s capabilities through the same interface.

The subagent DAG architecture remains the primary internal execution model. MCP becomes the protocol through which agents - internal or external - invoke that system.

-----

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        MCP Clients                          │
│   Internal LLM (Qwen / Claude)  │  External (Claude Code,  │
│   via noted chat UI             │  Claude Desktop, Cursor)  │
└────────────────────┬────────────────────────────────────────┘
                     │  JSON-RPC over Streamable HTTP
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    noted MCP Server                         │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Tool Router │  │ Resource Hub │  │ Approval Middleware│  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘  │
│         └────────────────┴───────────────────┘             │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│   Existing   │  │   Workflow   │  │   Execution Engine   │
│  Dispatcher  │  │  Templates   │  │  (Kernels, Airflow,  │
│  (38 skills) │  │  (DAG layer) │  │   MLflow, DVC, PTY)  │
└──────────────┘  └──────────────┘  └──────────────────────┘
```

### Transport Layer

noted will support Streamable HTTP as the primary transport, with stdio as a secondary option for local desktop clients.

**Streamable HTTP (primary)**

- Single endpoint at `/mcp` handles all MCP communication (replaces the legacy two-endpoint SSE pattern of separate `/sse` + `/messages/` endpoints)
- Supports both JSON responses and SSE streaming within the same endpoint, selected per-request
- Configured with `stateless_http=True` and `json_response=True` for optimal scalability
- The MCP server is mounted into noted’s existing FastAPI app via Starlette’s `Mount`, not as a separate process
- Proxied through noted’s existing nginx reverse proxy under `/mcp/`
- Protected by oauth2-proxy - MCP endpoints require the same authentication as the rest of noted
- This is the MCP SDK’s recommended transport for production deployments (SSE is legacy as of SDK v1.x)

**Stdio (secondary)**

- Enables local desktop clients (Claude Desktop) to connect directly via:
  
  ```
  docker exec -i noted-<container> python -m noted.mcp
  ```
- Not the primary path given noted’s WSL2/Docker Compose setup - treat as a convenience option for power users, not a first-class deployment target
- **Critical implementation constraint**: when running in stdio mode, `stdout` is reserved exclusively for MCP JSON-RPC messages. All logging (startup banners, debug output, library warnings) must be routed to `stderr` or a log file. Any stray `print()` or unguarded log line on `stdout` will fatally break JSON parsing in Claude Desktop or Cursor.

**Stdio wrapper design**: the `noted.mcp` module entry point (`__main__.py`) acts as the stdio transport bridge:

- On import, before any library code loads, redirect `sys.stdout` to `stderr` and replace `sys.stdout` with a dedicated JSON-RPC-only writer
- Set `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1` to prevent stray output
- Configure Python’s logging root handler to `stderr` explicitly
- Suppress third-party library banners by patching `sys.stdout` before imports
- The wrapper connects to the existing noted backend via its internal HTTP API (`localhost:8000`) rather than importing dispatcher code directly - this avoids loading heavy dependencies that might print on import and keeps the wrapper thin

The wrapper translates between stdio JSON-RPC and HTTP, calling the same `/mcp` endpoint that the Streamable HTTP transport uses. No dispatcher logic is duplicated.

**Networking**: `docker exec` runs inside the container’s network namespace, so `localhost:8000` reaches the noted backend directly. No port mapping or cross-container routing needed.

**Client configuration** (Claude Desktop / Cursor):

```json
{
  "mcpServers": {
    "noted": {
      "command": "docker",
      "args": ["exec", "-i", "noted-app", "python", "-m", "noted.mcp"],
      "env": {
        "NOTED_MCP_MODE": "stdio"
      }
    }
  }
}
```

The `NOTED_MCP_MODE` environment variable tells the entry point to use stdio transport instead of Streamable HTTP.

-----

## Tool and Resource Mapping

The 38 skills are split into MCP **Tools** (actions / verbs) and MCP **Resources** (readable state / nouns). This split is the key architectural decision: it gives the LLM read access to environment state without requiring function calls, and reserves tool calls for operations that compute or change state.

### Resources

Resources are exposed via the `noted://` URI scheme and served via `resources/list` and `resources/read`. Subscription (`resources/subscribe`) is supported for high-value push events.

|Domain   |Resource URI                            |Description                             |Subscribe|
|---------|----------------------------------------|----------------------------------------|---------|
|Workspace|`noted://project/env_status`            |State of pip/renv/pnpm lockfiles        |No       |
|Workspace|`noted://project/shadow_files`          |Current shadow file index               |No       |
|DVC      |`noted://dvc/lineage/current`           |Live JSON representation of the DVC DAG |Yes      |
|DVC      |`noted://dvc/status`                    |Current DVC tracking status             |No       |
|Airflow  |`noted://airflow/dags`                  |List of registered DAGs and their state |No       |
|Airflow  |`noted://airflow/logs/{dag_id}/{run_id}`|Execution logs for a specific DAG run   |Yes      |
|Airflow  |`noted://airflow/runs/{dag_id}`         |Run history for a DAG                   |No       |
|MLflow   |`noted://mlflow/experiments/active`     |Metrics and parameters of the active run|Yes      |
|MLflow   |`noted://mlflow/experiments/{id}/runs`  |Paginated run list for an experiment    |No       |
|MLflow   |`noted://mlflow/models/registry`        |Registered model list and versions      |No       |
|Hydra    |`noted://hydra/config/current`          |Resolved Hydra config for the active run|No       |
|Notebooks|`noted://notebooks/fs`                  |Notebook filesystem tree                |No       |
|Notebooks|`noted://notebooks/{id}/output`         |Last output of a specific notebook      |No       |

**Pagination requirement**: any resource that can return unbounded lists (MLflow runs, Airflow run history) must implement the MCP pagination spec. Returning full history in a single response is not acceptable given noted’s scale of experiment data.

**Push subscriptions**: DVC lineage, Airflow logs, and MLflow active run are the highest-value push targets. When a DVC sync completes, an Airflow task fails, or a metric crosses a threshold, the server pushes a `notifications/resources/updated` event to subscribed clients without requiring polling.

Per the MCP specification, the client must explicitly send a `resources/subscribe` request for a specific URI before the server can push update notifications for it.

**Subscription lifecycle**: subscriptions are tied to the chat session, not notebook load. The noted frontend issues `resources/subscribe` for the default high-value URIs (`noted://mlflow/experiments/active`, `noted://dvc/lineage/current`) when the user opens the chat panel or sends the first message in a session. If the chat panel is closed or the session is idle for a configurable period (default: 10 minutes), the frontend sends `resources/unsubscribe` to release server-side watchers. This avoids wasted resources during pure editing sessions while enabling reactive behaviour from the first LLM interaction. External clients manage their own subscription lifecycle - noted does not auto-subscribe on their behalf.

### Tools

Tools map to the existing 38 skills and are routed through the existing dispatcher. The tool schemas are the authoritative definition of each skill’s interface - they replace static skill injection in the system prompt for clients that support MCP.

**Execution**

|Tool              |Arguments                 |Underlying Action             |
|------------------|--------------------------|------------------------------|
|`execute_cell`    |`{lang, code, kernel_id?}`|ExecutionBridge via ZMQ       |
|`interrupt_kernel`|`{kernel_id}`             |Kernel interrupt signal       |
|`restart_kernel`  |`{kernel_id}`             |Kernel restart                |
|`get_cell_output` |`{cell_id}`               |Returns last output for a cell|

**Debugging**

|Tool               |Arguments     |Underlying Action                  |
|-------------------|--------------|-----------------------------------|
|`get_dap_stack`    |`{thread_id}` |DAP proxy stack frame query        |
|`get_dap_variables`|`{frame_id}`  |DAP proxy local variable inspection|
|`set_breakpoint`   |`{file, line}`|DAP proxy breakpoint registration  |

**Package Management**

|Tool             |Arguments              |Underlying Action                  |
|-----------------|-----------------------|-----------------------------------|
|`install_package`|`{lang, pkg, version?}`|renv::install / pip install via PTY|
|`list_packages`  |`{lang}`               |Installed package manifest         |

**DVC**

|Tool       |Arguments         |Underlying Action             |
|-----------|------------------|------------------------------|
|`dvc_run`  |`{stage?, force?}`|Executes DVC pipeline stage   |
|`dvc_push` |`{remote?}`       |Pushes tracked data to remote |
|`dvc_pull` |`{remote?}`       |Pulls tracked data from remote|
|`dvc_repro`|`{stage?}`        |Reproduces pipeline from stage|

**Airflow**

|Tool                |Arguments         |Underlying Action |
|--------------------|------------------|------------------|
|`trigger_dag`       |`{dag_id, conf?}` |Triggers a DAG run|
|`pause_dag`         |`{dag_id}`        |Pauses a DAG      |
|`get_dag_run_status`|`{dag_id, run_id}`|Returns run state |

**MLflow**

|Tool          |Arguments                   |Underlying Action                |
|--------------|----------------------------|---------------------------------|
|`log_metric`  |`{key, value, step?}`       |Logs a metric to the active run  |
|`log_params`  |`{params}`                  |Logs parameters to the active run|
|`log_artifact`|`{path}`                    |Logs a file artifact             |
|`start_run`   |`{experiment_id, run_name?}`|Starts a new MLflow run          |
|`end_run`     |`{status?}`                 |Ends the active run              |
|`get_run`     |`{run_id}`                  |Returns run metadata and metrics |

**Hydra**

|Tool             |Arguments       |Underlying Action                |
|-----------------|----------------|---------------------------------|
|`override_config`|`{group, value}`|Modifies Hydra compose parameters|
|`get_config`     |`{path?}`       |Returns resolved config subtree  |

**Workflows (Subagent DAG layer)**

|Tool                 |Arguments              |Underlying Action                       |
|---------------------|-----------------------|----------------------------------------|
|`list_workflows`     |`{}`                   |Returns available workflow templates    |
|`run_workflow`       |`{template_id, params}`|Instantiates and triggers a workflow DAG|
|`get_workflow_status`|`{run_id}`             |Returns DAG execution state             |
|`get_workflow_result`|`{run_id}`             |Returns aggregated workflow output      |

The workflow tools are the MCP surface for the subagent DAG architecture. External clients can trigger full multi-step workflows through a single `run_workflow` call without needing to know the internal DAG structure.

-----

## Approval Middleware

noted’s existing two-tier confirmation model (reads auto-execute, writes require confirmation) maps directly onto MCP tool classification.

**Auto-execute (read tier)**

Tools that are read-only or low-risk execute without user confirmation:

- All `get_*` tools
- `list_*` tools
- `set_breakpoint` (reversible debug session annotation, does not alter environment state)
- `get_workflow_status`, `get_workflow_result`

**Confirmation required (write tier)**

Tools that alter environment state, consume significant resources, or are irreversible require explicit user approval before the MCP server routes them to the dispatcher:

- `execute_cell`, `restart_kernel`
- `install_package`
- `dvc_push`, `dvc_pull`, `dvc_repro`
- `trigger_dag`
- `log_*`, `start_run`, `end_run`
- `run_workflow`
The approval middleware behaviour differs by client type:

**Internal noted UI**: the middleware intercepts the `tools/call` request, surfaces the pending action to the noted frontend, and holds the request until the user approves or rejects. This works because noted controls both the server and the frontend.

**External clients (Claude Code, Claude Desktop, Cursor)**: the MCP specification delegates user consent to the host client, not the server. Hanging a connection while waiting for out-of-band approval in the noted UI would cause the external client to timeout. Instead, write-tier tool calls from external clients are **immediately rejected** with a standard JSON-RPC authorisation error:

```json
{
  "error": {
    "code": -32001,
    "message": "Authorization error: write-tier tool requires explicit user approval. Enable write access for this client in noted settings."
  }
}
```

External clients that want write access must be explicitly granted it via scoped API keys (see External Client Access section), after which write-tier tools execute with the client’s own native confirmation flow (if any). This keeps the protocol clean and avoids coupling noted’s approval UI to external client lifecycles.

-----

## External Client Access

External MCP clients (Claude Desktop, Cursor, Claude Code) authenticate and receive access scopes through **scoped API keys** managed in noted's settings.

### Key structure

The noted settings UI (or config file) includes an **MCP Client Access** section:

```yaml
mcp_clients:
  - name: "Claude Desktop - workstation"
    key_hash: "$2b$12$..."    # bcrypt hash, never stored in plaintext
    scope: "read"              # "read" or "read+write"
    created: "2026-04-07"
    last_used: null
```

### Authentication flow

1. External MCP clients include the API key in the initial `initialize` request via a custom `x-noted-api-key` header (Streamable HTTP transport) or as a field in the initialize params (stdio transport)
2. The MCP server validates the key against stored hashes and binds the associated scope to the session
3. Read-scoped clients hit the approval middleware's rejection path for write-tier tools (existing -32001 error)
4. Read+write-scoped clients bypass noted's approval middleware entirely - the expectation is that the external client's own confirmation flow (Claude Desktop's tool approval dialog, Cursor's permission prompt) handles user consent
5. Keys can be revoked instantly by removing the entry from settings

### Default behaviour

If an external client connects without a key, it receives **read-only access** by default. This is the safe fallback - external clients can browse resources and call read-tier tools without any setup, but must be explicitly granted write access.

### Key provisioning

The noted settings UI provides a "Generate MCP Key" button that displays the key once on creation. The administrator copies it into their external client's MCP server configuration. The key is never shown again - only the name, scope, and creation date remain visible in the settings list.

-----

## Relationship to the Subagent DAG Architecture

MCP and the subagent DAG architecture are complementary, not competing:

|Concern                          |Owner                             |
|---------------------------------|----------------------------------|
|Task decomposition and sequencing|noted (workflow templates)        |
|Step execution                   |Airflow DAG nodes                 |
|Per-node model invocation        |noted’s OpenAI-compatible endpoint|
|External access to workflows     |MCP `run_workflow` tool           |
|Traceability                     |MLflow experiment records         |
|Protocol for all tool access     |MCP (internal and external)       |

The internal LLM routing logic remains on noted’s OpenAI-compatible endpoint. MCP is the access layer on top, not a replacement for the internal model routing.

As the workflow template library matures, each stable workflow becomes a well-defined MCP tool - external agents get access to predictable, well-scoped operations rather than raw skill invocations.

-----

## Token Budget Considerations

MCP reduces static context injection but does not eliminate token cost. The actual trade-off:

|Approach                        |Token cost                                                          |Flexibility                                             |
|--------------------------------|--------------------------------------------------------------------|--------------------------------------------------------|
|Static skill injection (current)|Fixed upfront cost per conversation; all 38 skills always present   |Predictable; wasteful for focused tasks                 |
|MCP tools/list                  |Schema tokens on discovery; only called tools consume further tokens|Scales with task complexity; lower cost for narrow tasks|

For noted’s internal LLM, the practical gain depends on task scope. The Dynamic Context Router (see Phase 4) addresses this by selecting only relevant tool schemas per turn - typically 5-8 schemas for focused tasks, scaling up for broad exploratory sessions. Subagent node calls benefit the most (always narrow by design, 1-3 schemas per node).

-----

## Implementation Phases

### Phase 1 - MCP Wrapper (Foundation)

Goal: expose existing dispatcher through MCP without changing any skill logic.

**SDK strategy**: the official `mcp` Python SDK (v1.27.0) handles all protocol-level concerns - JSON-RPC parsing, message framing, transport negotiation, and lifecycle methods (`initialize`, `ping`, `notifications/cancelled`). The MCP server is mounted into noted’s existing FastAPI app via Starlette’s `Mount` using `mcp.streamable_http_app()`. noted’s custom code sits on top of the SDK: the dispatcher bridge, approval middleware, rate limiter, and (in Phase 4) the Dynamic Context Router. Reimplementing JSON-RPC plumbing from scratch would add no value over the SDK.

- Integrate the official `mcp` Python SDK (low-level Server API for full schema control) for protocol handling
- Implement `tools/list` - return JSON schemas for the existing 38 skills
- Implement `tools/call` - route to `dispatcher.execute_skill(skill_name, args)`
- Mount MCP server into noted’s FastAPI app via Starlette `Mount` at `/mcp` using Streamable HTTP transport
- Proxy `/mcp/` through nginx with oauth2-proxy protection
- Implement the approval middleware for write-tier tools
- Implement rate limiting (see Rate Limiting section below)

Outcome: noted’s existing skills are accessible via MCP from internal and external clients. No skill logic changes.

### Phase 2 - Resource Layer

Goal: give the LLM read access to environment state without tool calls.

- Implement `resources/list` and `resources/read`
- Map the resource URIs defined above to their backend data sources
- Implement pagination for MLflow and Airflow list resources
- Implement `resources/subscribe` for DVC lineage, Airflow logs, and MLflow active run
- Connect subscription push events to Airflow task state change hooks and MLflow callback hooks

Outcome: the LLM can read environment state without consuming write-tier confirmation budget; push events enable reactive behaviour without polling.

### Phase 3 - Workflow Tool Surface

Goal: expose the subagent DAG architecture through MCP.

- Implement `list_workflows`, `run_workflow`, `get_workflow_status`, `get_workflow_result` tools
- `run_workflow` instantiates an Airflow DAG from a workflow template and returns a `run_id`
- Status and result tools poll Airflow and MLflow respectively
- Add workflow tool schemas to `tools/list`

Outcome: external clients can trigger full multi-step noted workflows through a single MCP tool call.

### Phase 4 - Internal LLM Migration

Goal: migrate the internal LLM from static skill injection to MCP-based tool discovery with a **Dynamic Context Router**.

Native function-calling models (Claude, Qwen) require tool schemas in the API `tools` array to emit tool calls. A text-only list of tool names in the system prompt does not work - the model physically cannot call tools whose schemas are not in the payload. Conversely, loading all 38 schemas into the `tools` array on every turn defeats the purpose of MCP. The solution is dynamic, per-turn schema selection.

**Dynamic Context Router**:

1. User sends a message to noted’s chat
2. The backend classifies the message into relevant tool domains using keyword matching, embedding similarity, or a lightweight classifier
3. The backend fetches only the matching tool schemas from the MCP server’s `tools/list` (e.g., user mentions "DAG run failed" - fetch Airflow + DVC tools; user asks "plot this" - fetch Execution tools only)
4. Those schemas (typically 5-8 per turn, not 38) are injected into the LLM’s `tools` array for that specific API call
5. If the LLM attempts to call a tool that was not in scope, the backend fetches the missing schema from MCP, adds it to the `tools` array, and retries the turn

A lightweight text index of all tool names grouped by domain may optionally remain in the system prompt as a hint for edge cases where the router misclassifies, but it is not the primary discovery mechanism - the `tools` array is.

- Implement the Dynamic Context Router as a pre-processing step before each LLM API call
- Remove the full 38-schema static injection from the base system prompt
- Route internal model tool calls through the MCP server
- Retain a minimal system prompt covering noted context, user preferences, and model routing policy
- Validate that all existing skill behaviours are preserved through the MCP layer

Outcome: noted’s internal LLM and external clients share the same tool surface. Per-turn token cost scales with task complexity (5-8 schemas for focused tasks vs 38 for broad sessions), and dual-maintenance of static prompts and MCP schemas is eliminated.

-----

## Deployment and Failure Isolation

### Failure isolation constraint

MCP is an additive layer, not a dependency. If the MCP server fails to initialize or crashes at runtime, the rest of noted must be completely unaffected - the internal chat UI, kernels, notebooks, all managers, and every existing feature must continue operating normally.

This is enforced architecturally:

- The MCP server is implemented as an independent FastAPI router (`backend/app/mcp/`). No other noted component imports from or depends on this package.
- The MCP router reads from `TOOL_DESCRIPTIONS`, `WRITE_TOOLS`, and `execute_tool()` in `llm_tools.py`, but `llm_tools.py` never imports from `mcp/`. The dependency is strictly one-directional.
- If the MCP router fails to register at startup (SDK import error, configuration problem), noted logs the error and continues without MCP endpoints. All other routers load independently.
- If an MCP connection or tool call crashes at runtime, the error is contained within the MCP request handler. It does not propagate to the dispatcher, kernel manager, or any other noted subsystem.

### Feature toggle

MCP is controlled by a config flag in noted's settings:

```yaml
mcp:
  enabled: true          # false disables MCP router registration and nginx location
  sdk_version: "1.x.y"  # pinned SDK version for reproducibility
```

When `mcp.enabled` is `false`:
- The MCP FastAPI router is not registered
- The nginx `/mcp/` location returns 404
- The stdio wrapper exits immediately with a descriptive message on stderr
- No MCP-related code is loaded into the noted process

This allows safe rollout (enable per-environment) and instant rollback (set to false, restart).

### SDK version pinning

The MCP specification is still evolving. The implementation targets a specific pinned version of the `mcp` Python SDK, recorded in:
- `requirements.txt` (or equivalent) with exact version pin (e.g., `mcp==1.x.y`)
- This section of the architecture doc, updated when the pin changes

The pinned version is chosen at the start of Phase 1 based on the latest stable release at that time. Upgrades are treated as deliberate changes, not automatic, and require re-running the Phase 1 acceptance gate.

### Parallel development compatibility

The MCP server is designed to coexist with parallel development on noted's core features (MLOps workflows, new tools, UI changes) without conflict:

- Phase 1 creates a new `backend/app/mcp/` package - no existing files are structurally modified
- The MCP wrapper reads `TOOL_DESCRIPTIONS` dynamically at request time, not from a hardcoded copy. If parallel work adds new tools to `llm_tools.py`, they automatically appear in MCP `tools/list`
- The one coordination rule: new tools added to `llm_tools.py` by any development effort must follow the existing schema format (name, description, arguments dict) and classify themselves in `WRITE_TOOLS` if they are write-tier. No other coordination is required.
- nginx changes (new `/mcp/` location) are additive and do not modify existing location blocks
- Dockerfile changes (SDK dependency) are a single additive line

-----

## Security Considerations

- **Authentication**: all MCP endpoints are behind oauth2-proxy, consistent with the rest of noted. No separate auth layer needed.
- **Authorisation**: the approval middleware enforces the read/write tier distinction regardless of whether the caller is the internal LLM or an external client.
- **External client trust**: external MCP clients (Claude Desktop, Cursor) are treated as user-level principals. Unauthenticated clients receive read-only access by default. Write-tier access requires a scoped API key provisioned through noted settings (see External Client Access section).
- **Secret isolation**: MCP tool calls do not expose Infisical-managed secrets in tool responses. This is enforced through two complementary layers:

  **Primary defense - environment-level restriction**: kernels never have Infisical-managed secrets in their process environment. When a kernel starts, noted injects only the environment variables the kernel needs to function (PATH, NODE_PATH, language-specific runtime vars). Secrets required for specific operations (API keys for MLflow, DVC remotes, Airflow connections) are held by the dispatcher and injected at execution time into the specific API calls that need them, not into the kernel's `os.environ`. This means `os.environ` in user code cannot leak secrets because the secrets are never there.

  **Secondary defense - output sanitisation**: as a safety net for secrets that must transiently pass through execution output (e.g., an API response that echoes a token), the dispatcher's return path includes a pattern-matching sanitiser:
  1. The dispatcher maintains a secret registry - value patterns loaded from Infisical-managed env vars at startup
  2. Before any tool result is serialized into the MCP JSON-RPC response, the sanitiser replaces matching patterns with `[REDACTED:<key_name>]`
  3. Sanitisation runs on the string representation of the result to catch secrets embedded in stack traces, print output, or error messages
  4. This applies to all tools that return user-generated or environment-generated content (`execute_cell`, `get_cell_output`, workflow results, etc.)

  **Limitations**: the output sanitiser is pattern-matching on known secret values, not a guarantee. If user code base64-encodes a secret or splits it across variables, the sanitiser will not catch it. The environment restriction is the stronger control - the sanitiser catches what leaks past it. Sensitive credentials should use short-lived tokens where possible.

-----

## Error Taxonomy

All MCP tool errors use a consistent schema with structured error codes. These codes are in the JSON-RPC server error range (-32000 to -32099) and are specific to noted's MCP server.

|Code  |Name                  |When                                                                     |Recoverable|
|------|----------------------|-------------------------------------------------------------------------|-----------|
|-32001|`authorization_error` |Write-tier tool called without approval                                  |Yes        |
|-32002|`execution_error`     |Skill executed but failed (cell error, package install failure, DVC conflict)|Yes     |
|-32003|`timeout_error`       |Skill did not complete within its allowed time window                     |Yes        |
|-32004|`resource_unavailable`|Target service is down (kernel crashed, Airflow unreachable, MLflow offline)|No       |
|-32005|`rate_limited`        |Client exceeded tool call rate limit                                     |Yes        |
|-32006|`validation_error`    |Arguments passed schema validation but are semantically invalid (e.g. nonexistent kernel_id)|No|

Every error response includes a structured `data` field:

```json
{
  "error": {
    "code": -32002,
    "message": "Cell execution failed",
    "data": {
      "skill": "execute_cell",
      "detail": "NameError: name 'df' is not defined",
      "recoverable": true
    }
  }
}
```

The `recoverable` flag tells the LLM whether retrying (possibly with different arguments) is reasonable. Rate-limited errors include an additional `retry_after` field (seconds) in the `data` payload.

-----

## Rate Limiting

Rate limiting is a Phase 1 requirement, not a deferred concern. An unprotected MCP endpoint with 38 tools is an amplification vector - one agentic loop can saturate kernels, flood Airflow's API, or exhaust MLflow's tracking store. Auto-execute read-tier tools are particularly exposed since they bypass the approval middleware.

**Implementation**: in-memory token bucket in the MCP server layer, keyed by client session ID. No external state (Redis) required - this is per-process, per-connection rate limiting.

**Boundary**: rate limiting applies strictly at the MCP client-to-server boundary. Internal execution triggered by a tool call (e.g., an Airflow DAG spawned by `run_workflow` that executes 50 kernel calls internally) does not count against the external client's rate limit. The rate limiter tracks JSON-RPC requests arriving at the MCP server, not downstream operations those requests trigger. Without this isolation, a single valid `run_workflow` call could cascade into internal rate-limit failures that block the workflow's own execution.

|Tier    |Tools                                                            |Rate   |Burst|
|--------|-----------------------------------------------------------------|-------|-----|
|Read    |All `get_*`, `list_*`, resource reads                            |30/min |10   |
|Write   |`execute_cell`, `install_package`, `dvc_*`, `trigger_dag`, `log_*`|10/min|3    |
|Workflow|`run_workflow`                                                   |3/min  |1    |

When a client exceeds its rate limit, the server returns:

```json
{
  "error": {
    "code": -32005,
    "message": "Rate limited",
    "data": {
      "skill": "execute_cell",
      "detail": "Write-tier rate limit exceeded",
      "recoverable": true,
      "retry_after": 6
    }
  }
}
```

-----

## Resolved Design Decisions

The following questions raised during design review have been resolved:

**Schema versioning**: handled via the `notifications/tools/list_changed` server event. When a skill’s JSON schema changes, the MCP server fires this notification and connected clients automatically re-fetch `tools/list`. No versioned endpoints (`/v1/mcp`, `/v2/mcp`) are needed.

**Partial workflow exposure**: individual DAG nodes are not exposed as MCP tools. Only whole workflows are accessible via `run_workflow`. Exposing nodes would risk the LLM attempting to act as the Airflow scheduler, defeating the sequencing guarantees the DAG architecture provides.

**External client approval UX**: resolved - see Approval Middleware section. External clients receive an immediate JSON-RPC rejection for write-tier tools unless explicitly granted write access in noted settings.

**set_breakpoint tier classification**: moved from write tier to auto-execute. Breakpoints are reversible debug session annotations that do not alter environment state, consume resources, or carry side effects. Requiring confirmation per breakpoint during active debugging would break flow. Analogous to `get_dap_stack` - an interaction with the DAP proxy, not the environment.

**Subscription timing**: subscriptions are tied to chat session lifecycle, not notebook load. Auto-subscribing on notebook open would create server-side watchers during pure editing sessions with no LLM interaction. See Resource section for lifecycle details.

**Rate limiting scope**: promoted from open question to Phase 1 requirement. Rate limiting applies strictly at the MCP client-to-server boundary - internal execution triggered by tool calls (e.g., Airflow DAG nodes) is exempt. See Rate Limiting section for tiered token bucket design and boundary definition.

**Secret isolation mechanism**: two-layer defense. Primary: environment-level restriction (kernels never receive Infisical secrets in their process environment). Secondary: output sanitisation with pattern matching as a safety net. See Security Considerations for details and documented limitations.

**Internal LLM migration strategy**: Dynamic Context Router. Native function-calling models require schemas in the API `tools` array - a text-only tool index does not work mechanically. The router classifies each user message into relevant domains and injects only matching schemas (typically 5-8 per turn) into the `tools` payload. See Phase 4 for details.

**SDK vs custom protocol implementation**: the official `mcp` Python SDK (v1.27.0) handles JSON-RPC parsing, message framing, transport negotiation, and lifecycle methods. The MCP server mounts into FastAPI via Starlette's `Mount` using Streamable HTTP transport. noted's custom code (dispatcher bridge, approval middleware, rate limiter, Dynamic Context Router) sits on top of the SDK's low-level Server API. No protocol plumbing is reimplemented.

**Streamable HTTP over SSE**: the MCP SDK recommends Streamable HTTP as the production transport, superseding the legacy SSE two-endpoint pattern. Streamable HTTP uses a single `/mcp` endpoint, supports both JSON and SSE streaming responses, and is the forward-looking standard. All references to SSE transport in earlier drafts have been replaced with Streamable HTTP.

**Stdio packaging**: thin wrapper (`noted.mcp.__main__`) bridges stdio JSON-RPC to the existing Streamable HTTP `/mcp` endpoint. stdout is reserved for JSON-RPC via early `sys.stdout` redirect. See Transport Layer section for full design and client configuration example.

**Failure isolation**: MCP is a strictly additive layer. The `mcp/` package has a one-directional dependency on `llm_tools.py` - never the reverse. If MCP fails to load or crashes, noted continues operating normally. See Deployment and Failure Isolation section.

**Feature toggle and SDK pinning**: MCP is controlled by `mcp.enabled` config flag. SDK version is pinned in requirements. Upgrades require re-running the Phase 1 acceptance gate. See Deployment and Failure Isolation section.

**Parallel development compatibility**: MCP reads `TOOL_DESCRIPTIONS` dynamically - new tools added by parallel development efforts automatically appear in `tools/list`. Only coordination rule: new tools must follow existing schema format and classify in `WRITE_TOOLS` if write-tier.

**External client write access grants**: scoped API keys managed in noted settings. Unauthenticated clients get read-only by default; write access requires an explicit key with `read+write` scope. Keys are bcrypt-hashed, revocable, and provisioned via the settings UI. See External Client Access section for full design.


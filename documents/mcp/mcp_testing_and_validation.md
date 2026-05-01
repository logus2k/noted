# noted - MCP Testing and Validation

Reference: [mcp_technical_architecture_notes.md](mcp_technical_architecture_notes.md) | [mcp_development_plan.md](mcp_development_plan.md)

This document defines test cases and acceptance criteria for every capability delivered by each phase. A phase is accepted when all its criteria pass. Tests are ordered to match the development plan task numbering.

-----

## Conventions

**Test types**:
- **Unit** - isolated function/class test, no external services
- **Integration** - tests interaction between two or more noted components
- **E2E** - full client-to-server round trip through the MCP protocol
- **Security** - validates access control, secret isolation, or rate limiting

**Acceptance criteria format**: each criterion is a falsifiable statement. The phase passes when every criterion marked **MUST** is met. Criteria marked **SHOULD** are desirable but not blocking.

-----

## Phase 1 - MCP Wrapper (Foundation)

### 1.1 Protocol and Transport

#### T1.1.1 - Streamable HTTP connection lifecycle

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted backend running, nginx proxying `/mcp/`|
|Steps|1. Client sends POST to `/mcp` with `initialize` JSON-RPC request 2. Server responds with `ServerCapabilities` (tools, resources listed) 3. Client sends `ping` via POST to `/mcp` 4. Server responds with pong 5. Client disconnects|
|Acceptance|**MUST**: `initialize` returns valid capabilities JSON via single `/mcp` endpoint. **MUST**: `ping` receives response within 2s. **MUST**: server cleans up session on disconnect. **MUST**: endpoint accepts both JSON and SSE streaming response formats|

#### T1.1.2 - Stdio transport

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted container running|
|Steps|1. Run `docker exec -i noted-app python -m noted.mcp` with `NOTED_MCP_MODE=stdio` 2. Send `initialize` JSON-RPC on stdin 3. Read response from stdout 4. Send `ping` on stdin 5. Read response from stdout 6. Send EOF|
|Acceptance|**MUST**: all responses are valid JSON-RPC on stdout, zero non-JSON output on stdout (no library banners, no logging, no warnings). **MUST**: logging output goes to stderr only. **MUST**: `initialize` and `ping` succeed identically to Streamable HTTP transport|

#### T1.1.3 - Stdout discipline under noisy imports

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|Stdio wrapper module available|
|Steps|1. Mock a third-party library that calls `print()` on import 2. Import `noted.mcp.__main__` 3. Capture stdout and stderr|
|Acceptance|**MUST**: stdout contains zero bytes from the mock library. **MUST**: stderr contains the mock library's output|

#### T1.1.4 - nginx proxy and authentication

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|nginx + oauth2-proxy running|
|Steps|1. POST to `/mcp` without auth cookie/token 2. POST to `/mcp` with valid auth|
|Acceptance|**MUST**: unauthenticated requests return 401/403. **MUST**: authenticated requests reach the MCP server. **MUST**: streaming responses are not buffered by nginx (verify `X-Accel-Buffering: no` or equivalent)|

#### T1.1.5 - Session management

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|MCP server running|
|Steps|1. Connect two clients simultaneously 2. Each sends `initialize` 3. Verify separate session IDs 4. Disconnect client A 5. Verify client B is unaffected 6. Verify client A's session is cleaned up|
|Acceptance|**MUST**: each client receives a unique session ID. **MUST**: disconnecting one client does not affect the other. **MUST**: server-side session state is released within 5s of disconnect|

-----

### 1.2 Tool Surface

#### T1.2.1 - tools/list schema completeness

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running with all skills registered|
|Steps|1. Connect client 2. Send `tools/list` request 3. Parse response|
|Acceptance|**MUST**: response contains exactly 38 tool definitions. **MUST**: each tool has `name`, `description`, and `inputSchema` fields. **MUST**: `inputSchema` is valid JSON Schema (validate with a JSON Schema validator). **MUST**: every tool name matches its corresponding dispatcher entry|

#### T1.2.2 - tools/call read-tier tool

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, at least one kernel active|
|Steps|1. Connect client 2. Call `get_cell_output` with a valid cell_id 3. Parse response|
|Acceptance|**MUST**: response contains the cell's output data. **MUST**: response matches the output returned by calling `execute_tool("get_cell_output", ...)` directly. **MUST**: no approval prompt is triggered|

#### T1.2.3 - tools/call with invalid arguments

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running|
|Steps|1. Call `execute_cell` with missing `lang` argument 2. Call `get_dap_stack` with nonexistent thread_id|
|Acceptance|**MUST**: missing required argument returns -32006 `validation_error`. **MUST**: semantically invalid argument returns -32006 `validation_error`. **MUST**: `data.recoverable` is `false` for validation errors|

#### T1.2.4 - tools/call dispatcher failure

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, kernel available|
|Steps|1. Call `execute_cell` with code `raise Exception("test")` 2. Parse error response|
|Acceptance|**MUST**: returns -32002 `execution_error`. **MUST**: `data.detail` contains the exception message. **MUST**: `data.recoverable` is `true`. **MUST**: `data.skill` is `"execute_cell"`|

#### T1.2.5 - tools/call when service is down

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, Airflow container stopped|
|Steps|1. Call `trigger_dag` with a valid dag_id|
|Acceptance|**MUST**: returns -32004 `resource_unavailable`. **MUST**: `data.recoverable` is `false`|

#### T1.2.6 - notifications/tools/list_changed

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|MCP server running, client connected and subscribed|
|Steps|1. Modify a tool schema in the registry 2. Trigger schema change notification 3. Client receives notification 4. Client re-fetches `tools/list`|
|Acceptance|**MUST**: client receives `notifications/tools/list_changed` event. **MUST**: re-fetched `tools/list` contains the updated schema|

-----

### 1.3 Approval Middleware

#### T1.3.1 - Internal client write-tier approval (accept)

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, internal client connected via noted UI|
|Steps|1. Internal client calls `execute_cell` (write-tier) 2. Verify approval prompt appears in noted frontend 3. User clicks approve 4. Verify tool executes and result is returned|
|Acceptance|**MUST**: request is held until user acts. **MUST**: approval prompt shows tool name and arguments. **MUST**: after approval, tool result is returned to the client. **MUST**: latency between approval and response is under 1s|

#### T1.3.2 - Internal client write-tier approval (reject)

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, internal client connected via noted UI|
|Steps|1. Internal client calls `install_package` (write-tier) 2. User clicks reject|
|Acceptance|**MUST**: returns -32001 `authorization_error`. **MUST**: tool is not executed (verify no side effects). **MUST**: `data.skill` is `"install_package"`|

#### T1.3.3 - External read-scoped client rejected on write-tier

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, external client connected with read-only scope|
|Steps|1. Call `execute_cell` (write-tier) 2. Call `restart_kernel` (write-tier) 3. Call `trigger_dag` (write-tier)|
|Acceptance|**MUST**: all three return immediate -32001 `authorization_error`. **MUST**: response time under 100ms (no blocking/hanging). **MUST**: no approval prompt appears in noted frontend. **MUST**: error message includes guidance to enable write access|

#### T1.3.4 - External read+write client passes write-tier

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, external client connected with read+write API key|
|Steps|1. Call `execute_cell` with valid code|
|Acceptance|**MUST**: tool executes without noted-side approval prompt. **MUST**: result is returned normally|

#### T1.3.5 - Read-tier tools bypass approval for all clients

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running|
|Steps|1. Internal client calls `get_cell_output` 2. External read-only client calls `list_packages` 3. External client calls `set_breakpoint`|
|Acceptance|**MUST**: all three execute immediately without any approval prompt. **MUST**: `set_breakpoint` is treated as read-tier (auto-execute)|

-----

### 1.4 Rate Limiting

#### T1.4.1 - Read-tier rate limit enforcement

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, client connected|
|Steps|1. Send 11 `get_cell_output` calls in rapid succession (burst limit: 10) 2. Parse response of the 11th call|
|Acceptance|**MUST**: first 10 calls succeed. **MUST**: 11th call returns -32005 `rate_limited`. **MUST**: `data.retry_after` is a positive integer (seconds). **MUST**: `data.recoverable` is `true`|

#### T1.4.2 - Write-tier rate limit enforcement

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, read+write client connected|
|Steps|1. Send 4 `execute_cell` calls in rapid succession (burst limit: 3)|
|Acceptance|**MUST**: first 3 calls succeed. **MUST**: 4th call returns -32005 `rate_limited`|

#### T1.4.3 - Rate limit recovery

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, client has exhausted read-tier burst|
|Steps|1. Exhaust burst limit 2. Wait for `retry_after` seconds 3. Send another request|
|Acceptance|**MUST**: request after waiting succeeds. **SHOULD**: `retry_after` value accurately predicts when the next request will be accepted|

#### T1.4.4 - Rate limits are per-session

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, two clients connected|
|Steps|1. Client A exhausts read-tier burst 2. Client B sends a read-tier request|
|Acceptance|**MUST**: Client B's request succeeds. **MUST**: Client A's rate limit does not affect Client B|

#### T1.4.5 - Internal execution exempt from rate limits

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|MCP server running, workflow engine available (or simulated)|
|Steps|1. Client calls `run_workflow` (counts as 1 workflow-tier request) 2. Workflow internally triggers 20 kernel executions 3. Monitor rate limiter state|
|Acceptance|**MUST**: only 1 request counted against the client's rate limit. **MUST**: internal kernel executions are not tracked by the rate limiter. **MUST**: workflow completes without rate-limit errors|

-----

### 1.5 External Client Access

#### T1.5.1 - Unauthenticated client gets read-only

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running|
|Steps|1. Connect without API key 2. Call `tools/list` 3. Call `get_cell_output` (read-tier) 4. Call `execute_cell` (write-tier)|
|Acceptance|**MUST**: `tools/list` succeeds. **MUST**: `get_cell_output` succeeds. **MUST**: `execute_cell` returns -32001 `authorization_error`|

#### T1.5.2 - Valid read-scoped key

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, read-scoped API key generated|
|Steps|1. Connect with read-scoped key in `x-noted-api-key` header 2. Call `list_packages` 3. Call `execute_cell`|
|Acceptance|**MUST**: `list_packages` succeeds. **MUST**: `execute_cell` returns -32001. **MUST**: `last_used` field updated in key record|

#### T1.5.3 - Valid read+write key

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, read+write API key generated|
|Steps|1. Connect with read+write key 2. Call `execute_cell` with valid code|
|Acceptance|**MUST**: tool executes and returns result. **MUST**: no noted-side approval prompt|

#### T1.5.4 - Invalid/revoked key

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running|
|Steps|1. Connect with a fabricated key string 2. Connect with a previously revoked key|
|Acceptance|**MUST**: both connections fall back to read-only scope (not rejected). **SHOULD**: invalid key attempt is logged server-side|

#### T1.5.5 - Key provisioning via settings UI

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted running with settings UI accessible|
|Steps|1. Open MCP Client Access in settings 2. Click "Generate MCP Key" 3. Set scope to read+write 4. Copy displayed key 5. Verify key appears in client list (name, scope, date visible; key value not visible) 6. Use key to connect 7. Revoke key in settings 8. Attempt to connect with revoked key|
|Acceptance|**MUST**: key displayed exactly once on creation. **MUST**: key value never shown again after creation dialog closes. **MUST**: key works for connection before revocation. **MUST**: key stops working immediately after revocation (falls back to read-only)|

-----

### 1.6 Secret Isolation

#### T1.6.1 - Kernel environment audit

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|Kernel started by noted|
|Steps|1. Execute `import os; print(os.environ)` in a Python kernel 2. Execute `console.log(process.env)` in a JavaScript kernel 3. Inspect output for any Infisical-managed secret values|
|Acceptance|**MUST**: no Infisical-managed secrets appear in kernel process environment. **MUST**: expected runtime vars (PATH, NODE_PATH, PYTHONPATH) are present|

#### T1.6.2 - Output sanitisation on direct secret value

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, output sanitiser active, test secret "sk-test-12345" registered|
|Steps|1. Call `execute_cell` with code `print("sk-test-12345")` 2. Parse tool result|
|Acceptance|**MUST**: result contains `[REDACTED:<key_name>]` instead of the secret value. **MUST**: no occurrence of `sk-test-12345` in the JSON-RPC response|

#### T1.6.3 - Output sanitisation in stack trace

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, sanitiser active, test secret registered|
|Steps|1. Call `execute_cell` with code that raises an exception containing the secret in the message|
|Acceptance|**MUST**: stack trace in error response has secret replaced with `[REDACTED:<key_name>]`|

#### T1.6.4 - Sanitisation does not corrupt non-secret output

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|Sanitiser active|
|Steps|1. Pass a large output string (10KB) containing no secret values through the sanitiser|
|Acceptance|**MUST**: output is byte-identical to input. **SHOULD**: sanitisation adds less than 5ms latency for 10KB payloads|

-----

### 1.7 Deployment and Failure Isolation

#### T1.7.1 - MCP router startup failure does not affect noted

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|noted backend with MCP SDK deliberately misconfigured (e.g., invalid SDK import)|
|Steps|1. Start noted backend 2. Verify noted logs an MCP initialization error 3. Access noted UI 4. Open a notebook, execute a cell 5. Use the chat UI 6. Verify all non-MCP functionality works|
|Acceptance|**MUST**: noted starts successfully despite MCP failure. **MUST**: error is logged with clear message (not a silent failure). **MUST**: all existing features (notebooks, kernels, chat, file editing) function normally. **MUST**: `/mcp` returns appropriate error (503 or 404), not crash the server|

#### T1.7.2 - MCP runtime crash is contained

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|noted running with MCP enabled, client connected|
|Steps|1. Trigger an unhandled exception inside an MCP tool call handler (inject a deliberate crash) 2. Verify the MCP client receives a JSON-RPC error response 3. Immediately use the noted UI to execute a cell, open a notebook, and send a chat message|
|Acceptance|**MUST**: the MCP error is returned to the MCP client as a JSON-RPC error. **MUST**: noted's internal chat, kernel execution, and notebook operations are unaffected. **MUST**: other MCP clients connected simultaneously are unaffected. **MUST**: no noted process restart is required|

#### T1.7.3 - Feature toggle: MCP disabled

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted config with `mcp.enabled: false`|
|Steps|1. Start noted 2. Attempt to POST to `/mcp` 3. Run `docker exec -i noted-app python -m noted.mcp` with `NOTED_MCP_MODE=stdio` 4. Verify noted UI works normally|
|Acceptance|**MUST**: `/mcp` returns 404. **MUST**: stdio wrapper exits immediately with descriptive message on stderr (not stdout). **MUST**: noted UI, chat, kernels, and all existing features work normally. **MUST**: no MCP-related code is loaded into the noted process (verify no `mcp` module in `sys.modules`)|

#### T1.7.4 - Feature toggle: MCP enabled

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted config with `mcp.enabled: true`|
|Steps|1. Start noted 2. POST `initialize` to `/mcp` 3. Verify MCP is operational 4. Verify noted UI works normally|
|Acceptance|**MUST**: MCP endpoints respond. **MUST**: `initialize` succeeds. **MUST**: noted UI is unaffected|

#### T1.7.5 - Dependency isolation: no reverse imports

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|noted codebase with MCP package|
|Steps|1. Scan all Python files outside `backend/app/mcp/` for imports from `backend.app.mcp` or `app.mcp` 2. Scan `llm_tools.py`, `llm_manager.py`, `anthropic_llm_manager.py`, `main.py` for MCP imports (except the conditional router registration in `main.py`)|
|Acceptance|**MUST**: zero imports from the `mcp/` package in any file outside `backend/app/mcp/`, with the single exception of the conditional registration block in `main.py`. **MUST**: `llm_tools.py` has no awareness of MCP|

#### T1.7.6 - SDK version pinning

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|noted requirements file|
|Steps|1. Check `requirements.txt` (or equivalent) for `mcp` dependency 2. Verify it uses an exact version pin (e.g., `mcp==1.x.y`, not `mcp>=1.0`)|
|Acceptance|**MUST**: `mcp` SDK is pinned to an exact version. **MUST**: version matches the version documented in the architecture doc|

#### T1.7.7 - Noted full regression with MCP enabled

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|noted running with `mcp.enabled: true`|
|Steps|1. Open noted UI 2. Create a notebook 3. Add and execute Python and JavaScript cells 4. Use the internal chat (send a message, receive a response with tool calls) 5. Open file editor, edit and save a file 6. Check that the explorer tree, environments panel, and problems panel work 7. Verify kernel start/stop 8. Verify DAP debugging (set breakpoint, hit breakpoint, inspect variables)|
|Acceptance|**MUST**: all features work identically to noted without MCP. **MUST**: no performance degradation observable in UI responsiveness. **MUST**: no errors in backend logs related to MCP affecting other components|

-----

### Phase 1 Acceptance Gate

Phase 1 is accepted when ALL of the following hold:

1. An external MCP client (Claude Desktop or equivalent) connects via stdio and successfully calls a read-tier tool end-to-end
2. An external MCP client connects via Streamable HTTP through nginx and successfully calls a read-tier tool end-to-end
3. Write-tier tools from read-scoped clients are rejected immediately with -32001
4. Write-tier tools from read+write clients execute without noted-side approval
5. Write-tier tools from the internal noted UI trigger approval and complete on accept
6. Rate limits enforce burst caps and return -32005 with retry_after
7. No Infisical secrets appear in any tool response
8. All 38 tools appear in `tools/list` with valid JSON Schema
9. The existing noted chat UI is functionally unchanged (regression)
10. MCP router startup failure does not prevent noted from starting or affect any existing feature
11. MCP runtime crash is contained to the MCP request handler and does not affect other noted subsystems
12. `mcp.enabled: false` disables all MCP endpoints and loads no MCP code
13. No file outside `backend/app/mcp/` imports from the MCP package (one-directional dependency)
14. `mcp` SDK version is pinned to an exact version in requirements

-----

## Phase 2 - Resource Layer

### 2.1 Resource Framework

#### T2.1.1 - resources/list returns all registered resources

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running with resource handlers registered|
|Steps|1. Send `resources/list` request|
|Acceptance|**MUST**: response contains 14 resource entries. **MUST**: each entry has `uri`, `name`, and `description`. **MUST**: URIs follow the `noted://` scheme|

#### T2.1.2 - resources/read with valid URI

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, at least one MLflow experiment active|
|Steps|1. Send `resources/read` for `noted://mlflow/experiments/active`|
|Acceptance|**MUST**: response contains structured data (metrics, parameters). **MUST**: data matches what `mlflow_manager` returns directly|

#### T2.1.3 - resources/read with invalid URI

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running|
|Steps|1. Send `resources/read` for `noted://nonexistent/resource`|
|Acceptance|**MUST**: returns appropriate error (resource not found). **MUST**: does not crash the server|

#### T2.1.4 - resources/read does not count against tool rate limits

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|MCP server running, client connected|
|Steps|1. Exhaust read-tier tool rate limit 2. Send `resources/read` for any valid resource|
|Acceptance|**MUST**: resource read succeeds even when tool rate limit is exhausted. **SHOULD**: resources have their own rate limit if needed|

-----

### 2.2 Resource Implementations

#### T2.2.1 - Each resource returns valid data

For each of the 14 resources, the following acceptance criteria apply:

|Resource URI|Precondition|Acceptance|
|------------|------------|----------|
|`noted://project/env_status`|At least one environment exists|**MUST**: returns JSON with lockfile state for each active environment (pip/renv/pnpm)|
|`noted://project/shadow_files`|At least one notebook open with shadow files|**MUST**: returns list of shadow file paths with their associated notebook|
|`noted://dvc/lineage/current`|DVC initialized in project|**MUST**: returns DAG structure as JSON with stages and dependencies|
|`noted://dvc/status`|DVC initialized|**MUST**: returns tracking status (changed/unchanged files)|
|`noted://airflow/dags`|Airflow running with at least one DAG|**MUST**: returns list of DAGs with id, state, schedule|
|`noted://airflow/logs/{dag_id}/{run_id}`|At least one completed DAG run|**MUST**: returns log text for the specified run|
|`noted://airflow/runs/{dag_id}`|DAG with run history|**MUST**: returns paginated run list (see T2.2.2)|
|`noted://mlflow/experiments/active`|Active MLflow run|**MUST**: returns current metrics, parameters, and run state|
|`noted://mlflow/experiments/{id}/runs`|Experiment with multiple runs|**MUST**: returns paginated run list (see T2.2.2)|
|`noted://mlflow/models/registry`|At least one registered model|**MUST**: returns model names, versions, and stages|
|`noted://hydra/config/current`|Hydra config loaded|**MUST**: returns resolved config tree as JSON|
|`noted://notebooks/fs`|At least one notebook in project|**MUST**: returns filesystem tree of notebooks|
|`noted://notebooks/{id}/output`|Notebook with executed cells|**MUST**: returns last output of the specified notebook|

#### T2.2.2 - Pagination for unbounded resources

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MLflow experiment with 50+ runs|
|Steps|1. Send `resources/read` for `noted://mlflow/experiments/{id}/runs` without cursor 2. Verify response contains a page of results and a `nextCursor` 3. Send follow-up request with cursor 4. Repeat until no `nextCursor` returned|
|Acceptance|**MUST**: first page returns a bounded number of results (not all 50+). **MUST**: `nextCursor` is present when more results exist. **MUST**: iterating through all pages returns all runs without duplicates or gaps. **MUST**: final page has no `nextCursor`. **SHOULD**: page size is configurable or documented|

#### T2.2.3 - Resource returns graceful error when backend unavailable

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Airflow container stopped|
|Steps|1. Send `resources/read` for `noted://airflow/dags`|
|Acceptance|**MUST**: returns structured error indicating Airflow is unavailable. **MUST**: does not crash server or hang|

-----

### 2.3 Push Subscriptions

#### T2.3.1 - Subscribe and receive notification

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, client connected, MLflow active run|
|Steps|1. Client sends `resources/subscribe` for `noted://mlflow/experiments/active` 2. Log a new metric to the active MLflow run (externally or via tool) 3. Observe client for notification|
|Acceptance|**MUST**: server acknowledges subscription. **MUST**: client receives `notifications/resources/updated` with the subscribed URI within 5s of the metric being logged|

#### T2.3.2 - Unsubscribe stops notifications

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|Client subscribed to `noted://mlflow/experiments/active`|
|Steps|1. Client sends `resources/unsubscribe` for the URI 2. Log another metric 3. Wait 10s|
|Acceptance|**MUST**: no notification received after unsubscribe. **MUST**: server-side watcher for this client+URI is released|

#### T2.3.3 - Airflow task failure triggers push

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|Client subscribed to `noted://airflow/logs/{dag_id}/{run_id}`|
|Steps|1. Trigger a DAG run that contains a task designed to fail 2. Wait for task failure|
|Acceptance|**MUST**: client receives `notifications/resources/updated` for the subscribed log URI. **MUST**: subsequent `resources/read` on that URI returns the failure logs|

#### T2.3.4 - DVC sync triggers push

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|Client subscribed to `noted://dvc/lineage/current`|
|Steps|1. Execute `dvc_push` or `dvc_pull` via MCP tool 2. Wait for completion|
|Acceptance|**MUST**: client receives `notifications/resources/updated` for the DVC lineage URI|

#### T2.3.5 - Chat session lifecycle governs subscriptions (internal client)

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|noted running, chat panel closed|
|Steps|1. Verify no active subscriptions exist 2. Open chat panel 3. Verify subscriptions issued for default URIs (`mlflow/experiments/active`, `dvc/lineage/current`) 4. Close chat panel 5. Verify subscriptions removed within configured idle timeout|
|Acceptance|**MUST**: no subscriptions active when chat panel is closed. **MUST**: default subscriptions auto-issued on chat panel open. **MUST**: subscriptions cleaned up on chat panel close|

#### T2.3.6 - Idle timeout triggers unsubscribe

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Chat panel open, subscriptions active, idle timeout set to 1 minute (test override)|
|Steps|1. Do not interact with chat for 1 minute 2. Check subscription state|
|Acceptance|**MUST**: subscriptions are removed after idle timeout. **MUST**: server-side watchers released|

#### T2.3.7 - External client subscription lifecycle is independent

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|External client connected|
|Steps|1. External client sends `resources/subscribe` for `noted://dvc/lineage/current` 2. Verify subscription active 3. Verify noted frontend does not auto-subscribe or auto-unsubscribe on behalf of external client|
|Acceptance|**MUST**: subscription persists until the external client explicitly unsubscribes or disconnects. **MUST**: noted frontend subscription lifecycle does not affect external client subscriptions|

-----

### Phase 2 Acceptance Gate

Phase 2 is accepted when ALL of the following hold:

1. `resources/list` returns all 14 resources with valid URIs
2. `resources/read` returns correct data for each of the 14 resources (verified against direct manager calls)
3. Paginated resources return bounded pages with working cursor iteration
4. At least one push subscription (MLflow, Airflow, or DVC) delivers a notification within 5s of the triggering event
5. Subscriptions are tied to chat session lifecycle for internal clients
6. External clients manage their own subscription lifecycle independently
7. Resource reads do not count against tool rate limits
8. All Phase 1 capabilities remain functional (regression)

-----

## Phase 3 - Workflow Tool Surface

### 3.1 Workflow Tools

#### T3.1.1 - list_workflows returns available templates

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, at least one workflow template registered|
|Steps|1. Call `list_workflows`|
|Acceptance|**MUST**: returns list of workflow templates with `template_id`, `name`, `description`, and `params` schema. **MUST**: auto-executes without approval (read-tier)|

#### T3.1.2 - run_workflow triggers DAG and returns run_id

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running, workflow engine operational, read+write client|
|Steps|1. Call `run_workflow` with valid template_id and params 2. Parse response|
|Acceptance|**MUST**: returns a `run_id` string. **MUST**: corresponding Airflow DAG is triggered (verify via Airflow API). **MUST**: requires write-tier approval/scope|

#### T3.1.3 - run_workflow with invalid template

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running|
|Steps|1. Call `run_workflow` with a nonexistent template_id|
|Acceptance|**MUST**: returns -32006 `validation_error`. **MUST**: DAG is not triggered|

#### T3.1.4 - get_workflow_status returns DAG state

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|A workflow previously triggered via T3.1.2|
|Steps|1. Call `get_workflow_status` with the run_id from T3.1.2 2. Wait for workflow to complete 3. Call `get_workflow_status` again|
|Acceptance|**MUST**: first call returns in-progress state. **MUST**: second call returns completed/failed state. **MUST**: auto-executes without approval (read-tier)|

#### T3.1.5 - get_workflow_result returns aggregated output

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|A workflow that completed successfully|
|Steps|1. Call `get_workflow_result` with the run_id|
|Acceptance|**MUST**: returns aggregated output from MLflow experiment records. **MUST**: output includes per-node results. **MUST**: auto-executes without approval (read-tier)|

#### T3.1.6 - Workflow tools appear in tools/list

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|MCP server running|
|Steps|1. Send `tools/list` 2. Filter for workflow tools|
|Acceptance|**MUST**: `list_workflows`, `run_workflow`, `get_workflow_status`, `get_workflow_result` all present. **MUST**: `run_workflow` is annotated as write-tier|

-----

### 3.2 Workflow Rate Limiting and Access Control

#### T3.2.1 - Workflow rate limit enforcement

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|MCP server running, read+write client|
|Steps|1. Call `run_workflow` twice in rapid succession (burst limit: 1)|
|Acceptance|**MUST**: first call succeeds. **MUST**: second call returns -32005 `rate_limited`. **MUST**: `data.retry_after` is present|

#### T3.2.2 - Workflow requires write scope

|Field|Value|
|-----|-----|
|Type|Security|
|Precondition|Read-only external client connected|
|Steps|1. Call `run_workflow`|
|Acceptance|**MUST**: returns -32001 `authorization_error`|

#### T3.2.3 - Workflow internal execution exempt from client rate limit

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|MCP server running, workflow engine with multi-node DAG|
|Steps|1. Client calls `run_workflow` for a template with 20+ nodes 2. DAG executes all nodes 3. Check client's rate limiter state|
|Acceptance|**MUST**: only 1 request counted against client's workflow tier. **MUST**: DAG node executions do not trigger rate-limit errors|

-----

### Phase 3 Acceptance Gate

Phase 3 is accepted when ALL of the following hold:

1. `list_workflows` returns available templates with valid schemas
2. `run_workflow` triggers an Airflow DAG, returns a run_id, and requires write scope
3. `get_workflow_status` accurately reflects DAG execution state transitions
4. `get_workflow_result` returns aggregated output from MLflow after completion
5. Workflow rate limit (3/min, burst 1) is enforced at MCP boundary
6. Internal DAG execution is exempt from client rate limits
7. All Phase 1 and Phase 2 capabilities remain functional (regression)

-----

## Phase 4 - Internal LLM Migration

### 4.1 Dynamic Context Router

#### T4.1.1 - Domain classification accuracy

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|Domain classifier implemented|
|Steps|Run the classifier against a test set of representative user messages:|
|- "Why did my DAG fail?" -> Airflow domain|
|- "Install pandas" -> Package Management domain|
|- "What's the loss curve?" -> MLflow domain|
|- "Fix my plot" -> Execution domain|
|- "Set a breakpoint on line 42" -> Debugging domain|
|- "Push my data to remote" -> DVC domain|
|- "Change the learning rate to 0.001" -> Hydra domain|
|- "Run the data quality check" -> Workflow domain|
|Acceptance|**MUST**: at least 90% of test messages classified to the correct primary domain. **MUST**: classification latency under 50ms per message. **SHOULD**: multi-domain messages (e.g., "run the DAG and log the results to MLflow") return both relevant domains|

#### T4.1.2 - Schema injection is selective

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Dynamic Context Router active, MCP server running|
|Steps|1. Send "Install numpy" to noted chat 2. Intercept the LLM API call 3. Inspect the `tools` array|
|Acceptance|**MUST**: `tools` array contains Package Management schemas (`install_package`, `list_packages`). **MUST**: `tools` array does NOT contain all 38 schemas. **SHOULD**: array contains 8 or fewer schemas|

#### T4.1.3 - Out-of-scope tool retry succeeds

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|Dynamic Context Router active|
|Steps|1. Send a message classified as Execution domain 2. LLM unexpectedly requests `log_metric` (MLflow, not in scope) 3. Observe retry behaviour|
|Acceptance|**MUST**: backend detects the out-of-scope tool call. **MUST**: backend fetches `log_metric` schema from MCP. **MUST**: backend retries the turn with the expanded `tools` array. **MUST**: LLM call succeeds on retry. **MUST**: retry is invisible to the user (no error shown)|

#### T4.1.4 - Router does not degrade broad sessions

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|Dynamic Context Router active|
|Steps|1. Send a broad message like "Help me debug this ML pipeline - the DAG is failing and the model metrics look wrong" 2. Inspect the `tools` array|
|Acceptance|**MUST**: router includes schemas from multiple domains (Airflow, MLflow, Execution, Debugging). **MUST**: LLM can call tools from any of the included domains without retries|

-----

### 4.2 System Prompt Migration

#### T4.2.1 - Static TOOL_DESCRIPTIONS removed

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|Phase 4 migration complete|
|Steps|1. Inspect system prompt sent to AnthropicLLMManager 2. Inspect system prompt sent to local LLMManager|
|Acceptance|**MUST**: neither system prompt contains the full 38-schema `TOOL_DESCRIPTIONS` block. **SHOULD**: system prompt contains a lightweight text index as fallback hint|

#### T4.2.2 - Internal tool calls route through MCP

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Phase 4 migration complete, MCP server running|
|Steps|1. Send a chat message that triggers a tool call 2. Trace the call path|
|Acceptance|**MUST**: tool call flows through MCP server (`tools/call`), not direct `execute_tool()`. **MUST**: approval middleware and rate limiting apply to internal calls. **MUST**: error taxonomy (-32001 to -32006) is used for internal errors|

#### T4.2.3 - Minimal system prompt retained

|Field|Value|
|-----|-----|
|Type|Unit|
|Precondition|Phase 4 migration complete|
|Steps|1. Inspect system prompt content|
|Acceptance|**MUST**: contains noted context (project, environment). **MUST**: contains user preferences. **MUST**: contains model routing policy. **MUST**: does NOT contain full tool schemas|

-----

### 4.3 Regression

#### T4.3.1 - All 24 existing tools produce identical results via MCP

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Phase 4 migration complete|
|Steps|For each of the 24 tools: 1. Call via MCP `tools/call` 2. Call via direct `execute_tool()` (temporarily re-enabled for testing) 3. Compare results|
|Acceptance|**MUST**: results are functionally identical for all 24 tools. Acceptable differences: timing fields, request IDs. Unacceptable differences: data content, error classification, side effects|

#### T4.3.2 - Token usage measurement

|Field|Value|
|-----|-----|
|Type|Integration|
|Precondition|Phase 4 migration complete|
|Steps|1. Run 10 representative chat conversations (mix of focused and broad) 2. Measure per-turn token count in the `tools` array 3. Compare against baseline (38 schemas static)|
|Acceptance|**MUST**: focused tasks (single domain) use fewer tokens than baseline. **SHOULD**: average per-turn tool token count is 60% or less of the static baseline. **MUST**: no conversation fails due to missing tools (retry loop catches all misses)|

#### T4.3.3 - End-to-end chat with full stack

|Field|Value|
|-----|-----|
|Type|E2E|
|Precondition|All phases complete|
|Steps|1. Open noted chat 2. Ask "Why did my last Airflow run fail?" 3. LLM reads Airflow resource or calls Airflow tool 4. Ask "Fix the code and re-run the cell" 5. LLM calls execute_cell (write-tier, triggers approval) 6. Approve 7. LLM returns result|
|Acceptance|**MUST**: Dynamic Context Router selects correct domains at each turn. **MUST**: approval middleware triggers for write-tier calls. **MUST**: full conversation completes without errors or retries visible to the user|

-----

### Phase 4 Acceptance Gate

Phase 4 is accepted when ALL of the following hold:

1. Domain classifier achieves 90%+ accuracy on the test message set
2. Per-turn `tools` array contains only relevant schemas (not all 38)
3. Out-of-scope tool retry succeeds transparently
4. All 24 existing tools produce identical results through MCP vs direct dispatch
5. Static `TOOL_DESCRIPTIONS` block is removed from both LLM system prompts
6. Internal tool calls route through MCP server with approval and rate limiting
7. Average per-turn tool token count is measurably lower than static baseline
8. Full end-to-end chat conversation completes with Dynamic Context Router, approval, and rate limiting
9. All Phase 1, Phase 2, and Phase 3 capabilities remain functional (regression)

-----

## Cross-Phase Regression Matrix

After each phase ships, run the previous phase's acceptance gate tests to confirm no regressions. This matrix defines which gates must pass:

|Shipping phase|Gates that must pass|
|--------------|--------------------|
|Phase 1|Phase 1 gate|
|Phase 2|Phase 1 gate + Phase 2 gate|
|Phase 3|Phase 1 gate + Phase 2 gate + Phase 3 gate|
|Phase 4|Phase 1 gate + Phase 2 gate + Phase 3 gate + Phase 4 gate|

Any regression in a previous phase's gate is a release blocker for the current phase.

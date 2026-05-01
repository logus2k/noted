# noted - MCP Server Development Plan

Reference: [mcp_technical_architecture_notes.md](mcp_technical_architecture_notes.md)

-----

## Current State Assessment

Before estimating work, this is what already exists and can be reused:

**Tool system (backend/app/managers/llm_tools.py)**
- 24 tools defined in `TOOL_DESCRIPTIONS` with name, description, and argument schemas
- `execute_tool()` dispatcher routes tool calls to async handler functions
- `WRITE_TOOLS` set already classifies tools into read vs write tiers
- Write action approval flow exists (`prepare_write_action`, `execute_write_tool`)
- Tool call parsing: `<tool_call>{...}</tool_call>` XML block format

**Skill system (backend/app/managers/llm_skills.py)**
- `SkillRegistry` loads skills from `data/skills/` (YAML frontmatter + markdown)
- 10+ domain skills (Airflow, MLflow, DVC, Hydra, etc.) with triggers, priority, max_tokens
- Skills are knowledge documents, not callable tools - they inject domain guidance into the system prompt

**LLM integration**
- `LLMRouter` switches between local Qwen backend and Anthropic Claude API
- `AnthropicLLMManager` injects full `TOOL_DESCRIPTIONS` into the system prompt on every call
- `LLMContext` builds context messages (notebook state, active runs, config)
- `LLMMemory` handles per-project conversation history
- Streaming support with thinking blocks

**Domain managers (backend/app/managers/)**
- `mlflow_manager.py` - MLflow tracking client
- `airflow_manager.py` - Airflow REST API v2 client
- `dvc_manager.py` - DVC subprocess wrapper with MinIO backend
- `hydra_manager.py` - Hydra config resolution
- `kernel_manager.py` - Jupyter kernel lifecycle
- `notebook_manager.py` - Notebook CRUD and cell execution
- `file_manager.py` - File I/O with project scoping
- `venv_manager.py` - Virtual environment management (pip, renv, pnpm)
- `terminal_manager.py` - Terminal/shell sessions

**Infrastructure**
- FastAPI backend with 23 routers
- nginx reverse proxy with WebSocket support
- oauth2-proxy authentication
- Socket.IO for real-time frontend communication

**What does NOT exist yet**
- MCP server or any MCP protocol code
- `noted://` URI scheme or resource abstraction
- Rate limiting middleware
- API key management for external clients
- Dynamic Context Router
- Stdio transport wrapper
- Output sanitisation layer for secrets
- Workflow template system (subagent DAG layer is planned, not built)

-----

## Estimation Conventions

Estimates are in **developer-days** (1 dev-day = focused work day, no meetings). Ranges reflect uncertainty: low end assumes no surprises, high end accounts for SDK edge cases, testing, and integration bugs.

Each task is tagged:
- **NEW** - built from scratch
- **WRAP** - wraps or adapts existing code
- **MODIFY** - changes existing code

-----

## Phase 1 - MCP Wrapper (Foundation)

**Goal**: expose existing dispatcher through MCP without changing any skill logic.

**Dependency**: none (first phase).

**What you can do after Phase 1 (that you cannot do today)**:
- Connect Claude Desktop, Claude Code, or Cursor to noted as an MCP server - they discover and call all 38 tools
- External users browse noted's capabilities via `tools/list` without any noted UI knowledge
- Read-tier tools (get_cell_output, list_packages, get_dap_stack, etc.) work immediately for any connected client
- Write-tier tools work for clients with a scoped API key, gated by the client's own confirmation UX
- noted can be demonstrated as a headless AI execution engine controlled entirely from external clients
- Secret values are never leaked in tool responses
- Agentic loops from external clients are rate-limited and cannot overwhelm backend services

**What stays the same**: the internal noted chat UI continues using static tool injection and direct dispatch - no user-facing changes to the existing LLM experience. Phase 1 is purely additive.

**This phase is a complete, shippable product on its own.** Phases 2-4 are enhancements, not requirements.

### 1.1 MCP SDK integration and server scaffold

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.1.1|NEW|Install `mcp` Python SDK, create `backend/app/mcp/` package with server class|1d|
|1.1.2|NEW|Implement `initialize` handshake, `ping`, `notifications/cancelled` lifecycle via SDK|1d|
|1.1.3|NEW|Mount MCP server into FastAPI via Starlette `Mount` at `/mcp` using Streamable HTTP transport (`mcp.streamable_http_app()`)|1-2d|
|1.1.4|NEW|Configure `stateless_http=True`, `json_response=True`; integrate MCP session manager into FastAPI lifespan|0.5d|
|1.1.5|NEW|Session management: track connected clients, session IDs, client metadata|1d|

**Subtotal**: 4.5-5.5d

### 1.2 Tool surface

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.2.1|WRAP|Convert `TOOL_DESCRIPTIONS` from current format to MCP JSON Schema format for `tools/list`|1-2d|
|1.2.2|WRAP|Implement `tools/call` - bridge MCP requests to existing `execute_tool()` dispatcher|1d|
|1.2.3|WRAP|Map existing `WRITE_TOOLS` set to MCP tool annotations (read/write tier metadata)|0.5d|
|1.2.4|NEW|Error mapping: translate dispatcher exceptions to MCP error taxonomy (-32001 to -32006)|1d|
|1.2.5|NEW|Implement `notifications/tools/list_changed` for schema versioning|0.5d|

**Subtotal**: 4-5d

### 1.3 Approval middleware

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.3.1|WRAP|Adapt existing `prepare_write_action` / `execute_write_tool` flow to MCP request lifecycle|1-2d|
|1.3.2|NEW|Internal client path: hold JSON-RPC request, surface to frontend via Socket.IO, await approval|1-2d|
|1.3.3|NEW|External client path: immediate -32001 rejection for write-tier tools from read-scoped clients|0.5d|
|1.3.4|NEW|Client type detection: distinguish internal vs external clients on session init|0.5d|

**Subtotal**: 3-5d

### 1.4 Rate limiting

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.4.1|NEW|Token bucket implementation (in-memory, per-session, tiered: read/write/workflow)|1d|
|1.4.2|NEW|Rate limit middleware in MCP request pipeline, -32005 error with `retry_after`|0.5d|
|1.4.3|NEW|Boundary enforcement: only MCP client-to-server requests counted, internal execution exempt|0.5d|

**Subtotal**: 2d

### 1.5 External client access

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.5.1|NEW|API key model: generation, bcrypt hashing, storage in noted config|1d|
|1.5.2|NEW|Key validation on `initialize`: extract from `x-noted-api-key` header or init params, bind scope to session|0.5d|
|1.5.3|NEW|Settings UI: MCP Client Access section (generate key, list clients, revoke)|1-2d|
|1.5.4|NEW|Default read-only behaviour for unauthenticated external clients|0.5d|

**Subtotal**: 3-4d

### 1.6 Secret isolation

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.6.1|MODIFY|Audit kernel startup to verify Infisical secrets are not in process environment|0.5d|
|1.6.2|NEW|Output sanitiser: secret registry loaded from Infisical at startup, pattern replacement in tool results|1-1.5d|
|1.6.3|NEW|Integration: sanitiser in dispatcher return path, before MCP response serialization|0.5d|

**Subtotal**: 2-2.5d

### 1.7 Infrastructure and deployment

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.7.1|MODIFY|nginx config: add `/mcp/` proxy location with Streamable HTTP support (no buffering, long timeouts)|0.5d|
|1.7.2|MODIFY|oauth2-proxy: ensure `/mcp/` endpoints are covered by existing auth|0.5d|
|1.7.3|NEW|Stdio wrapper: `noted.mcp.__main__` with stdout redirect, HTTP bridge to `/mcp`|1-1.5d|
|1.7.4|NEW|Dockerfile: install `mcp` SDK dependency (pinned version)|0.5d|
|1.7.5|NEW|Feature toggle: `mcp.enabled` config flag; conditional router registration in `main.py`; nginx location returns 404 when disabled; stdio wrapper exits with message on stderr when disabled|1d|
|1.7.6|NEW|Failure isolation: wrap MCP router registration in try/except so startup failures are logged and noted continues without MCP; verify no other module imports from `backend/app/mcp/`|0.5d|
|1.7.7|NEW|SDK version pin: lock `mcp` SDK to specific version in requirements, document target spec revision in architecture doc|0.5d|

**Subtotal**: 4.5-5d

### 1.8 Testing and validation

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|1.8.1|NEW|End-to-end test: Claude Desktop connects via stdio, calls read-tier tool, gets result|1d|
|1.8.2|NEW|End-to-end test: internal noted UI calls tool via Streamable HTTP transport|1d|
|1.8.3|NEW|Approval flow test: write-tier tool from internal client triggers approval, completes on accept|0.5d|
|1.8.4|NEW|Rate limiting test: burst past limits, verify -32005 and retry_after|0.5d|
|1.8.5|NEW|External client test: read-only client rejected on write-tier, read+write client passes|0.5d|
|1.8.6|NEW|Secret sanitisation test: execute cell that prints known secret value, verify redaction|0.5d|
|1.8.7|NEW|Failure isolation test: MCP router crash does not affect noted; MCP disabled mode works; startup failure is logged and noted runs without MCP|1d|
|1.8.8|NEW|Feature toggle test: `mcp.enabled=false` disables all MCP endpoints and stdio wrapper|0.5d|
|1.8.9|NEW|Noted regression test: existing chat UI, kernel execution, notebook operations all functional with MCP enabled and disabled|1d|

**Subtotal**: 6.5d

### Phase 1 Total: 28-35 developer-days

-----

## Phase 2 - Resource Layer

**Goal**: give the LLM read access to environment state without tool calls.

**Dependency**: Phase 1 complete (MCP server running, transport working).

**What you can do after Phase 2 (that you could not do after Phase 1)**:
- LLM clients read environment state passively (MLflow metrics, DVC lineage, Airflow DAG status, Hydra config) without consuming write-tier confirmation budget or tool call rate limits
- Push notifications: when an Airflow task fails, a DVC sync completes, or an MLflow metric crosses a threshold, subscribed clients are notified automatically - no polling needed
- External clients (Claude Desktop, Cursor) can inspect noted's full environment state via `resources/read` without needing to know which tool to call
- The LLM can answer questions like "what's the current experiment status?" by reading a resource instead of executing a tool, which is faster and lower-cost

**What stays the same**: tool calling works identically to Phase 1. The internal noted chat UI still uses static tool injection. Resources are an additive capability - everything from Phase 1 continues working.

**This phase can be skipped or deferred.** Without it, the LLM simply calls `get_*` tools instead of reading resources - functionally equivalent, just less efficient.

### 2.1 Resource framework

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|2.1.1|NEW|Resource registry: `noted://` URI scheme parser, resource handler registration|1d|
|2.1.2|NEW|Implement `resources/list` endpoint returning all registered resources with URI templates|0.5d|
|2.1.3|NEW|Implement `resources/read` endpoint with URI routing to handlers|1d|
|2.1.4|NEW|Pagination framework: cursor-based pagination for list resources per MCP spec|1-1.5d|

**Subtotal**: 3.5-4d

### 2.2 Resource implementations

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|2.2.1|WRAP|`noted://project/env_status` - read from venv_manager (pip/renv/pnpm lockfile state)|0.5d|
|2.2.2|WRAP|`noted://project/shadow_files` - read shadow file index from LSP manager|0.5d|
|2.2.3|WRAP|`noted://dvc/lineage/current` - read from dvc_manager DAG output|0.5d|
|2.2.4|WRAP|`noted://dvc/status` - read from dvc_manager status|0.5d|
|2.2.5|WRAP|`noted://airflow/dags` - read from airflow_manager DAG list|0.5d|
|2.2.6|WRAP|`noted://airflow/logs/{dag_id}/{run_id}` - read from airflow_manager log fetch|0.5d|
|2.2.7|WRAP|`noted://airflow/runs/{dag_id}` - read from airflow_manager with pagination|1d|
|2.2.8|WRAP|`noted://mlflow/experiments/active` - read from mlflow_manager active run|0.5d|
|2.2.9|WRAP|`noted://mlflow/experiments/{id}/runs` - read from mlflow_manager with pagination|1d|
|2.2.10|WRAP|`noted://mlflow/models/registry` - read from mlflow_manager model registry|0.5d|
|2.2.11|WRAP|`noted://hydra/config/current` - read from hydra_manager resolved config|0.5d|
|2.2.12|WRAP|`noted://notebooks/fs` - read from notebook_manager filesystem tree|0.5d|
|2.2.13|WRAP|`noted://notebooks/{id}/output` - read from notebook_manager last output|0.5d|

**Subtotal**: 7d

### 2.3 Push subscriptions

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|2.3.1|NEW|Subscription manager: track client subscriptions per URI, handle subscribe/unsubscribe requests|1-1.5d|
|2.3.2|NEW|`notifications/resources/updated` push event infrastructure|1d|
|2.3.3|MODIFY|Airflow task state hook: trigger push on task completion/failure for subscribed `airflow/logs` URIs|1-2d|
|2.3.4|MODIFY|MLflow callback hook: trigger push on metric log or run state change for subscribed `mlflow/experiments/active`|1-2d|
|2.3.5|MODIFY|DVC sync hook: trigger push on DVC push/pull completion for subscribed `dvc/lineage/current`|1d|
|2.3.6|MODIFY|Frontend: issue `resources/subscribe` on chat panel open, `resources/unsubscribe` on close/idle timeout|1d|

**Subtotal**: 6-8.5d

### 2.4 Testing

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|2.4.1|NEW|Resource read tests: each of the 14 resources returns valid data|1.5d|
|2.4.2|NEW|Pagination test: MLflow runs and Airflow run history paginate correctly|0.5d|
|2.4.3|NEW|Subscription test: trigger Airflow task failure, verify push received by subscribed client|1d|
|2.4.4|NEW|Lifecycle test: subscription cleaned up on disconnect and idle timeout|0.5d|

**Subtotal**: 3.5d

### Phase 2 Total: 20-23 developer-days

-----

## Phase 3 - Workflow Tool Surface

**Goal**: expose the subagent DAG architecture through MCP.

**Dependency**: Phase 1 complete. Phase 2 is not a hard dependency (workflow tools are tools, not resources), but having resources available enriches workflow result inspection.

**Important note**: Phase 3 depends on the subagent DAG architecture and workflow template system, which are currently planned but not built. The estimates below cover only the MCP surface layer - they assume the underlying Airflow DAG orchestration for workflows exists. If it does not, the workflow engine itself must be built first (estimated separately below).

**What you can do after Phase 3 (that you could not do after Phase 2)**:
- External clients trigger full multi-step noted workflows through a single `run_workflow` call - no knowledge of Airflow DAGs, MLflow experiments, or internal orchestration required
- A Claude Desktop user can say "run the data quality workflow on this dataset" and noted handles the entire DAG execution, returning aggregated results
- Workflow status polling and result retrieval available via MCP, enabling agentic loops that trigger a workflow, wait for completion, and act on the result
- Stable, well-scoped workflow operations replace raw skill invocations for complex multi-step tasks

**What stays the same**: individual tools from Phase 1 and resources from Phase 2 continue working. Workflows are a higher-level abstraction on top of them.

**This phase can be skipped entirely.** If the subagent DAG architecture is not built, or if external clients don't need workflow orchestration, Phases 1 and 2 provide full tool and resource access. Workflows are a convenience layer for multi-step operations, not a prerequisite for anything else.

### 3.1 Workflow engine prerequisite (if not yet built)

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|3.1.1|NEW|Workflow template format: define schema for multi-step workflow definitions (YAML/JSON)|2-3d|
|3.1.2|NEW|Template registry: load, validate, and list workflow templates|1-2d|
|3.1.3|NEW|DAG generator: convert workflow template into Airflow DAG definition|3-5d|
|3.1.4|NEW|Workflow execution: trigger DAG, track run state, aggregate results from MLflow|2-3d|
|3.1.5|NEW|Per-node model invocation: nodes call noted's OpenAI-compatible endpoint for LLM steps|2-3d|

**Workflow engine subtotal**: 10-16d (only if not already built)

### 3.2 MCP workflow tools

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|3.2.1|WRAP|`list_workflows` - return available templates from registry|0.5d|
|3.2.2|NEW|`run_workflow` - validate params, instantiate DAG, return run_id|1-2d|
|3.2.3|WRAP|`get_workflow_status` - query Airflow DAG run state|0.5d|
|3.2.4|WRAP|`get_workflow_result` - aggregate output from MLflow experiment records|1d|
|3.2.5|NEW|Add workflow tool schemas to MCP `tools/list`, classify as write-tier|0.5d|

**Subtotal**: 3.5-4.5d

### 3.3 Testing

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|3.3.1|NEW|End-to-end: trigger workflow via MCP, poll status, retrieve result|1-2d|
|3.3.2|NEW|Rate limiting: verify workflow tier (3/min, burst 1) enforced|0.5d|
|3.3.3|NEW|External client: verify run_workflow requires write scope|0.5d|

**Subtotal**: 2-3d

### Phase 3 Total: 5.5-7.5 developer-days (MCP surface only) + 10-16d (workflow engine, if not built)

-----

## Phase 4 - Internal LLM Migration

**Goal**: migrate the internal LLM from static skill injection to MCP-based tool discovery with a Dynamic Context Router.

**Dependency**: Phase 1 complete. Phases 2 and 3 should be complete for full coverage, but Phase 4 can start in parallel with Phase 3 using the Phase 1 tool surface.

**What you can do after Phase 4 (that you could not do after Phase 3)**:
- The internal noted chat LLM uses the same MCP tool surface as external clients - one tool definition, one code path, zero dual-maintenance
- Per-turn token cost drops from 38 full schemas (~2000+ tokens) to 5-8 relevant schemas (~300-500 tokens), scaling with task complexity
- Adding a new tool to noted means adding it once to the MCP server - it's automatically available to the internal LLM, Claude Desktop, Cursor, and any other MCP client
- The Dynamic Context Router enables the internal LLM to handle focused tasks (debugging, package management) without loading irrelevant tool schemas (Airflow, DVC) into context

**What stays the same**: all tool, resource, and workflow capabilities from Phases 1-3. The user-facing chat experience is functionally identical - the LLM can still call all the same tools. The change is internal: how those tools are discovered and injected.

**This phase is an optimization, not a functional requirement.** The internal LLM works correctly with static injection through Phases 1-3. Phase 4 improves token efficiency and eliminates maintenance overhead, but no user-visible capability depends on it. It is the right time to do this work when you are actively adding new tools and feeling the cost of maintaining both static prompts and MCP schemas.

### 4.1 Dynamic Context Router

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|4.1.1|NEW|Domain classifier: map user messages to tool domains (keyword matching as baseline)|2-3d|
|4.1.2|NEW|Schema fetcher: query MCP `tools/list`, cache schemas, select subset by domain tags|1d|
|4.1.3|NEW|Router integration: inject selected schemas into LLM `tools` array before each API call|1d|
|4.1.4|NEW|Retry loop: if LLM calls an out-of-scope tool, fetch missing schema and retry the turn|1-1.5d|
|4.1.5|NEW|Domain tagging: annotate each MCP tool with domain tags (execution, debugging, airflow, mlflow, dvc, hydra, workflow)|0.5d|

**Subtotal**: 5.5-7d

### 4.2 System prompt migration

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|4.2.1|MODIFY|Remove `TOOL_DESCRIPTIONS` injection from `AnthropicLLMManager` system prompt|0.5d|
|4.2.2|MODIFY|Remove tool injection from local `LLMManager` system prompt|0.5d|
|4.2.3|MODIFY|Add optional lightweight text index to system prompt as fallback hint|0.5d|
|4.2.4|MODIFY|Route internal tool calls through MCP server instead of direct `execute_tool()`|1-2d|
|4.2.5|MODIFY|Retain minimal system prompt: noted context, user preferences, model routing policy|0.5d|

**Subtotal**: 3-4d

### 4.3 Skill system integration

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|4.3.1|NEW|Evaluate whether domain skills (from `data/skills/`) should influence the router's domain classification (skill triggers as routing hints)|1d|
|4.3.2|MODIFY|If skills inform routing: feed active skill triggers to the domain classifier as additional signal|1d|

**Subtotal**: 1-2d

### 4.4 Validation and regression testing

|Task|Type|Description|Estimate|
|----|----|-----------|--------|
|4.4.1|NEW|Regression: run each of the 24 existing tools through MCP path, verify identical results to direct dispatch|2-3d|
|4.4.2|NEW|Router accuracy: test domain classification against a set of representative user messages, measure precision/recall|1d|
|4.4.3|NEW|Token measurement: compare per-turn token usage (before: 38 schemas static, after: 5-8 dynamic) across task types|0.5d|
|4.4.4|NEW|Fallback test: LLM requests out-of-scope tool, verify retry succeeds|0.5d|
|4.4.5|NEW|End-to-end chat test: full conversation through MCP path with approval, rate limiting, and context routing|1d|

**Subtotal**: 5-6d

### Phase 4 Total: 14.5-19 developer-days

-----

## Summary

|Phase|Scope|Estimate|Cumulative|Value delivered|Stop here?|
|-----|-----|--------|----------|---------------|----------|
|Phase 1|MCP Wrapper (Foundation)|28-35d|28-35d|noted becomes a remote MCP server - external clients connect and use all 38 tools|Yes - complete product|
|Phase 2|Resource Layer|20-23d|48-58d|Passive state reads + push notifications - LLM awareness without tool calls|Yes - enhanced product|
|Phase 3|Workflow Tool Surface (MCP only)|5.5-7.5d|53.5-65.5d|One-call multi-step workflows for external clients|Yes - skip if no DAG engine|
|Phase 3|Workflow Engine (if not built)|10-16d|63.5-81.5d|(Prerequisite for workflow tools)|N/A|
|Phase 4|Internal LLM Migration|14.5-19d|78-100.5d|Unified tool surface, token savings, zero dual-maintenance|Yes - optimization complete|

**Total: 68-84.5 developer-days** (with workflow engine: 78-100.5d)

**Each phase is independently shippable.** The plan is designed so you can stop after any phase and have a coherent, production-ready system. Phase 1 is the only mandatory investment - it unlocks external client access and the MCP protocol surface. Phases 2-4 are additive enhancements that can be prioritized, deferred, or skipped based on what noted needs at the time.

-----

## Recommended Execution Order

Phases 1 through 4 are sequential by design, but there is room for parallelism within and across phases:

**Critical path**: Phase 1 must complete first - everything else depends on the MCP server being functional.

**Parallel opportunities**:
- Phase 2 resource implementations (2.2) can be split across developers - each resource handler is independent
- Phase 3 workflow engine (3.1) can start in parallel with Phase 2 since it's backend-only work with no MCP dependency until 3.2
- Phase 4 Dynamic Context Router design (4.1) can start during Phase 2, since it only needs Phase 1's `tools/list`

**Recommended sequencing with two developers**:

```
Week 1-4:   Dev A: Phase 1.1-1.4 (SDK, tools, approval, rate limiting)
            Dev B: Phase 1.5-1.7 (client access, secrets, infrastructure)
Week 4:     Both: Phase 1.8 (testing)

Week 5-7:   Dev A: Phase 2.1-2.2 (resource framework + implementations)
            Dev B: Phase 3.1 (workflow engine prerequisite)
Week 7-8:   Dev A: Phase 2.3 (subscriptions)
            Dev B: Phase 3.2-3.3 (MCP workflow tools + testing)
Week 8:     Dev A: Phase 2.4 (resource testing)

Week 9-11:  Dev A: Phase 4.1-4.2 (Dynamic Context Router + prompt migration)
            Dev B: Phase 4.3-4.4 (skill integration + regression testing)
```

**With two developers: approximately 11 weeks.**
**With one developer: approximately 16-20 weeks.**

-----

## Parallel Development with MLOps Workflows

MCP development can run in parallel with the MLOps workflow effort (Airflow DAGs, MLflow pipelines, Evidently integration) with near-zero conflict.

**Why there is no conflict**:

|MCP Phase 1 touches|MLOps workflow effort touches|Overlap|
|-------------------|-----------------------------|-------|
|`backend/app/mcp/` (new package)|`airflow_manager.py`, `mlflow_manager.py`, `dvc_manager.py`|None|
|`llm_tools.py` (read only)|`llm_tools.py` (may add new tools)|Safe - see rule below|
|`nginx.conf` (new `/mcp/` block)|Not nginx|None|
|`Dockerfile` (one pip install line)|`Dockerfile` (possible new dependencies)|Minimal - additive lines|
|Frontend settings UI (new panel)|Frontend notebooks/editors|None|

**One coordination rule**: if the MLOps effort adds new tools to `TOOL_DESCRIPTIONS` in `llm_tools.py`, they must follow the existing schema format and classify themselves in `WRITE_TOOLS` if they alter environment state. No other coordination is required - the MCP wrapper reads from `TOOL_DESCRIPTIONS` dynamically, so new tools appear in `tools/list` automatically.

**Merge strategy**: MCP work lives in a dedicated branch. Since it creates a new package (`backend/app/mcp/`) and only adds to infrastructure files (nginx, Dockerfile), merge conflicts with the MLOps branch are limited to trivially resolvable additive changes.

-----

## Risk Register

|Risk|Impact|Mitigation|
|----|------|----------|
|`mcp` Python SDK Streamable HTTP transport has unexpected integration issues with FastAPI|Phase 1 delayed 3-5d|Evaluate SDK transport classes early (task 1.1.1); Streamable HTTP is the SDK's recommended path so issues are unlikely but test early|
|Dynamic Context Router misclassifies domains, causing LLM to miss tools|Phase 4 degraded UX|Retry loop (4.1.4) catches failures; keyword matching baseline is low-risk; can always fall back to broader domain sets|
|Airflow/MLflow callback hooks for push subscriptions are unreliable or high-latency|Phase 2 subscriptions flaky|Subscriptions are additive - polling via `resources/read` always works as fallback; push is a UX enhancement, not a correctness requirement|
|Workflow engine (Phase 3 prerequisite) takes longer than estimated|Phase 3 delayed|Phase 3 MCP surface (3.2) is decoupled - can be built with stubs and connected when engine is ready|
|Rate limiting in-memory bucket lost on process restart|Temporary burst after restart|Acceptable for Phase 1; if noted moves to multi-process, migrate to shared state (Redis)|
|External client auth (API keys) adds friction for adoption|Low external client usage|Read-only without key is frictionless; keys only needed for write access, which is a deliberate security gate|
|MCP server crash affects noted core functionality|noted downtime|Failure isolation: MCP router wrapped in try/except, one-directional dependency, feature toggle for instant disable (task 1.7.5-1.7.6)|
|MCP SDK breaking change on upgrade|Phase regression|SDK version pinned; upgrades require re-running Phase 1 acceptance gate (task 1.7.7)|
|Parallel MLOps development conflicts with MCP branch|Merge conflicts|MCP lives in new package with no shared file modifications; one coordination rule for new tools in llm_tools.py|

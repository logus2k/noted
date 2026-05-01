# noted — LLM Assistant Integration
## Architecture Patterns and Implementation Guide

*Version 1.0 | March 2026*

---

## 1. Introduction and Goals

noted already eliminates context-switching across the MLOps toolchain. The LLM assistant layer extends that philosophy into the reasoning domain: instead of opening a separate chat window, copying and pasting code, and manually cross-referencing MLflow run IDs, the practitioner stays inside noted while the assistant has direct, structured access to the live workspace state.

This document describes the patterns and concrete implementation recommendations for integrating a local LLM into noted. The integration targets three audiences of capability:

- **Notebook / code assistance** - completion, explanation, refactoring, and error diagnosis in the editor.
- **MLOps reasoning** - interpreting experiment results, suggesting next steps, comparing runs, and generating DAG or config fragments from intent.
- **Workflow automation** - executing multi-step operations (trigger a sweep, register the champion, update a Hydra template) through tool calls rather than manual UI navigation.

All LLM inference runs on-premises. No data leaves the host. The integration must work within the existing single-container Docker architecture and must not require frontend framework changes (noted uses vanilla ES6 modules).

---

## 2. Deployment Topology

The recommended topology adds one sidecar container to the existing noted compose stack. noted's FastAPI backend acts as the sole gateway - the browser never communicates with the LLM container directly, preserving the existing security posture where secrets remain server-side.

### 2.1 Recommended Model: Ollama

Ollama is the recommended local LLM runtime for this integration. It exposes an OpenAI-compatible REST API, supports CUDA via the NVIDIA Container Toolkit (which noted already uses), handles model management (pull, delete, list), and has first-class Docker support.

| Property | Value |
|---|---|
| Container name | noted-ollama |
| Base image | ollama/ollama:latest (or :rocm for AMD) |
| Port | 11434 (internal to Docker network only) |
| GPU passthrough | deploy.resources.reservations.devices (same pattern as noted GPU compose) |
| Model storage | Named Docker volume: ollama_data |
| Network | noted internal bridge network (not exposed externally) |

### 2.2 Recommended Models

The following models are well-suited to the noted use case. All are available via `ollama pull`. Model selection should be driven by available VRAM; the RTX 4090 (24 GB) can comfortably run any of these.

| Model | Size | VRAM (4-bit) | Strengths | Recommended For |
|---|---|---|---|---|
| qwen2.5-coder:32b | 32B | ~20 GB | Best code quality, Python/ML focus | Primary choice on 4090 |
| qwen2.5-coder:14b | 14B | ~10 GB | Strong code, faster responses | If 32B too slow in practice |
| deepseek-r1:14b | 14B | ~10 GB | Reasoning chains, MLOps analysis | Experiment interpretation |
| llama3.1:8b | 8B | ~6 GB | Fast, general-purpose | Lightweight deployments |
| codestral:22b | 22B | ~14 GB | Code-first, multilingual | Mixed code/text workloads |

For the noted RTX 4090 deployment, **qwen2.5-coder:32b** is the primary recommendation. It delivers frontier-level Python and ML code quality and fits comfortably in 24 GB at Q4_K_M quantization.

### 2.3 Docker Compose Addition

Add the following service to the existing noted compose file. The GPU stanza mirrors the pattern already used in `docker-compose.gpu.yml`:

```yaml
  noted-ollama:
    image: ollama/ollama:latest
    container_name: noted-ollama
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - noted-net
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=2
```

Add `ollama_data: {}` to the top-level volumes block. `OLLAMA_KEEP_ALIVE=24h` prevents the model from being evicted between requests. `OLLAMA_NUM_PARALLEL=2` allows one streaming response and one background request to coexist.

### 2.4 Backend Configuration

Add the Ollama base URL to noted's environment or settings manager:

```env
OLLAMA_BASE_URL=http://noted-ollama:11434
OLLAMA_DEFAULT_MODEL=qwen2.5-coder:32b
OLLAMA_CONTEXT_WINDOW=8192
```

---

## 3. Backend Integration Layer

All LLM interaction is mediated by a new manager service inside the noted FastAPI backend, following the existing pattern of dedicated manager classes (KernelManager, MLflowManager, etc.). The manager is responsible for prompt construction, context assembly, tool routing, and streaming response relay.

### 3.1 LLMManager Service

Create `backend/app/services/llm_manager.py`. The manager holds an `httpx.AsyncClient` pointed at Ollama and exposes methods consumed by the API route layer:

```python
class LLMManager:
    def __init__(self, base_url: str, default_model: str):
        self.base_url = base_url
        self.default_model = default_model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat_stream(self, messages, model=None, tools=None) -> AsyncIterator[str]:
        # POST to /api/chat with stream=True
        # Yield SSE chunks as they arrive
        ...

    async def health(self) -> dict:
        # GET /api/tags - returns available models
        ...

    async def pull_model(self, model: str) -> AsyncIterator[str]:
        # POST /api/pull with stream=True
        # Yields progress events for the UI
        ...
```

### 3.2 API Routes

Add a new route module at `backend/app/api/llm.py` with the following endpoints. These mirror the pattern of existing route modules (airflow.py, mlflow.py):

| Method | Path | Description |
|---|---|---|
| POST | /api/llm/chat | Main chat endpoint. Accepts messages + context descriptor. Streams SSE. |
| POST | /api/llm/complete | Single-turn code completion. Returns JSON (no streaming). |
| GET | /api/llm/models | List available Ollama models. |
| POST | /api/llm/models/pull | Pull a model from Ollama registry. Streams progress. |
| GET | /api/llm/health | Ollama connectivity and loaded model status. |
| POST | /api/llm/tools/dispatch | Execute a tool call returned by the LLM. |

The `/api/llm/chat` endpoint accepts a `context_descriptor` object alongside the message array. This descriptor is resolved server-side into concrete context before the messages are forwarded to Ollama, so the frontend never needs to know how to fetch MLflow run details, Hydra config hashes, or kernel state.

### 3.3 Context Assembly

The most important design decision in the integration is how workspace context is assembled into the system prompt. The pattern that works best for MLOps assistants is layered context injection: a stable base system prompt is supplemented with dynamic, request-specific context blocks that are assembled at request time.

#### 3.3.1 System Prompt Structure

The system prompt is assembled from ordered blocks. Blocks that are not relevant to the current interaction are omitted to keep the context window focused:

```python
def build_system_prompt(ctx: ContextDescriptor) -> str:
    blocks = []
    blocks.append(PERSONA_BLOCK)          # Always included
    blocks.append(TOOLS_SCHEMA_BLOCK)      # Always included
    if ctx.notebook_path:
        blocks.append(notebook_block(ctx)) # Active notebook cells
    if ctx.active_run_id:
        blocks.append(run_block(ctx))      # MLflow run metrics/params
    if ctx.hydra_config_hash:
        blocks.append(config_block(ctx))   # Resolved Hydra config YAML
    if ctx.dvc_hash:
        blocks.append(data_block(ctx))     # DVC tracked file metadata
    if ctx.dag_id:
        blocks.append(dag_block(ctx))      # Airflow DAG structure
    if ctx.selected_cell_source:
        blocks.append(cell_block(ctx))     # Currently selected cell
    return '\n\n'.join(blocks)
```

#### 3.3.2 Notebook Context Block

The notebook context block passes the currently open notebook cells to the LLM. To stay within context window limits, apply a cell selection strategy rather than passing all cells unconditionally:

- **Always include**: the currently selected cell and the cell immediately preceding it.
- **Include if present**: any cell with a non-empty output or error in its last execution.
- **Truncate**: cell outputs longer than 2000 characters are truncated with a note.
- **Cap**: maximum 20 cells total regardless of notebook size.

Pass cells as a compact JSON array rather than reconstructed Python source. This preserves cell boundaries and output metadata that help the LLM understand execution state:

```
NOTEBOOK CONTEXT:
File: /projects/jena_weather/training.ipynb
Kernel: Python 3.12 (venv: jena_weather_env) [IDLE]
Active MLflow run: run_abc123 (experiment: jena_weather_lstm)

[Cell 3 - code]
model = LSTMForecaster(cfg.model)
trainer = pl.Trainer(max_epochs=cfg.training.max_epochs)

[Cell 4 - code - SELECTED]
trainer.fit(model, datamodule=dm)

[Cell 4 - output]
Epoch 12/50: train_loss=0.0823, val_loss=0.0941
...(truncated, 48 more lines)
```

#### 3.3.3 MLflow Context Block

When the notebook has an active MLflow run or the user has selected a run in the Explorer, inject a structured summary of that run. Fetch this from MLflowManager rather than re-querying MLflow directly:

```
ACTIVE MLFLOW RUN:
Run ID: run_abc123  |  Status: RUNNING
Experiment: jena_weather_lstm
Params: lr=0.001, hidden=128, layers=2, dropout=0.2
Latest metrics: train_loss=0.0823, val_loss=0.0941, epoch=12
Tags: hydra_config_hash=a3f9..., dvc_data_hash=7c2b...
```

#### 3.3.4 Persona Block

The persona block establishes the assistant's role, tone, and constraints. Keep it concise - verbose personas reduce the effective context for actual workspace data:

```
You are an expert ML engineer and MLOps assistant embedded in 'noted',
an on-premises collaborative notebook and MLOps platform.

You have access to the user's live workspace: open notebooks, active
MLflow runs, Hydra configurations, DVC data versions, and Airflow DAGs.
When the workspace context is provided above, always ground your answers
in that specific state rather than giving generic advice.

You can call tools to read additional workspace state or to take actions.
Always explain what you are about to do before calling a tool.
Prefer minimal, surgical code edits over full rewrites.
Format code in Python unless another language is explicitly requested.
When suggesting experiments, relate them to the current MLflow run.
```

---

## 4. Streaming and Real-time Delivery

LLM responses must stream token-by-token to avoid the appearance of a frozen UI during long generations. noted already uses Socket.IO for real-time events (live metrics, kernel output, pipeline status). The same infrastructure can carry LLM token streams.

### 4.1 Streaming via Socket.IO

The recommended approach is to relay the Ollama token stream through the existing Socket.IO connection rather than adding a separate SSE endpoint. This avoids connection multiplicity on the client and re-uses the existing event infrastructure.

Define two new Socket.IO events:

| Event | Direction | Payload |
|---|---|---|
| llm:token | server -> client | { request_id, token } |
| llm:done | server -> client | { request_id, finish_reason, tool_calls? } |
| llm:error | server -> client | { request_id, message } |
| llm:chat | client -> server | { request_id, messages, context_descriptor } |

The backend Socket.IO handler for `llm:chat` spawns an asyncio task that calls `LLMManager.chat_stream()` and emits `llm:token` events for each chunk. The `request_id` (a UUID generated client-side) lets the frontend route tokens to the correct chat session when multiple tabs are open.

### 4.2 Chat Panel Frontend

The existing chat panel (referenced in the README as "built-in chat panel connected to an external LLM agent") becomes the primary surface. The recommended changes are minimal and additive:

- Replace the external LLM endpoint call with a Socket.IO `llm:chat` emission.
- Add a `context_descriptor` builder that reads current state from the notebook editor, Explorer selection, and kernel manager.
- Render incoming `llm:token` events by appending to the assistant message buffer and re-rendering the message via the existing markdown renderer (marked.js).
- Handle `llm:done` with `tool_calls` by rendering a tool-call confirmation widget before dispatching.

### 4.3 Context Descriptor Construction (Frontend)

The frontend constructs the `context_descriptor` by reading state from already-available module references. No new API calls are required at request time:

```javascript
function buildContextDescriptor() {
  const nb = NotebookEditor.getActive();
  return {
    notebook_path:       nb?.path ?? null,
    selected_cell_index: nb?.selectedCellIndex ?? null,
    active_run_id:       nb?.metadata?.active_run_id ?? null,
    hydra_config_hash:   nb?.metadata?.hydra_config_hash ?? null,
    dvc_hash:            nb?.metadata?.last_dvc_hash ?? null,
    dag_id:              ExplorerPanel.getSelectedDagId() ?? null,
    explorer_selection:  ExplorerPanel.getSelection() ?? null,
  };
}
```

---

## 5. Tool Calling (Function Calling)

Tool calling is the mechanism by which the LLM can take actions inside noted rather than merely describing what to do. Modern instruction-tuned models (including qwen2.5-coder and llama3.1) support OpenAI-compatible function calling syntax, which Ollama passes through.

The tool set should be designed around two principles: read tools are always safe to execute automatically; write tools require user confirmation before execution. This mirrors the conservative default used in agentic systems.

### 5.1 Read Tools (Auto-execute)

| Tool Name | Description | Parameters |
|---|---|---|
| get_run_details | Fetch full metrics, params, and tags for an MLflow run | run_id |
| get_experiment_runs | List runs in an experiment with summary metrics | experiment_name, limit, sort_by |
| compare_runs | Return a diff table of two runs | run_id_a, run_id_b |
| get_resolved_config | Return the fully resolved Hydra config for a given hash | config_hash |
| get_dag_structure | Return task graph and latest run status for a DAG | dag_id |
| get_file_contents | Read a project file (notebooks excluded by default) | path, max_lines |
| get_dvc_history | Return version history for a DVC-tracked file | path |
| get_model_lineage | Return the full lineage chain for a registered model version | model_name, version |
| search_knowledge_graph | Query the noted Knowledge Graph for entities matching a pattern | query, perspective |

### 5.2 Write Tools (Require User Confirmation)

| Tool Name | Description | Parameters |
|---|---|---|
| insert_cell | Insert a new code or markdown cell into the active notebook | content, cell_type, position |
| replace_cell_source | Replace the source of a specific cell | cell_index, new_source |
| trigger_dag | Trigger an Airflow DAG run with given parameters | dag_id, conf |
| register_model | Register a model version from an MLflow run | run_id, artifact_path, model_name |
| save_config_template | Save a named Hydra config template | name, config_hash, overrides |
| promote_best_config | Promote the best run's config as a named template | experiment_name, metric, mode |
| create_git_commit | Stage and commit current changes | message |

### 5.3 Tool Schema Format

Tools are passed to Ollama in the OpenAI-compatible `tools` array. Define them in a central schema module (`llm_tools.py`) and inject them into every chat request:

```python
GET_RUN_DETAILS_TOOL = {
    'type': 'function',
    'function': {
        'name': 'get_run_details',
        'description': 'Fetch complete metrics, parameters, and tags for an MLflow run.',
        'parameters': {
            'type': 'object',
            'properties': {
                'run_id': {
                    'type': 'string',
                    'description': 'The MLflow run ID'
                }
            },
            'required': ['run_id']
        }
    }
}
```

### 5.4 Tool Dispatch Flow

When the LLM returns a `tool_calls` block in the `llm:done` event, the frontend renders a confirmation widget for write tools or auto-dispatches read tools. After execution, the tool result is appended to the conversation history as a tool message and another chat turn is initiated to let the LLM incorporate the result:

```javascript
// Frontend tool dispatch pattern
socket.on('llm:done', async ({ request_id, tool_calls }) => {
  if (!tool_calls?.length) return;
  for (const call of tool_calls) {
    const isWrite = WRITE_TOOLS.has(call.function.name);
    if (isWrite) {
      const confirmed = await showConfirmation(call);
      if (!confirmed) continue;
    }
    const result = await fetch('/api/llm/tools/dispatch', {
      method: 'POST',
      body: JSON.stringify({ tool_call: call }),
    }).then(r => r.json());
    // Append tool result to conversation and continue
    appendToolResult(call.id, result);
    continueChatWithToolResult();
  }
});
```

---

## 6. MLOps-Specific Integration Points

These are the integration points that make noted's LLM assistant materially more useful than a generic code chat tool. Each connects an existing noted capability to the assistant through context injection or tool calls.

### 6.1 Experiment Interpretation

When the user opens a run detail panel or selects an experiment in the Explorer, inject the run's full metrics history, parameters, and tags into the context. The assistant can then answer questions like "why did validation loss spike at epoch 14?" or "which hyperparameter change had the most impact?" by reasoning over the actual data rather than generic ML advice.

Implementation: add an "Ask Assistant" button to the run detail panel. Clicking it pre-populates the chat with the selected run's `context_descriptor` and a default prompt inviting the user to ask about the run.

### 6.2 Run Comparison Summaries

The existing run comparison panel shows a diff table. Augment it with an "Explain Difference" button that sends both run IDs to the assistant with the prompt: "Summarize the key differences between these two runs and what likely caused the change in validation performance." The assistant can use the `compare_runs` tool to fetch detailed data if it needs more than what is in the context.

### 6.3 Sweep Analysis

After a Hydra sweep completes (all Airflow DAG runs finish), the assistant can automatically receive a post-sweep summary notification and respond with an analysis of the parameter space, identifying which dimensions mattered most and suggesting the next sweep range. This requires:

- A `sweep_complete` event emitted by the pipeline monitor (already has Socket.IO polling).
- A backend handler that fetches all sweep run results and constructs a compact summary table.
- An LLM call with that table injected and the prompt "Analyze this sweep and recommend the next step."
- The response streamed into a collapsible "Sweep Analysis" section in the sweep UI.

### 6.4 DAG Generation from Notebook

The existing "Export as Pipeline Task" feature converts notebook cells to DAG tasks. The LLM can improve this by inferring task boundaries, dependencies, and operator types from cell content. Add a "Generate DAG" option to the notebook bar that sends the full notebook cell list and asks the LLM to produce a valid Airflow 3.0 DAG using the `insert_cell` or file write tools.

### 6.5 Config Recommendation

When a user asks "what should I try next?", the assistant has access via context and tools to: the current Hydra config hash, the full run history for the experiment, and the DVC data hash. It can cross-reference all three to suggest a specific configuration change grounded in what has and has not been tried, rather than generic advice.

### 6.6 Error Diagnosis in Task Logs

The existing task log viewer highlights error lines and allows clipboard copy. Add an "Explain Error" button that sends the error block to the assistant with the DAG structure as context. The assistant can identify whether the error is a Python import issue, a data shape mismatch, an Airflow operator misconfiguration, or a resource constraint.

### 6.7 Automated Model Card Generation (Phase 5 Feature)

Phase 5 plans automated model cards (T-5.2). The LLM is the natural engine for this: pass the model lineage chain (Data -> Config -> Code -> Run -> Model), the best run's metrics, and the registered model's alias, and prompt the LLM to generate a structured model card in Markdown. The existing DocumentConverter pipeline can then render it to Word.

---

## 7. Inline Code Assistance in the Editor

Beyond the chat panel, the LLM can assist directly in the CodeMirror 6 editor. Two modes are recommended, in order of implementation complexity:

### 7.1 On-Demand Cell Explanation and Refactor

The simplest integration: a context menu item on code cells ("Explain", "Refactor", "Add type hints", "Write docstring"). Each sends the selected cell source to the chat panel with a pre-formed prompt, using the standard chat path. This requires zero changes to CodeMirror and leverages the existing chat infrastructure.

### 7.2 Ghost-Text Completion

Inline ghost-text completion (similar to GitHub Copilot) is more invasive but significantly improves the editing experience. The implementation requires a CodeMirror 6 extension. The key decisions are:

| Property | Decision |
|---|---|
| Trigger | Debounced (800ms) on cursor idle, or explicit Ctrl+Space. Never on every keystroke. |
| Context sent | Current cell source up to cursor position + preceding cell sources (capped at 1500 tokens). |
| Model for completion | A smaller, faster model (llama3.1:8b or qwen2.5-coder:7b) to minimize latency. |
| Rendering | CodeMirror 6 ViewPlugin + Decoration.widget with ghost-text CSS styling. |
| Acceptance | Tab key accepts the full suggestion; right arrow accepts one token. |
| Cancellation | Any keypress other than Tab/arrow dismisses the ghost text. |
| Abort | Each new completion request aborts the previous in-flight request via AbortController. |

The completion endpoint (`/api/llm/complete`) uses Ollama's `/api/generate` (not `/api/chat`) with `raw=true` and stop sequences set to the next logical token boundaries (`["\n\n", "` ``` `"]`). This avoids the overhead of chat-format message construction for short completions.

### 7.3 ML-Aware Completion Context

Standard completion only sees the text buffer. Because noted has live kernel state, the completion context can be enriched with variable names and types from the kernel's namespace. Add a kernel introspection call before each completion request:

```python
# Backend: inject kernel namespace summary into completion context
async def get_kernel_namespace_summary(kernel_id: str) -> str:
    result = await kernel_manager.execute_silent(
        kernel_id,
        'import json; print(json.dumps({k: type(v).__name__ for k,v in locals().items()}))'
    )
    return f'# Available variables: {result}'
```

Prepend this summary as a comment to the completion prompt. The LLM will then complete using the actual variable names and types in scope rather than guessing.

---

## 8. Conversation Memory and Session Management

LLMs are stateless between requests. Conversation history must be maintained client-side and sent with each turn. The following session management strategy is recommended for noted:

### 8.1 Per-Notebook Sessions

Each open notebook tab maintains its own conversation session. The session is a flat array of message objects that accumulates over the notebook's lifetime. Sessions are stored in notebook metadata (the existing pattern for persisting per-notebook state) and survive page reloads.

| Property | Value |
|---|---|
| Session key | notebook.metadata.llm_session |
| Structure | Array of { role, content, tool_calls?, timestamp } objects |
| Max session length | Trim to last 20 messages when exceeding 40 to prevent context overflow |
| Cross-notebook | The global chat panel (non-notebook mode) uses a separate global_llm_session |

### 8.2 Context Refresh on Each Turn

On every new chat turn, the workspace context (notebook cells, active run, config hash) is re-assembled from live state. This means the LLM always has current information even if the user edited cells or started a new run between turns. The conversation history carries the dialogue; the system prompt carries the current workspace snapshot.

### 8.3 Explicit Context Commands

Users should be able to steer context explicitly. Support the following slash commands in the chat input:

| Command | Effect |
|---|---|
| /clear | Clear conversation history for the current session. |
| /context | Show the current context descriptor as JSON (debug aid). |
| /run \<run_id\> | Pin a specific MLflow run into the context regardless of notebook state. |
| /dag \<dag_id\> | Pin a specific DAG into the context. |
| /file \<path\> | Include a specific file's contents in the next turn. |
| /model \<model_name\> | Switch the active Ollama model for this session. |

---

## 9. Security and Privacy

All LLM inference runs locally. No user data, code, or model artifacts leave the Docker network. The following additional security controls are recommended:

### 9.1 Authentication

The `/api/llm/*` routes must be protected by the same access-key authentication used by noted's terminal endpoint. The LLM backend manager should never be accessible from outside the noted container.

### 9.2 File Access Scope

The `get_file_contents` tool must enforce path restrictions identical to noted's existing file API: only paths within mounted project directories are accessible. Absolute paths outside the project scope must be rejected.

### 9.3 Write Tool Confirmation

All write tools require explicit user confirmation before execution. The confirmation widget must display the full tool call parameters (not a summary) so the user can verify exactly what action will be taken.

### 9.4 Notebook Content in Context

Cell outputs can contain sensitive data (model weights, API responses, database query results). The cell truncation strategy (Section 3.3.2) limits exposure. An optional per-notebook setting `include_outputs_in_llm_context` (default: true) should allow users to disable output injection.

### 9.5 Model Pull Authorization

The `/api/llm/models/pull` endpoint should require the same access key as terminal access. Pulling large models (20+ GB) is a significant operation and should not be triggerable by unauthenticated requests.

---

## 10. Phased Implementation Roadmap

The following sequence minimizes risk by establishing the infrastructure first and adding capabilities incrementally. Each phase is independently useful and does not require subsequent phases to deliver value.

### Phase A: Infrastructure (1-2 days)

This phase establishes the foundation without touching any existing noted code.

- Add noted-ollama to `docker-compose.yml` and `docker-compose.gpu.yml`.
- Pull qwen2.5-coder:32b and llama3.1:8b on first startup via an init script or entrypoint.
- Create LLMManager with health check, `chat_stream`, and `complete` methods.
- Register `/api/llm/health` and `/api/llm/models` routes.
- Verify Ollama connectivity from the noted container via `docker exec`.

### Phase B: Chat Panel Rewire (2-3 days)

Connect the existing chat panel to the local LLM, replacing any external endpoint.

- Implement `llm:chat` Socket.IO event handler in the backend.
- Update the chat panel frontend to emit `llm:chat` and handle `llm:token` / `llm:done` events.
- Implement `context_descriptor` construction in the frontend.
- Implement system prompt assembly with notebook and MLflow context blocks.
- Validate end-to-end: open a notebook, run a cell, ask a question about the output.

### Phase C: Read Tools (2-3 days)

Enable the LLM to query workspace state autonomously.

- Define tool schemas for all read tools in `llm_tools.py`.
- Implement `/api/llm/tools/dispatch` with read-only tool handlers.
- Add frontend auto-dispatch logic for read tool calls.
- Test: "What are the metrics for run abc123?" with no run in context - LLM should call `get_run_details`.

### Phase D: MLOps Integrations (3-4 days)

Add the MLOps-specific UI integration points.

- "Ask Assistant" button on run detail panels.
- "Explain Difference" button on run comparison panel.
- "Explain Error" button in task log viewer.
- Post-sweep analysis notification handler.

### Phase E: Write Tools (2-3 days)

Add write tool capability with user confirmation.

- Implement confirmation widget in the chat panel.
- Implement write tool handlers: `insert_cell`, `replace_cell_source`, `trigger_dag`.
- Add `WRITE_TOOLS` set to frontend for confirmation routing.
- Test: "Create a new cell that plots the loss curve from the current run."

### Phase F: Inline Completion (3-5 days)

Implement ghost-text code completion in the CodeMirror editor.

- Implement `/api/llm/complete` endpoint using Ollama `/api/generate`.
- Implement CodeMirror 6 ViewPlugin for ghost-text rendering.
- Add debounced trigger on cursor idle.
- Add kernel namespace introspection for ML-aware context.
- Tune stop sequences and context length for sub-second latency.

---

## 11. Configuration Reference

The following environment variables should be added to noted's configuration, alongside the existing `MLFLOW_TRACKING_URI`, `AIRFLOW_BASE_URL`, and MinIO credentials:

| Variable | Default | Description |
|---|---|---|
| OLLAMA_BASE_URL | http://noted-ollama:11434 | Ollama API base URL |
| OLLAMA_CHAT_MODEL | qwen2.5-coder:32b | Default model for chat and MLOps reasoning |
| OLLAMA_COMPLETE_MODEL | qwen2.5-coder:7b | Model for inline completion (latency-optimized) |
| OLLAMA_CONTEXT_WINDOW | 8192 | Context window size in tokens |
| OLLAMA_MAX_NOTEBOOK_CELLS | 20 | Max cells included in notebook context |
| OLLAMA_MAX_OUTPUT_CHARS | 2000 | Max cell output characters before truncation |
| OLLAMA_KEEP_ALIVE | 24h | Model keep-alive duration in Ollama |
| OLLAMA_COMPLETION_DELAY | 800 | Milliseconds idle before ghost-text trigger |
| LLM_WRITE_TOOLS_ENABLED | true | Enable write tool calls (set false to disable) |

---

## 12. Summary

The architecture described in this document achieves LLM assistance that is contextually grounded in live workspace state, rather than a generic chat overlay. The key principles are:

1. **Sidecar, not invasive**: Ollama runs as a separate container. noted's backend remains the single gateway. No new external dependencies are introduced into the main container.

2. **Context is assembled server-side**: The frontend sends a lightweight descriptor; the backend resolves it into concrete MLflow metrics, Hydra configs, and DVC metadata. The LLM receives workspace reality, not stale descriptions.

3. **Tools extend reach**: Read tools let the LLM autonomously fetch run details, compare experiments, and traverse the knowledge graph. Write tools let it act on the workspace with user confirmation.

4. **Phased delivery**: Each phase delivers independently useful capability. Phase A-B alone (infrastructure + rewired chat) is a meaningful improvement over an external LLM connection.

5. **Zero framework changes**: The frontend integration uses Socket.IO events and fetch calls consistent with existing patterns. No build tooling, no new frontend dependencies beyond the CodeMirror extension in Phase F.

The resulting assistant understands the practitioner's actual experiment, their current Hydra configuration, the data version in use, and the pipeline structure - and can act on all of them without context-switching. This closes the loop that noted set out to close: from raw data to deployed model, inside one application, with an AI collaborator that knows the workspace as well as the practitioner does.

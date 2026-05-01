# Local LLM Integration Plan for noted

*Consolidated from 8 LLM consultations, grounded in noted's actual codebase and agent_server.*

---

## 1. Design Principles

- **Reuse agent_server**: noted already has a production llama.cpp inference server with Socket.IO streaming, OpenAI-compatible REST, agent presets, conversation memory, and STT/TTS. No new inference container needed.
- **Context assembled server-side**: The frontend sends a lightweight descriptor; noted's FastAPI backend resolves it into concrete MLflow metrics, Hydra configs, DVC metadata, and notebook cells, then forwards the enriched prompt to agent_server.
- **Manager pattern**: A new `LLMManager` in `backend/app/managers/` follows the same pattern as `KernelManagerService`, `MLflowManager`, etc. It talks to agent_server's `/v1/chat/completions` endpoint.
- **Minimal frontend changes**: `ChatService.js` already connects to agent_server via `AgentClient.js`. The rewire is adding context injection, not replacing the transport.
- **Zero vendor lock-in**: agent_server exposes an OpenAI-compatible API. If the inference backend changes later, only `LLM_BASE_URL` changes.

---

## 2. Deployment Topology

### 2.1 Current State

agent_server already runs as a Docker container on `logus2k_network` (port 7701) with GPU passthrough. noted's frontend connects to it via `https://logus2k.com/llm` using the `docbro` agent preset.

```
Browser  -->  noted (8123)  -->  [no context injection today]
   |
   +------->  agent_server (7701) via logus2k.com/llm  (direct Socket.IO)
```

### 2.2 Target State

noted's backend becomes the context orchestrator. The frontend still uses `AgentClient.js` for streaming, but chat requests now route through noted's backend first for context enrichment before reaching agent_server.

```
Browser  -->  noted (8123)
                |
                +--> LLMManager --> agent_server (7701) /v1/chat/completions
                |                   (context-enriched prompts)
                |
                +--> AgentClient.js (Socket.IO direct for streaming)
                     (lightweight chat, STT/TTS - unchanged)
```

Two integration paths coexist:

- **Context-enriched chat**: Frontend calls noted's `/api/llm/chat` (REST/SSE). noted assembles context, calls agent_server's `/v1/chat/completions` with streaming, and relays SSE tokens back. Used for MLOps-aware queries.
- **Lightweight chat**: Frontend continues using `AgentClient.js` directly for simple questions, STT/TTS. No change needed.

### 2.3 Concurrency Model

agent_server uses a **worker pool** (`pool_size` in `agent_config.json`). Each worker is an independent llama.cpp `Llama()` instance loaded into VRAM. With `pool_size: 1` (current default), there is one model copy in memory and requests are serialized - while one user's tokens are generating, other LLM requests queue in an `asyncio.Queue` and wait their turn.

Importantly:
- **Per-user state is separate from the engine.** Each connected client gets its own `SessionState` (conversation history, cancellation token, async lock). Multiple users can be connected simultaneously - they just share the inference engine sequentially.
- **Non-LLM operations are unaffected.** The engine runs on a thread pool executor (`run_in_executor`), so noted's event loop stays responsive. Notebook saves, kernel execution, file operations - none of these block while the LLM generates.
- **For 4-5 users doing ML work** (intermittent, bursty LLM questions), `pool_size: 1` is adequate. The odds of two people hitting "send" in the same 10-15 second generation window are low in practice.
- **Scaling option**: Increasing `pool_size` loads additional full model copies into VRAM (e.g., `pool_size: 2` with Qwen 3.5 9B Q6_K = ~18 GB, fits on a 4090). This allows truly parallel generation for two users simultaneously. Only needed if concurrent usage becomes a bottleneck.
- **Phase E caution**: Auto-triggered inline completion (every 800ms per active user) is the real concurrency multiplier. If 4 users have auto-complete firing, it would saturate the queue. Recommendation: make Phase E opt-in (Ctrl+Space only) or defer until concurrency is validated.

### 2.4 Network Connectivity

agent_server needs to be reachable from the noted container. Two options:

- **Option A**: Add agent_server to `noted-network` (second network in its compose) - cleanest
- **Option B**: Use the host-exposed port (`localhost:7701`) from noted container with `network_mode` or `extra_hosts`

Option A is preferred. Add to agent_server's `docker-compose.yml`:

```yaml
networks:
  - logus2k_network
  - noted-network

networks:
  noted-network:
    external: true
```

### 2.5 Agent Preset for noted

Add a new `noted.agent.json` preset in agent_server's `data/agents/`:

```json
{
  "name": "noted",
  "system_prompt": "noted_system_prompt.txt",
  "params_override": {
    "temperature": 0.5,
    "max_tokens": 2048
  },
  "memory_policy": "thread_window"
}
```

The system prompt file contains the persona block (see Section 3.3). Context blocks are prepended dynamically by noted's backend before each request.

### 2.6 Backend Configuration

Add to noted's environment:

```env
LLM_BASE_URL=http://agent_server:7701
LLM_AGENT_NAME=noted
LLM_CONTEXT_WINDOW=16384
```

**Context window**: Set `n_ctx: 16384` in agent_server's `agent_config.json` (up from the default 8192). With Qwen 3.5 9B Q6_K using ~9 GB for weights, bumping to 16K adds ~1-2 GB for KV cache - well within the RTX 4090's 24 GB budget.

**Token budget** with 16K context and `max_tokens: 2048` reserved for the response:

| Component | Typical size | Notes |
|---|---|---|
| System prompt (persona) | ~150 tokens | Fixed, small |
| Notebook context (3-5 cells + outputs) | 800-2000 tokens | Cell selection heuristics limit this |
| MLflow run block | 100-200 tokens | Params + metrics summary |
| Hydra config block | 200-400 tokens | Resolved YAML |
| DVC/DAG blocks | 100-300 tokens | Only if relevant |
| Conversation history (6-8 turns) | 2000-4000 tokens | Rolling window |
| Current question | 50-200 tokens | |
| **Total input** | **~3400-7250** | Comfortably under ~14K input budget |
| **Response budget** | 2048 tokens | max_tokens setting |

This gives generous headroom for multi-turn conversations with rich workspace context. Even with all context blocks active and 8 turns of history, the total stays well within budget.

### 2.7 Thinking Mode Strategy

Qwen 3 supports `/think` and `/no_think` directives in system or user messages. The model wraps its reasoning in `<think>...</think>` tags before producing the final answer.

**Where to use each mode:**

| Use case | Mode | Rationale |
|---|---|---|
| Context-enriched chat (Phase B) | `/think` | MLOps reasoning benefits from chain-of-thought (why is val_loss diverging, compare runs, suggest next experiment) |
| Tool calling decisions (Phase C) | `/think` | Model needs to reason about which tool to call and with what parameters |
| MLOps UI buttons (Phase D) | `/think` | "Explain Error", "Explain Difference" are analytical tasks |
| Inline code completion (Phase E) | `/no_think` | Speed is critical, direct code output only |

**Implementation:**

- The `noted` agent system prompt includes `/think` by default (already set in `noted_system_prompt.txt`)
- The `/api/llm/complete` endpoint (Phase E) prepends `/no_think` to its system prompt
- Users can override per-message by typing `/think` or `/no_think` in the chat input - Qwen 3 follows the most recent directive

**Frontend handling of `<think>` blocks:**

The streamed response will contain `<think>...</think>` tags. The frontend needs to handle these during rendering:

1. **During streaming**: Detect `<think>` opening tag, buffer thinking tokens separately, show a "Reasoning..." indicator
2. **On `</think>` close**: Hide the indicator, begin rendering the final answer
3. **After completion**: Render the thinking content in a collapsible "Show reasoning" section above the answer (collapsed by default)
4. **In conversation history**: When sending history back to the model, strip `<think>` blocks from previous assistant messages (per Qwen 3 best practices - no thinking content in history)

```javascript
// Thinking mode state machine for streaming
class ThinkingParser {
    constructor() {
        this.inThinking = false;
        this.thinkingBuffer = '';
        this.answerBuffer = '';
    }

    processToken(token) {
        if (token.includes('<think>')) {
            this.inThinking = true;
            // Handle partial tag at boundary
            const after = token.split('<think>')[1] || '';
            this.thinkingBuffer += after;
            return { type: 'thinking_start' };
        }
        if (token.includes('</think>')) {
            this.inThinking = false;
            const before = token.split('</think>')[0] || '';
            this.thinkingBuffer += before;
            const after = token.split('</think>')[1] || '';
            if (after) this.answerBuffer += after;
            return { type: 'thinking_end', thinking: this.thinkingBuffer, answer: after };
        }
        if (this.inThinking) {
            this.thinkingBuffer += token;
            return { type: 'thinking_token', token };
        }
        this.answerBuffer += token;
        return { type: 'answer_token', token };
    }
}
```

**Stripping thinking from history** (in noted's backend before sending to agent_server):

```python
import re

def strip_thinking(content: str) -> str:
    """Remove <think>...</think> blocks from assistant messages in history."""
    return re.sub(r'<think>[\s\S]*?</think>\s*', '', content).strip()
```

---

## 3. Backend Integration

### 3.1 LLMManager

Create `backend/app/managers/llm_manager.py`. Talks to agent_server's OpenAI-compatible `/v1/chat/completions` endpoint via `httpx`.

```python
class LLMManager:
    def __init__(self, base_url: str, agent_name: str):
        self.base_url = base_url
        self.agent_name = agent_name
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat_stream(self, messages, temperature=0.5, max_tokens=2048):
        """POST /v1/chat/completions with stream=True. Yields SSE chunks."""
        async with self.client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.agent_name,
                "messages": messages,
                "stream": True,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    yield json.loads(line[6:])

    async def chat(self, messages, temperature=0.5, max_tokens=2048):
        """POST /v1/chat/completions without streaming. Returns full response."""
        resp = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.agent_name,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return resp.json()

    async def complete(self, prompt, max_tokens=256):
        """Code completion via chat with /no_think for fast direct output."""
        messages = [
            {"role": "system", "content": "Complete the following code. Output only code, no explanation. /no_think"},
            {"role": "user", "content": prompt},
        ]
        return await self.chat(messages, temperature=0.7, max_tokens=max_tokens)

    async def health(self):
        """GET /v1/models - verify agent_server is reachable."""
        resp = await self.client.get(f"{self.base_url}/v1/models")
        return resp.json()
```

Initialized in `main.py`:

```python
llm_mgr = LLMManager(
    base_url=os.getenv("LLM_BASE_URL", "http://agent_server:7701"),
    agent_name=os.getenv("LLM_AGENT_NAME", "noted"),
)
```

### 3.2 API Routes

Add `backend/app/routers/llm.py`:

| Method | Path | Description |
|---|---|---|
| POST | /api/llm/chat | Context-enriched chat. Streams SSE back to frontend. |
| POST | /api/llm/complete | Single-turn code completion, returns JSON. |
| GET | /api/llm/health | agent_server connectivity + model status. |
| POST | /api/llm/tools/dispatch | Execute a tool call returned by the LLM. |

No `/api/llm/models/pull` needed - model management stays in agent_server's `agent_config.json`.

### 3.3 Context Assembly

The core value-add. noted's backend enriches prompts with workspace state before forwarding to agent_server.

#### System Prompt (in agent_server's noted_system_prompt.txt)

```
You are an expert ML engineer and MLOps assistant embedded in 'noted',
an on-premises collaborative notebook and MLOps platform.

You have access to the user's live workspace: open notebooks, active
MLflow runs, Hydra configurations, DVC data versions, and Airflow DAGs.
When workspace context is provided, always ground your answers in that
specific state rather than giving generic advice.

Prefer minimal, surgical code edits over full rewrites.
Format code in Python unless another language is explicitly requested.
When suggesting experiments, relate them to the current MLflow run.
```

#### Dynamic Context Blocks (prepended by noted's backend)

Assembled in `backend/app/managers/llm_context.py` from a lightweight `context_descriptor`:

```python
async def build_context_message(ctx, mlflow_mgr, hydra_mgr, dvc_mgr, airflow_mgr):
    """Build a context block injected as the first user message."""
    blocks = []
    if ctx.get("notebook_path"):
        blocks.append(await notebook_block(ctx))
    if ctx.get("active_run_id"):
        blocks.append(await run_block(ctx, mlflow_mgr))
    if ctx.get("hydra_config_hash"):
        blocks.append(await config_block(ctx, hydra_mgr))
    if ctx.get("dvc_hash"):
        blocks.append(await data_block(ctx, dvc_mgr))
    if ctx.get("dag_id"):
        blocks.append(await dag_block(ctx, airflow_mgr))
    if not blocks:
        return None
    return {"role": "user", "content": "WORKSPACE CONTEXT:\n\n" + "\n\n".join(blocks)}
```

#### Notebook Context Block

Cell selection heuristics to stay within the 16K context window:

- **Always include**: the selected cell and the 2 cells immediately before it
- **Include if present**: any cell with a non-empty output or error
- **Truncate**: cell outputs longer than 2000 chars with a "(truncated)" note
- **Cap**: max 20 cells regardless of notebook size
- **Budget**: notebook context block should not exceed ~3000 tokens (~12K chars)

```
NOTEBOOK CONTEXT:
File: /projects/jena_weather/training.ipynb
Kernel: Python 3.12 (venv: jena_weather_env) [IDLE]

[Cell 3 - code]
model = LSTMForecaster(cfg.model)
trainer = pl.Trainer(max_epochs=cfg.training.max_epochs)

[Cell 4 - code - SELECTED]
trainer.fit(model, datamodule=dm)

[Cell 4 - output]
Epoch 12/50: train_loss=0.0823, val_loss=0.0941
...(truncated, 48 more lines)
```

#### MLflow Context Block

```
ACTIVE MLFLOW RUN:
Run ID: run_abc123  |  Status: RUNNING
Experiment: jena_weather_lstm
Params: lr=0.001, hidden=128, layers=2, dropout=0.2
Latest metrics: train_loss=0.0823, val_loss=0.0941, epoch=12
Tags: hydra_config_hash=a3f9..., dvc_data_hash=7c2b...
```

### 3.4 Chat Flow (SSE relay)

The `/api/llm/chat` endpoint assembles context, then streams from agent_server back to the browser via SSE:

```python
@router.post("/api/llm/chat")
async def llm_chat(request: LLMChatRequest):
    # 1. Build context from descriptor
    ctx_message = await build_context_message(
        request.context_descriptor, mlflow_mgr, hydra_mgr, dvc_mgr, airflow_mgr
    )

    # 2. Assemble messages, stripping <think> blocks from history
    messages = []
    if ctx_message:
        messages.append(ctx_message)
    for msg in request.messages:
        if msg["role"] == "assistant":
            messages.append({**msg, "content": strip_thinking(msg["content"])})
        else:
            messages.append(msg)

    # 3. Stream from agent_server back to browser (including <think> tags)
    async def generate():
        async for chunk in llm_mgr.chat_stream(messages):
            delta = chunk["choices"][0].get("delta", {})
            if content := delta.get("content"):
                yield f"data: {json.dumps({'token': content})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 4. Tool Calling

Tools let the LLM query and act on noted's workspace. Whether Qwen 3.5 9B supports native function calling via llama.cpp needs testing. If not, tool calling can be implemented via structured output parsing (JSON block in the response).

Split into read (auto-execute) and write (require user confirmation).

### 4.1 Read Tools (Auto-execute)

| Tool | Description | Backend Source |
|---|---|---|
| get_run_details | Full metrics, params, tags for an MLflow run | MLflowManager |
| get_experiment_runs | List runs with summary metrics | MLflowManager |
| compare_runs | Diff table of two runs | MLflowManager |
| get_resolved_config | Fully resolved Hydra config | HydraManager |
| get_dag_structure | Task graph + latest run status | AirflowManager |
| get_file_contents | Read a project file | FileManager |
| get_dvc_history | Version history for a DVC-tracked file | DvcManager |
| search_knowledge_graph | Query the Knowledge Graph | graph_proxy (noted-graph:5523) |

### 4.2 Write Tools (User Confirmation Required)

| Tool | Description |
|---|---|
| insert_cell | Insert code/markdown cell into notebook |
| replace_cell_source | Replace source of a specific cell |
| trigger_dag | Trigger an Airflow DAG run |
| register_model | Register model version from MLflow run |
| save_config_template | Save a named Hydra config template |

### 4.3 Tool Dispatch Flow

1. LLM returns tool call (native `tool_calls` or parsed from structured JSON output)
2. Frontend checks: read tool -> auto-dispatch; write tool -> show confirmation widget
3. Confirmed tool call -> POST `/api/llm/tools/dispatch`
4. Backend executes via the appropriate manager
5. Result appended to conversation as a follow-up message
6. Another chat turn initiated so LLM can incorporate the result

---

## 5. Frontend Integration

### 5.1 Dual-Mode Chat

The frontend gains two paths:

**Simple chat (unchanged)**: `AgentClient.js` -> agent_server Socket.IO directly. Used for quick questions, STT/TTS voice interaction. Events: `Chat` -> `RunStarted` / `ChatChunk` / `ChatDone`. No context enrichment.

**Context-enriched chat (new)**: `fetch('/api/llm/chat')` with SSE streaming. Used when the user wants MLOps-aware answers. `ChatService.js` gets a toggle or auto-detects based on whether workspace context is available.

### 5.2 ChatService.js Changes

Minimal changes to the existing `ChatService.js`:

```javascript
// New: context-enriched path via noted backend SSE
async sendWithContext(text) {
    const contextDescriptor = buildContextDescriptor();
    const messages = this._history.concat([{ role: 'user', content: text }]);

    const response = await fetch('/api/llm/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, context_descriptor: contextDescriptor }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
            if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                const { token } = JSON.parse(line.slice(6));
                this._chatPanel.appendToken(token);
            }
        }
    }
    this._chatPanel.messageComplete();
}
```

The existing `AgentClient.js` path (`runText` -> `Chat` event) remains untouched for simple/voice interactions.

### 5.3 Context Descriptor Construction

```javascript
function buildContextDescriptor() {
    const nb = app._notebookEditor;
    const room = app._currentRoom;
    return {
        notebook_path:       nb?.path ?? null,
        selected_cell_index: nb?.selectedCellIndex ?? null,
        active_run_id:       nb?.metadata?.active_run_id ?? null,
        hydra_config_hash:   nb?.metadata?.hydra_config_hash ?? null,
        dvc_hash:            nb?.metadata?.last_dvc_hash ?? null,
        dag_id:              app._explorerPanel?.getSelectedDagId?.() ?? null,
        project_id:          room?.project_id ?? null,
    };
}
```

### 5.4 Tool Confirmation Widget

When the LLM response contains a tool call, render a confirmation card for write tools:

```javascript
if (toolCall && WRITE_TOOLS.has(toolCall.name)) {
    const confirmed = await showToolConfirmation(toolCall);
    if (!confirmed) return;
}
const result = await fetch('/api/llm/tools/dispatch', {
    method: 'POST',
    body: JSON.stringify({ tool_call: toolCall }),
}).then(r => r.json());
```

### 5.5 MLOps Integration Points (UI Buttons)

Add contextual buttons to existing panels that pre-populate the chat:

| Location | Button | Action |
|---|---|---|
| Run detail panel | "Ask Assistant" | Opens chat with run context + default prompt |
| Run comparison panel | "Explain Difference" | Sends both run IDs with comparison prompt |
| Task log viewer | "Explain Error" | Sends error block + DAG structure to chat |
| Notebook cell toolbar | "Explain" / "Refactor" | Sends cell source with pre-formed prompt |
| Hydra config panel | "Suggest Sweep" | Sends current config with sweep generation prompt |

---

## 6. Inline Code Completion (Ghost Text)

### 6.1 Architecture

A CodeMirror 6 `ViewPlugin` extension added to `CellEditor.js` and `FileEditor.js`.

| Property | Decision |
|---|---|
| Trigger | Debounced (800ms) on cursor idle, or explicit Ctrl+Space |
| Context sent | Current cell up to cursor + preceding cell sources (capped at 1500 tokens) |
| Endpoint | `/api/llm/complete` (noted backend -> agent_server `/v1/chat/completions`) |
| Rendering | `Decoration.widget` with ghost-text CSS (faded gray) |
| Accept | Tab accepts full suggestion; right arrow accepts one word |
| Cancel | Any other keypress dismisses ghost text |
| Abort | Each new request cancels the previous via AbortController |

### 6.2 ML-Aware Context

Because noted has live kernel state, enrich the completion prompt with variable names and types:

```python
async def get_kernel_namespace_summary(kernel_id):
    result = await kernel_mgr.execute_silent(
        kernel_id,
        'import json; print(json.dumps({k: type(v).__name__ for k,v in locals().items()}))'
    )
    return f'# Available variables: {result}'
```

Prepend this as a comment so the LLM completes with actual variable names in scope.

---

## 7. Session Management

### 7.1 Per-Notebook Sessions

Each open notebook maintains its own conversation history. Stored in notebook metadata (existing pattern), survives page reloads.

| Property | Value |
|---|---|
| Session key | `notebook.metadata.llm_session` |
| Structure | Array of `{ role, content, timestamp }` |
| Max length | Trim to last 10 messages when exceeding 20 (keeps ~4000 tokens for history within 16K budget) |
| Global mode | Non-notebook chat uses a separate `global_llm_session` |

agent_server's own `ThreadWindowMemory` provides a second layer of memory for the direct `AgentClient.js` path via `thread_id`. Update its `max_context_tokens` to `16384` to match the new `n_ctx`.

### 7.2 Context Refresh

On every new chat turn via the context-enriched path, workspace context is re-assembled from live state. The conversation history carries the dialogue; the context message carries the current workspace snapshot.

### 7.3 Chat Slash Commands

| Command | Effect |
|---|---|
| /clear | Clear conversation history for current session |
| /context | Show current context descriptor as JSON (debug) |
| /run <run_id> | Pin a specific MLflow run into context |
| /dag <dag_id> | Pin a specific DAG into context |
| /file <path> | Include a file's contents in next turn |

---

## 8. Observability

### 8.1 LLM Session Logging via MLflow

Each context-enriched chat session can be wrapped as an MLflow run:

```python
with mlflow.start_run(run_name=f"llm-assist-{session_id}"):
    mlflow.log_param("model", "qwen-3.5-9b")
    mlflow.log_param("agent", "noted")
    mlflow.log_text(user_prompt, "prompt.txt")
    mlflow.log_text(context_block, "context.txt")
    mlflow.log_text(response, "response.txt")
    mlflow.log_metric("latency_ms", elapsed)
```

### 8.2 Structured Logging

All prompts, context payloads, tool calls, and latencies logged via Python logging:

```
prompt | context_sources | tools_invoked | model | latency_ms
```

---

## 9. Security

- **Network isolation**: agent_server reachable only via Docker internal network from noted container
- **Auth**: `/api/llm/*` routes protected by same access-key auth as terminal endpoint
- **File scope**: `get_file_contents` tool enforces same path restrictions as noted's file API
- **Write confirmation**: All write tools require explicit user confirmation with full parameter display
- **Output sensitivity**: Optional per-notebook `include_outputs_in_llm_context` setting (default: true)
- **Resource capping**: agent_server already manages GPU memory via `n_gpu_layers` and model config

---

## 10. Phased Implementation

Each phase is independently useful. No phase requires subsequent phases to deliver value.

Effort estimates account for the fact that agent_server and the chat UI already exist - the work is wiring context, not building infrastructure from scratch.

### Phase A: Connectivity (half day) - DONE

Bridge agent_server to noted-network. Configure for noted's workload.

- [x] Add `noted-network` as external network in agent_server's `docker-compose.yml`
- [x] Set `n_ctx: 16384` and `max_context_tokens: 16384` in agent_server's `agent_config.json`
- [x] Create `noted.agent.json` preset + `noted_system_prompt.txt` in agent_server's `data/agents/`
- [ ] Add `LLM_BASE_URL` and `LLM_AGENT_NAME` to noted's environment
- [ ] Verify: `curl http://agent_server:7701/v1/models` from inside the noted container

### Phase B: Context-Enriched Chat (2-3 days)

The core feature. noted's backend assembles workspace context and proxies to agent_server.

- [ ] Create `backend/app/managers/llm_manager.py` (httpx client to `/v1/chat/completions`)
- [ ] Create `backend/app/managers/llm_context.py` (context block builders using existing managers)
- [ ] Create `backend/app/routers/llm.py` with `/api/llm/chat` (SSE streaming) and `/api/llm/health`
- [ ] Initialize `llm_mgr` in `main.py`
- [ ] Add `sendWithContext()` to `ChatService.js` with `buildContextDescriptor()`
- [ ] Add UI toggle or auto-detection for context-enriched vs simple chat mode
- [ ] Validate: open notebook, run cell, ask "explain the output of the selected cell"

### Phase C: Tool Calling (2-3 days)

Enable LLM to query and act on workspace state.

- [ ] Create `backend/app/managers/llm_tools.py` (tool schemas + dispatch registry)
- [ ] Add `/api/llm/tools/dispatch` endpoint
- [ ] Test Qwen 3.5 9B function calling support via llama.cpp; if unsupported, implement structured JSON output parsing as fallback
- [ ] Add frontend tool confirmation widget for write tools
- [ ] Add frontend auto-dispatch for read tools
- [ ] Test: "What are the metrics for run X?" -> LLM calls `get_run_details`

### Phase D: MLOps UI Buttons (1-2 days)

Contextual "Ask Assistant" entry points across noted's panels.

- [ ] "Ask Assistant" on run detail panel
- [ ] "Explain Difference" on run comparison panel
- [ ] "Explain Error" in task log viewer
- [ ] "Explain" / "Refactor" on notebook cell toolbar
- [ ] "Suggest Sweep" on Hydra config panel

### Phase E: Inline Completion (3-4 days)

Ghost-text code completion in CodeMirror.

- [ ] Add `/api/llm/complete` endpoint in `llm.py` (uses agent_server `/v1/chat/completions` with low temperature)
- [ ] Build CodeMirror 6 `ViewPlugin` in `frontend/js/llm/CompletionExtension.js`
- [ ] Integrate into `CellEditor.js` and `FileEditor.js`
- [ ] Add debounced trigger on cursor idle (800ms) and Ctrl+Space
- [ ] Add kernel namespace introspection for ML-aware context
- [ ] Tune max_tokens and temperature for sub-second responses

**Total estimated effort: 9-13 days** (down from 14-20 in the Ollama-based plan)

---

## 11. Files to Create / Modify

### New Files

| File | Purpose | Phase |
|---|---|---|
| `backend/app/managers/llm_manager.py` | httpx client to agent_server `/v1/chat/completions` | B |
| `backend/app/managers/llm_context.py` | Context assembly (workspace state -> prompt blocks) | B |
| `backend/app/managers/llm_tools.py` | Tool schemas + dispatch registry | C |
| `backend/app/routers/llm.py` | REST endpoints: `/api/llm/chat`, `/complete`, `/health`, `/tools/dispatch` | B |
| `frontend/js/llm/CompletionExtension.js` | CodeMirror 6 ghost-text plugin | E |
| `agent_server/data/agents/noted.agent.json` | Agent preset for noted integration | A |
| `agent_server/data/agents/noted_system_prompt.txt` | MLOps-aware persona prompt | A |

### Modified Files

| File | Change | Phase |
|---|---|---|
| `agent_server/docker-compose.yml` | Add `noted-network` as external network | A |
| `backend/app/main.py` | Initialize `LLMManager` | B |
| `frontend/js/ChatService.js` | Add `sendWithContext()` + context descriptor builder | B |
| `frontend/js/CellEditor.js` | Add CompletionExtension to CodeMirror extensions | E |
| `frontend/js/FileEditor.js` | Add CompletionExtension to CodeMirror extensions | E |

---

## 12. What This Plan Deliberately Excludes

- **Ollama**: agent_server already provides the same llama.cpp inference with better integration (Socket.IO streaming, agent presets, conversation memory, STT/TTS). Running both would duplicate GPU usage.
- **Vector DB / embedding store**: The Knowledge Graph (noted-graph:5523) already serves as the retrieval engine. Qdrant/Chroma adds complexity without proportional benefit.
- **LangChain / LlamaIndex / LangGraph**: Direct `httpx` calls to agent_server's OpenAI-compatible API are simpler and avoid heavy dependencies.
- **Separate LLM gateway service**: noted's backend already proxies MLflow, Airflow, and the graph service. Adding another gateway is unnecessary indirection.
- **New Socket.IO events in noted**: Using SSE via `/api/llm/chat` for context-enriched chat is simpler than adding `llm:*` events to noted's Socket.IO, since the direct `AgentClient.js` path already handles Socket.IO streaming for simple chat.
- **Kubernetes**: noted runs on single-machine Docker Compose.

---

## 13. Model and Resource Considerations

### 13.1 Current Model

agent_server currently runs **Qwen 3.5 9B Q6_K**. The config also has entries for Qwen 2.5 7B, EuroLLM 22B, Phi-4, and others.

### 13.2 VRAM Budget (RTX 4090 - 24 GB)

| Component | VRAM | Notes |
|---|---|---|
| Qwen 3.5 9B Q6_K weights | ~9 GB | Fixed cost, loaded once |
| KV cache (n_ctx=16384) | ~2 GB | Scales with context window |
| **Total (pool_size=1)** | **~11 GB** | Leaves ~13 GB free for training workloads |
| **Total (pool_size=2)** | **~22 GB** | Tight but fits; leaves ~2 GB |

### 13.3 Recommendations

- **Chat + MLOps reasoning**: Qwen 3.5 9B at 16K context is a good baseline. If deeper reasoning is needed, consider switching to a larger model (Qwen 2.5 32B Q4 or DeepSeek-Coder-V2) - but this would consume ~20 GB for weights alone, leaving no room for concurrent training.
- **Inline completion (Phase E)**: The same 9B model works but occupies the engine during generation. A smaller/faster model (Qwen 2.5 3B or Phi-4-mini) would give better latency. agent_server supports only one active model at a time, so inline completion shares the engine with chat. If Phase E auto-trigger creates contention, options are: (a) make it Ctrl+Space-only, (b) run a second agent_server instance with a small model on a different port, or (c) increase pool_size if VRAM allows.
- **Function calling**: Needs testing with Qwen 3.5 9B via llama.cpp. Fallback: structured JSON output parsing from the response text.
- **Context window scaling**: 16K is the recommended starting point. Can be increased to 32K (~4 GB KV cache) if conversations regularly need more depth, at the cost of reducing headroom for training or pool_size=2.

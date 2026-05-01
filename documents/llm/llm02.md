**Local LLM Integration Guide for noted: Building an On-Premises AI Assistant in a Colab-Style MLOps Environment**

### 1. Why Local LLM + Why Now
- **On-premises requirement** → No OpenAI/Anthropic keys, no data leaving the machine.
- **GPU acceleration** → noted already ships CUDA runtimes; the same GPUs can serve the LLM.
- **Full traceability** → Every LLM call can be logged as an MLflow run (via the existing auto-instrumentation).
- **MLOps-native context** → The assistant already lives inside the same workspace that knows about MLflow runs, DVC hashes, Hydra configs, Airflow DAGs, MinIO objects and the Knowledge Graph service (port 5523).
- **General editor support** → The assistant must help with .py files, Markdown, config YAMLs, and notebook cells exactly like it does for Jupyter notebooks.

### 2. Recommended Architectural Patterns (Chosen for noted’s Stack)

#### Pattern A – Proxy + OpenAI-Compatible API (Recommended Baseline)
- Run **Ollama** (or vLLM / TGI) as a sibling Docker service.
- noted’s FastAPI backend acts as a thin proxy + context injector.
- Frontend chat panel (already exists) talks only to `/api/chat` (no direct browser-to-Ollama).
- Benefits: zero browser CORS issues, single source of auth, easy streaming via Server-Sent Events (SSE) or Socket.IO continuation.

#### Pattern B – Agentic Loop with Tool Calling (MLOps Super-Power)
- LLM receives a system prompt that includes:
  - Current open notebook / file content (truncated)
  - Selected code block
  - Resolved Hydra config
  - Latest MLflow run ID + DVC hash
  - Knowledge Graph entity summary (via the existing Alpine service)
- LLM can emit `tool_calls` (Ollama 0.3+ native support).
- Backend implements ~12 typed tools (Pydantic + FastAPI) that wrap the existing internal clients (MLflow, Airflow API, DVC subprocess, MinIO client, Knowledge Graph REST).

#### Pattern C – RAG over Project + Knowledge Graph (Context Enrichment)
- Use the already-running **noted-graph** service as the retrieval engine.
- On every chat request:
  1. Quick vector search (or simple keyword + relationship BFS) over projects, runs, models, configs, DAGs.
  2. Inject top-3 entities + their lineage as structured JSON in the prompt.
- Optional lightweight vector store (Chroma or LanceDB in the same PostgreSQL) for notebook Markdown chunks.

#### Pattern D – Inline Completions (Copilot-style) – Future Phase
- Separate `/api/complete` endpoint using a fast 3-7B model (Phi-3, Gemma-2-2B, Qwen2.5-Coder-7B).
- Triggered by Ctrl+Space or “@” in CodeMirror.
- Kept separate from the main chat panel to avoid latency conflicts.

### 3. Concrete Implementation Steps (Docker-First)

#### Step 1 – Add Ollama Service (5 minutes)
Append to `services/docker-compose.yml` (and the GPU variant):

```yaml
  noted-ollama:
    image: ollama/ollama:latest
    container_name: noted-ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"   # only exposed to noted container, not host
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped
```

Add volume in `docker-compose.gpu.yml` if needed and update `data/docker-compose.mounts.yml` generation logic (already exists for projects).

Pull first model on startup (add to noted entrypoint or init container):

```bash
ollama pull qwen2.5-coder:14b   # or llama3.2:3b for CPU-only testing
ollama pull nomic-embed-text     # for optional local embeddings
```

#### Step 2 – Backend Integration (FastAPI)
Add to `backend/requirements.txt`:

```txt
openai>=1.40.0          # works with any OpenAI-compatible endpoint
litellm>=1.50.0         # optional – one-line fallback to other backends
pydantic>=2.9
langchain-core>=0.3     # only for structured output + tool parsing (lightweight)
```

Create `backend/app/llm/__init__.py` and `proxy.py`:

```python
# backend/app/llm/proxy.py
from openai import AsyncOpenAI
client = AsyncOpenAI(
    base_url="http://noted-ollama:11434/v1",
    api_key="ollama"  # dummy
)

async def stream_chat(messages: list, tools: list = None, temperature=0.7):
    stream = await client.chat.completions.create(
        model="qwen2.5-coder:14b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        stream=True,
        temperature=temperature
    )
    async for chunk in stream:
        yield chunk
```

#### Step 3 – Context Builder (The Magic)
`backend/app/llm/context.py`

```python
async def build_context(notebook_id: str | None, file_path: str | None):
    ctx = {
        "project": current_project_name(),
        "open_notebook": await get_notebook_cells(notebook_id) if notebook_id else None,
        "selected_code": get_selected_code(),           # from WebSocket or metadata
        "hydra_config": await resolve_active_hydra_config(),
        "mlflow_run": await mlflow_client.get_latest_run(),
        "dvc_hash": await dvc_current_hash(),
        "graph_summary": await graph_client.query(
            f"entities near {current_path}", limit=4
        )
    }
    return format_as_structured_prompt(ctx)
```

#### Step 4 – Tool Definitions (12 MLOps-Native Tools)
Use Pydantic models (already used everywhere in noted):

```python
class TriggerDag(BaseModel):
    dag_id: str
    conf: dict = Field(default_factory=dict)

class GetMlflowRun(BaseModel):
    run_id: str

# ... similarly for: list_experiments, dvc_push, minio_ls, register_model, 
# get_knowledge_graph_lineage, load_config_template, etc.
```

Register them once at startup and pass to every LLM call when the user types “use tools” or when the model decides.

Backend route example:

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    messages = await build_messages(request.user_message, request.context)
    tools = [TriggerDag.model_json_schema(), ...]
    
    async for chunk in stream_chat(messages, tools):
        if tool_calls := chunk.choices[0].delta.tool_calls:
            # execute tool via existing internal clients
            result = await execute_tool(tool_calls[0])
            messages.append({"role": "tool", "content": json.dumps(result)})
            # continue streaming with new context
        else:
            # forward token to frontend via SSE or Socket.IO
            yield chunk
```

#### Step 5 – Frontend Changes (Minimal)
The existing chat panel (jsPanel + Socket.IO) already supports real-time updates.

Only two changes needed:

1. Replace the external LLM endpoint with `/api/chat` (SSE or continue using Socket.IO room “chat”).
2. Add three buttons above the input box:
   - “Attach current notebook” (auto-populates context)
   - “Use MLOps Tools”
   - “Explain this cell” (sends selected cell + lineage)

Streaming tokens are rendered exactly like the current external implementation (just swap the source).

#### Step 6 – Logging & Traceability
Every chat session is automatically wrapped as an MLflow run:

```python
with mlflow.start_run(run_name=f"llm-assist-{session_id}"):
    mlflow.log_param("model", "qwen2.5-coder:14b")
    mlflow.log_text(user_prompt, "prompt.txt")
    # artifacts: generated code snippets, tool results
```

### 4. Security & On-Premises Hardening
- Ollama listens only on Docker network (no host port exposure).
- All calls go through noted’s JWT session (same as Airflow proxy).
- Rate limiting + token budget per user (PostgreSQL table).
- Model weights stay inside `ollama_data` volume (persistent).
- Optional: air-gapped mode – preload models during `docker build`.

### 5. Performance Recommendations
- **Default model** (most users): `qwen2.5-coder:14b` or `llama3.2:3b` (CPU fallback).
- **High-end GPU** (A100/H100): `deepseek-coder-v2:236b` via vLLM (swap image).
- Quantization: `qwen2.5-coder:14b-q4_K_M` for <12 GB VRAM.
- Keep temperature=0.7 for coding, 0.2 for MLOps reasoning.

### 6. Phase-In Roadmap (Fits noted’s Existing Phases)
- **Phase 4 extension (Q2 2026)**: Ollama service + proxy + basic context (already 80 % done).
- **Phase 5.8**: Full agentic tools + Knowledge Graph RAG.
- **Phase 5.9**: Inline completions + “Predict cell” template already exists – just wire to `/api/complete`.
- **Phase 5.10**: Model Card auto-generation using the same DocumentConverter pipeline + LLM.

### 7. Quick Start for Developers
```bash
# 1. Add the ollama service (see above)
# 2. docker compose up -d noted-ollama
# 3. ollama pull qwen2.5-coder:14b
# 4. Add the 4 files in backend/app/llm/
# 5. Restart noted
# 6. Open chat panel → type “Explain the current experiment”
```

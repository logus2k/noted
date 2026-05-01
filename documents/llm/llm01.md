# Local LLM Integration Architecture for 'noted'

## 1. Deployment & Infrastructure Patterns

Since **noted** already utilizes a microservices architecture via Docker Compose, the local LLM should be deployed as a dedicated, independent container. Do not run the LLM inference inside the main FastAPI container; this will block the event loop and crash real-time Socket.IO features.

### Recommended Pattern: The Sidecar Inference Engine
Add an inference server like **Ollama** or **vLLM** to your Docker Compose stack.
* **Ollama:** Best for ease of use, excellent CPU/GPU fallback, and supports a wide variety of quantized models (GGUF) which saves VRAM for the actual ML workloads running in the notebooks.
* **vLLM:** Best for high-throughput serving if you have dedicated, heavy-duty GPU nodes.

**Concrete Implementation:**
Update `services/docker-compose.gpu.yml` to include the LLM service:

```yaml
services:
  noted-llm:
    image: ollama/ollama:latest
    container_name: noted-llm
    volumes:
      - ../data/ollama:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```
*Note: Your FastAPI backend (`noted`) will communicate with `http://noted-llm:11434`.*

---

## 2. Backend Orchestration (FastAPI)

The **noted** backend must act as the "Context Orchestrator." The frontend should never talk directly to the LLM container. The backend will assemble context from your various MLOps services (MLflow, Airflow, MinIO, Knowledge Graph) before sending the prompt to the LLM.

### Integration Patterns
* **Streaming via Socket.IO or SSE:** To maintain a snappy UX, LLM responses must be streamed. Since you already extensively use Socket.IO for real-time metrics and DAG monitoring, use it to emit `llm_token` events.
* **Context Injection:** Before sending a user's chat message to the LLM, the FastAPI route should enrich the prompt with workspace metadata.

**Concrete Implementation:**
Create an `llm_service.py` in your backend that interfaces with the local LLM and the `noted-graph` (port 5523).

1.  **System Prompting:** Define a strong system prompt: *"You are the noted AI assistant. You have access to MLflow, Airflow, and DVC. The user is currently working in project X..."*
2.  **Context Assembly:** If the user asks "Why did my last pipeline fail?", the backend fetches the latest failed DAG run from the Airflow DB or API, extracts the tail of the task log, and prepends it to the LLM prompt.

---

## 3. Frontend & UI/UX Patterns (Vanilla ES6 + CodeMirror 6)

The UI needs to support two distinct interaction models: conversational reasoning (Chat) and ambient assistance (Inline Code).

### Pattern A: The Context-Aware Chat Panel
You already have a chat panel in your 4-column layout. Enhance it to be aware of the active tab.

* **Active Tab Binding:** When the user has a Notebook open, the chat payload sent to the backend should include `active_cell_content` and `active_cell_output`.
* **Actionable UI Responses:** The LLM shouldn't just return markdown. If it suggests a bash command (e.g., `dvc pull`), the frontend should render a "Run in Terminal" button. If it suggests Python code, render an "Insert in Notebook" button.

### Pattern B: Inline Code Completion (Ghost Text)
For the general text/code editor and notebook cells, implement GitHub Copilot-style ghost text.

* **Implementation:** Build a custom **CodeMirror 6 Extension**.
* **Debouncing:** Listen to document changes in CodeMirror. Debounce the input by ~500ms. If the user pauses typing, capture the text before and after the cursor.
* **FIM (Fill-In-the-Middle) Prompting:** Send a request to the FastAPI backend using a FIM-compatible local model (like `Codestral` or `DeepSeek-Coder` via Ollama).
* **Rendering:** Use CodeMirror 6's `Decoration.widget` to render the suggested text in a faded gray color inline. Bind the `Tab` key to accept the completion.

---

## 4. MLOps Context Integration (The "Secret Sauce")

To make the LLM truly useful for *MLOps* and not just generic coding, tie it into your existing tools.

### RAG via the Knowledge Graph
You have an Alpine + Python service running a Knowledge Graph on port 5523. This is your retrieval engine.
* When a user asks "Which model is the current champion?", the backend queries the Knowledge Graph for the node with the `@champion` alias, retrieves its lineage (DVC Hash -> Hydra Config -> MLflow Run), and feeds that structured data to the LLM to generate a natural language summary.

### Diagnostic Assistance
* **Airflow Logs:** Add a "Explain this Error" button inside your inline task log viewer. It grabs the exact error trace and sends it to the LLM.
* **Hydra Configs:** Allow the user to ask the chat panel: "Generate a Hydra sweep config to test learning rates from 0.001 to 0.1". The backend passes the current active YAML schema to the LLM to ensure the syntax matches the project.
* **MLflow Run Comparison:** If the user is in the Run Comparison panel, pass the metrics diff table to the LLM and ask: "Summarize the tradeoff between these two runs."

---

## 5. Phased Rollout Recommendations

To align with your Phase 4/5 roadmap, I recommend implementing this in steps:

1.  **Step 1: Foundation (Infrastructure & Chat)**
    * Add Ollama to `docker-compose.gpu.yml`.
    * Connect the existing frontend Chat Panel to a FastAPI WebSocket/Socket.IO endpoint that streams responses from a lightweight model (e.g., `Llama-3-8B-Instruct`).
2.  **Step 2: Ambient Assistance (CodeMirror 6)**
    * Develop the CodeMirror 6 FIM extension for inline code completions in notebooks and `.py` files using a local coder model.
3.  **Step 3: MLOps Grounding (Tooling)**
    * Integrate the LLM with the `noted-graph` API so it can answer questions about the workspace state, Airflow DAGs, and MLflow registry.









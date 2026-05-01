# Local LLM Integration Guide for "noted" MLOps Platform

This document outlines the architectural patterns and concrete implementation suggestions for integrating a local Large Language Model (LLM) into the **noted** platform. The goal is to provide a seamless, on-premises AI assistant that enhances code authoring, general reasoning, and MLOps workflows involving Airflow, MLflow, MinIO, and Hydra.

---

## 1. Architectural Patterns

To maintain the "Zero vendor lock-in" and "On-premises" philosophy of **noted**, the LLM integration should follow a modular, service-oriented pattern.

### 1.1. Sidecar Inference Pattern
Instead of embedding the LLM directly into the `noted` FastAPI container, run the LLM as a separate "sidecar" service. This allows for independent scaling and hardware allocation (e.g., assigning specific GPUs to the LLM).

| Component | Responsibility |
| :--- | :--- |
| **Inference Engine** | Hosting the model (e.g., Ollama, vLLM, or TGI). |
| **Proxy Layer** | The `noted` backend acts as a secure proxy, injecting context and handling authentication. |
| **Frontend Client** | A dedicated CodeMirror extension and Chat Panel for user interaction. |

### 1.2. Context-Aware Injection Pattern
The LLM's utility is directly proportional to the context it possesses. The system should automatically gather and inject relevant metadata into the prompt without user intervention.

*   **Runtime Context**: Current Python version, installed packages (`uv pip freeze`), and active virtual environment.
*   **Workspace Context**: Open file contents, directory structure, and recent terminal commands.
*   **MLOps Context**: Active MLflow experiment, current Hydra configuration, and DVC-tracked data versions.

---

## 2. Concrete Implementation Suggestions

### 2.1. Local Inference Backend
For an on-premises environment, we recommend two primary options:

1.  **Ollama (Ease of Use)**: Best for quick deployment and support for a wide range of models (Llama 3, CodeLlama, Mistral).
    *   *Implementation*: Add an `noted-llm` service to `docker-compose.yml` using the `ollama/ollama` image.
2.  **vLLM (Performance)**: Best for high-throughput scenarios and production-grade serving.
    *   *Implementation*: Use the `vllm/vllm-openai` image, which provides an OpenAI-compatible API out of the box.

### 2.2. MLOps Tool Integration (The "Assistant Helper")

The LLM should be "aware" of the specialized tools already integrated into **noted**.

#### A. MLflow & Experiment Reasoning
*   **Pattern**: "Explain this Run".
*   **Implementation**: When a user selects a run in the Experiments browser, provide a "Send to AI" button. The backend fetches run metrics and parameters via the MLflow API and sends them to the LLM with a prompt: *"Analyze this MLflow run. Why is the validation accuracy lower than the training accuracy?"*

#### B. Hydra Config Composition
*   **Pattern**: "Config Generator".
*   **Implementation**: Allow the LLM to suggest Hydra overrides.
*   **Example**: User asks: *"Suggest a Hydra sweep for a learning rate between 1e-5 and 1e-2 for my LSTM model."* The LLM returns a YAML snippet that the UI can directly apply to the Hydra Compose panel.

#### C. Airflow DAG Debugging
*   **Pattern**: "Log Analyzer".
*   **Implementation**: Integrate with the Task Log Viewer. If a task fails, a "Debug with AI" button sends the last 50 lines of the Airflow log to the LLM to identify the root cause (e.g., OOM, missing dependency, or data drift).

#### D. DVC & Data Lineage
*   **Pattern**: "Lineage Narrator".
*   **Implementation**: Use the Knowledge Graph data to provide the LLM with a full view of the lineage. The LLM can then answer: *"Which dataset version was used for the current @champion model?"*

---

## 3. Technical Integration Steps

### 3.1. Backend (FastAPI)
Extend the existing FastAPI backend to include an `/api/ai` endpoint. This endpoint should:
1.  **Gather Context**: Query the internal state (current notebook, active venv, MLflow URI).
2.  **Format Prompt**: Use a template engine (like Jinja2) to construct a system prompt including the gathered context.
3.  **Stream Response**: Use Server-Sent Events (SSE) to stream the LLM response back to the frontend for a "typing" effect.

### 3.2. Frontend (CodeMirror 6)
Leverage the existing CodeMirror 6 setup to add "Ghost Text" or "Inline Suggestions".
*   **Implementation**: Create a CodeMirror extension that listens for a specific debounce period and calls the `/api/ai/completions` endpoint.
*   **UI**: Use the `jsPanel` library (already in use) to create a floating "AI Command Palette" (Ctrl+K) for quick actions like "Refactor", "Document", or "Optimize".

---

## 4. Security and Privacy (On-Premises)

Since the application runs on-premises, ensure the following:
*   **No External Calls**: Hardcode the LLM endpoint to the internal Docker network (e.g., `http://noted-llm:11434`).
*   **Data Persistence**: Store chat histories in the `noted-postgres` database to allow for "Long-term Memory" across sessions.
*   **Resource Capping**: Use Docker resource limits to ensure the LLM doesn't starve the training kernels of GPU memory.

---

## 5. Summary Table of Integration Points

| Feature | Integration Method | LLM Role |
| :--- | :--- | :--- |
| **Notebooks** | CodeMirror Extension | Autocomplete, Docstring generation, Bug fixing. |
| **MLflow** | API Hook | Run comparison analysis, Metric trend explanation. |
| **Hydra** | YAML Parser | Config validation, Sweep parameter suggestion. |
| **Airflow** | Log Scraper | Error diagnosis, DAG optimization suggestions. |
| **DVC** | Metadata Injection | Data drift detection, Versioning strategy advice. |
| **Knowledge Graph** | Graph Traversal | Answering complex "How is X related to Y" questions. |

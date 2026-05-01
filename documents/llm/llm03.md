**Integrating a Local LLM into the `noted` Platform**

**Objective:** Enhance the `noted` MLOps platform with a local Large Language Model (LLM) to act as an intelligent assistant for code generation, explanation, debugging, and general reasoning within the context of ML projects and MLOps activities managed by `noted`.

**Context:** `noted` already unifies essential tools like Jupyter notebooks, MLflow, DVC, Hydra, and Airflow. Integrating an LLM should feel native, leveraging the existing architecture (FastAPI backend, ES6 frontend, WebSocket real-time communication) and enhancing workflows across these tools.

**Integration Patterns & Implementation Suggestions:**

1.  **LLM Backend Service Integration:**
    *   **Pattern:** Treat the LLM as an internal service, similar to MLflow or Airflow, potentially running in its own Docker container managed by the main `docker-compose` setup. Alternatively, it could be a process launched by the main `noted` container (if resource constraints allow).
    *   **Implementation:**
        *   **Containerization:** Create a new service definition (e.g., `noted-llm`) in the `docker-compose.yml` file. This service would run an open-source LLM inference server like `Ollama`, `vLLM`, or `Text Generation WebUI`.
        *   **Backend API Layer (FastAPI):** Implement new endpoints in the main `noted` FastAPI application (e.g., `/api/v1/llm/chat`, `/api/v1/llm/generate`). These endpoints will handle requests from the frontend, interact with the LLM service (via its API, e.g., Ollama's `/api/generate` or `/api/chat`), manage conversation history, and proxy responses back to the frontend. Consider caching frequent requests for efficiency.
        *   **Resource Management:** Ensure the LLM service has appropriate access to GPU resources if needed, similar to the `--gpus all` flag used for the main `noted` container.

2.  **Frontend User Interface (UI) & User Experience (UX):**
    *   **Pattern:** Provide an intuitive, always-accessible chat interface and context-aware code assistance features within the existing UI layout.
    *   **Implementation:**
        *   **Dedicated Chat Panel:** Integrate the existing "AI assistant: built-in chat panel connected to an external LLM agent" mentioned in the README. Ensure this panel is fully functional, easily accessible (e.g., via the icon bar or a keyboard shortcut), and allows for multi-turn conversations.
        *   **Inline Code Assistance:** Add subtle UI elements (e.g., icons next to code cells in notebooks, or above text editor panes) to trigger LLM assistance.
            *   **Generate/Explain/Refactor:** Right-click context menus in the Python/Markdown editors and Notebook cells could offer options like "Ask LLM", "Explain Selection", "Refactor Code", or "Fix Error".
            *   **Smart Completions:** While typing in the notebook/code editor (perhaps triggered by a hotkey like `Ctrl+Shift+Space`), provide a small pop-up or suggestion area showing potential code completions or next steps based on the LLM's understanding of the current context (code, variables, comments).

3.  **Context Enrichment for LLM Queries:**
    *   **Pattern:** Provide the LLM with relevant contextual information from the user's current workspace to deliver precise and actionable responses.
    *   **Implementation:**
        *   **Code Context:** When requesting help on a specific code block, send the relevant cell content, surrounding cells, or the entire notebook/file content to the LLM API endpoint.
        *   **Project/MLOps Context:** Allow users to include information about the current project, active MLflow experiment/run, Hydra configuration, or even recent Airflow pipeline statuses/logs in their query. This could be done via a checkbox in the chat panel ("Include project context") or by allowing the LLM to query `noted`'s backend APIs for this information when needed (e.g., fetch the current Hydra config hash, retrieve metrics from the latest MLflow run).
        *   **File Content:** Enable users to ask questions about specific files in their workspace (e.g., "Summarize this data preprocessing script"). The backend can read the file content and include it in the prompt.

4.  **Specific Use Cases & Prompt Engineering:**
    *   **Pattern:** Predefine prompts or templates for common tasks to guide the LLM effectively.
    *   **Implementation:**
        *   **Code Generation/Completion:** "Generate Python code for a PyTorch DataLoader based on the following dataset structure..." or "Complete the following function to calculate F1 score."
        *   **Code Explanation:** "Explain the purpose of the following code snippet: {selected_code}"
        *   **Debugging:** "The following error occurred: '{error_message}'. What might be causing it and how can I fix it?" (Include relevant code context).
        *   **MLOps Assistance:**
            *   "Write an Airflow DAG to run the training script `train.py` with the Hydra config `model=lstm,dataset=iris`." (Leverage DAG templates and Hydra integration).
            *   "Compare the performance metrics of runs `{run_id_1}` and `{run_id_2}` from experiment `{exp_name}`." (Fetch data via MLflow API and present to LLM).
            *   "How do I modify the current Hydra config to use the AdamW optimizer with a learning rate of 0.001?"
            *   "Help me write a DVC pipeline stage to preprocess the data in `{input_path}` and save it to `{output_path}`."
        *   **General Reasoning:** "Based on the experiment results, what hyperparameters seem most important for improving recall?"

5.  **Security & Access Control:**
    *   **Pattern:** Ensure LLM interactions respect the application's security model.
    *   **Implementation:**
        *   The LLM backend service should be accessible only internally within the Docker network.
        *   All communication via the FastAPI backend acts as a secure proxy, preventing direct exposure of the LLM API endpoint to the frontend/browser.
        *   Any file content sent to the LLM should be handled securely, respecting the user's workspace boundaries.

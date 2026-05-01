---
name: noted-platform-overview
description: What noted is - architecture, capabilities, and key concepts. Use when user asks what noted is, how the platform works, what tools are integrated, what containers run, or for a general overview of the system.
triggers: [workspace_active]
priority: 1
max_tokens: 500
---
noted is an on-premises collaborative notebook and MLOps platform.

CORE CAPABILITIES:
- Jupyter-compatible notebooks with CodeMirror 6 editor
- Multiple Python runtimes/venvs per project
- Real-time collaboration via Socket.IO
- File management with project and mount-based organization

MLOPS INTEGRATIONS:
- MLflow: experiment tracking, model registry, artifact management, serving
- Airflow: pipeline orchestration, parameter sweeps, real-time monitoring
- DVC: data version control backed by MinIO (S3-compatible)
- Hydra: structured configuration management with composition and templates
- Knowledge Graph: entity relationship visualization

KEY CONCEPTS:
- Projects: contain notebooks, code, configs, and DAGs
- Mounts: external directories mounted into noted (read-write)
- Run Manager: defines cell groups as named runs, executes with automatic MLflow start/end and framework autologging
- Live Metrics: real-time metric streaming during training via Socket.IO
- Lineage: Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry)

ARCHITECTURE:
- 12 Docker containers: noted, mlflow, airflow (x5), minio, serving, graph, postgres, redis
- All on-premises, zero cloud dependency
- Docker Compose with mounts.yml for project data

PRIMARY INTERACTION SURFACE: The user spends most of their time in the **notebook editor** and the **Explorer panel**. All MLOps tools (MLflow, Airflow, DVC, Hydra) are accessible without leaving the notebook environment.

ANSWERING CONCEPTUAL QUESTIONS:
- For "what is noted?" / "how does X work?" / "where do users spend time?" / "how does noted track lineage?" - answer DIRECTLY from this overview. Do NOT call any tool (no query_knowledge_graph, no get_file_contents, etc.) - all the answer is already here.
- When citing the lineage chain, list it in order: Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry).
- When asked about primary interaction or "where users spend time", explicitly mention BOTH the notebook editor AND the Explorer panel, and note that MLOps tools are accessed without leaving the notebook environment.

# Local LLM Integration Architecture for the noted Platform

## 1. Objectives

Integrate a **local LLM assistant** into the noted environment to support:

* Code assistance
* ML experiment reasoning
* Pipeline debugging
* Configuration generation
* Documentation generation
* Interactive notebook support
* Experiment analysis

The assistant must operate:

* **Fully on-premises**
* **Without vendor lock-in**
* **Within the existing noted architecture**
* **Using workspace context**

---

# 2. Architectural Principles

### 2.1 Core Design Constraints

The LLM integration must:

1. **Run locally**
2. **Use the existing backend**
3. **Access workspace state**
4. **Respect security boundaries**
5. **Scale with GPU resources**

---

### 2.2 Design Principles

| Principle              | Description                               |
| ---------------------- | ----------------------------------------- |
| Contextual             | LLM receives project state, code, configs |
| Modular                | LLM is an independent service             |
| Observable             | all prompts and outputs logged            |
| Tool-driven            | LLM interacts through structured tools    |
| Deterministic fallback | code generation reproducible              |
| Offline first          | no internet dependency                    |

---

# 3. Recommended System Architecture

## 3.1 Component Layout

Add a **dedicated LLM service**.

```
                  Browser
                     │
                     │
            ┌────────▼────────┐
            │     noted       │
            │ FastAPI backend │
            └────────┬────────┘
                     │
                     │ REST / WebSocket
                     │
        ┌────────────▼─────────────┐
        │        LLM Gateway       │
        │ (agent orchestration)    │
        └────────────┬─────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
  ┌──────▼───────┐      ┌────────▼────────┐
  │ Local LLM     │      │ Embedding Model │
  │ (vLLM/ollama) │      │ + vector store  │
  └───────────────┘      └─────────────────┘
```

The gateway performs:

* context gathering
* tool invocation
* prompt orchestration
* response streaming

---

# 4. LLM Runtime Options

Recommended inference engines:

| Engine                              | Pros                           | Cons          |
| ----------------------------------- | ------------------------------ | ------------- |
| **vLLM**                            | best throughput, GPU optimized | heavier setup |
| **Ollama**                          | easiest deployment             | less scalable |
| **Text Generation Inference (TGI)** | production scale               | larger infra  |
| **llama.cpp**                       | CPU capable                    | slower        |

Recommended default:

**vLLM**

---

## Example deployment

```
docker run \
  --gpus all \
  -p 8001:8000 \
  vllm/vllm-openai \
  --model mistralai/Mistral-7B-Instruct
```

Expose **OpenAI-compatible API**.

---

# 5. LLM Gateway Service

This service orchestrates reasoning.

Responsibilities:

* prompt templates
* context building
* tool routing
* streaming responses
* safety filtering
* logging

---

## Recommended Implementation

Language:

```
Python
FastAPI
```

Libraries:

```
LangGraph
LlamaIndex
or
custom agent loop
```

Given the sophistication of noted, **custom orchestration is preferable**.

---

# 6. Context Injection Strategy

LLMs are only useful if given **workspace context**.

### Context sources

| Source         | Method          |
| -------------- | --------------- |
| Notebook cells | kernel capture  |
| Python files   | workspace scan  |
| Hydra configs  | YAML injection  |
| MLflow runs    | metadata query  |
| DVC datasets   | hash + metadata |
| Airflow DAGs   | DAG parser      |

---

## Context assembly pipeline

```
User prompt
     │
     ▼
Context builder
     │
     ├── active notebook
     ├── current file
     ├── selected code
     ├── MLflow experiment
     ├── Hydra config
     └── project summary
```

---

## Example context payload

```
{
 "active_file": "train.py",
 "selected_code": "...",
 "hydra_config": {...},
 "mlflow_run": {...},
 "dvc_data_hash": "...",
 "recent_cells": [...]
}
```

---

# 7. Tool-Driven Agent Pattern

Instead of raw prompts, expose **tools**.

Example tools:

| Tool                  | Purpose           |
| --------------------- | ----------------- |
| search_codebase       | semantic search   |
| read_file             | retrieve code     |
| run_python            | execute code      |
| query_mlflow          | experiment lookup |
| query_dvc             | dataset metadata  |
| query_airflow         | DAG status        |
| generate_hydra_config | config creation   |
| explain_run           | run analysis      |

---

## Example tool interface

```python
class Tool:
    name: str
    description: str
    input_schema: dict

    def run(self, args):
        ...
```

---

# 8. Retrieval Augmented Generation (RAG)

To reason over projects.

## Required Indexes

Index these artifacts:

* Python files
* notebooks
* configs
* experiment metadata
* documentation

---

### Embedding model

Recommended:

```
bge-large-en
or
Instructor-XL
```

---

### Vector database

Options:

| DB       | Advantage          |
| -------- | ------------------ |
| Qdrant   | fast + open source |
| Weaviate | strong schema      |
| Chroma   | simple             |

Recommended:

**Qdrant**

---

## RAG pipeline

```
prompt
  │
  ▼
embedding
  │
  ▼
vector search
  │
  ▼
context retrieved
  │
  ▼
LLM prompt
```

---

# 9. Notebook Integration

The LLM should support **cell-level assistance**.

### Features

* explain cell
* optimize code
* generate next cell
* convert to pipeline task
* debug errors

---

### UI pattern

Add **cell action buttons**:

```
[Run] [Explain] [Optimize] [Convert to DAG]
```

---

### Backend flow

```
cell -> context -> LLM -> suggestion
```

---

# 10. Code Editor Integration

Add features similar to **Copilot**.

Capabilities:

* inline completion
* refactoring
* docstring generation
* type hinting

---

## Implementation pattern

Use **prefix + suffix prompting**.

Example:

```
<file before cursor>
### COMPLETE CODE
<file after cursor>
```

---

# 11. MLflow-Aware Reasoning

Assistant should understand experiments.

Example prompts:

```
Explain why run A outperformed run B.
```

Gateway queries:

```
MLflow metrics
params
artifacts
```

Then injects structured data.

---

Example context:

```
run_A:
  lr: 0.001
  accuracy: 0.94

run_B:
  lr: 0.01
  accuracy: 0.88
```

---

# 12. Hydra Configuration Assistance

Capabilities:

* generate configs
* explain configs
* create sweeps

Example prompt:

```
Generate Hydra config for GRU model
```

---

Example output:

```
model:
  type: gru
  hidden_size: 128
  layers: 2
```

---

# 13. Pipeline Reasoning

Assistant can inspect DAGs.

Example:

```
Why did my pipeline fail?
```

Gateway collects:

```
Airflow logs
task dependencies
parameters
```

---

# 14. Execution Tools

Allow LLM to execute controlled tasks.

Example tool:

```
run_python(code)
```

Security constraints:

* sandboxed
* resource limits
* restricted modules

---

# 15. Memory System

Maintain conversation memory.

Two levels:

### Session memory

Current chat.

### Project memory

Stored embeddings of:

* experiments
* findings
* documentation

---

# 16. Streaming Responses

Use existing **Socket.IO infrastructure**.

Flow:

```
LLM token stream
 → gateway
 → Socket.IO
 → UI chat panel
```

---

# 17. Logging and Observability

All prompts logged.

Store:

```
prompt
context
response
tools used
latency
```

Possible storage:

```
PostgreSQL
or
MLflow artifacts
```

---

# 18. Security Model

Important for on-prem systems.

Rules:

* no direct shell access
* no unrestricted filesystem
* explicit tool permissions
* prompt injection filtering

---

# 19. Performance Considerations

Use:

* GPU batching
* KV cache reuse
* context compression
* selective retrieval

---

### Context size management

Use:

```
token budget allocator
```

Example:

```
4096 tokens total
```

Split:

```
1500 project context
1500 code
500 instructions
596 prompt
```

---

# 20. Suggested Models

Good models for code + ML reasoning:

| Model               | Size                | Notes |
| ------------------- | ------------------- | ----- |
| DeepSeek-Coder      | excellent coding    |       |
| CodeLlama           | stable              |       |
| Mistral-7B-Instruct | good reasoning      |       |
| Mixtral-8x7B        | strong performance  |       |
| Qwen2.5-Coder       | modern coding model |       |

Recommended baseline:

```
DeepSeek-Coder-33B
```

or

```
Mixtral-8x7B
```

---

# 21. Example API Design

### Chat endpoint

```
POST /llm/chat
```

Payload:

```
{
 "prompt": "...",
 "project_id": "...",
 "file": "...",
 "cell_id": "...",
 "context_level": "auto"
}
```

---

### Code completion endpoint

```
POST /llm/complete
```

---

### Tool endpoint

```
POST /llm/tool
```

---

# 22. Suggested Development Phases

## Phase 1

Basic chat assistant.

Features:

* code explanation
* workspace search
* notebook context

---

## Phase 2

RAG integration.

Features:

* project search
* documentation retrieval

---

## Phase 3

Tool agents.

Features:

* MLflow analysis
* pipeline debugging
* config generation

---

## Phase 4

Autonomous workflows.

Examples:

```
Generate full training pipeline
```

---

# 23. UI Integration Points in noted

Integrate assistant in:

| Location          | Capability            |
| ----------------- | --------------------- |
| Chat panel        | general reasoning     |
| Notebook cells    | contextual assistance |
| Code editor       | inline completion     |
| MLflow runs       | analysis              |
| Hydra configs     | generation            |
| Airflow pipelines | debugging             |

---

# 24. Advanced Feature: Knowledge Graph Integration

The **noted knowledge graph** is extremely powerful.

LLM should query it.

Example:

```
Find all runs that used this dataset.
```

Graph traversal:

```
dataset → runs → models
```

This allows:

* lineage reasoning
* experiment discovery
* impact analysis

---

# 25. Example Agent Flow

User asks:

```
Why is my model overfitting?
```

Agent pipeline:

```
1 retrieve experiment runs
2 retrieve configs
3 retrieve metrics
4 analyze curves
5 generate answer
```

---

# 26. Minimal Implementation Stack

Recommended stack:

```
LLM runtime:
  vLLM

Agent gateway:
  FastAPI + custom tools

Embeddings:
  bge-large

Vector DB:
  Qdrant

Indexing:
  LlamaIndex

Streaming:
  Socket.IO
```

---

# 27. Example Deployment (Docker)

Add services:

```
noted-llm
noted-embeddings
noted-qdrant
```

---

# 28. Long-Term Direction

Potential advanced capabilities:

* automatic experiment analysis
* pipeline synthesis
* dataset anomaly detection
* hyperparameter suggestions
* automatic model cards
* debugging agents

---

# 29. Key Design Recommendation

**Do NOT embed the LLM directly inside the noted container.**

Instead use:

```
noted
noted-llm-gateway
noted-llm-runtime
```

This preserves:

* modularity
* scaling
* model swapping

---

# 30. Summary

Recommended architecture:

```
Frontend Chat UI
        │
        ▼
FastAPI backend
        │
        ▼
LLM Gateway (agents + tools)
        │
 ┌──────┴─────────┐
 │                │
vLLM runtime    Vector DB
 │                │
Embeddings      Workspace index
```

This enables the LLM to reason about:

* code
* experiments
* pipelines
* configurations
* data lineage

directly within the **noted unified MLOps environment**. 

---

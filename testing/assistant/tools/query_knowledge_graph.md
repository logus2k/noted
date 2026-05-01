# Tool: query_knowledge_graph

**Type:** tool
**Tier:** read
**Domain:** knowledge_graph
**Handler:** [backend/app/managers/llm_tools.py `_tool_query_knowledge_graph`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns project entities + relationships (Data, Config, Code, Pipeline, Run, Model). For conceptual/platform-design questions, use the `noted-platform-overview` skill instead — the graph reflects ACTUAL project state.

## Input schema

- `project_id` (required).

## Setup prerequisites

- Project: `noted-testing` (or any with graph populated).

## Scenarios

### S1 - Basic graph
"what entities + relationships does the project have?" → `query_knowledge_graph(project_id)`.

### S2 - Lineage chain
"trace lineage from data to model" → graph; if empty, mention conceptual chain.

### S3 - Empty graph
Report empty; explain it populates as runs accrue; no fabrication.

### S4 - Wrong tool for conceptual Q
"how does noted track lineage in general?" → conceptual; answer from skill, NOT graph.

### S5 - Combined with run lookup
T1: graph. T2: details on a shown run → `get_run_details`.

### S6 - No graph (DEFERRED)
### S7 - Large graph pagination (DEFERRED)

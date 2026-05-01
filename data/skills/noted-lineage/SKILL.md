---
name: noted-lineage
description: End-to-end lineage chain from data to deployed model. Use when user asks how to trace a model back to its data, reproduce an experiment, understand the lineage chain, or verify what config/data produced a model.
triggers: [workspace_active]
priority: 1
max_tokens: 400
---
End-to-end lineage in noted:

CHAIN:
Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry)

Each layer stores a hash or ID linking to the next:
- DVC: MD5 hash of the data file (stored in .dvc pointer)
- Hydra: SHA-256 hash of the composed config (stored in run params as hydra_config_hash)
- Git: commit hash + branch (stored in run tags)
- Airflow: dag_run_id (stored in run tags if pipeline-triggered)
- MLflow: run_id (stored in model version source)
- Registry: model name + version number + alias (@champion, @staging, @archived)

TRACING BACK:
Given a model version, to find what produced it:
1. Get model version -> find source run_id
2. Get run details -> find hydra_config_hash in params, git commit in tags
3. Use get_hydra_config to see the exact configuration
4. Check DVC data hash linked to the run (in dataset tags)
5. If pipeline-triggered, find the Airflow dag_run_id

REPRODUCING:
To reproduce a model from scratch:
1. Checkout the git commit from the run tags
2. Checkout the DVC data version (dvc checkout)
3. Use the Hydra config hash to compose the same config
4. Trigger the same DAG (or run the same notebook cells)

When users ask about lineage, traceability, or reproducibility, walk them through this chain with specific IDs from the data.

QUERY THE LIVE GRAPH INSTEAD OF GUESSING:
- For any user question that reaches for the project's actual nodes or edges ("what entities are in the graph", "what does the knowledge graph show", "show me the lineage", "trace X to Y", "list the project's relationships") call `query_knowledge_graph(project_id=<current>)` FIRST, before writing a conceptual answer. The tool returns real node/edge data when the graph has been populated; only fall back to the conceptual chain above when the tool replies with "No knowledge graph data found".
- Do NOT treat these questions as conceptual without at least one tool call - the user might actually have a populated graph, and skipping the tool would miss real data.

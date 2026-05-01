# Skill: noted-lineage

**Type:** skill
**Source:** [data/skills/noted-lineage/SKILL.md](../../../data/skills/noted-lineage/SKILL.md)

## Purpose

Explains noted's Data → Config → Code → Pipeline → Run → Model lineage chain and how each step is tracked.

## Scenarios

### S1 - Lineage chain
Conceptual; no query_knowledge_graph call; present chain in order.

### S2 - Trace deployed model back
`get_serving_status` → model + run_id; chain explanation; drill via get_run_details optional.

### S3 - hydra_config_hash meaning
Identifier for composed config; reproducibility marker.

### S4 - DVC hash rationale
Exact data version; drift detection.

### S5 - Missing lineage
Likely run created outside Run Manager; suggest re-run.

### S6 - Cross-tool (DAG → MLflow)
Tags link them; inspect via get_run_details.

### S7 - Cross-project (DEFERRED)
### S8 - Re-registration (DEFERRED)

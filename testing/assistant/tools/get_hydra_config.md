# Tool: get_hydra_config

**Type:** tool
**Tier:** read
**Domain:** hydra
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_hydra_config`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns the RESOLVED Hydra config (composed + overridden). For raw `config.yaml` use `get_file_contents`.

## Input schema

- `project_id` (required).

## Setup prerequisites

- Project with Hydra config (e.g. `jena_weather` or any with config/ tree).

## Scenarios

### S1 - Resolved config
"show resolved Hydra config" → `get_hydra_config(project_id)`; do NOT use get_file_contents.

### S2 - Specific section
"what's in training?" → extract subsection.

### S3 - Active group
"which data option is active?" → report selection + source file.

### S4 - Raw vs resolved
"open config.yaml" → `get_file_contents` (raw); not `get_hydra_config`.

### S5 - Override visibility
"any overrides?" → report active overrides; "none" if defaults.

### S6 - Project without Hydra (DEFERRED)
### S7 - Deeply-nested overrides (DEFERRED)

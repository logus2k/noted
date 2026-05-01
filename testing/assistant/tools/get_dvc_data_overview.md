# Tool: get_dvc_data_overview

**Type:** tool
**Tier:** read
**Domain:** dvc
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_dvc_data_overview`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists all DVC-tracked data files across projects: filename, size, hash, project. Used for inventory questions and as the entry to `get_dvc_file_history`.

## Input schema

- No arguments.

## Setup prerequisites

- DVC tracking active in at least one project.

## Scenarios

### S1 - Basic overview
"what data files are tracked by DVC?" → `get_dvc_data_overview`; no history call.

### S2 - Specific file
"is X tracked?" → scan result; do not call history unless asked.

### S3 - Inventory count
"how many tracked datasets?" → count + group by project.

### S4 - Multi-turn list then history
T1: overview. T2: "history of first" → `get_dvc_file_history` reusing repo_path+dvc_file.

### S5 - Generic "data" question
"what data does the project have?" → DVC overview is the right answer.

### S6 - No DVC files (DEFERRED)
### S7 - Cross-project drilldown (DEFERRED)

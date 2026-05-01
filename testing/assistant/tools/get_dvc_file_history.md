# Tool: get_dvc_file_history

**Type:** tool
**Tier:** read
**Domain:** dvc
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_dvc_file_history`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns version history for a single DVC-tracked file: hashes, timestamps, optionally commit messages.

## Input schema

- `repo_path` (required), `dvc_file` (required).

## Setup prerequisites

- A DVC-tracked file with at least one version exists in the named repo.

## Scenarios

### S1 - Basic history fetch
"history of X.csv in jena_weather" → `get_dvc_file_history(repo_path, dvc_file)`.

### S2 - Latest version
"what's the latest of X?" → first row.

### S3 - Hash lookup
"current md5 of X?" → quote from tool result.

### S4 - Wrong path
Tool errors; report; suggest overview.

### S5 - Multi-turn overview then history
T1: `get_dvc_data_overview`. T2: `get_dvc_file_history` reusing args.

### S6 - 100+ versions (DEFERRED)
### S7 - Deleted-from-tracking (DEFERRED)

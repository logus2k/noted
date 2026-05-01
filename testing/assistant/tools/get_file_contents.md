# Tool: get_file_contents

**Type:** tool
**Tier:** read
**Domain:** files
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_file_contents`](../../../backend/app/managers/llm_tools.py)

## Purpose

Reads a file from the current project (path resolved against active project context). Used to inspect known paths; for "where is X defined" use `search_files` first.

## Input schema

- `path` (required, string), `max_lines` (optional, int, default 100).

## Setup prerequisites

- Project: `noted-testing` (or any project with files of interest).

## Scenarios

### S1 - Read a Python file
Direct read; do NOT call search_files.

### S2 - Limit lines
Pass `max_lines=30`; mention truncation.

### S3 - Nonexistent file
Tool errors; report; suggest list/search; do not fabricate.

### S4 - Read config.yaml
Read the file; explain sections; `get_hydra_config` is for the RESOLVED config (different).

### S5 - Multi-turn list then read
T1: `list_files`. T2: open first → `get_file_contents` reusing path.

### S6 - Search vs read
"where is train_model defined?" → `search_files` first; then `get_file_contents` is OK.

### S7 - Binary file (DEFERRED)
### S8 - Non-UTF8 (DEFERRED)

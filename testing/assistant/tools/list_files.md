# Tool: list_files

**Type:** tool
**Tier:** read
**Domain:** files
**Handler:** [backend/app/managers/llm_tools.py `_tool_list_files`](../../../backend/app/managers/llm_tools.py)

## Purpose

Lists files in a project directory, with optional glob filter. One level at a time.

## Input schema

- `project_id` (required), `path` (optional), `pattern` (optional).

## Setup prerequisites

- Project: `noted-testing` (or any).

## Scenarios

### S1 - List project root
"what files at root?" → `list_files(project_id)`.

### S2 - List subdirectory
"what's in src/?" → `path="src"`.

### S3 - Glob pattern
"all python files in src/" → `pattern="*.py"`.

### S4 - Empty directory
Tool empty/error; report.

### S5 - Multi-turn discover then read
T1: list `.ipynb` files. T2: open first → `get_notebook_cells`.

### S6 - Very-deep tree (DEFERRED)
### S7 - Hidden files (DEFERRED)

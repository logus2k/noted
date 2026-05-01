# Tool: search_files

**Type:** tool
**Tier:** read
**Domain:** files / search
**Handler:** [backend/app/managers/llm_tools.py `_tool_search_files`](../../../backend/app/managers/llm_tools.py)

## Purpose

Greps file contents across the project. Returns file paths + matching lines.

## Input schema

- `project_id`, `query` (required); `path`, `file_pattern`, `max_results` (optional).

## Setup prerequisites

- Project: `noted-testing` (or any with code).

## Scenarios

### S1 - Find function def
"where is train_model defined?" → `search_files(query="def train_model")`.

### S2 - Find string usage
Direct grep; report files+lines; "0 matches" if empty.

### S3 - file_pattern filter
"only in .py" → pass `file_pattern="*.py"`.

### S4 - path filter
"in src/" → pass `path="src"`.

### S5 - Multi-turn search then read
T1: search. T2: "open that file" → `get_file_contents`.

### S6 - Empty result
Report zero; do not fabricate.

### S7 - Regex special chars (DEFERRED)
### S8 - max_results overflow (DEFERRED)

# Tool: update_file

**Type:** tool
**Tier:** write
**Domain:** files
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Updates an existing project file. NOT for notebooks (use `update_cell` / `batch_update_cells`); NOT for lint fixes (use `fix_lint_issues`); NOT for new files (use `create_file`).

## Setup prerequisites

- Target file exists in project.

## Scenarios

### S1 - Edit project file
Direct call; report change.

### S2 - Read first if needed
T1: `get_file_contents`. T2: `update_file`.

### S3 - Don't use for lint
"fix F401" → `fix_lint_issues`, not update_file.

### S4 - Don't use for new file
"create new file" → `create_file`, not update_file.

### S5 - Don't use on notebooks
".ipynb cell update" → `update_cell`; update_file would corrupt JSON.

### S6 - Protected path (DEFERRED)
### S7 - Very-large file (DEFERRED)

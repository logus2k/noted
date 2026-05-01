# Tool: get_notebook_cells

**Type:** tool
**Tier:** read
**Domain:** notebook
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_notebook_cells`](../../../backend/app/managers/llm_tools.py)

## Purpose

Reads cells from a notebook. Defaults to all cells (≤80K chars). Use `indices` for specific cell numbers, or `from_index`/`to_index` for ranges. `include_outputs=true` for cell outputs.

## Input schema

- `project_id`, `notebook_path` (required); `indices`, `from_index`, `to_index`, `include_outputs` (optional).

## Setup prerequisites

- A notebook exists at `notebook_path` (e.g. `training_sandbox.ipynb`).

## Scenarios

### S1 - Read full notebook
No subset args; report all cells.

### S2 - Specific cells
`indices=[1,5,10]`; report only requested.

### S3 - Range read
`from_index=5, to_index=10`; inclusive.

### S4 - Include outputs
`include_outputs=true`; quote output verbatim.

### S5 - Find cell by content
"which cell defines the model?" → read; identify cell number; brief excerpt.

### S6 - Notebook not found
Tool errors; report; suggest `list_files`.

### S7 - 80K char truncation (DEFERRED)
### S8 - Rich outputs (DEFERRED)

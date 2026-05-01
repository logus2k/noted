# Tool: insert_cell

**Type:** tool
**Tier:** write
**Domain:** notebook
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Inserts a new notebook cell at a specified position. Use for "add" / "create" / "write new". For modifying existing cells use `update_cell`.

## Setup prerequisites

- Notebook open.

## Scenarios

### S1 - Add new cell
"add new cell after 5" → `insert_cell`.

### S2 - Don't use update for new
"create a new cell" → `insert_cell`, NOT update.

### S3 - Markdown cell
Insert markdown variant.

### S4 - Multiple inserts → batch
Three cells → `batch_update_cells` (single confirm).

### S5 - Insert after find
T1: `get_notebook_cells`. T2: insert at located index.

### S6 - Bad index (DEFERRED)
### S7 - md vs code variants (DEFERRED)

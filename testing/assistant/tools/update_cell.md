# Tool: update_cell

**Type:** tool
**Tier:** write (confirmation panel via platform)
**Domain:** notebook
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Updates a single notebook cell. CRITICAL: `new_content` MUST include the COMPLETE cell content, not just changed lines.

## Input schema

- Per backend wrapper; cell_index + new_content as defined.

## Setup prerequisites

- Notebook open with cells of interest.

## Scenarios

### S1 - Fix lint
COMPLETE content; platform confirms; report change.

### S2 - Refactor
Read first if needed; update with COMPLETE content.

### S3 - Multi-turn read then update
T1: `get_notebook_cells`. T2: update with full content.

### S4 - Don't update for navigation
"go to" → `scroll_to_cell`, NOT update_cell.

### S5 - Multi-cell → batch
Multiple cells → `batch_update_cells` (single confirm).

### S6 - Cell with widgets (DEFERRED)
### S7 - Very-large cell (DEFERRED)

# Tool: scroll_to_cell

**Type:** tool
**Tier:** read (UI navigation; no state mutation)
**Domain:** notebook / navigation
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Scrolls the notebook editor to a specific cell and selects it. UI-only; does not return cell content.

## Input schema

- `cell_index` (required, int, 1-based).

## Setup prerequisites

- A notebook is open in the editor.

## Scenarios

### S1 - Scroll to cell
Direct call; do not also read.

### S2 - Find then scroll
T1: `get_notebook_cells` to locate. T2: `scroll_to_cell` reusing index.

### S3 - First / last cell
"go to first" → `cell_index=1`.

### S4 - Read vs scroll
"show me cell 5" → `get_notebook_cells` (content); not scroll.

### S5 - Out of range (DEFERRED)
### S6 - No notebook open (DEFERRED)

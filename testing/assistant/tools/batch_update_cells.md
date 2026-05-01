# Tool: batch_update_cells

**Type:** tool
**Tier:** write
**Domain:** notebook / batch
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Bundles multiple cell mutations (update + insert) into a single transaction with one confirmation. Preferred over multiple `update_cell` / `insert_cell` calls when changes are coordinated.

## Setup prerequisites

- Notebook open with target cells.

## Scenarios

### S1 - Multi-cell rename
Bundle updates; single confirm; COMPLETE content per cell.

### S2 - Insert + update combined
One batch handles both.

### S3 - Don't batch single change
Single → `update_cell`; batch for ≥2.

### S4 - Refactor across many cells
Discover affected; bundle all.

### S5 - Discover then batch-edit
T1: `search_files`. T2: batch update.

### S6 - Mixed insert+update+delete (DEFERRED)
### S7 - Large-batch atomic semantics (DEFERRED)

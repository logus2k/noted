# Tool: get_lint_diagnostics

**Type:** tool
**Tier:** read
**Domain:** linting
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns current linter diagnostics for the open file (errors + warnings with rule codes).

## Input schema

- No arguments.

## Setup prerequisites

- A linted file is open in the editor (Python via Ruff, JS via Biome).

## Scenarios

### S1 - Basic lint check
"any warnings?" → `get_lint_diagnostics`; do NOT auto-fix.

### S2 - Suggest fix path
Mention `fix_lint_issues` as next step.

### S3 - Rule code lookup
"what's F401?" → find entries; explain (unused import); quote lines.

### S4 - Summary
Count by severity; group by rule code.

### S5 - Pre-flight before fix
T1: diagnostics. T2: "fix them all" → `fix_lint_issues`.

### S6 - Hundreds of warnings (DEFERRED)
### S7 - Multi-language file (DEFERRED)

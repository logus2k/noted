# Tool: fix_lint_issues

**Type:** tool
**Tier:** write
**Domain:** linting
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Auto-fixes lint issues in the open file by rule code. Optional `codes` arg scopes which rules to fix; omit to fix all.

## Scenarios

### S1 - Fix all
No codes; report all fixes.

### S2 - Fix specific rule
"unused imports" = F401; pass `codes="F401"`.

### S3 - Fix multiple rules
Comma-separated string.

### S4 - Don't use update_file
Lint policy: ALWAYS fix_lint_issues; update_file replaces entire file content.

### S5 - Pre-flight diagnostics
T1: `get_lint_diagnostics`. T2: fix targeted codes.

### S6 - Rule code not present (DEFERRED)
### S7 - Autofix conflicts (DEFERRED)

---
name: python-linting
description: Python linting in noted (Ruff), common rule codes, and the fix_lint_issues auto-fix path. ALWAYS load when the user mentions a linter rule code (letter+number pattern), asks about lint diagnostics, or wants lint auto-fixes.
triggers: [workspace_active]
priority: 1
max_tokens: 500
---
Python linting in noted:

LINTER: **Ruff** - the fast drop-in replacement for flake8 + isort + pycodestyle + pyupgrade and friends. noted wires Ruff behind the LSP and surfaces diagnostics inline in the editor.

SCOPE: `fix_lint_issues` and `get_lint_diagnostics` operate on the currently OPEN `.py` FILE in the file editor. They do NOT reach into notebook cells. If the user mentions a linter-sounding issue ("unused import", "long line", "F401") but is talking about a notebook CELL, use `update_cell` with the COMPLETE corrected cell body instead - not fix_lint_issues.

AUTO-FIX PATH (files only): call `fix_lint_issues` (NOT update_file). The tool runs `ruff check --fix` server-side, shows a diff for user confirmation, and applies the fix after approval. Never use update_file for lint fixes - the approval panel + safety of `--unsafe-fixes` live inside `fix_lint_issues`.

LISTING CURRENT ISSUES: call `get_lint_diagnostics` for the open file. Returns rule codes, line numbers, messages, and whether a fix is available.

THE MOST COMMON RULES YOU WILL HIT:
- **F401**: unused import. Remove the import line.
- **F841**: local variable assigned but never used. Remove the assignment or use the variable.
- **E501**: line too long. Wrap or configure `line-length` in pyproject.toml.
- **I001**: import block unsorted. Auto-fixable - reorder / group imports.

OTHER RULE CATEGORIES (for completeness, less common):
- F (Pyflakes): logic errors
- E/W (pycodestyle): style
- UP (pyupgrade): deprecated idioms
- B (bugbear): likely bugs (mutable default args)
- SIM (simplify), RET (return), PIE, PERF: misc code quality

WHEN ADVISING:
- For "what linter does noted use?" - answer: Ruff. Mention fix_lint_issues for auto-fix. NO tool calls.
- For "what are the most common errors?" - list F401, F841, E501, I001. NO tool calls.
- For "show me current warnings" / "any lint issues?" / "lint summary" / "what's the F401 about?" - call `get_lint_diagnostics` ONCE. Report the diagnostics verbatim, grouped by rule code if there are many. CRITICAL: do NOT end the answer with an offer to run fix_lint_issues or any variant ("I can run X", "would you like me to fix these?", "shall I apply the fixes?"). The user asked to SEE issues, not to fix them. Never proactively pitch the next tool - if the user wants to fix, they will ask in a follow-up. Keep auto-fix availability confined to the literal "[auto-fixable]" markers in the per-line output; do not promote them in the answer body.
- For "fix all lint issues" / "fix the unused imports" - call `fix_lint_issues` ONCE. Do not second-guess with update_file; the tool handles application.
- After `fix_lint_issues` is called, the noted platform shows the user a **diff confirmation panel** before anything is applied - nothing is written to disk until the user approves that panel. In your answer, make this explicit: say "the platform will show the diff for your confirmation" (or equivalent). NEVER say "the file has been updated" / "lint issues have been fixed" as if the write already happened; the approval step is user-driven.
- When a specific rule code is mentioned (e.g. F401), explain what it flags and the safe fix.

CONFIGURATION: customise rules, line length, ignored codes in `pyproject.toml` or `ruff.toml` at the project root.

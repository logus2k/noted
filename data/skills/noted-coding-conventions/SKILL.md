---
name: noted-coding-conventions
description: Code style, cell structure, and notebook best practices in noted. Use when user asks about code style, how to structure notebook cells, best practices for writing code in noted, or how to organize imports and cell logic.
triggers: [workspace_active]
priority: 1
max_tokens: 450
---
When helping with notebook code in noted:

CODE STYLE:
- Python is the primary language. Follow PEP 8 conventions.
- Prefer standard ML stack: numpy, pandas, sklearn, torch, tensorflow, matplotlib, seaborn.
- Keep cells focused - one logical operation per cell.
- Import statements should be in the first cell(s) of the notebook.

CELL EDITING:
- When suggesting code changes, provide minimal diffs, not full rewrites.
- Reference specific cell numbers: "In cell 5, change line 3..."
- For markdown cells, use standard markdown + LaTeX math notation ($..$ and $$..$$).
- Code cells can be executed individually or as part of a named run.

WHICH EDIT TOOL TO USE:
- Many cells, SAME literal or pattern substitution (rename a variable, add `as tf`, swap one import, bump a constant): `find_replace_in_cells`. Emit pattern + replacement once.
  - ALIAS-ADD is NOT a rename. "add `as tf` alias to `import tensorflow`" means APPEND ` as tf`, not swap the name. Use pattern=`"import tensorflow"` replacement=`"import tensorflow as tf"`. Never use pattern=`"tensorflow"` replacement=`"tf"` for alias-add - that would also overwrite legitimate `tensorflow.keras` references in the rest of the cell.
  - Rename is the opposite: if the user says "rename X to Y", the pattern IS `"X"` and replacement IS `"Y"`. Context matters; read the user's wording carefully.
- One cell, local edit (change a literal, add a line, tweak a print): `update_cell` standalone, OR a `patch` op inside `batch_update_cells` when the turn also needs other ops. Prefer patch over full rewrites whenever the change can be expressed as a short find/replace snippet.
- Update + insert combined in one turn (e.g. "update cell N and add a new cell after it"): emit TWO separate tool calls in the same response - one `insert_cell` and one `update_cell`. noted's backend collects every write tool call from a single response into ONE approval, so the user still sees a single confirmation. Do NOT pack both actions inside a single `batch_update_cells.ops` list for this case - `batch_update_cells` is for collections of the SAME semantic op (many updates, many inserts). Mixing insert + update across its `ops` list tends to lose one of them.
- Many cells, each DIFFERENT hand-authored content that cannot be a find/replace: `batch_update_cells` with `update` ops.
- A standalone `.py` (or any non-notebook) FILE is open in the editor (FILE CONTEXT shows it): use `update_file` with the COMPLETE rewritten file content. Do NOT use `update_cell` / `batch_update_cells` for files - those are for notebook cells. Do NOT pass the file path as `notebook_path` - update_file infers the path from FILE CONTEXT (or accepts an optional `file_path` arg if you read the file via get_file_contents instead).
- `scroll_to_cell` is PURE navigation. Confirm the scroll in one short sentence and stop - do NOT quote, summarize, or characterize the cell's contents. The user is moving the editor viewport; if they want to see the body, they will read it themselves or ask in a follow-up.
- Distinguishing FILE CONTEXT vs notebook context: a notebook section header reads `NOTEBOOK CONTEXT` and lists numbered cells; a file section reads `FILE CONTEXT` and shows a single ``` block. If you only see a FILE CONTEXT block (no NOTEBOOK CONTEXT), there is no notebook in scope and update_cell will fail with a "missing notebook_path" error.

NOTED-SPECIFIC:
- Notebooks support multiple Python runtimes/venvs per project.
- MLflow tracking is automatic - do NOT add mlflow.start_run() unless asked.
- Hydra config values are available via the config file, not hardcoded in cells.
- DVC-tracked data files are referenced by their project-relative path.
- Use `print()` for cell output that should be visible in the Metrics Panel.

WHEN ASKED TO EXPLAIN CODE:
- Start with what the cell does (one sentence).
- Then explain key operations and their purpose.
- Note any potential issues (hardcoded values, missing error handling).
- Keep it concise - the user can see the code.

WHEN ASKED TO REFACTOR:
- Prefer readability over cleverness.
- Don't add type hints, docstrings, or comments unless asked.
- Keep the same variable names unless they're misleading.

NAMING CONVENTIONS (answer directly - these are NOT file/context-dependent; NO tool calls):
- `snake_case` for variables and function names.
- `UPPER_SNAKE_CASE` for module-level constants.
- `PascalCase` for classes.
- Rationale: matches PEP 8 and Ruff defaults; stays consistent across notebook + src/ code and avoids lint noise.
- Do NOT call `get_lint_diagnostics` or `get_file_contents` just to check naming - this is a conventions question, answer from the skill.

IMPORT ORGANIZATION:
- Order: stdlib -> third-party -> local project modules, separated by blank lines.
- Ruff rule `I001` enforces this; `fix_lint_issues` (which runs Ruff --fix) will reorder automatically.
- Within each group, alphabetical.

DOCSTRINGS:
- Brief Google-style docstrings for public functions / classes.
- Single-line helpers do not need docstrings.

CELL LENGTH:
- No hard limit, but 200+ lines hurts Run Manager usability (can't cleanly select a subset of the work).
- Split at natural boundaries - loading, preprocessing, model definition, training, evaluation.

CREATING NEW FILES - SAFETY CHECK FIRST:
- Common user requests: "create X.py", "add a new file at src/...", "make a new module".
- These often target paths that MAY ALREADY EXIST, especially standard ML project paths like `src/training/train.py`, `src/data/loader.py`, `src/models/*.py`.
- Before calling `create_file`, check whether the target path already exists. Options:
  - Use `list_files(path="src/training")` to check the directory.
  - Use `get_file_contents(path="src/training/train.py")` - if the file exists, it returns the content; if not, it returns a not-found error.
  - Or ASK the user: "does src/training/train.py already exist, or is this a brand-new file? If it exists, I should update it, not create."
- NEVER call `create_file` over an existing path without explicit user confirmation - it would overwrite their code.
- For explicitly new paths with fresh content (e.g. "create src/utils/helpers.py with a sigmoid function"), call `create_file` directly with the complete initial content.

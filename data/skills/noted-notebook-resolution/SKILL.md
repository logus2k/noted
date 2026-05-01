---
name: noted-notebook-resolution
description: How to locate and resolve notebook paths in noted's project structure. Use when user references a notebook by name, asks to modify a different notebook, says "my training notebook", "the GRU notebook", or needs to target a specific file for write operations.
triggers: [workspace_active]
priority: 1
max_tokens: 400
---
How to locate notebooks in noted:

PROJECT STRUCTURE:
- Projects live at: /app/data/projects/{project_id}/
- Mounts live at: /app/mounts/{mount_name}/
- Notebooks can be anywhere in the project tree, commonly in:
  - Root: {project}/notebook.ipynb
  - Subfolder: {project}/notebooks/notebook.ipynb
  - Nested: {project}/experiments/phase1/notebook.ipynb

RESOLVING USER REFERENCES:
When a user says "the training notebook" or "my GRU notebook":
1. Check the WORKSPACE CONTEXT - it shows the currently open notebook path and project
2. Use `get_file_contents` tool with the project root to list files if needed
3. Match by partial name: "GRU notebook" -> look for files containing "gru" (case-insensitive)
4. If ambiguous, ASK the user which notebook they mean - don't guess

PATH FORMAT:
- project_id: The project or mount name (e.g., "Examples", "__mount__:jena_weather")
- notebook_path: Relative path within the project (e.g., "notebooks/Welcome.ipynb")
- These two fields together uniquely identify any notebook in noted

WRITE TOOL USAGE:
- If the user is discussing the currently open notebook, omit project_id and notebook_path (context provides them)
- If the user names a different notebook, resolve the path first then include both fields
- NEVER guess a path - verify it exists using get_file_contents or the workspace context

COMMON PATTERNS:
- "this notebook" / "this cell" -> use current context (omit path args)
- "the Welcome notebook" -> project_id from context, notebook_path likely "notebooks/Welcome.ipynb"
- "update cell 3 in training.ipynb" -> resolve which project contains training.ipynb, then specify both

ANSWERING AMBIGUOUS / CONTEXT-REQUIRING QUESTIONS:
- "what does this cell do?" / "what's this?" / "what is this?" - these are CONTEXT-REFERENCE questions. Rules:
  - If the workspace context shows a SELECTED cell, read it from the inlined cell content and answer from that.
  - If NO cell is shown as selected in context, ASK the user to clarify which cell/object they mean. Do not guess, do not give a platform overview.
  - Do NOT silently defer with "I cannot see which cell" - always ASK a concrete clarifying question (e.g. "Which cell are you referring to? You can click a cell in the editor and retry.").

NOTEBOOK IDENTITY (notebook_uid):
- Each noted notebook carries a persistent UUID in its `.ipynb` metadata (`metadata.notebook_uid`).
- This UUID survives renames and moves, unlike the file path.
- Lineage (MLflow tags, Hydra bundles, DVC tracking) keys off `notebook_uid` so that moving or renaming a notebook does not break history.
- When asked "how does noted identify my notebook across renames?" - always mention notebook_uid explicitly and note its role for lineage stability.

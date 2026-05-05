"""LLM Tool Definitions and Dispatch - enables LLM to query noted's workspace.

Tools are described in the system prompt. The LLM invokes them by outputting
a <tool_call> JSON block. The backend parses it, executes via the appropriate
manager, and feeds the result back for the LLM to incorporate.
"""

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)


# Speculative-retrieval cache hit threshold. The chat router fires a
# graph_and_vector_search using the user's verbatim message as the
# question; the model then rephrases lightly when constructing its
# actual tool_call (e.g. "Explain me X" → "What is X?"). Strict
# equality misses these. Token-set Jaccard (after stopword/punct
# filter) catches them: same nouns + same intent. Threshold 0.7 is
# permissive enough for "explain X" ↔ "what is X" while strict enough
# to reject genuinely different questions about overlapping topics.
SPECULATIVE_MATCH_THRESHOLD = 0.7

# Common English stopwords that don't carry retrieval signal. Kept
# small + tight to avoid over-filtering. The reranker does the heavy
# semantic work; this set just stops "the/of/a" from inflating Jaccard.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "for",
    "from", "has", "have", "in", "is", "it", "its", "me", "of", "on",
    "or", "so", "that", "the", "this", "to", "was", "what", "when",
    "where", "which", "who", "why", "with", "you",
})


def _question_key_tokens(s: str) -> set:
    """Lowercase + tokenize + drop stopwords + drop tokens shorter than
    3 chars (typically articles or noise). Returns a set for Jaccard."""
    return {t for t in re.findall(r"\w+", (s or "").lower())
            if len(t) > 2 and t not in _STOPWORDS}


def _question_match_ratio(spec_q: str, actual_q: str) -> float:
    """Token-set Jaccard similarity. Returns 1.0 on exact-string match
    (cheap fast-path) and 0.0 if either input has no key tokens."""
    if not spec_q or not actual_q:
        return 0.0
    if spec_q == actual_q:
        return 1.0
    s = _question_key_tokens(spec_q)
    a = _question_key_tokens(actual_q)
    if not s or not a:
        return 0.0
    return len(s & a) / len(s | a)


# ── Tool Definitions (injected into system prompt) ────────────────

TOOL_DESCRIPTIONS = """
Available tools (invoke by outputting a <tool_call> block):

MLflow:
1. get_experiment_runs - List recent MLflow runs for an experiment
   Args: {"experiment_name": "string"}
2. get_run_details - Get full details for a specific MLflow run
   Args: {"run_id": "string"}
3. compare_runs - Compare two MLflow runs side by side
   Args: {"run_id_a": "string", "run_id_b": "string"}

Airflow:
4. list_dags - List all Airflow DAGs (pipelines)
   Args: {} (no args required)
5. get_dag_status - Get DAG details and recent runs
   Args: {"dag_id": "string"}
6. get_task_log - Get log output from a specific task in a DAG run
   Args: {"dag_id": "string", "dag_run_id": "string", "task_id": "string"}

DVC:
7. get_dvc_data_overview - List all DVC-tracked data files across projects
   Args: {} (no args required)
8. get_dvc_file_history - Get version history for a DVC-tracked file
   Args: {"repo_path": "string", "dvc_file": "string"}

Files & Config:
9. get_file_contents - Read a file from the current project. The path is resolved automatically from the active project context.
   Args: {"path": "string (relative path, e.g. src/training/train.py)", "max_lines": number (optional, default 100)}
10. list_files - List files in a project directory, with optional glob pattern
    Args: {"project_id": "string", "path": "string (optional, subdirectory)", "pattern": "string (optional, e.g. *.py)"}
11. search_files - Search file contents across the project (grep-like)
    Args: {"project_id": "string", "query": "string", "path": "string (optional, subdirectory)", "file_pattern": "string (optional, e.g. *.py)", "max_results": number (optional, default 20)}
12. get_hydra_config - Get the resolved Hydra configuration
    Args: {"project_id": "string"}

Knowledge Graph:
13. query_knowledge_graph - Query the project knowledge graph for entity relationships
    Args: {"project_id": "string"}

Notebook:
14. get_notebook_cells - Read cells from a notebook
    Args: {"project_id": "string", "notebook_path": "string", "indices": [array of cell indices, optional], "from_index": number (optional), "to_index": number (optional), "include_outputs": boolean (optional, default false)}
    Default (no range args): reads the entire notebook. Pass indices/from_index/to_index only when you need a specific subset. Result is capped at 80,000 chars; if truncated, the response tells you where to resume with from_index.
15. scroll_to_cell - Scroll the notebook editor to make a specific cell visible and select it. Use this when the user asks to "show", "navigate to", "go to", or "highlight" a cell.
    Args: {"cell_index": number (1-based, matches the numbers shown in WORKSPACE CONTEXT)}

Skills:
16. get_skill - Load detailed instructions for a specific topic. IMPORTANT: check the ACTIVE SKILLS section of the workspace context FIRST - any skill listed there is already loaded in your context; calling get_skill for it is a redundant fetch and wastes tokens. Only call this tool for skills NOT currently listed as active.
    Args: {"skill_name": "string", "reference": "string (optional, for loading reference docs)"}

Agents:
17. run_agent - Delegate a heavy reading/exploration task to a subagent that runs in a fresh context window (no history). Use this WHEN any of these triggers fire:
    (a) the user explicitly asks for a subagent / "run a subagent" / "use the notebook-explorer subagent" / "delegate this" - take it literally, do not substitute a direct tool call even when one would also work.
    (b) the user asks for a multi-file summary, codebase overview, or "across all relevant files / the project / the codebase" wording (e.g. "summarize how the project trains and evaluates models across all relevant files", "give me a project overview", "what does this codebase do"). The subagent reads the files in its own context and returns a compact summary, sparing the main context.
    (c) summarizing a whole notebook in one shot.
    Args: {"task": "string (detailed task description)", "agent_name": "string"}
    Available agents: notebook-explorer (reads notebooks/files, returns a concise summary)
    Note: Requires Anthropic API. Always uses Haiku for speed. Results are compact summaries, not raw content.

Write (require user confirmation):
18. update_cell - Modify a single notebook cell
    Args: {"cell_index": number (1-based, matches the numbers shown in WORKSPACE CONTEXT), "new_content": "string", "description": "string", "project_id": "string (optional)", "notebook_path": "string (optional)"}
19. insert_cell - Insert a new cell
    Args: {"after_cell_index": number (1-based; use 0 to insert at the top), "cell_type": "code"|"markdown", "content": "string", "description": "string", "project_id": "string (optional)", "notebook_path": "string (optional)"}
20. batch_update_cells - Apply the SAME kind of op to MULTIPLE cells in one confirmation. REQUIRES at least 2 ops in the `ops` list - this tool exists to amortize the cost of batched edits, so single-op batches are wrong. For ANY single-op edit, use the op-specific tool directly: `update_cell` for one update, `insert_cell` for one insert, `update_cell` (with full new content) for one patch. All items in `ops` MUST share an op type: either all "update" (each cell gets different custom content), all "patch" (local find/replace inside each cell), or all "insert" (several new cells in one shot). For a mixed insert+update in the same turn, do NOT stuff them into one batch_update_cells call - emit separate `insert_cell` and `update_cell` tool calls; noted's backend batches multi-write-call turns into one approval automatically. For same-edit-across-many-cells (renames, alias adds, import swaps) prefer find_replace_in_cells.
    Args: {"ops": [{"op": "update", "cell_index": number (1-based), "new_content": "string", "description": "string"} | {"op": "patch", "cell_index": number (1-based), "find": "string", "replace": "string", "description": "string"} | {"op": "insert", "after_cell_index": number (1-based; 0 = top), "cell_type": "code"|"markdown", "content": "string", "description": "string"}], "description": "string", "project_id": "string (optional)", "notebook_path": "string (optional)"}
    The `ops` list is ordered; it must contain AT LEAST 2 items (single-op cases must use update_cell / insert_cell directly). Every item MUST set `op` explicitly so the backend knows how to interpret it.
20b. find_replace_in_cells - Apply the SAME literal substring (or regex) substitution across one or many cells. The backend reads each cell and rewrites it; you only emit the pattern and replacement. Use for renames ("X" -> "features"), alias adds ("import tensorflow" -> "import tensorflow as tf"), constant bumps, etc. Much shorter to emit than batch_update_cells when the edit is structurally uniform.
    Args: {"pattern": "string", "replacement": "string", "cell_indices": [array of 1-based ints, optional], "is_regex": boolean (optional, default false), "description": "string", "project_id": "string (optional)", "notebook_path": "string (optional)"}
21. update_file - Modify a .py or other text file. If the file is already open in the editor (its content appears under FILE CONTEXT) the file_path is inferred and you only need new_content + description. If the file is NOT open but you've just read it via get_file_contents, pass the same path back as file_path so the executor knows which file to write.
    Args: {"new_content": "string (complete file content)", "description": "string", "file_path": "string (optional - required only when the file is not open in the editor)"}
22. create_file - Create a new file in the project
    Args: {"file_path": "string", "content": "string", "description": "string", "project_id": "string (optional)"}
23. get_lint_diagnostics - Get current linter diagnostics (errors, warnings) for the currently open Python file. Returns rule codes, messages, line numbers, and available auto-fixes.
    Args: {} (no args - uses the file from context)
24. fix_lint_issues - Auto-fix lint issues in the open Python file. ALWAYS use this for lint/linting fixes. NEVER use update_file for lint fixes.
    Args: {"codes": "string (optional, e.g. 'F401' or 'F401,PIE790' to fix specific rules only)"}

To call a tool, output EXACTLY this format:
<tool_call>{"name": "tool_name", "args": {"arg1": "value1"}}</tool_call>

CRITICAL RULES:
- Output NOTHING after the </tool_call> closing tag. Stop completely. The system executes the tool and resumes the conversation with the result.
- Do NOT simulate, predict, or describe the tool result. Do NOT write "Tool result:", "Done!", or any follow-up before the system provides the actual result.
- For READ tools (get_file_contents, get_run_details, list_*, etc.): call ONE at a time and wait for the result before calling another - later reads usually depend on earlier ones.
- For WRITE tools (insert_cell, update_cell, update_file, create_file, fix_lint_issues, find_replace_in_cells): emitting MULTIPLE write tool calls in the SAME response is the preferred pattern when the user asked for multiple actions. The backend collects every write tool call from one response into a SINGLE approval, so the user sees one confirmation dialog regardless of how many calls were emitted.
- For write tools: include the COMPLETE new cell content, not just the changed lines. Provide a brief description of what you are about to change and why, then output the tool call. IMPORTANT: write tools are NOT applied automatically — the user must approve them first. Never say "Done" or use past tense before a write tool call. Say "I'll make the following changes" or similar.
- NEVER use update_file to fix lint issues. ALWAYS use fix_lint_issues instead — it runs the fix server-side and only needs the rule codes.
- When modifying many cells that all receive the SAME custom content: use batch_update_cells (or find_replace_in_cells for uniform substitutions). Never call update_cell multiple times in a row with different custom bodies - that produces multiple approvals and multiple tokens of overhead.
- For uniform edits across cells (rename a variable, add an alias, bump a constant, swap one import for another), call find_replace_in_cells with a pattern+replacement. It is shorter and less error-prone than retyping every cell's body in batch_update_cells.
- For an insert plus an update in the same turn (e.g. "update cell N and add a new cell after it"): emit insert_cell AND update_cell as two separate tool calls in the same response. DO NOT pack both into a single batch_update_cells call - batch_update_cells is for homogeneous batches (same op type repeated across cells) only. Mixed ops inside one batch_update_cells.ops list has been observed to lose ops.
- When the user explicitly mentions "subagent", "agent", "delegate", "run a subagent", "use the notebook-explorer", or any equivalent phrasing, you MUST use the `run_agent` tool. Do not substitute a "more direct" tool like `search_files` or `get_notebook_cells` even when one would also work - the user asked for the delegation path. Picking a different tool is a procedural failure.
- When the user asks a SCHEMA / SHAPE / OUTPUT-FORMAT / "what does the endpoint expect" / shape-error-diagnostic question about a deployed model, call get_serving_schema ONCE, report the schema, and STOP. NEVER append a "you can call invoke_model() for a smoke test" sentence - the user is constructing their own request or diagnosing, not asking to run the model. Pitching invoke_model in this context is a procedural failure.
- If project_id/notebook_path are omitted, the currently focused notebook is used.
- READ STRATEGICALLY: each tool call costs money. Use the minimum number of tool calls possible. To locate code (e.g. "where is the training loop?"), use search_files ONCE — it returns cell indices directly, so you can answer immediately without calling get_notebook_cells afterwards. Only call get_notebook_cells when the user needs to SEE the actual cell content. Never read cells sequentially or in multiple batches.
""".strip()


# ── Tool Registry ─────────────────────────────────────────────────

def get_tool_descriptions() -> str:
    """Return tool descriptions for injection into the system prompt."""
    return TOOL_DESCRIPTIONS


def parse_tool_call(text: str) -> Optional[dict]:
    """Parse the first <tool_call> block from the LLM response.

    Returns {"name": str, "args": dict} or None if no tool call found.
    """
    calls = parse_all_tool_calls(text)
    return calls[0] if calls else None


_ALL_TOOL_NAMES = {
    'update_cell', 'insert_cell', 'batch_update_cells', 'find_replace_in_cells', 'update_file', 'create_file',
    'get_experiment_runs', 'get_run_details', 'list_run_artifacts', 'get_serving_status', 'get_serving_schema', 'invoke_model', 'deploy_model', 'list_registered_models', 'list_model_versions', 'register_model', 'set_model_alias', 'compare_runs', 'get_file_contents',
    'get_hydra_config', 'list_dags', 'get_dag_status', 'get_task_log',
    'get_dvc_data_overview', 'get_dvc_file_history', 'query_knowledge_graph',
    'get_skill', 'list_files', 'search_files', 'get_notebook_cells', 'run_agent',
    'scroll_to_cell', 'get_lint_diagnostics', 'fix_lint_issues', 'fetch_url', 'web_search',
    'list_projects',
}


def _extract_balanced_json(text: str, start: int) -> int:
    """Find the end of a balanced JSON object starting at `start`. Returns end index or -1."""
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == '\\':
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def parse_all_tool_calls(text: str) -> list:
    """Parse tool calls from LLM response.

    Supports both <tool_call>{...}</tool_call> blocks and raw JSON {\"name\": ...} objects.
    Returns list of {"name": str, "args": dict} dicts.
    """
    import re
    results = []

    # 1. Try <tool_call> blocks first
    for match in re.finditer(r'<tool_call>\s*(\{)', text):
        start = match.start(1)
        end = _extract_balanced_json(text, start)
        if end < 0:
            continue
        json_str = text[start:end]
        after = text[end:end+20].strip()
        if not after.startswith('</tool_call>'):
            continue
        try:
            call = json.loads(json_str)
            if "name" in call and "args" in call:
                results.append(call)
            elif "name" in call:
                name = call.pop("name")
                results.append({"name": name, "args": call})
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool call JSON: %s", json_str[:200])

    if results:
        return results

    # 2. Fallback: detect raw JSON with "name" matching a known tool
    for match in re.finditer(r'\{\s*"name"\s*:\s*"(\w+)"', text):
        if match.group(1) not in _ALL_TOOL_NAMES:
            continue
        start = match.start()
        end = _extract_balanced_json(text, start)
        if end < 0:
            continue
        try:
            call = json.loads(text[start:end])
            if "name" in call:
                name = call.get("name")
                args = call.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                results.append({"name": name, "args": args})
        except json.JSONDecodeError:
            continue

    return results


# Write tools that require user confirmation before execution
WRITE_TOOLS = {"update_cell", "insert_cell", "batch_update_cells", "find_replace_in_cells", "update_file", "create_file", "fix_lint_issues"}


def is_write_tool(tool_call: dict) -> bool:
    """Check if a tool call requires user confirmation."""
    return tool_call.get("name", "") in WRITE_TOOLS


async def prepare_write_action(tool_call: dict, managers: dict, ctx: dict) -> dict:
    """Prepare a write action for user confirmation (does not execute).

    Args:
        tool_call: {"name": str, "args": dict}
        managers: Dict of manager instances
        ctx: Context descriptor with project_id, notebook_path

    Returns:
        Dict with action details for the frontend confirmation panel:
        {"id": str, "tool": str, "args": dict, "current_content": str|None,
         "project_id": str, "notebook_path": str}
    """
    import uuid

    name = tool_call["name"]
    args = tool_call.get("args", {})

    # Always use context values - LLM often sends incorrect/placeholder project_id and notebook_path
    project_id = ctx.get("project_id", "") or args.get("project_id", "")
    notebook_path = ctx.get("notebook_path", "") or args.get("notebook_path", "")

    action = {
        "id": str(uuid.uuid4()),
        "tool": name,
        "args": args,
        "project_id": project_id,
        "notebook_path": notebook_path,
        "current_content": None,
    }

    # For update_cell, fetch current cell content for diff
    if name == "update_cell":
        # LLM sends 1-based cell_index; convert to 0-based for array access
        cell_index_1 = int(args.get("cell_index", 0))
        cell_index = cell_index_1 - 1 if cell_index_1 > 0 else -1
        # Store 0-based index in args for the frontend/executor
        args["cell_index"] = cell_index
        notebook_mgr = managers.get("notebook")
        logger.info("prepare_write: cell_index=%s (1-based: %s) project_id=%r notebook_path=%r mgr=%s",
                     cell_index, cell_index_1, project_id, notebook_path, notebook_mgr is not None)
        if notebook_mgr and project_id and notebook_path:
            try:
                notebook = notebook_mgr.get_notebook(project_id, notebook_path)
                cells = notebook.get("cells", [])
                logger.info("prepare_write: found %d cells, requesting index %d", len(cells), cell_index)
                if 0 <= cell_index < len(cells):
                    action["current_content"] = cells[cell_index].get("source", "")
                    if isinstance(action["current_content"], list):
                        action["current_content"] = "".join(action["current_content"])
                    action["cell_type"] = cells[cell_index].get("cell_type", "code")
                    logger.info("prepare_write: got current_content (%d chars)", len(action["current_content"]))
            except Exception as e:
                logger.warning("Failed to fetch cell content for diff: %s", e)
        else:
            logger.warning("prepare_write: missing mgr=%s project=%r path=%r",
                          notebook_mgr is not None, project_id, notebook_path)

    # For update_file, include current file content from context for diff.
    # The file_path is normally taken from ctx (the file open in the editor),
    # but we also accept an explicit file_path arg from the model for
    # multi-turn flows where get_file_contents named the target without
    # opening it (no FILE CONTEXT is set in that case).
    if name == "update_file":
        current = ctx.get("file_content", "")
        if current:
            action["current_content"] = current
        explicit_path = (args.get("file_path") or "").strip()
        action["file_path"] = explicit_path or ctx.get("file_path", "")

    # For fix_lint_issues, generate the fixed content server-side using ruff
    if name == "fix_lint_issues":
        import subprocess
        content = ctx.get("file_content", "")
        file_path = ctx.get("file_path", "")
        notebook_path_ctx = ctx.get("notebook_path", "")
        codes = args.get("codes", "")

        # If ctx doesn't carry in-memory content, read from disk so the fix
        # path still works in tests and saved-state scenarios.
        if not content and file_path and project_id:
            file_mgr_inst = managers.get("files")
            if file_mgr_inst:
                try:
                    from app.managers.project_registry import get_registry as _get_reg
                    registry = _get_reg()
                    root_type = "mount" if registry.is_mount(project_id) else "project"
                    _res = file_mgr_inst.read_file(root_type, project_id, file_path)
                    if isinstance(_res, dict):
                        content = _res.get("content", "") or ""
                    elif isinstance(_res, str):
                        content = _res
                except Exception as e:
                    logger.warning("fix_lint_issues disk-fallback failed: %s", e)

        if content and file_path:
            # File mode
            cmd = ["ruff", "check", "--preview", "--fix", "--unsafe-fixes", "--stdin-filename", file_path, "-"]
            if codes:
                cmd.extend(["--select", codes])
            try:
                result = subprocess.run(cmd, input=content, capture_output=True, text=True, timeout=10)
                fixed = result.stdout if result.stdout else content
                # Keep the model's original tool name AND its original args so
                # the harness/judge see what the model actually asked for.
                # executor_tool + executor_args carry the transformation used
                # internally for execution.
                action["executor_tool"] = "update_file"
                action["executor_args"] = {"new_content": fixed, "description": f"Auto-fix lint issues ({codes or 'all rules'})"}
                action["current_content"] = content
                action["file_path"] = file_path
            except Exception as e:
                logger.error("fix_lint_issues failed: %s", e)

        elif notebook_path_ctx and not file_path:
            # Notebook mode: fix each code cell, return as update_cell actions
            logger.info("fix_lint_issues: notebook mode for %s", notebook_path_ctx)
            notebook_mgr_inst = managers.get("notebook")
            if notebook_mgr_inst:
                try:
                    nb = notebook_mgr_inst.get_notebook(project_id, notebook_path_ctx)
                    nb = notebook_mgr_inst.prepare_for_wire(nb)
                    extra = []
                    for i, cell in enumerate(nb.get("cells", [])):
                        if cell.get("cell_type") != "code":
                            continue
                        src = cell.get("source", "")
                        if not src.strip():
                            continue
                        cmd = ["ruff", "check", "--preview", "--fix", "--unsafe-fixes", "--stdin-filename", f"cell_{i}.py", "-"]
                        if codes:
                            cmd.extend(["--select", codes])
                        res = subprocess.run(cmd, input=src, capture_output=True, text=True, timeout=10)
                        fixed = res.stdout if res.stdout else src
                        if fixed != src:
                            extra.append({
                                "id": str(uuid.uuid4()),
                                "tool": "update_cell",
                                "args": {"cell_index": i, "new_content": fixed,
                                         "description": f"Fix lint ({codes or 'all'}) in cell {i + 1}"},
                                "current_content": src,
                                "project_id": project_id,
                                "notebook_path": notebook_path,
                            })
                    logger.info("fix_lint_issues: %d cells changed", len(extra))
                    if extra:
                        # Preserve the original tool name (fix_lint_issues);
                        # executor_tool/args carry the underlying implementation.
                        first = extra[0]
                        action["executor_tool"] = "update_cell"
                        action["executor_args"] = first["args"]
                        action["current_content"] = first.get("current_content")
                        if len(extra) > 1:
                            action["_extra_actions"] = extra[1:]
                except Exception as e:
                    logger.error("fix_lint_issues (notebook) failed: %s", e)

    # For create_file, no current content (it's new)
    if name == "create_file":
        action["file_path"] = args.get("file_path", "")

    return action


async def expand_batch_tool(tool_call: dict, managers: dict, ctx: dict) -> list:
    """Expand a batch_update_cells call into individual update_cell and
    insert_cell actions.

    Accepts two argument shapes:

    1. New unified shape (preferred, easier for small models to emit
       reliably because it is one uniform array, not two named arrays):
           ops: [
             {op: "update", cell_index: N, new_content: "...", description: "..."},
             {op: "insert", after_cell_index: N, cell_type: "code", content: "...", description: "..."},
             ...
           ]

    2. Legacy shape (kept for back-compat while callers migrate):
           updates: [{cell_index, new_content, description}]
           inserts: [{after_cell_index, cell_type, content, description}]
           changes: [...]   # legacy alias for updates

    Gemma sometimes emits arrays as Python-style strings; we loose-parse
    them (json.loads -> ast.literal_eval -> give up).
    """
    args = tool_call.get("args", {})
    raw_ops = args.get("ops")
    raw_updates = args.get("updates", args.get("changes", []))
    raw_inserts = args.get("inserts", [])

    def _loose_parse(s: str):
        try:
            return json.loads(s)
        except Exception:
            pass
        try:
            import ast
            return ast.literal_eval(s)
        except Exception as e:
            logger.warning("batch_update_cells: could not decode string (%s): %r", e, s[:200])
            return None

    def _coerce_list(x):
        if x is None:
            return []
        if isinstance(x, str):
            parsed = _loose_parse(x)
            return parsed if isinstance(parsed, list) else []
        return x if isinstance(x, list) else []

    def _coerce_dict(x):
        if isinstance(x, str):
            parsed = _loose_parse(x)
            return parsed if isinstance(parsed, dict) else None
        return x if isinstance(x, dict) else None

    # Normalize both shapes into a single ordered list of typed items so the
    # emission code below has one path. Each item is a dict with an 'op' key.
    items: list[dict] = []
    if raw_ops is not None:
        for it in _coerce_list(raw_ops):
            d = _coerce_dict(it)
            if d is not None:
                items.append(d)
    else:
        for u in _coerce_list(raw_updates):
            d = _coerce_dict(u)
            if d is not None:
                d = {**d, "op": d.get("op") or "update"}
                items.append(d)
        for i in _coerce_list(raw_inserts):
            d = _coerce_dict(i)
            if d is not None:
                d = {**d, "op": d.get("op") or "insert"}
                items.append(d)

    if not items:
        return []

    def _infer_op(d: dict) -> str:
        op = str(d.get("op", "")).strip().lower()
        if op in ("update", "patch", "insert"):
            return op
        # Infer from present keys when 'op' is missing or malformed.
        if "find" in d and "replace" in d and "cell_index" in d:
            return "patch"
        if "cell_index" in d and "new_content" in d:
            return "update"
        if "after_cell_index" in d or ("cell_type" in d and "content" in d):
            return "insert"
        return ""

    # patch ops read current cell content from disk; load the notebook once.
    need_patch = any(_infer_op(it) == "patch" for it in items)
    patch_cells = None
    if need_patch:
        notebook_mgr = managers.get("notebook")
        project_id = ctx.get("project_id") if ctx else None
        notebook_path = ctx.get("notebook_path") if ctx else None
        if notebook_mgr and project_id and notebook_path:
            try:
                notebook = notebook_mgr.get_notebook(project_id, notebook_path)
                patch_cells = notebook.get("cells", [])
            except Exception as e:
                logger.warning("batch_update_cells: patch requires notebook load, which failed: %s", e)

    actions: list = []
    for it in items:
        op = _infer_op(it)
        if op == "update":
            try:
                ci_1 = int(it.get("cell_index", 0))
            except (TypeError, ValueError):
                ci_1 = 0
            if ci_1 <= 0:
                continue
            single_call = {
                "name": "update_cell",
                "args": {
                    # prepare_write_action expects 1-based.
                    "cell_index": ci_1,
                    "new_content": it.get("new_content", ""),
                    "description": it.get("description", ""),
                },
            }
            actions.append(await prepare_write_action(single_call, managers, ctx))
        elif op == "patch":
            if patch_cells is None:
                continue
            try:
                ci_1 = int(it.get("cell_index", 0))
            except (TypeError, ValueError):
                ci_1 = 0
            if ci_1 <= 0 or ci_1 > len(patch_cells):
                continue
            cell = patch_cells[ci_1 - 1]
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            if not isinstance(source, str):
                continue
            find = str(it.get("find", ""))
            replace = str(it.get("replace", ""))
            if not find or find not in source:
                continue
            new_content = source.replace(find, replace)
            single_call = {
                "name": "update_cell",
                "args": {
                    "cell_index": ci_1,
                    "new_content": new_content,
                    "description": it.get("description", f"patch cell {ci_1}"),
                },
            }
            actions.append(await prepare_write_action(single_call, managers, ctx))
        elif op == "insert":
            try:
                aci_1 = int(it.get("after_cell_index", it.get("after", 0)))
            except (TypeError, ValueError):
                aci_1 = 0
            if aci_1 < 0:
                aci_1 = 0
            cell_type = it.get("cell_type", "code")
            if cell_type not in ("code", "markdown"):
                cell_type = "code"
            single_call = {
                "name": "insert_cell",
                "args": {
                    # prepare_write_action expects 1-based; conversion happens at execution time.
                    "after_cell_index": aci_1,
                    "cell_type": cell_type,
                    "content": it.get("content", it.get("new_content", "")),
                    "description": it.get("description", ""),
                },
            }
            actions.append(await prepare_write_action(single_call, managers, ctx))
        # silently skip unclassifiable items; the final actions list
        # determines whether the caller sees a no-actions outcome.

    return actions


async def expand_find_replace_tool(tool_call: dict, managers: dict, ctx: dict) -> list:
    """Expand a find_replace_in_cells call into individual update_cell actions.

    Reads the current notebook, applies the pattern/replacement to each
    targeted cell, and builds one update_cell action per cell that actually
    changed. This keeps the model's tool emission to a short pattern string
    regardless of how many cells need editing.
    """
    args = tool_call.get("args", {})
    pattern = args.get("pattern", "")
    replacement = args.get("replacement", "")
    raw_indices = args.get("cell_indices") or []
    is_regex = bool(args.get("is_regex", False))
    overall_desc = args.get("description", "") or f"Replace '{pattern}' with '{replacement}'"

    if not isinstance(pattern, str) or not pattern:
        return []
    if not isinstance(replacement, str):
        replacement = str(replacement)

    # Parse cell_indices: model may send it as a list of ints, list of strs,
    # or a Python-literal string (Gemma quirk).
    if isinstance(raw_indices, str):
        import ast
        try:
            parsed = ast.literal_eval(raw_indices)
            raw_indices = parsed if isinstance(parsed, list) else []
        except Exception:
            raw_indices = []

    project_id = ctx.get("project_id") if ctx else None
    notebook_path = ctx.get("notebook_path") if ctx else None
    notebook_mgr = managers.get("notebook")
    if not (notebook_mgr and project_id and notebook_path):
        logger.warning("find_replace_in_cells: missing notebook manager or ctx (project_id=%r notebook_path=%r)",
                        project_id, notebook_path)
        return []

    try:
        notebook = notebook_mgr.get_notebook(project_id, notebook_path)
    except Exception as e:
        logger.warning("find_replace_in_cells: notebook load failed: %s", e)
        return []
    cells = notebook.get("cells", [])
    n_cells = len(cells)

    # Resolve target indices (0-based)
    if raw_indices:
        targets: list[int] = []
        for ci_1 in raw_indices:
            try:
                ci_1 = int(ci_1)
            except (TypeError, ValueError):
                continue
            if 1 <= ci_1 <= n_cells:
                targets.append(ci_1 - 1)
    else:
        targets = [i for i, c in enumerate(cells) if c.get("cell_type") == "code"]

    if is_regex:
        import re as _re
        try:
            rx = _re.compile(pattern)
        except _re.error as e:
            logger.warning("find_replace_in_cells: invalid regex %r: %s", pattern, e)
            return []

    actions: list = []
    skipped_1based: list[int] = []  # targeted cells whose source had no match
    matched_1based: list[int] = []  # targeted cells that produced an action
    for ci_0 in targets:
        cell = cells[ci_0]
        cell_1 = ci_0 + 1
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        if not isinstance(source, str):
            skipped_1based.append(cell_1)
            continue

        if is_regex:
            new_source, n_subs = rx.subn(replacement, source)
        else:
            n_subs = source.count(pattern)
            if n_subs == 0:
                new_source = source
            else:
                new_source = source.replace(pattern, replacement)

        if n_subs == 0 or new_source == source:
            skipped_1based.append(cell_1)
            continue

        matched_1based.append(cell_1)
        per_cell_desc = (f"{overall_desc} (cell {cell_1}, "
                         f"{n_subs} match{'es' if n_subs != 1 else ''})")
        single_call = {
            "name": "update_cell",
            "args": {
                # prepare_write_action expects the LLM's 1-based convention
                # and handles the 1 -> 0 conversion itself; feed it the
                # 1-based value so the downstream "Cell N updated" message
                # and frontend index stay consistent.
                "cell_index": cell_1,
                "new_content": new_source,
                "description": per_cell_desc,
            },
        }
        action = await prepare_write_action(single_call, managers, ctx)
        actions.append(action)

    # Surface the per-cell outcome so the model's follow-up answer can report
    # on every cell the user asked about, not just the ones that were rewritten.
    # Prefixing the first action's description means the "Cell N updated" tool
    # result the model sees for action 0 carries the full batch summary.
    if actions and skipped_1based:
        summary = (f"[batch summary] targeted cells {matched_1based + skipped_1based}; "
                   f"applied to {matched_1based}; "
                   f"skipped (pattern not present) {skipped_1based}. ")
        args0 = actions[0].get("args") or {}
        args0["description"] = summary + str(args0.get("description") or "")
        actions[0]["args"] = args0

    return actions


async def execute_write_tool(action: dict, managers: dict) -> str:
    """Execute a confirmed write action.

    Args:
        action: The pending action dict (from prepare_write_action)
        managers: Dict of manager instances

    Returns:
        String result to feed back to the LLM
    """
    # `executor_tool` is set when the user-facing tool name (e.g. fix_lint_issues)
    # maps to a different underlying executor (e.g. update_file). Fall back to
    # `tool` when no remap is needed.
    name = action.get("executor_tool") or action["tool"]
    args = action.get("executor_args") or action["args"]
    project_id = action["project_id"]
    notebook_path = action["notebook_path"]

    try:
        if name == "update_cell":
            return await _tool_update_cell(args, managers, project_id, notebook_path)
        elif name == "insert_cell":
            return await _tool_insert_cell(args, managers, project_id, notebook_path)
        elif name == "update_file":
            return await _tool_update_file(action, managers)
        elif name == "create_file":
            return await _tool_create_file(action, managers)
        else:
            return f"Error: Unknown write tool '{name}'"
    except Exception as e:
        logger.exception("Write tool execution failed: %s", name)
        return f"Error executing {name}: {type(e).__name__}: {e}"


async def execute_tool(tool_call: dict, managers: dict, ctx: dict = None) -> str:
    """Execute a read-only tool call and return the result as a string.

    Args:
        tool_call: {"name": str, "args": dict}
        managers: Dict of manager instances
        ctx: Optional context descriptor (project_id, file_path, etc.)

    Returns:
        String result to feed back to the LLM
    """
    name = tool_call["name"]
    args = tool_call.get("args", {})

    try:
        if name == "get_experiment_runs":
            return await _tool_get_experiment_runs(args, managers)
        elif name == "get_run_details":
            return await _tool_get_run_details(args, managers)
        elif name == "list_run_artifacts":
            return await _tool_list_run_artifacts(args, managers)
        elif name == "get_serving_status":
            return await _tool_get_serving_status(args, managers)
        elif name == "get_serving_schema":
            return await _tool_get_serving_schema(args, managers)
        elif name == "invoke_model":
            return await _tool_invoke_model(args, managers)
        elif name == "deploy_model":
            return await _tool_deploy_model(args, managers)
        elif name == "list_registered_models":
            return await _tool_list_registered_models(args, managers)
        elif name == "list_model_versions":
            return await _tool_list_model_versions(args, managers)
        elif name == "register_model":
            return await _tool_register_model(args, managers)
        elif name == "set_model_alias":
            return await _tool_set_model_alias(args, managers)
        elif name == "compare_runs":
            return await _tool_compare_runs(args, managers)
        elif name == "get_file_contents":
            return await _tool_get_file_contents(args, managers, ctx)
        elif name == "list_files":
            return await _tool_list_files(args, managers, ctx)
        elif name == "search_files":
            return await _tool_search_files(args, managers, ctx)
        elif name == "get_notebook_cells":
            return await _tool_get_notebook_cells(args, managers, ctx)
        elif name == "list_projects":
            return await _tool_list_projects(args, managers)
        elif name == "get_hydra_config":
            return await _tool_get_hydra_config(args, managers, ctx)
        elif name == "list_dags":
            return await _tool_list_dags(args, managers, ctx)
        elif name == "get_dag_status":
            return await _tool_get_dag_status(args, managers)
        elif name == "get_task_log":
            return await _tool_get_task_log(args, managers)
        elif name == "get_dvc_data_overview":
            return await _tool_get_dvc_data_overview(args, managers)
        elif name == "get_dvc_file_history":
            return await _tool_get_dvc_file_history(args, managers, ctx)
        elif name == "query_knowledge_graph":
            return await _tool_query_knowledge_graph(args, managers, ctx)
        elif name == "get_skill":
            return await _tool_get_skill(args, managers, ctx or {})
        elif name == "get_lint_diagnostics":
            return await _tool_get_lint_diagnostics(args, managers, ctx)
        elif name == "fix_lint_issues":
            return "This is a write tool - it should go through the approval panel."
        elif name == "run_agent":
            return await _tool_run_agent(args, managers, ctx)
        elif name == "fetch_url":
            return await _tool_fetch_url(args)
        elif name == "web_search":
            return await _tool_web_search(args)
        elif name == "search_docs":
            return await _tool_search_docs(args, managers)
        elif name == "research_topic":
            return await _tool_research_topic(args, managers)
        elif name == "graph_and_vector_search":
            # Speculation hook: if the chat router pre-fired this tool with
            # the same question, await the pre-fetched task instead of
            # running the retrieval again. Saves the retrieval-time portion
            # of stop #1 (the gap between thinking-end and "Show graph").
            spec = managers.get("_speculative") if isinstance(managers, dict) else None
            spec_q = (spec or {}).get("args", {}).get("question", "") if spec else ""
            actual_q = args.get("question", "") or ""
            match_ratio = _question_match_ratio(spec_q, actual_q) if spec else 0.0
            if (
                spec
                and spec.get("task") is not None
                and match_ratio >= SPECULATIVE_MATCH_THRESHOLD
            ):
                import time as _t
                _t_wait_start = _t.perf_counter()
                try:
                    result = await spec["task"]
                    wait_ms = (_t.perf_counter() - _t_wait_start) * 1000
                    elapsed_ms = (_t.perf_counter() - spec.get("started_at", _t_wait_start)) * 1000
                    # Copy the speculative metadata bag (graph_provenance etc.)
                    # into the live one so the chat router's SSE emit fires.
                    live_meta = managers.get("_tool_metadata")
                    spec_meta = spec.get("metadata") or {}
                    if isinstance(live_meta, dict) and isinstance(spec_meta, dict):
                        live_meta.update(spec_meta)
                    logger.info(
                        "SPECULATIVE_HIT tool=graph_and_vector_search wait_for_completion_ms=%.1f total_speculative_ms=%.1f match_ratio=%.2f",
                        wait_ms, elapsed_ms, match_ratio,
                    )
                    # Mark the speculative slot consumed so the cleanup path
                    # at the end of the request doesn't try to cancel it.
                    spec["consumed"] = True
                    return result
                except Exception as e:
                    logger.exception(
                        "SPECULATIVE_FAILED tool=graph_and_vector_search err=%s; falling back to fresh dispatch",
                        type(e).__name__,
                    )
                    # Fall through to a fresh dispatch
            # If we had a spec but it didn't qualify (below threshold),
            # log the near-miss so the threshold can be tuned from real
            # data over time.
            if spec and 0.0 < match_ratio < SPECULATIVE_MATCH_THRESHOLD:
                logger.info(
                    "SPECULATIVE_NEAR_MISS tool=graph_and_vector_search match_ratio=%.2f spec_q=%r actual_q=%r",
                    match_ratio, spec_q[:100], actual_q[:100],
                )
            return await _tool_graph_and_vector_search(args, managers)
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        logger.exception("Tool execution failed: %s", name)
        return f"Error executing {name}: {type(e).__name__}: {e}"


# ── Tool Implementations ─────────────────────────────────────────


async def _tool_get_experiment_runs(args: dict, managers: dict) -> str:
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"

    experiment_name = args.get("experiment_name", "")
    filter_tag = (args.get("filter_tag") or "").strip()
    experiments = mlflow_mgr.list_experiments()
    experiment = next((e for e in experiments if e["name"] == experiment_name), None)
    if not experiment:
        return f"No experiment found with name '{experiment_name}'"

    # Build MLflow filter_string from the `key=value` convenience arg.
    filter_string = ""
    if filter_tag:
        if "=" not in filter_tag:
            return f"Error: filter_tag must be 'key=value' (got {filter_tag!r})"
        k, _, v = filter_tag.partition("=")
        filter_string = f"tags.{k.strip()} = '{v.strip()}'"

    runs = mlflow_mgr.list_runs(
        experiment["experiment_id"], max_results=20, filter_string=filter_string
    )
    if not runs:
        if filter_tag:
            return f"Experiment '{experiment_name}' has no runs matching tag {filter_tag}"
        return f"Experiment '{experiment_name}' exists but has no runs"

    lines = [f"Experiment: {experiment_name} ({len(runs)} runs)"]
    for run in runs:
        name = run.get("run_name") or run["run_id"][:8]
        status = run["status"]
        line = f"\n  Run: {name} (ID: {run['run_id']}) [{status}]"

        metrics = run.get("metrics", {})
        if metrics:
            line += "\n    Metrics: " + ", ".join(f"{k}={v}" for k, v in metrics.items())

        params = run.get("params", {})
        if params:
            line += "\n    Params: " + ", ".join(f"{k}={v}" for k, v in params.items())

        lines.append(line)

    return "\n".join(lines)


async def _tool_get_run_details(args: dict, managers: dict) -> str:
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"

    run_id = args.get("run_id", "")
    run = mlflow_mgr.get_run(run_id)

    lines = [
        f"Run: {run.get('run_name', '')} (ID: {run['run_id']})",
        f"Status: {run['status']}",
        f"Start: {run.get('start_time', '?')}",
        f"End: {run.get('end_time', '?')}",
    ]

    # Compute and inline the duration so the model doesn't have to calculate
    # from timestamps. Handles string-ISO and epoch-ms representations.
    start_raw = run.get("start_time")
    end_raw = run.get("end_time")
    if start_raw and end_raw:
        try:
            from datetime import datetime
            def _to_dt(v):
                if isinstance(v, (int, float)):
                    # epoch ms
                    return datetime.fromtimestamp(v / 1000.0)
                if isinstance(v, str):
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                return None
            sdt, edt = _to_dt(start_raw), _to_dt(end_raw)
            if sdt and edt:
                total = (edt - sdt).total_seconds()
                if total < 60:
                    dur = f"{total:.3f}s"
                elif total < 3600:
                    dur = f"{total/60:.2f}m ({total:.1f}s)"
                else:
                    dur = f"{total/3600:.2f}h ({total:.1f}s)"
                lines.append(f"Duration: {dur}")
        except Exception:
            pass

    metrics = run.get("metrics", {})
    if metrics:
        lines.append("Metrics:")
        for k, v in metrics.items():
            lines.append(f"  {k}: {v}")

    params = run.get("params", {})
    if params:
        lines.append("Parameters:")
        for k, v in params.items():
            lines.append(f"  {k}: {v}")

    tags = run.get("tags", {})
    if tags:
        lines.append("Tags:")
        for k, v in tags.items():
            lines.append(f"  {k}: {v}")

    # Artifacts - classic run artifact tree (MLflow 2.x style) classified by kind.
    try:
        classified = mlflow_mgr.list_artifacts_classified(run_id)
    except Exception:
        classified = None
    if classified:
        models = classified.get("models", []) or []
        images = classified.get("images", []) or []
        charts = classified.get("charts", []) or []
        files = classified.get("files", []) or []
        if any([models, images, charts, files]):
            lines.append("Artifacts:")
            if models:
                lines.append(f"  Models ({len(models)}):")
                for m in models:
                    children = m.get("children", []) or []
                    lines.append(f"    - {m['path']}/ (MLmodel directory, {len(children)} files)")
                    for c in children[:30]:
                        name = c["path"].split("/")[-1]
                        suffix = "/" if c.get("is_dir") else ""
                        size = c.get("file_size")
                        size_str = f" ({size} bytes)" if size else ""
                        lines.append(f"        {name}{suffix}{size_str}")
                    if len(children) > 30:
                        lines.append(f"        ... +{len(children) - 30} more")
            if images:
                lines.append(f"  Images ({len(images)}):")
                for it in images[:20]:
                    lines.append(f"    - {it['path']}")
                if len(images) > 20:
                    lines.append(f"    ... +{len(images) - 20} more")
            if charts:
                lines.append(f"  Charts ({len(charts)}):")
                for it in charts[:20]:
                    lines.append(f"    - {it['path']}")
                if len(charts) > 20:
                    lines.append(f"    ... +{len(charts) - 20} more")
            if files:
                lines.append(f"  Files ({len(files)}):")
                for it in files[:20]:
                    size = it.get("file_size")
                    size_str = f" ({size} bytes)" if size else ""
                    suffix = "/" if it.get("is_dir") else ""
                    lines.append(f"    - {it['path']}{suffix}{size_str}")
                if len(files) > 20:
                    lines.append(f"    ... +{len(files) - 20} more")

    # Logged Models - MLflow 3.x entities stored under {experiment_id}/models/,
    # not directly in the run's artifact tree. Surface them explicitly so the
    # assistant can tell the user "yes, a model was saved" and can name the
    # files inside without needing a follow-up tool call.
    try:
        logged_models = mlflow_mgr.list_logged_models_for_run(run_id)
    except Exception:
        logged_models = []
    if logged_models:
        lines.append(f"Logged Models (MLflow 3.x) ({len(logged_models)}):")
        for lm in logged_models:
            model_id = lm.get("model_id", "?")
            artifacts = lm.get("artifacts", []) or []
            lines.append(f"  - model_id: {model_id} ({len(artifacts)} artifacts)")
            uri = lm.get("artifact_uri")
            if uri:
                lines.append(f"      artifact_uri: {uri}")
            for a in artifacts[:30]:
                name = a["path"].split("/")[-1]
                suffix = "/" if a.get("is_dir") else ""
                size = a.get("file_size")
                size_str = f" ({size} bytes)" if size else ""
                lines.append(f"      {name}{suffix}{size_str}")
            if len(artifacts) > 30:
                lines.append(f"      ... +{len(artifacts) - 30} more")

    return "\n".join(lines)


async def _tool_list_registered_models(args: dict, managers: dict) -> str:
    """List all registered models with their current aliases. Use this to find
    out which model name to pass to register_model / deploy_model, and which
    version each alias currently points at."""
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"
    try:
        models = mlflow_mgr.list_registered_models()
    except Exception as e:
        return f"Error listing registered models: {e}"
    if not models:
        return "No registered models. Use register_model(run_id, model_name) to create the first one."
    lines = [f"Registered models ({len(models)}):"]
    for m in models:
        aliases = m.get("aliases") or {}
        if aliases:
            alias_str = ", ".join(f"@{a}->v{v}" for a, v in aliases.items())
            lines.append(f"  - {m['name']} (aliases: {alias_str})")
        else:
            lines.append(f"  - {m['name']} (no aliases)")
    return "\n".join(lines)


async def _tool_list_model_versions(args: dict, managers: dict) -> str:
    """List all versions of a specific registered model, newest first, with
    run_id and any aliases each version carries."""
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"
    model_name = (args.get("model_name") or "").strip()
    if not model_name:
        return "Error: model_name is required"
    try:
        versions = mlflow_mgr.list_model_versions(model_name)
    except Exception as e:
        return f"Error listing versions of '{model_name}': {e}"
    if not versions:
        return f"No versions found for registered model '{model_name}'."
    lines = [f"Versions of '{model_name}' ({len(versions)}):"]
    for v in versions:
        aliases = v.get("aliases") or []
        alias_str = f" [{', '.join(f'@{a}' for a in aliases)}]" if aliases else ""
        run = v.get("run_id") or "?"
        status = v.get("status", "")
        lines.append(f"  v{v['version']}{alias_str}  run_id={run}  status={status}")
    return "\n".join(lines)


async def _tool_register_model(args: dict, managers: dict) -> str:
    """Register a run's model artifact into the MLflow Model Registry under
    the given name. Creates the registered model if it doesn't exist yet.
    Returns the new version number, which you can then pass to deploy_model
    or set_model_alias."""
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"
    run_id = (args.get("run_id") or "").strip()
    model_name = (args.get("model_name") or "").strip()
    artifact_path = (args.get("artifact_path") or "model").strip()
    if not run_id or not model_name:
        return "Error: run_id and model_name are required."
    try:
        result = mlflow_mgr.register_model(run_id=run_id, artifact_path=artifact_path, model_name=model_name)
    except Exception as e:
        return f"Error registering model: {e}"
    lines = ["Model registered."]
    lines.append(f"  Name: {result.get('model_name')}")
    lines.append(f"  Version: {result.get('version')}")
    lines.append(f"  From run: {result.get('run_id')}")
    if result.get("source"):
        lines.append(f"  Source: {result['source']}")
    lines.append(f"Next steps: set_model_alias (to promote this version to @champion or @staging) or deploy_model (to load it into serving).")
    return "\n".join(lines)


async def _tool_set_model_alias(args: dict, managers: dict) -> str:
    """Move an alias (e.g., 'champion', 'staging') to point at a specific
    version of a registered model. This is how promotion works in MLflow 3.x:
    aliases are movable pointers, version numbers are stable identifiers."""
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"
    model_name = (args.get("model_name") or "").strip()
    raw_version = args.get("version")
    alias = (args.get("alias") or "").strip().lstrip("@")
    # Accept the user-style "v3" form as well as plain "3" / 3 / "v003".
    # MLflow stores versions as integers; strip a leading 'v' or 'V' before
    # casting so the model never has to translate the user's wording.
    if raw_version is None:
        version = ""
    else:
        version = str(raw_version).strip()
        if version[:1] in ("v", "V") and version[1:].isdigit():
            version = version[1:]
    if not model_name or not version or not alias:
        return "Error: model_name, version, and alias are all required."
    try:
        mlflow_mgr.set_model_alias(model_name=model_name, version=str(version), alias=alias)
    except Exception as e:
        return f"Error setting alias: {e}"
    return f"Alias @{alias} on '{model_name}' now points at version {version}."


async def _tool_deploy_model(args: dict, managers: dict) -> str:
    """Deploy a registered MLflow model into the noted-serving container.
    Consumes the /load NDJSON stream and returns the final terminal state."""
    import os
    import json as _json
    import httpx

    model_name = (args.get("model_name") or "").strip()
    version = args.get("version")
    alias = args.get("alias")
    if not model_name:
        return "Error: model_name is required."
    if not version and not alias:
        return "Error: provide either 'version' (e.g. '7') or 'alias' (e.g. 'champion')."

    serving_url = os.environ.get('SERVING_URL', 'http://noted-serving:5522')
    body = {"model_name": model_name}
    if version is not None:
        body["version"] = str(version)
    if alias is not None:
        body["alias"] = str(alias)

    phases_seen = []
    terminal = None
    try:
        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream('POST', f'{serving_url}/load', json=body) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode('utf-8', 'replace')[:300]
                    return f"Error: serving returned HTTP {resp.status_code}: {text}"
                async for line in resp.aiter_lines():
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        event = _json.loads(line)
                    except Exception:
                        continue
                    phase = event.get("phase")
                    if phase in ("ready", "error"):
                        terminal = event
                        break
                    phases_seen.append(phase)
    except httpx.ConnectError:
        return f"Error: noted-serving is unreachable at {serving_url}. The serving container may be down."
    except httpx.ReadTimeout:
        return "Error: deploy timed out after 180 seconds. The model may still be loading; query get_serving_status in a moment."
    except Exception as e:
        return f"Error during deploy: {type(e).__name__}: {e}"

    if terminal is None:
        return f"Deploy ended without a terminal event. Observed phases: {phases_seen}. Query get_serving_status to check final state."

    if terminal.get("phase") == "error":
        err = terminal.get("error") or "unknown error"
        return f"Deploy failed: {err}"

    # Success path. The /load terminal event is {"phase":"ready","result":{...health payload...}}.
    result = terminal.get("result") or {}
    lines = ["Deploy succeeded."]
    if result.get("model_name"):
        lines.append(f"  Model: {result['model_name']}")
    if result.get("version"):
        lines.append(f"  Version: {result['version']}")
    if result.get("alias"):
        lines.append(f"  Alias: @{result['alias']}")
    if result.get("framework"):
        lines.append(f"  Framework: {result['framework']}")
    if result.get("run_id"):
        lines.append(f"  From run: {result['run_id']}")
    if result.get("num_parameters"):
        lines.append(f"  Parameters: {result['num_parameters']:,}")
    lines.append("The model is now loaded and ready to accept prediction requests at POST /api/serving/predict.")
    return "\n".join(lines)


async def _tool_get_serving_status(args: dict, managers: dict) -> str:
    """Query noted-serving's health endpoint to report which model (if any) is
    currently loaded and whether it is ready to serve predictions."""
    import os
    import requests

    serving_url = os.environ.get('SERVING_URL', 'http://noted-serving:5522')
    try:
        resp = requests.get(f'{serving_url}/health', timeout=10)
    except requests.exceptions.ConnectionError:
        return f"Error: noted-serving is unreachable at {serving_url}. The serving container may be down."
    except Exception as e:
        return f"Error contacting serving container: {e}"

    if resp.status_code != 200:
        return f"Error: serving health returned HTTP {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
    except Exception:
        return f"Error: serving health response was not valid JSON: {resp.text[:200]}"

    status = data.get("status", "unknown")
    model_name = data.get("model_name")
    version = data.get("version")
    alias = data.get("alias")
    framework = data.get("framework")
    run_id = data.get("run_id")
    error = data.get("error")
    phase = data.get("phase")
    phase_detail = data.get("phase_detail")

    if status == "idle" or not model_name:
        return (
            "Serving container: idle. No model is currently loaded.\n"
            "To load one, deploy a registered model from the Registry panel "
            "(or POST to /api/serving/load)."
        )

    lines = [f"Serving status: {status}"]
    if status == "loading":
        lines.append(f"A load is in progress.")
        if phase:
            lines.append(f"  Phase: {phase}" + (f" - {phase_detail}" if phase_detail else ""))
        if model_name:
            lines.append(f"  Target model: {model_name}" + (f" v{version}" if version else ""))
    elif status == "ready":
        lines.append(f"Loaded model: {model_name}")
        if version:
            lines.append(f"  Version: {version}")
        if alias:
            lines.append(f"  Alias: @{alias}")
        if framework:
            lines.append(f"  Framework: {framework}")
        if run_id:
            lines.append(f"  Produced by run: {run_id}")
        lines.append("The model is ready to accept prediction requests at POST /api/serving/predict.")
    elif status == "error":
        lines.append(f"Serving container is in error state.")
        if error:
            lines.append(f"  Error: {error}")
        if model_name:
            lines.append(f"  Last attempted model: {model_name}" + (f" v{version}" if version else ""))

    return "\n".join(lines)


async def _tool_get_serving_schema(args: dict, managers: dict) -> str:
    """Fetch input/output signatures for the model currently loaded in the
    serving container. Needed before constructing a test payload."""
    import os
    import requests

    serving_url = os.environ.get('SERVING_URL', 'http://noted-serving:5522')
    try:
        resp = requests.get(f'{serving_url}/schema', timeout=10)
    except requests.exceptions.ConnectionError:
        return f"Error: noted-serving is unreachable at {serving_url}. The serving container may be down."
    except Exception as e:
        return f"Error contacting serving container: {e}"

    if resp.status_code == 404:
        return "No model is currently loaded. Deploy one with deploy_model first, then call get_serving_schema again."
    if resp.status_code != 200:
        return f"Error: serving /schema returned HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        data = resp.json()
    except Exception:
        return f"Error: serving /schema response was not valid JSON: {resp.text[:200]}"

    lines = ["Serving schema:"]
    for key in ("model_name", "version", "alias", "framework"):
        v = data.get(key)
        if v is not None:
            lines.append(f"  {key}: {v}")

    inputs = data.get("inputs") or data.get("input_schema")
    outputs = data.get("outputs") or data.get("output_schema")
    shape = data.get("input_shape") or data.get("example_input_shape")
    output_shape = data.get("output_shape") or data.get("example_output_shape")
    input_format = data.get("input_format")

    if input_format:
        lines.append(f"  input_format: {input_format}")
    if shape:
        lines.append(f"  input_shape (incl. batch): {shape}")
    if output_shape:
        lines.append(f"  output_shape (incl. batch): {output_shape}")
    if inputs:
        lines.append(f"  inputs: {json.dumps(inputs, ensure_ascii=False)[:800]}")
    if outputs:
        lines.append(f"  outputs: {json.dumps(outputs, ensure_ascii=False)[:800]}")

    mlflow_example = data.get("example_input") or data.get("dummy_input")
    if mlflow_example is not None:
        lines.append(f"  MLflow-logged example input: {json.dumps(mlflow_example, ensure_ascii=False)[:400]}")

    lines.append("")
    lines.append("[End of schema. This is the complete specification for the deployed model's")
    lines.append("input and output shapes. Stop after reporting this to the user - do NOT append")
    lines.append("any 'you can test with invoke_model' suggestion. If the user later asks to test,")
    lines.append("invoke_model's own description will guide you at that point.]")
    return "\n".join(lines)


async def _tool_invoke_model(args: dict, managers: dict) -> str:
    """POST a prediction payload to the loaded model via the serving container.

    If `data` is omitted, fetches the schema and auto-builds a zeros tensor of
    the right shape as a smoke test. If `data` is provided, forwards it as-is
    to /api/serving/predict (really /predict on noted-serving).
    """
    import os
    import requests

    serving_url = os.environ.get('SERVING_URL', 'http://noted-serving:5522')
    data = args.get("data")

    # Small local models sometimes JSON-encode nested arrays into a string when
    # they emit tool_call arguments. Detect that and parse it back into a real
    # list/dict so the serving container sees structured data, not a string.
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.startswith(("[", "{")):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as e:
                return (
                    f"Error: `data` arrived as a JSON-shaped string but failed to parse: {e}. "
                    f"First 200 chars: {stripped[:200]}. Pass `data` as an actual JSON array/object, "
                    f"not a stringified one."
                )
        else:
            return (
                f"Error: `data` must be a JSON array or object (e.g. a nested list matching "
                f"the model's input shape), not a plain string. Received: {stripped[:200]}"
            )

    # Smoke test path: reuse the server-built example_request_body so the
    # skeleton is shaped correctly for tensor, dataframe, AND columnar models.
    if data is None:
        try:
            schema_resp = requests.get(f'{serving_url}/schema', timeout=10)
        except requests.exceptions.ConnectionError:
            return f"Error: noted-serving is unreachable at {serving_url}."
        except Exception as e:
            return f"Error fetching schema for auto-smoke-test: {e}"

        if schema_resp.status_code == 404:
            return "No model is currently loaded. Deploy one with deploy_model first."
        if schema_resp.status_code != 200:
            return f"Error: /schema returned HTTP {schema_resp.status_code}: {schema_resp.text[:200]}"

        try:
            schema = schema_resp.json()
        except Exception:
            return f"Error: /schema returned non-JSON: {schema_resp.text[:200]}"

        example_body = schema.get("example_request_body")
        if isinstance(example_body, dict) and "data" in example_body:
            data = example_body["data"]
            smoke_test_note = f" (auto smoke test, input_format={schema.get('input_format', '?')})"
        else:
            # Fallback for older serving containers that don't emit
            # example_request_body yet: build a zeros tensor from input_shape.
            shape = schema.get("input_shape") or schema.get("example_input_shape")
            if not shape:
                return ("Error: model schema does not expose an example_request_body or input "
                        "shape. Call get_serving_schema and construct data manually.")
            try:
                full_shape = list(shape)
                if full_shape and full_shape[0] in (None, -1, 0):
                    full_shape[0] = 1

                def _zeros(dims):
                    if not dims:
                        return 0.0
                    return [_zeros(dims[1:]) for _ in range(int(dims[0]))]

                data = _zeros(full_shape)
                smoke_test_note = f" (auto smoke test with zeros tensor of shape {full_shape})"
            except Exception as e:
                return f"Error: could not synthesize zeros tensor for shape {shape}: {e}"
    else:
        smoke_test_note = ""

    # POST the prediction
    try:
        pred_resp = requests.post(
            f'{serving_url}/predict',
            json={"data": data},
            timeout=60,
        )
    except requests.exceptions.ConnectionError:
        return f"Error: noted-serving is unreachable at {serving_url}."
    except Exception as e:
        return f"Error calling /predict: {e}"

    if pred_resp.status_code != 200:
        return f"Error: /predict returned HTTP {pred_resp.status_code}: {pred_resp.text[:500]}"

    try:
        result = pred_resp.json()
    except Exception:
        return f"Error: /predict returned non-JSON: {pred_resp.text[:500]}"

    preds = result.get("predictions")
    lines = [f"Prediction OK{smoke_test_note}."]
    if preds is not None:
        # Compute shape summary without bringing in numpy
        def _shape(x):
            if isinstance(x, list):
                if not x:
                    return [0]
                return [len(x)] + _shape(x[0])
            return []
        pred_shape = _shape(preds) if isinstance(preds, list) else None
        if pred_shape:
            lines.append(f"  Output shape: {pred_shape}")
        # Show a small preview
        preview = json.dumps(preds, ensure_ascii=False)
        if len(preview) > 600:
            preview = preview[:600] + f"... [truncated, {len(preview) - 600} more chars]"
        lines.append(f"  Predictions preview: {preview}")
    else:
        lines.append(f"  Raw response: {json.dumps(result, ensure_ascii=False)[:800]}")
    return "\n".join(lines)


async def _tool_list_run_artifacts(args: dict, managers: dict) -> str:
    """Recursive-capable artifact lister: list the contents at a specific path
    inside a run's (or a Logged Model's) artifact tree."""
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"

    run_id = args.get("run_id", "")
    path = args.get("path", "") or ""
    if not run_id:
        return "Error: run_id is required"

    try:
        items = mlflow_mgr.list_artifacts(run_id, path)
    except Exception as e:
        return f"Error listing artifacts: {e}"

    if not items:
        return f"No artifacts at path '{path or '/'}' for run {run_id}."

    lines = [f"Artifacts for run {run_id} at path '{path or '/'}':"]
    for it in items:
        suffix = "/" if it.get("is_dir") else ""
        size = it.get("file_size")
        size_str = f" ({size} bytes)" if size else ""
        lines.append(f"  {it['path']}{suffix}{size_str}")
    return "\n".join(lines)


async def _tool_compare_runs(args: dict, managers: dict) -> str:
    mlflow_mgr = managers.get("mlflow")
    if not mlflow_mgr:
        return "Error: MLflow not available"

    id_a = args.get("run_id_a", "")
    id_b = args.get("run_id_b", "")
    run_a = mlflow_mgr.get_run(id_a)
    run_b = mlflow_mgr.get_run(id_b)

    # Use short run_ids as column headers so the model cannot swap A/B when
    # mapping metrics back to a user-named version / alias. The full run_id
    # is also printed in the header block for traceability.
    a_short = id_a[:8] if id_a else (run_a.get("run_id", "")[:8])
    b_short = id_b[:8] if id_b else (run_b.get("run_id", "")[:8])
    col_a = f"{a_short} ({run_a.get('run_name', '-')})"
    col_b = f"{b_short} ({run_b.get('run_name', '-')})"

    lines = [f"Comparing runs:"]
    lines.append(f"  run_id_a = {run_a.get('run_id', '?')}  name={run_a.get('run_name', '?')}")
    lines.append(f"  run_id_b = {run_b.get('run_id', '?')}  name={run_b.get('run_name', '?')}")

    col_width = max(len(col_a), len(col_b), 15)

    # Compare metrics
    all_metric_keys = set(run_a.get("metrics", {}).keys()) | set(run_b.get("metrics", {}).keys())
    if all_metric_keys:
        lines.append("\nMetrics:")
        lines.append(f"  {'Metric':<30} {col_a:<{col_width}} {col_b:<{col_width}}")
        lines.append(f"  {'-'*30} {'-'*col_width} {'-'*col_width}")
        for k in sorted(all_metric_keys):
            va = run_a.get("metrics", {}).get(k, "-")
            vb = run_b.get("metrics", {}).get(k, "-")
            lines.append(f"  {k:<30} {str(va):<{col_width}} {str(vb):<{col_width}}")

    # Compare params
    all_param_keys = set(run_a.get("params", {}).keys()) | set(run_b.get("params", {}).keys())
    if all_param_keys:
        lines.append("\nParameters:")
        lines.append(f"  {'Param':<30} {col_a:<{col_width}} {col_b:<{col_width}}")
        lines.append(f"  {'-'*30} {'-'*col_width} {'-'*col_width}")
        for k in sorted(all_param_keys):
            va = run_a.get("params", {}).get(k, "-")
            vb = run_b.get("params", {}).get(k, "-")
            marker = " *" if str(va) != str(vb) else ""
            lines.append(f"  {k:<30} {str(va):<{col_width}} {str(vb):<{col_width}}{marker}")

    return "\n".join(lines)


async def _tool_get_file_contents(args: dict, managers: dict, ctx: dict = None) -> str:
    file_mgr = managers.get("files")
    if not file_mgr:
        return "Error: File manager not available"

    path = args.get("path", "")
    max_lines = args.get("max_lines", 100)

    try:
        # Resolve the path: if it looks like a relative path (no project prefix),
        # use the project_id from the current context
        parts = path.split("/", 1)
        first_part = parts[0]

        from app.managers.project_registry import get_registry
        registry = get_registry()
        clean_first = registry.clean_id(first_part)

        # Check if first part is a known project name
        if registry.exists(clean_first):
            project_id = clean_first
            rel_path = parts[1] if len(parts) == 2 else ""
        elif ctx and ctx.get("project_id"):
            # LLM sent a relative path - use the context project_id
            project_id = registry.clean_id(ctx["project_id"])
            rel_path = path
        else:
            project_id = clean_first
            rel_path = parts[1] if len(parts) == 2 else ""

        root_type = "mount" if registry.is_mount(project_id) else "project"
        root_name = project_id
        logger.info("get_file_contents: raw_path=%r -> root_type=%s root_name=%s rel_path=%s",
                     path, root_type, root_name, rel_path)
        result = file_mgr.read_file(root_type, root_name, rel_path)
        content = result.get("content", "")
    except Exception as e:
        logger.error("get_file_contents failed: path=%r error=%s", path, e)
        return f"Error reading file '{path}': {e}"

    lines = content.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"\n...(truncated, showing first {max_lines} lines)")

    return "\n".join(lines)


async def _tool_get_hydra_config(args: dict, managers: dict, ctx: dict = None) -> str:
    hydra_mgr = managers.get("hydra")
    if not hydra_mgr:
        return "Error: Hydra not available"

    project_id = args.get("project_id", "") or (ctx or {}).get("project_id", "")
    result = hydra_mgr.compose(project_id)
    yaml_str = result.get("yaml", "")

    if not yaml_str:
        return f"No Hydra configuration found for project '{project_id}'"

    # Include the defaults/selections preamble so the model can answer
    # "which X is currently active?" without guessing from the resolved yaml.
    lines = [f"Hydra config for '{project_id}':"]
    sources = result.get("sources") or {}
    if isinstance(sources, dict) and sources:
        lines.append("\nActive group selections (from defaults + overrides):")
        for group, meta in sorted(sources.items()):
            if isinstance(meta, dict):
                selection = meta.get("selection") or meta.get("default") or "?"
                file_ref = meta.get("path") or meta.get("source") or ""
                if file_ref:
                    lines.append(f"  {group}: {selection}  (from {file_ref})")
                else:
                    lines.append(f"  {group}: {selection}")
            else:
                lines.append(f"  {group}: {meta}")
        lines.append("")
    lines.append("Resolved YAML:")
    lines.append(yaml_str)
    return "\n".join(lines)




async def _tool_list_files(args: dict, managers: dict, ctx: dict = None) -> str:
    file_mgr = managers.get("files")
    if not file_mgr:
        return "Error: File manager not available"

    from app.managers.project_registry import get_registry
    registry = get_registry()
    # Prefer the project_id from the ctx (authoritative, frontend-supplied) and
    # only fall back to an arg value if ctx is absent. The model often omits
    # project_id because it only knows the ID from the workspace context.
    project_id_raw = (ctx or {}).get("project_id", "") or args.get("project_id", "")
    project_id = registry.clean_id(project_id_raw)
    rel_path = args.get("path", "")
    pattern = args.get("pattern", "")

    if not project_id:
        return "Error: project_id is required"

    try:
        root = registry.resolve(project_id)
        search_dir = file_mgr._secure_path(root, rel_path) if rel_path else root
    except Exception as e:
        return f"Error resolving path: {e}"

    results = []
    try:
        for dirpath, dirnames, filenames in os.walk(search_dir):
            # Skip hidden directories
            dirnames[:] = [d for d in sorted(dirnames) if not d.startswith('.')]
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == '.':
                rel_dir = ''
            for fname in sorted(filenames):
                if fname.startswith('.'):
                    continue
                if pattern and not fnmatch.fnmatch(fname, pattern):
                    continue
                entry_path = os.path.join(rel_dir, fname) if rel_dir else fname
                results.append(entry_path)
                if len(results) >= 200:
                    break
            if len(results) >= 200:
                break
    except Exception as e:
        return f"Error listing files: {e}"

    if not results:
        desc = f"matching '{pattern}' " if pattern else ""
        return f"No files {desc}found in {project_id}/{rel_path or '(root)'}"

    header = f"Files in {project_id}/{rel_path or '(root)'}:"
    if pattern:
        header += f" (pattern: {pattern})"
    if len(results) >= 200:
        header += " [showing first 200]"
    return header + "\n" + "\n".join(results)


async def _tool_search_files(args: dict, managers: dict, ctx: dict = None) -> str:
    file_mgr = managers.get("files")
    if not file_mgr:
        return "Error: File manager not available"

    from app.managers.project_registry import get_registry
    registry = get_registry()
    project_id_raw = (ctx or {}).get("project_id", "") or args.get("project_id", "")
    project_id = registry.clean_id(project_id_raw)
    query = args.get("query", "")
    rel_path = args.get("path", "")
    file_pattern = args.get("file_pattern", "")
    max_results = min(int(args.get("max_results", 20)), 50)

    if not project_id or not query:
        return "Error: project_id and query are required"

    try:
        root = registry.resolve(project_id)
        search_dir = file_mgr._secure_path(root, rel_path) if rel_path else root
    except Exception as e:
        return f"Error resolving path: {e}"

    query_lower = query.lower()
    matches = []

    try:
        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in sorted(dirnames) if not d.startswith('.')]
            for fname in sorted(filenames):
                if fname.startswith('.'):
                    continue
                if file_pattern and not fnmatch.fnmatch(fname, file_pattern):
                    continue
                # Skip binary extensions
                ext = os.path.splitext(fname)[1].lower()
                if ext in {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.tar',
                           '.gz', '.pkl', '.pickle', '.parquet', '.h5', '.hdf5',
                           '.pyc', '.so', '.whl'}:
                    continue
                full_path = os.path.join(dirpath, fname)
                rel_file = os.path.relpath(full_path, root)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for lineno, line in enumerate(f, 1):
                            if query_lower in line.lower():
                                matches.append(f"{rel_file}:{lineno}: {line.rstrip()}")
                                if len(matches) >= max_results:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break
    except Exception as e:
        return f"Error searching files: {e}"

    if not matches:
        return f"No matches for '{query}' in {project_id}/{rel_path or '(root)'}"

    header = f"Search results for '{query}' in {project_id}:"
    if len(matches) >= max_results:
        header += f" [showing first {max_results} matches]"
    return header + "\n" + "\n".join(matches)


async def _tool_list_projects(args: dict, managers: dict) -> str:
    """Return the list of projects (internal + mounted) that noted knows
    about. Lets the model resolve a user's free-text reference like
    "the Jena project" to a real project_id before calling project-scoped
    tools (get_experiment_runs, list_dags, list_files, get_notebook_cells)."""
    notebook_mgr = managers.get("notebook")
    if not notebook_mgr:
        return "Error: Notebook manager not available"
    try:
        projects = notebook_mgr.list_projects()
    except Exception as e:
        return f"Error listing projects: {type(e).__name__}: {e}"
    if not projects:
        return "No projects registered. The user has not created any projects yet."
    lines = [f"Found {len(projects)} project(s):"]
    for p in projects:
        nb = p.get("notebooks_count", 0)
        src = p.get("source", "internal")
        lines.append(f"- id={p.get('id', '?')}  source={src}  notebooks={nb}")
    lines.append("")
    lines.append(
        "Use the `id` value verbatim as `project_id` when calling project-"
        "scoped tools (get_experiment_runs, list_dags, list_files, etc.)."
    )
    return "\n".join(lines)


async def _tool_get_notebook_cells(args: dict, managers: dict, ctx: dict = None) -> str:
    notebook_mgr = managers.get("notebook")
    if not notebook_mgr:
        return "Error: Notebook manager not available"

    from app.managers.project_registry import get_registry
    project_id_raw = (ctx or {}).get("project_id", "") or args.get("project_id", "")
    project_id = get_registry().clean_id(project_id_raw)
    notebook_path = args.get("notebook_path", "") or (ctx or {}).get("notebook_path", "")
    indices = args.get("indices")  # list of specific indices, optional
    from_index = args.get("from_index")
    to_index = args.get("to_index")
    include_outputs = args.get("include_outputs", False)

    if not project_id or not notebook_path:
        return "Error: project_id and notebook_path are required"

    # Use in-memory cells from the browser if available (unsaved changes),
    # otherwise fall back to disk.
    cells_override = managers.get("notebook_cells_override")
    if cells_override is not None:
        cells = [{"cell_type": c.get("cell_type", "code"), "source": c.get("source", ""), "outputs": []} for c in cells_override]
    else:
        try:
            notebook = notebook_mgr.get_notebook(project_id, notebook_path)
        except Exception as e:
            return f"Error loading notebook: {e}"
        cells = notebook.get("cells", [])

    total = len(cells)

    # Result size caps (char budget is the real limit - models with 128K+ context
    # can comfortably ingest the entire notebook in one call for typical sizes).
    MAX_RESULT_CHARS = 80000
    MAX_CELL_SOURCE_CHARS = 8000

    # Determine which cells to include
    # LLM uses 1-based cell numbers; convert to 0-based for internal array access
    if indices is not None:
        indices_0 = [int(i) - 1 for i in indices]
        selected = [(i, cells[i]) for i in indices_0 if 0 <= i < total]
    elif from_index is not None or to_index is not None:
        lo = int(from_index) - 1 if from_index is not None else 0
        hi = int(to_index) if to_index is not None else total  # to_index is inclusive, -1+1=0 net
        selected = [(i, cells[i]) for i in range(max(0, lo), min(total, hi))]
    else:
        # Default: all cells (MAX_RESULT_CHARS caps huge notebooks mid-iteration)
        selected = [(i, cells[i]) for i in range(total)]

    if not selected:
        return f"No cells found for the given range in {notebook_path} (total cells: {total})"

    lines = [f"Notebook: {notebook_path} | Total cells: {total} | Showing: {len(selected)} cell(s)"]
    total_chars = len(lines[0])

    for idx, cell in selected:
        cell_type = cell.get("cell_type", "code")
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        source = source.rstrip()
        # Truncate very large cell sources (e.g. embedded base64 images in markdown)
        if len(source) > MAX_CELL_SOURCE_CHARS:
            source = source[:MAX_CELL_SOURCE_CHARS] + f"\n...(cell source truncated, {len(source) - MAX_CELL_SOURCE_CHARS} more chars)"
        cell_text = f"\n[Cell {idx + 1} - {cell_type}]\n{source}"

        if include_outputs and cell_type == "code":
            from app.managers.llm_context import _format_outputs
            outputs = cell.get("outputs", [])
            if outputs:
                output_text = _format_outputs(outputs)
                if output_text:
                    cell_text += f"\n[Cell {idx + 1} - output]\n{output_text}"

        # Stop if adding this cell would exceed the total result limit
        if total_chars + len(cell_text) > MAX_RESULT_CHARS:
            lines.append(f"\n...(result truncated at {MAX_RESULT_CHARS} chars; use from_index={idx + 1} to continue)")
            break
        lines.append(cell_text)
        total_chars += len(cell_text)

    return "\n".join(lines)


async def _tool_fetch_url(args: dict) -> str:
    """Fetch a URL using the persistent stealth browser."""
    from app.managers.web_fetch_manager import fetch_url
    url = args.get("url", "").strip()
    max_chars = int(args.get("max_chars", 10000))
    return await fetch_url(url, max_chars)


async def _tool_web_search(args: dict) -> str:
    """Run a web search via the persistent stealth browser (DDG HTML)."""
    from app.managers.web_fetch_manager import web_search
    query = args.get("query", "").strip()
    top_n = int(args.get("top_n", 8))
    return await web_search(query, top_n)


async def _tool_run_agent(args: dict, managers: dict, ctx: dict | None = None) -> str:
    task = args.get("task", "").strip()
    agent_name = args.get("agent_name", "notebook-explorer").strip()
    if not task:
        return "Error: task is required"
    from app.managers.llm_agents import run_subagent
    return await run_subagent(task, agent_name, managers, ctx=ctx)


# ── Airflow Tools ─────────────────────────────────────────────────


async def _tool_list_dags(args: dict, managers: dict, ctx: dict = None) -> str:
    """List DAGs. Scoped to the current project when one is active in ctx.

    Airflow aggregates DAGs from every mounted project (fileloc under
    `/opt/airflow/dags/_projects/<project_id>/` for regular projects, or
    `/opt/airflow/dags/<mount_name>/` for mounts). Without scoping the model
    sees DAGs from unrelated projects and can't tell which belong to the user.
    Pass `scope=all` in args to override and get the global list.
    """
    airflow_mgr = managers.get("airflow")
    if not airflow_mgr:
        return "Error: Airflow not available"

    scope = (args or {}).get("scope", "current")
    current_project = (ctx or {}).get("project_id", "") if ctx else ""

    try:
        # Use raw API to get fileloc (list_dags() drops it)
        data = airflow_mgr._api("GET", "/dags", params={"limit": 200})
        raw_dags = data.get("dags", [])
    except Exception as e:
        return f"Error listing DAGs: {e}"

    if not raw_dags:
        return "No DAGs found in Airflow"

    def _dag_project(dag: dict) -> str:
        """Extract the project id from fileloc, or '' if it can't be parsed."""
        fileloc = dag.get("fileloc") or ""
        prefix = "/opt/airflow/dags/"
        if not fileloc.startswith(prefix):
            return ""
        rel = fileloc[len(prefix):]
        parts = rel.split("/", 2)
        if not parts:
            return ""
        first = parts[0]
        # Regular noted projects live under `_projects/<id>/dags/...`
        if first == "_projects" and len(parts) >= 2:
            return parts[1]
        # Mounted projects live directly under `<mount>/dags/...`
        return first

    annotated = []
    for d in raw_dags:
        project = _dag_project(d)
        annotated.append({
            "dag_id": d["dag_id"],
            "description": d.get("description", ""),
            "is_paused": d.get("is_paused", False),
            "tags": [t.get("name", t) if isinstance(t, dict) else t for t in d.get("tags", [])],
            "schedule": d.get("timetable_summary") or "None",
            "project": project,
        })

    if scope == "current" and current_project:
        filtered = [d for d in annotated if d["project"] == current_project]
        # Fallback: if no DAG matches the current project (e.g. Examples /
        # legacy projects with a different mount name), show the global list
        # rather than an empty message so the tool stays useful.
        if filtered:
            annotated = filtered
            header = f"Airflow DAGs in project '{current_project}' ({len(annotated)} total):"
        else:
            header = f"Airflow DAGs (no DAG in project '{current_project}'; showing all {len(annotated)} globally):"
    else:
        header = f"Airflow DAGs ({len(annotated)} total):"

    lines = [header]
    for dag in annotated:
        status = "paused" if dag["is_paused"] else "active"
        tags = ", ".join(dag["tags"])
        line = f"\n  {dag['dag_id']} [{status}] schedule={dag['schedule']}"
        if dag["project"]:
            line += f" project={dag['project']}"
        if tags:
            line += f" tags=[{tags}]"
        if dag.get("description"):
            line += f"\n    {dag['description']}"
        lines.append(line)

    return "\n".join(lines)


async def _tool_get_dag_status(args: dict, managers: dict) -> str:
    airflow_mgr = managers.get("airflow")
    if not airflow_mgr:
        return "Error: Airflow not available"

    dag_id = args.get("dag_id", "")

    try:
        dag = airflow_mgr.get_dag(dag_id)
        runs = airflow_mgr.list_dag_runs(dag_id, limit=5)
        tasks = airflow_mgr.get_dag_tasks(dag_id)
    except Exception as e:
        return f"Error getting DAG '{dag_id}': {e}"

    lines = [f"DAG: {dag_id}"]
    lines.append(f"Status: {'paused' if dag.get('is_paused') else 'active'}")
    lines.append(f"Schedule: {dag.get('schedule', 'None')}")

    if tasks:
        lines.append(f"\nTasks ({len(tasks)}):")
        for t in tasks:
            lines.append(f"  - {t.get('task_id', '?')} ({t.get('operator', '?')})")

    if runs:
        lines.append(f"\nRecent runs ({len(runs)}):")
        for r in runs:
            state = r.get("state", "?")
            duration = f"{r['duration']:.1f}s" if r.get("duration") else "?"
            lines.append(f"  - {r['dag_run_id']} [{state}] duration={duration} started={r.get('start_date', '?')}")
    else:
        lines.append("\nRecent runs: (none - this DAG has no executed runs yet)")
        lines.append("Since there are no runs, get_task_log cannot return a log. Do NOT fabricate")
        lines.append("run IDs. The correct answer is to report plainly that no runs exist and ask")
        lines.append("the user to provide a specific dag_run_id. Do NOT suggest triggering or")
        lines.append("unpausing the DAG - noted has no tools for that; triggering is a separate")
        lines.append("Airflow-UI action the user can take themselves if they want.")

    return "\n".join(lines)


_ANSI_RE = re.compile(r"\x1B(?:\[[0-9;]*[A-Za-z]|\]8;;[^\x07]*\x07)|\x1B\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI colour / cursor escapes. Keras/tqdm progress bars emit
    huge amounts of these, which drown out the actual summary lines (final
    metrics, run_id, return value) when the log is length-truncated."""
    return _ANSI_RE.sub("", text)


async def _tool_get_task_log(args: dict, managers: dict) -> str:
    airflow_mgr = managers.get("airflow")
    if not airflow_mgr:
        return "Error: Airflow not available"

    dag_id = args.get("dag_id", "")
    dag_run_id = args.get("dag_run_id", "")
    task_id = args.get("task_id", "")

    try:
        log = airflow_mgr.get_task_log(dag_id, dag_run_id, task_id)
    except Exception as e:
        return f"Error getting task log: {e}"

    if not log:
        return f"No log found for task '{task_id}' in run '{dag_run_id}'"

    # Strip ANSI escapes BEFORE truncating so progress bars don't hog budget.
    # A 350k-char raw Keras log compacts to ~50k without ANSI, and the final
    # summary section (MAE / RMSE / run_id) fits cleanly in the tail budget.
    original_len = len(log)
    log = _strip_ansi(log)
    stripped_len = len(log)

    # Keep the last 12k chars of the cleaned log. This is enough to capture
    # the final epoch summary + post-training metric prints + XCom return
    # value for every training task we've observed.
    MAX_TAIL = 12000
    truncated = False
    if len(log) > MAX_TAIL:
        log = log[-MAX_TAIL:]
        truncated = True

    if truncated:
        header = (
            f"...(log truncated: original {original_len} chars -> "
            f"{stripped_len} after stripping ANSI -> last {MAX_TAIL} chars shown. "
            "Report ONLY numbers that literally appear in the snippet; never "
            "infer or fabricate metrics, run_ids, or other values.)\n"
        )
        log = header + log

    return f"Task log for {task_id} in {dag_run_id}:\n{log}"


# ── DVC Tools ─────────────────────────────────────────────────────


async def _tool_get_dvc_data_overview(args: dict, managers: dict) -> str:
    dvc_mgr = managers.get("dvc")
    if not dvc_mgr:
        return "Error: DVC not available"

    try:
        collections = dvc_mgr.data_overview()
    except Exception as e:
        return f"Error getting DVC data overview: {e}"

    if not collections:
        return "No DVC-tracked data found in any project"

    lines = ["DVC-tracked data:"]
    for col in collections:
        lines.append(f"\n  Project: {col['name']} ({col['root_type']})")
        for f in col.get("files", []):
            size_mb = f.get("size", 0) / (1024 * 1024)
            lines.append(f"    - {f['path']} ({size_mb:.1f} MB, hash={f.get('hash', '?')[:12]})")

    return "\n".join(lines)


async def _tool_get_dvc_file_history(args: dict, managers: dict, ctx: dict = None) -> str:
    dvc_mgr = managers.get("dvc")
    if not dvc_mgr:
        return "Error: DVC not available"

    repo_path = args.get("repo_path", "")
    dvc_file = args.get("dvc_file", "")

    # Default repo_path to the active project's filesystem location when the
    # model omits it (typical - the model only knows the project_id from ctx).
    if not repo_path and ctx and ctx.get("project_id"):
        try:
            from app.managers.project_registry import get_registry as _get_proj_registry
            repo_path = _get_proj_registry().resolve(ctx["project_id"]) or ""
        except Exception:
            pass

    # If the model gave just a basename ("data.csv") without a path, look
    # up the actual DVC-tracked file by basename so the tool stays useful
    # when the user doesn't know the exact path. Skip when dvc_file already
    # contains a separator.
    if dvc_file and "/" not in dvc_file and repo_path:
        try:
            import os as _os
            target_basename = dvc_file
            matches: list[str] = []
            for root, _dirs, files in _os.walk(repo_path):
                for fn in files:
                    if fn == target_basename or fn == f"{target_basename}.dvc":
                        rel = _os.path.relpath(_os.path.join(root, fn), repo_path)
                        # Strip the .dvc suffix if present so the lookup
                        # uses the data file name (the manager looks at the
                        # .dvc pointer in git log either way).
                        if rel.endswith(".dvc"):
                            rel = rel[:-4]
                        matches.append(rel)
            # Prefer the shortest match (closest to the project root) so
            # nested duplicates of the same name don't confuse the lookup.
            if matches:
                matches.sort(key=len)
                dvc_file = matches[0]
        except Exception:
            pass

    try:
        history = dvc_mgr.file_history(repo_path, dvc_file)
    except Exception as e:
        return f"Error getting DVC file history: {e}"

    versions = history.get("versions", [])
    if not versions:
        return f"No version history found for '{dvc_file}'"

    lines = [f"Version history for {dvc_file} ({len(versions)} versions):"]
    for v in versions:
        lines.append(f"  - {v.get('commit_hash', '?')[:8]} | {v.get('date', '?')} | {v.get('message', '?')}")
        if v.get("hash"):
            lines.append(f"    data hash: {v['hash']}")

    return "\n".join(lines)


# ── Knowledge Graph Tool ──────────────────────────────────────────


async def _tool_query_knowledge_graph(args: dict, managers: dict, ctx: dict = None) -> str:
    import os
    import requests as req

    graph_url = os.environ.get('GRAPH_URL', 'http://noted-graph:5523')
    project_id = args.get("project_id", "") or (ctx or {}).get("project_id", "")

    try:
        resp = req.get(f"{graph_url}/graph/{project_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"Error querying knowledge graph: {e}"

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        return f"No knowledge graph data found for project '{project_id}'"

    lines = [f"Knowledge Graph for '{project_id}': {len(nodes)} nodes, {len(edges)} edges"]

    # Group nodes by type
    by_type = {}
    for n in nodes:
        t = n.get("type", "unknown")
        by_type.setdefault(t, []).append(n)

    for ntype, items in sorted(by_type.items()):
        lines.append(f"\n  {ntype} ({len(items)}):")
        for item in items[:10]:
            label = item.get("label") or item.get("id", "?")
            lines.append(f"    - {label}")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")

    return "\n".join(lines)


# ── Skills Tool ───────────────────────────────────────────────────


async def _tool_fix_lint_issues(args: dict, managers: dict, ctx: dict = None) -> str:
    """Run ruff --fix to auto-fix all fixable lint issues.

    This is a READ tool that generates the fixed content and returns it.
    The LLM should then use update_file with the fixed content, which goes
    through the approval panel.

    But since the LLM can't reliably generate 8K+ token tool calls, this
    tool returns a special marker that the backend intercepts to create
    a pending write action directly.
    """
    import subprocess

    if not ctx or not ctx.get("file_path") or not ctx.get("project_id"):
        return "Error: No Python file in context. Open a .py file first."

    file_path = ctx.get("file_path", "")
    codes = args.get("codes", "")  # optional: specific rule codes like "F401,PIE790"

    content = ctx.get("file_content", "")
    if not content:
        # Fall back to disk when the frontend didn't push in-memory content.
        file_mgr = managers.get("files")
        if file_mgr:
            try:
                from app.managers.project_registry import get_registry as _get_reg
                registry = _get_reg()
                project_id = ctx.get("project_id", "")
                root_type = "mount" if registry.is_mount(project_id) else "project"
                result = file_mgr.read_file(root_type, project_id, file_path)
                if isinstance(result, dict):
                    content = result.get("content", "") or ""
                elif isinstance(result, str):
                    content = result
            except Exception as e:
                return f"Error: could not read {file_path} from disk: {e}"
        if not content:
            return "Error: File content not available in context or on disk."

    try:
        cmd = ["ruff", "check", "--preview", "--fix", "--unsafe-fixes", "--stdin-filename", file_path, "-"]
        if codes:
            cmd.extend(["--select", codes])

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(cmd, input=content, capture_output=True, text=True, timeout=10),
        )
        fixed = result.stdout if result.stdout else content
        if fixed == content:
            return "No auto-fixable issues found. The file is clean."

        old_lines = content.split('\n')
        new_lines = fixed.split('\n')
        removed = len(old_lines) - len(new_lines)

        # Store the fixed content for the pending action system
        ctx['_lint_fixed_content'] = fixed

        return f"Auto-fix ready: {removed} line(s) would be removed. Tell the user you will apply the fix and then call update_file."
    except Exception as e:
        return f"Error running fix: {e}"


async def _tool_get_lint_diagnostics(args: dict, managers: dict, ctx: dict = None) -> str:
    """Run ruff check on the file or notebook from context and return diagnostics."""
    import subprocess

    if not ctx or not ctx.get("project_id"):
        return "Error: No file or notebook in context."

    file_path = ctx.get("file_path", "")
    notebook_path = ctx.get("notebook_path", "")

    # Notebook: use Jupytext to create percent-format script (same as LSP bridge)
    if notebook_path and not file_path:
        notebook_mgr = managers.get("notebook")
        if not notebook_mgr:
            return "Error: NotebookManager not available."
        try:
            nb = notebook_mgr.get_notebook(ctx["project_id"], notebook_path)
            nb = notebook_mgr.prepare_for_wire(nb)
        except Exception as e:
            return f"Error loading notebook: {e}"

        from app.managers.notebook_lsp_bridge import NotebookLSPBridge
        bridge = NotebookLSPBridge(ctx["project_id"], notebook_path)
        try:
            content = bridge.generate(nb)
        except Exception as e:
            return f"Error converting notebook: {e}"

        virtual_path = f"{notebook_path}.py"
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["ruff", "check", "--preview", "--output-format", "json", "-e",
                     "--stdin-filename", virtual_path, "-"],
                    input=content, capture_output=True, text=True, timeout=10,
                ),
            )
            import json as json_mod
            diagnostics = json_mod.loads(result.stdout) if result.stdout else []
        except Exception as e:
            return f"Error running linter: {e}"

        if not diagnostics:
            return "No lint issues found - the notebook is clean."

        output_lines = [f"Found {len(diagnostics)} lint issue(s) in {notebook_path}:\n"]
        for d in diagnostics:
            code = d.get("code", "?")
            msg = d.get("message", "")
            row = d.get("location", {}).get("row", 1)
            region = bridge._find_region(row - 1)
            if region and region.cell_type == 'code':
                local_line = row - 1 - region.start_line + 1
                fix = d.get("fix")
                fix_info = f" [auto-fixable: {fix['message']}]" if fix else ""
                output_lines.append(f"  Cell {region.cell_index + 1}, Line {local_line}: {code} - {msg}{fix_info}")

        return "\n".join(output_lines)

    # File mode
    if not file_path:
        return "Error: No Python file or notebook in context."
    if not file_path.endswith(".py"):
        return "Error: Lint diagnostics only available for Python files and notebooks."

    content = ctx.get("file_content", "")
    if not content:
        # Fall back to reading the file from disk via the file manager when the
        # frontend didn't send in-memory content (always the case in tests, and
        # for some saved-state scenarios in the real frontend).
        file_mgr = managers.get("files")
        if file_mgr:
            try:
                from app.managers.project_registry import get_registry as _get_reg
                registry = _get_reg()
                project_id = ctx.get("project_id", "")
                root_type = "mount" if registry.is_mount(project_id) else "project"
                _result = file_mgr.read_file(root_type, project_id, file_path)
                # read_file returns a dict {name, path, content, encoding, ...}
                # Extract the string content for text files.
                if isinstance(_result, dict):
                    content = _result.get("content", "") or ""
                elif isinstance(_result, str):
                    content = _result
            except Exception as e:
                return f"Error: could not read {file_path} from disk: {e}"
        if not content:
            return "Error: File content not available in context or on disk."
    if not isinstance(content, str):
        return f"Error: internal - expected string file content, got {type(content).__name__}"

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ruff", "check", "--preview", "--output-format", "json", "-e",
                 "--stdin-filename", file_path, "-"],
                input=content,
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )
        import json as json_mod
        diagnostics = json_mod.loads(result.stdout) if result.stdout else []

        if not diagnostics:
            return "No lint issues found - the file is clean."

        lines = [f"Found {len(diagnostics)} lint issue(s) in {file_path}:\n"]
        for d in diagnostics:
            code = d.get("code", "?")
            msg = d.get("message", "")
            line = d.get("location", {}).get("row", "?")
            fix = d.get("fix")
            fix_info = f" [auto-fixable: {fix['message']}]" if fix else ""
            lines.append(f"  Line {line}: {code} - {msg}{fix_info}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error running linter: {e}"


async def _tool_get_skill(args: dict, managers: dict, ctx: dict = None) -> str:
    from app.managers.llm_skills import get_registry

    skill_name = args.get("skill_name", "")
    ref_path = args.get("reference", "")
    registry = get_registry()

    # Load a specific reference file from the skill's references/ folder
    # (reference loads are always permitted - they carry content beyond the main SKILL.md)
    if ref_path:
        ref_content = registry.get_skill_reference(skill_name, ref_path)
        if ref_content:
            return f"SKILL REFERENCE [{skill_name}/{ref_path}]:\n{ref_content}"
        return f"Reference '{ref_path}' not found in skill '{skill_name}'"

    # Redirect if the skill is already auto-injected for the current turn.
    # Re-fetching the same content wastes tokens and the model should use the
    # ACTIVE SKILLS block instead.
    if ctx is not None:
        try:
            from app.managers.llm_context import _get_matched_skills
            # Pass empty blocks - sufficient for ctx-based condition detection
            # (workspace_active, notebook_cell_selected, mlflow_run_in_context, etc.).
            # We miss conditions that require inspecting built blocks, but those
            # are narrow and the redirect is best-effort.
            active = [name for name, _ in _get_matched_skills(ctx, [])]
            if skill_name in active:
                return (
                    f"Skill '{skill_name}' is already active in your current context - "
                    f"its content is in the ACTIVE SKILLS block of the workspace context. "
                    f"Do NOT call get_skill for it; answer from the content already provided. "
                    f"This redirect saves tokens; refetching was redundant."
                )
        except Exception:
            # If active-skill detection fails, fall through and serve the content
            # as before. Better to be slightly redundant than to break get_skill.
            pass

    # Load the main SKILL.md content
    content = registry.get_skill(skill_name)
    if content:
        return f"SKILL [{skill_name}]:\n{content}"

    # Skill not found - list available skills to help the LLM. Filter by
    # active Domains so the model only sees skills from Domains the user has
    # turned on (legacy data/skills/ entries are bucketed under the 'noted'
    # Domain).
    try:
        from app.routers.kb import get_active_domains
        active_domains = set(get_active_domains() or [])
    except Exception:
        active_domains = None
    available = registry.list_skills()
    if active_domains is not None:
        names = [name for name, meta in available
                 if meta.get("domain_id") in active_domains]
    else:
        names = [name for name, _ in available]
    return f"Skill '{skill_name}' not found. Available skills: {', '.join(names)}"


# ── Write Tools ───────────────────────────────────────────────────


async def _tool_update_cell(args: dict, managers: dict,
                            project_id: str, notebook_path: str) -> str:
    """Return confirmation message for update_cell.

    The actual cell modification happens in the frontend editor (via _applyWriteAction).
    This function only generates the tool result that the LLM sees after user confirmation.
    """
    cell_index = args.get("cell_index", -1)
    description = args.get("description", "")
    notebook_name = (notebook_path or "").split("/")[-1] or "current notebook"
    return f"Cell {cell_index + 1} in {notebook_name} updated successfully. Changes: {description}"


async def _tool_insert_cell(args: dict, managers: dict,
                            project_id: str, notebook_path: str) -> str:
    """Return confirmation message for insert_cell.

    The actual cell insertion happens in the frontend editor (via _applyWriteAction).
    This function only generates the tool result that the LLM sees after user confirmation.
    """
    # LLM sends 1-based after_cell_index; convert to 0-based for frontend
    after_index_1 = int(args.get("after_cell_index", 0))
    after_index = after_index_1 - 1 if after_index_1 > 0 else -1
    args["after_cell_index"] = after_index
    cell_type = args.get("cell_type", "code")
    description = args.get("description", "")
    insert_pos = after_index_1 + 1 if after_index_1 > 0 else 1
    notebook_name = (notebook_path or "").split("/")[-1] or "current notebook"
    return f"New {cell_type} cell inserted at position {insert_pos} in {notebook_name}. Description: {description}"


async def _tool_update_file(action: dict, managers: dict) -> str:
    """Write updated content to a file on disk.

    Unlike cell updates (which happen in the frontend editor), file updates
    are written server-side since the file editor needs to reload.
    """
    file_path = action.get("file_path") or ""
    # Prefer executor_args when the action was transformed from another tool
    # (e.g. fix_lint_issues -> update_file). Falls back to action.args otherwise.
    effective_args = action.get("executor_args") or action["args"]
    new_content = effective_args.get("new_content", "")
    description = effective_args.get("description", "")
    project_id = action.get("project_id", "")

    if not file_path or not project_id:
        return f"Error: missing file_path or project_id"

    file_mgr = managers.get("files")
    if not file_mgr:
        return "Error: FileManager not available"

    from app.managers.project_registry import get_registry
    registry = get_registry()
    clean_id = registry.clean_id(project_id)
    root_type = "mount" if registry.is_mount(clean_id) else "project"

    try:
        file_mgr.write_file(root_type, clean_id, file_path, new_content)
        filename = file_path.split("/")[-1]
        return f"File {filename} updated successfully. Description: {description}"
    except Exception as e:
        return f"Error writing file: {type(e).__name__}: {e}"


async def _tool_create_file(action: dict, managers: dict) -> str:
    """Create a new file on disk."""
    file_path = action.get("file_path") or action["args"].get("file_path", "")
    content = action["args"].get("content", "")
    description = action["args"].get("description", "")
    project_id = action.get("project_id", "")

    if not file_path or not project_id:
        return f"Error: missing file_path or project_id"

    file_mgr = managers.get("files")
    if not file_mgr:
        return "Error: FileManager not available"

    try:
        from app.managers.project_registry import get_registry
        registry = get_registry()
        root_type = "mount" if registry.is_mount(project_id) else "project"
        file_mgr.write_file(root_type, project_id, file_path, content)
        return f"File {file_path} created successfully. Description: {description}"
    except Exception as e:
        return f"Error creating file: {type(e).__name__}: {e}"


async def _tool_search_docs(args: dict, managers: dict) -> str:
    """Search docs across every active Knowledge Base (Domain).

    Multi-active fan-out: queries every active Domain's `<id>__corpus`
    collection in parallel and merges by reranker score. Without the
    fan-out, a default-collection call hits the legacy `noted_corpus`
    name (gone since the per-Domain consolidation) and returns zero
    chunks even when the active eu_ai/etc Domain has perfect matches.

    Graceful-degradation-by-design: if noted-rag is unreachable, return
    a textual hint rather than raising. If no Domain returns a strong
    match, tell the Assistant to decline rather than fabricate.
    """
    rag_mgr = managers.get("rag")
    if not rag_mgr:
        return "Error: RagManager not available"

    _t_start = time.perf_counter()

    query = (args.get("query") or "").strip()
    if not query:
        return "Error: 'query' is required"
    tags = args.get("tags") or None
    if tags is not None and not isinstance(tags, list):
        tags = None
    source_paths = args.get("source_paths") or None
    if source_paths is not None and not isinstance(source_paths, list):
        source_paths = None
    top_k = int(args.get("top_k") or 5)

    from app.routers.kb import get_active_domains
    active_domains = get_active_domains() or ["noted"]

    # Single multi-collection search: noted-rag does ChromaDB fan-out
    # across all collections, merges by distance, and runs ONE reranker
    # batch — eliminates the per-Domain rerank-batch GPU contention that
    # used to cost ~1 s per active Domain.
    collections = [f"{did}__corpus" for did in active_domains]
    result = await rag_mgr.search_multi(
        query=query, collections=collections,
        tags=tags, top_k=top_k, source_paths=source_paths,
    )
    if not isinstance(result, dict):
        result = {"status": "unavailable", "chunks": []}
    any_unavailable = result.get("status") != "ok"

    chunks = []
    for c in result.get("chunks") or []:
        c2 = dict(c)
        # Map kb_id -> domain_id for output-side compatibility.
        if "kb_id" in c2 and "domain_id" not in c2:
            c2["domain_id"] = c2["kb_id"]
        chunks.append(c2)
    merged = chunks  # alias for name compatibility below

    if not chunks and any_unavailable and not merged:
        return (
            "Documentation search is currently unavailable. Answer from "
            "existing context, any active skills, or the conversation so far; "
            "or ask the user to retry later."
        )
    if not chunks:
        tag_suffix = f" with tags {tags}" if tags else ""
        return (
            f"No strong documentation match for query '{query}'{tag_suffix} "
            f"across active Domains ({', '.join(active_domains)}). "
            "Tell the user you do not have documented information on this, "
            "and do NOT fabricate an answer. You may suggest rephrasing the "
            "question or activating a different Domain."
        )

    # Citation instruction: the model must cite each used chunk with the
    # EXACT `[markdown_chunk:<hex>]` tag shown above its excerpt. Positive-
    # only instruction: do NOT use negative examples here. Gemma was
    # observed remixing the literal substrings of forbidden examples (e.g.
    # given `[kb=sw_arch, chunk 1]` as a "do NOT use" example, it produced
    # `[markdown_chunk:kb=sw_arch]` by copying the kb=sw_arch substring).
    # Keep the prompt anchored to the correct pattern only.
    lines = [
        f"Found {len(chunks)} documentation chunk(s) for query: {query}",
        "",
        "CITATION RULE:",
        "Each excerpt below is preceded by its citation tag in the form "
        "`[markdown_chunk:<12-character-hex>]`. When you use an excerpt in "
        "your answer, copy THAT EXACT TAG verbatim (the full bracketed string, "
        "including the brackets, the `markdown_chunk:` prefix, and the hex id) "
        "and place it immediately after the supported claim. Use ONLY tags "
        "that appear above an excerpt below; never invent a tag. If no chunk "
        "supports a claim, leave the claim uncited rather than fabricating.",
        "",
    ]
    for i, c in enumerate(chunks, 1):
        source_path = c.get("source_path", "") or ""
        section_path = c.get("section_path", "") or ""
        # Derive the noted-graph entity id from (source_path, chunk_index).
        # Chunk_index is the last `#`-separated segment of the chromadb id
        # (slug stripping in upsert_chunks guarantees no internal `#`).
        chunk_index = None
        cid = c.get("id") or ""
        if cid:
            tail = cid.rsplit("#", 1)[-1]
            try:
                chunk_index = int(tail)
            except (TypeError, ValueError):
                chunk_index = None
        cite_tag = ""
        if chunk_index is not None and source_path:
            graph_hex = hashlib.sha1(
                f"{source_path}#{chunk_index}".encode()
            ).hexdigest()[:12]
            cite_tag = f"[markdown_chunk:{graph_hex}]"
        # Header carries ONLY the tag + the source path (for the model's
        # benefit if it needs to mention the document by name). No `chunk N`
        # numbering, no `domain=...`, no score - those were the cues Gemma
        # remixed into invented citation formats.
        if cite_tag:
            header = f"--- {cite_tag}  source: {source_path} ---"
        else:
            header = f"--- source: {source_path} ---"
        lines.append(header)
        lines.append(c.get("text", "").strip())
        lines.append("")
    _t_total_ms = (time.perf_counter() - _t_start) * 1000
    logger.info(
        "TOOL_TIMING tool=search_docs domains=%s total_ms=%.1f",
        active_domains, _t_total_ms,
    )
    return "\n".join(lines).strip()


async def _tool_research_topic(args: dict, managers: dict) -> str:
    """Answer thematic / relational questions via GraphRAG.

    Returns the envelope's `answer` (markdown) directly, with a short
    footer listing citations + mode + communities used. If the graph is
    unavailable or empty, tell the Assistant to say so rather than fabricate.
    """
    gm = managers.get("graphrag")
    if not gm:
        return "Error: GraphRagManager not available"

    _t_start = time.perf_counter()

    question = (args.get("question") or "").strip()
    if not question:
        return "Error: 'question' is required"
    mode = (args.get("mode") or "auto").strip()
    if mode not in ("auto", "global", "local"):
        mode = "auto"
    # Domain routing: model picks from active Domains (workspace context
    # already lists them). Without this, gm.query() falls back to the
    # FIRST active Domain (alphabetical), which means EU AI answers SW
    # Agents questions etc. The model usually reasons correctly about
    # which domain is most relevant; we just need to honor its choice.
    # `resolve_domain_id` accepts either the slug (`sw_arch`) or the
    # human-readable name (`Software Agents`) - the model picks either.
    from app.routers.kb import resolve_domain_id
    domain_id = resolve_domain_id(args.get("domain_id"))

    envelope = await gm.query(question, mode=mode, kb_id=domain_id)

    if envelope.get("status") == "unavailable":
        return (
            "GraphRAG is currently unreachable. Tell the user the knowledge-"
            "graph service is down; fall back to search_docs if the question "
            "is about a specific fact."
        )

    answer = (envelope.get("answer") or "").strip()
    if not answer:
        return (
            "GraphRAG returned no answer for this question. Tell the user you "
            "don't have graph-backed information on this topic; do NOT fabricate."
        )

    citations = envelope.get("citations") or []
    mode_used = envelope.get("mode") or mode
    communities = envelope.get("communities_used") or []
    built_at = envelope.get("graph_built_at")
    rebuild_in_progress = envelope.get("rebuild_in_progress")

    footer_parts: list[str] = []
    if citations:
        footer_parts.append(f"citations: {', '.join(citations[:10])}")
        if len(citations) > 10:
            footer_parts.append(f"(+{len(citations) - 10} more)")
    footer_parts.append(f"mode={mode_used}")
    if communities:
        footer_parts.append(f"communities={communities}")
    if built_at:
        footer_parts.append(f"graph_built_at={built_at}")
    if rebuild_in_progress:
        footer_parts.append("rebuild_in_progress=true")
    footer = "\n\n---\n" + " | ".join(footer_parts) if footer_parts else ""

    # Side-channel: surface the GraphRAG subgraph so the chat router can
    # emit it as a `graph_provenance` SSE event for the per-answer trace
    # button. Without this, research_topic answers cite entities/edges/
    # communities but the user has no way to inspect the graph trace.
    metadata = managers.get("_tool_metadata")
    if metadata is not None:
        subgraph = envelope.get("subgraph") or {}
        # Use top-N highest-rank nodes as entry entities so the GraphPanel
        # trace UI's "Open full graph" button has a seed (it gates on the
        # presence of entry_entities[0]). Each carries kb_id so the panel
        # can build per-entity URLs against the correct Domain.
        nodes = subgraph.get("nodes") or []
        def _rank(n):
            return float((n.get("properties") or {}).get("rank") or 0)
        ranked_nodes = sorted(nodes, key=_rank, reverse=True)
        entry_entities = [
            {**n, "kb_id": domain_id} for n in ranked_nodes[:5]
        ]
        # Tag every node + edge with kb_id too so per-entity click-throughs
        # in the trace panel resolve to the right Domain.
        tagged_nodes = [{**n, "kb_id": domain_id} for n in nodes]
        tagged_edges = [{**e, "kb_id": domain_id} for e in (subgraph.get("edges") or [])]
        metadata["graph_provenance"] = {
            "question": question,
            "kb_id": domain_id,
            "entry_entities": entry_entities,
            "entities": tagged_nodes,
            "edges": tagged_edges,
            "per_entity_chunks": {},
            "per_edge_chunks": [],
            "chunk_excerpts": [],
            "communities_used": communities,
        }

    _t_total_ms = (time.perf_counter() - _t_start) * 1000
    logger.info(
        "TOOL_TIMING tool=research_topic domain=%s mode=%s total_ms=%.1f",
        domain_id, mode, _t_total_ms,
    )
    return answer + footer


async def _tool_graph_and_vector_search(args: dict, managers: dict) -> str:
    """Parallel graph + vector retrieval, single combined tool result.

    Pipeline (designed to actually achieve parallelism, not just appear to):
      1. Embed the query ONCE via noted-rag /embed.
      2. Fan out to noted-rag /search_by_vector (chunks + reranker) AND
         noted-graph /research/retrieve (vector input -> BFS) concurrently.
      3. Format both result sets into one tool-result payload.

    Why embed-once matters: previously both fan-out branches re-embedded
    the same query inside their respective endpoints. Both embeds hit the
    same noted-rag bge-m3 GPU, serializing there. The "parallel" call was
    ~80% of sequential. With this refactor, only the reranker (rag side)
    uses GPU - the graph side is pure HTTP + ChromaDB lookup + ArcadeDB
    BFS, all CPU - so the two sides run truly concurrently.

    Returns a single text payload for the chat-side Assistant Gemma to
    synthesize into one cohesive answer.
    """
    rag_mgr = managers.get("rag")
    gm = managers.get("graphrag")
    if not rag_mgr and not gm:
        return "Error: neither RagManager nor GraphRagManager available"

    _t_start = time.perf_counter()
    _t_embed_ms = None
    _t_fanout_ms = None

    question = (args.get("question") or "").strip()
    if not question:
        return "Error: 'question' is required"
    top_k = int(args.get("top_k_chunks") or 5)
    source_paths = args.get("source_paths") or None
    if source_paths is not None and not isinstance(source_paths, list):
        source_paths = None
    # Domain scoping: model picks from active Domains via `domain_id`. When
    # set, ONLY query that one Domain (focused answer, no cross-domain
    # noise). When omitted, fan out across all active Domains as before.
    # Accept either slug or human-readable name (model picks either).
    from app.routers.kb import resolve_domain_id
    requested_domain = resolve_domain_id(args.get("domain_id"))

    # ── Step 1: embed ONCE upfront (single GPU call) ───────────────
    query_vector: list[float] = []
    if rag_mgr:
        _t_e = time.perf_counter()
        embed_result = await rag_mgr.embed([question])
        _t_embed_ms = (time.perf_counter() - _t_e) * 1000
        if embed_result.get("status") == "ok":
            vectors = embed_result.get("vectors") or []
            if vectors:
                query_vector = vectors[0]

    # If embed failed, fall back to text-input endpoints (each will
    # re-embed; we lose the parallel win but still get an answer).
    use_vector = bool(query_vector)

    # ── Step 2: fan out concurrently ────────────────────────────────
    async def _noop():
        return None

    # Multi-active fan-out: query EVERY active Domain in parallel and merge.
    # Vector results: union all chunks, sort by reranker score, keep top_k.
    # Graph results: union entities + edges + chunk_excerpts, dedup by id.
    # Single-active is the n=1 case of the same code (no special branch).
    # When `domain_id` is provided by the model, scope to that one Domain
    # (the model has reasoned which Domain holds the answer; honor it).
    from app.routers.kb import get_active_domains
    active_kbs = get_active_domains() or ["noted"]
    if requested_domain and requested_domain in active_kbs:
        active_kbs = [requested_domain]

    def _coll(kb_id: str) -> str:
        # Convention only; the noted Domain's manifest is rewritten from
        # the legacy `noted_corpus` to `noted__corpus` by the Domain
        # migration on noted-graph startup.
        return f"{kb_id}__corpus"

    # Per-task timing for the graph branch only (rag is now ONE call).
    _per_task_ms: dict[str, float] = {}

    async def _track(label: str, coro):
        _t = time.perf_counter()
        try:
            return await coro
        finally:
            _per_task_ms[label] = round((time.perf_counter() - _t) * 1000, 1)

    # Rag side: ONE multi-collection search instead of N parallel calls.
    # noted-rag does Chroma fan-out, merges by distance, runs one rerank
    # batch, returns top_k chunks each tagged with kb_id. Eliminates the
    # rerank-batch GPU contention that was the dominant rag-side cost.
    if rag_mgr:
        rag_collections = [_coll(k) for k in active_kbs]
        if use_vector:
            rag_call = rag_mgr.search_multi(
                query=question, collections=rag_collections,
                top_k=top_k, source_paths=source_paths, vector=query_vector,
            )
        else:
            rag_call = rag_mgr.search_multi(
                query=question, collections=rag_collections,
                top_k=top_k, source_paths=source_paths,
            )
        rag_task = _track('rag:multi', rag_call)
    else:
        rag_task = _noop()

    # Graph side: per-kb fan-out (ArcadeDB is per-Domain, not poolable).
    graph_tasks = []
    for kb_id in active_kbs:
        if gm:
            if use_vector:
                graph_tasks.append(_track(f'graph:{kb_id}', gm.retrieve_by_vector(query_vector, kb_id=kb_id)))
            else:
                graph_tasks.append(_track(f'graph:{kb_id}', gm.retrieve(question, mode="local", kb_id=kb_id)))
        else:
            graph_tasks.append(_noop())

    _t_f = time.perf_counter()
    all_results = await asyncio.gather(rag_task, *graph_tasks, return_exceptions=True)
    _t_fanout_ms = (time.perf_counter() - _t_f) * 1000
    rag_multi_result = all_results[0]
    graph_results_per_kb = list(all_results[1:])

    # Rag result: chunks already merged + reranked server-side, tagged
    # with kb_id. No further per-Domain merging needed.
    if isinstance(rag_multi_result, Exception):
        rag_result = {
            "status": "unavailable",
            "detail": f"{type(rag_multi_result).__name__}: {rag_multi_result}",
            "chunks": [],
        }
    elif not rag_multi_result or rag_multi_result.get("status") != "ok":
        rag_result = {"status": "unavailable", "chunks": []}
    else:
        rag_result = {"status": "ok", "chunks": rag_multi_result.get("chunks") or []}

    # Merge graph results across KBs: union entry_entities + entities +
    # edges + chunk_excerpts deduped by id. Tag each entity/excerpt with
    # its source kb_id.
    graph_errors: list[str] = []
    merged_entry: list[dict] = []
    merged_entities: list[dict] = []
    merged_edges: list[dict] = []
    merged_excerpts: list[dict] = []
    merged_per_entity: dict[str, list[str]] = {}
    merged_per_edge: list[dict] = []
    seen_entity_ids: set[str] = set()
    seen_edge_keys: set[str] = set()
    seen_excerpt_ids: set[str] = set()
    notes: list[str] = []
    for kb_id, gr in zip(active_kbs, graph_results_per_kb):
        if isinstance(gr, Exception):
            graph_errors.append(f"{kb_id}: {type(gr).__name__}: {gr}")
            continue
        if not gr or gr.get("status") == "unavailable":
            continue
        if gr.get("note"):
            notes.append(f"{kb_id}: {gr['note']}")
            continue
        for e in gr.get("entry_entities") or []:
            eid = e.get("id")
            if eid and eid not in seen_entity_ids:
                seen_entity_ids.add(eid)
                merged_entry.append({**e, "kb_id": kb_id})
        for e in gr.get("entities") or []:
            eid = e.get("id")
            if not eid or eid in seen_entity_ids:
                continue
            seen_entity_ids.add(eid)
            merged_entities.append({**e, "kb_id": kb_id})
        for ed in gr.get("edges") or []:
            key = f"{ed.get('source')}|{ed.get('target')}|{ed.get('type')}"
            if key in seen_edge_keys:
                continue
            seen_edge_keys.add(key)
            merged_edges.append({**ed, "kb_id": kb_id})
        for c in gr.get("chunk_excerpts") or []:
            cid = c.get("id")
            if cid and cid in seen_excerpt_ids:
                continue
            if cid:
                seen_excerpt_ids.add(cid)
            merged_excerpts.append({**c, "kb_id": kb_id})
        # Per-entity / per-edge grounding: shallow-merge dicts/lists.
        for eid, cids in (gr.get("per_entity_chunks") or {}).items():
            cur = merged_per_entity.setdefault(eid, [])
            for cid in cids:
                if cid not in cur:
                    cur.append(cid)
        for ec in (gr.get("per_edge_chunks") or []):
            merged_per_edge.append(ec)
    if merged_entry or merged_entities or merged_edges:
        graph_result = {
            "status": "ok",
            "entry_entities": merged_entry,
            "entities": merged_entities,
            "edges": merged_edges,
            "chunk_excerpts": merged_excerpts,
            "per_entity_chunks": merged_per_entity,
            "per_edge_chunks": merged_per_edge,
            "active_kbs": active_kbs,
        }
        if notes:
            graph_result["note"] = "; ".join(notes)
    elif notes:
        graph_result = {"note": "; ".join(notes)}
    elif graph_errors:
        graph_result = {"status": "unavailable", "detail": "; ".join(graph_errors)}
    else:
        graph_result = {"status": "ok", "entry_entities": [], "entities": [], "edges": [], "chunk_excerpts": []}

    out_parts: list[str] = [
        f"Combined retrieval for question: {question}\n",
        "## How to use this output",
        "Two complementary sources follow. Both should inform your single answer:",
        "- Documentation chunks (vector RAG): pre-formed prose passages from noted's docs, ranked by semantic relevance and reranker score. STRONGEST FOR specific facts, quoted procedures, exact API/config details, and direct passages you can cite.",
        "- Knowledge graph context: entities (concepts/components/people/etc.) and the relationships between them, with the SUPPORTING DOCUMENTATION CHUNKS that mention each entity and each relationship attached inline. STRONGEST FOR structural connections (\"X is part of Y\", \"X relates to Y\"), thematic groupings, and tracing how different parts of the platform interact.",
        "Use the chunks for the substance and quotes; use the graph for the connecting tissue. The supporting chunks attached to each graph item ARE the evidence that lets you trust and cite the relationship.\n",
        "## Citation rule",
        "Each chunk excerpt below has a header line of the form "
        "`### [markdown_chunk:<HEX>]  source: <path>` where `<HEX>` is a "
        "12-character lowercase hexadecimal id (only the characters 0-9 "
        "and a-f). The complete bracketed string from a header is the "
        "ONLY valid citation tag value.",
        "Most sentences in your answer should have NO citation tag. "
        "Uncited prose is the default. Cite only the specific load-bearing "
        "claims that quote or paraphrase a particular excerpt.",
        "When you do cite, copy the bracketed tag character-for-character "
        "from the header above the excerpt you used (the brackets, the "
        "literal text `markdown_chunk:`, and the exact 12 hex characters). "
        "Place the tag immediately after the sentence it supports.",
        "Numbers that appear inside chunk text (article numbers, recital "
        "numbers, page numbers, paragraph numbers, section numbers) are "
        "part of the source content; they are NOT tag values. If you "
        "cannot find an exact `[markdown_chunk:<HEX>]` header above an "
        "excerpt that supports your claim, write the claim with no tag.\n",
    ]

    # Build a chunk_id -> citation tag map shared by the chunks section AND
    # the graph grounding section (which references chunks by id), so both
    # surfaces present the same citation tag for the same chunk.
    cite_tag_by_id: dict[str, str] = {}
    def _compute_cite_tag(c: dict) -> str:
        cid = c.get("id") or ""
        if not cid:
            return ""
        if cid in cite_tag_by_id:
            return cite_tag_by_id[cid]

        # Graph-side chunks (from noted-graph's _chunk_excerpts) arrive
        # with id already in `markdown_chunk:<hex>` form. Use it directly.
        # Vector-side chunks arrive with id like `<source_path>#<chunk_index>`
        # and we compute the hex from sha1(source#index)[:12].
        if cid.startswith("markdown_chunk:"):
            body = cid.split(":", 1)[1]
            if re.fullmatch(r"[0-9a-f]{8,16}", body):
                tag = f"[{cid}]"
                cite_tag_by_id[cid] = tag
                return tag
            return ""

        # Vector-side: source_path is required to compute the hash. Some
        # callers may pass `doc_path` instead, so accept either.
        source_path = c.get("source_path") or c.get("doc_path") or ""
        if not source_path:
            return ""
        tail = cid.rsplit("#", 1)[-1]
        try:
            chunk_index = int(tail)
        except (TypeError, ValueError):
            return ""
        graph_hex = hashlib.sha1(
            f"{source_path}#{chunk_index}".encode()
        ).hexdigest()[:12]
        tag = f"[markdown_chunk:{graph_hex}]"
        cite_tag_by_id[cid] = tag
        return tag

    # ── Vector chunks ───────────────────────────────────────────────
    out_parts.append("## Documentation chunks (vector RAG)\n")
    if isinstance(rag_result, Exception):
        out_parts.append(f"_RAG search failed: {type(rag_result).__name__}: {rag_result}_\n")
    elif not rag_result or rag_result.get("status") == "unavailable":
        out_parts.append("_Documentation search unavailable._\n")
    else:
        chunks = rag_result.get("chunks") or []
        if not chunks:
            out_parts.append("_No documentation chunks matched._\n")
        else:
            for c in chunks:
                cite_tag = _compute_cite_tag(c)
                source_path = c.get("source_path", "") or ""
                # Header carries ONLY the citation tag + source path. No
                # `chunk N` numbering, no score, no kb=... - those were
                # cues the model remixed into invented citation formats.
                if cite_tag:
                    hdr = f"### {cite_tag}  source: {source_path}"
                else:
                    hdr = f"### source: {source_path}"
                out_parts.append(hdr)
                out_parts.append((c.get("text") or "").strip())
                out_parts.append("")

    # ── Graph context with grounding ────────────────────────────────
    out_parts.append("## Knowledge graph context (entities + relationships, each with supporting chunks)\n")
    if isinstance(graph_result, Exception):
        out_parts.append(f"_Graph retrieve failed: {type(graph_result).__name__}: {graph_result}_\n")
    elif not graph_result or graph_result.get("status") == "unavailable":
        out_parts.append("_Knowledge graph unavailable._\n")
    elif graph_result.get("note"):
        out_parts.append(f"_{graph_result['note']}_\n")
    else:
        entry = graph_result.get("entry_entities") or []
        ents = graph_result.get("entities") or []
        edges = graph_result.get("edges") or []
        chunk_excerpts = graph_result.get("chunk_excerpts") or []
        per_entity_chunks = graph_result.get("per_entity_chunks") or {}
        per_edge_chunks = graph_result.get("per_edge_chunks") or []

        # Index excerpts by id for O(1) lookup when rendering grounding
        excerpt_by_id = {c.get("id"): c for c in chunk_excerpts if c.get("id")}

        def _render_chunk_brief(cid: str) -> str:
            c = excerpt_by_id.get(cid)
            if not c:
                return f"  - _(chunk not in excerpt set)_"
            cite_tag = _compute_cite_tag(c)
            # Graph-side chunks use `doc_path` rather than `source_path`.
            source_path = c.get("source_path") or c.get("doc_path") or ""
            text = (c.get("text") or "").strip().replace("\n", " ")
            tag_prefix = f"{cite_tag} " if cite_tag else ""
            return f"  - {tag_prefix}_from {source_path}:_ {text[:280]}"

        if entry:
            entry_labels = []
            for e in entry[:10]:
                lbl = e.get("label") or e.get("id", "")
                typ = e.get("type") or ""
                entry_labels.append(f"{lbl} ({typ})" if typ else lbl)
            out_parts.append("**Entry entities (vector hits on entity index):** "
                             + ", ".join(entry_labels))
            out_parts.append("")

        # Sort entities by rank, cap to top 12 (matches retriever's grounding cap)
        def _erank(e):
            return -float(((e.get("properties") or {}).get("rank") or 0))
        ents_sorted = sorted(ents, key=_erank)[:12]
        if ents_sorted:
            out_parts.append("### Top entities with their supporting chunks")
            for e in ents_sorted:
                eid = e.get("id", "") or ""
                lbl = e.get("label") or eid
                typ = e.get("type", "")
                desc = (e.get("properties") or {}).get("description", "")
                # Embed the canonical citation tag inline so the model copies
                # it verbatim. Citing by label produced 404s because the
                # /api/citations/E:<id> resolver expects the entity_id, not
                # the human-readable label.
                e_tag = f"[E:{eid}] " if eid else ""
                out_parts.append(f"- {e_tag}**{lbl}** ({typ}): {desc[:200]}")
                grounding = per_entity_chunks.get(eid) or []
                for cid in grounding:
                    out_parts.append(_render_chunk_brief(cid))
            out_parts.append("")

        if per_edge_chunks:
            out_parts.append("### Relationships with their supporting chunks (chunks that mention BOTH endpoints)")
            for ec in per_edge_chunks[:30]:
                src = ec.get('source','')
                tgt = ec.get('target','')
                etype = ec.get('type','')
                # R: tag form is `R:src>type>tgt` (parsed by the citation
                # resolver via str.split('>')). Inject inline to match the
                # entity-tag pattern.
                r_tag = f"[R:{src}>{etype}>{tgt}] " if src and tgt else ""
                out_parts.append(f"- {r_tag}**{src}** —[{etype}]→ **{tgt}**")
                for cid in ec.get("chunk_ids") or []:
                    out_parts.append(_render_chunk_brief(cid))
            out_parts.append("")
        elif edges:
            # Fallback: no co-mention chunks found, list relationships unsupported
            out_parts.append("### Relationships (top 30, no co-mention chunks found)")
            for r in edges[:30]:
                src = r.get('source','')
                tgt = r.get('target','')
                etype = r.get('type','')
                r_tag = f"[R:{src}>{etype}>{tgt}] " if src and tgt else ""
                out_parts.append(f"- {r_tag}`{src}` —[{etype}]→ `{tgt}`")
            out_parts.append("")

    # Side-channel: stash the structured graph payload so the chat router
    # can emit it as a `graph_provenance` SSE event for the per-answer
    # trace UI. Tools that don't write here have no SSE side-effect.
    metadata = managers.get("_tool_metadata")
    if metadata is not None and isinstance(graph_result, dict) and not isinstance(graph_result, Exception):
        metadata["graph_provenance"] = {
            "question": question,
            "entry_entities": graph_result.get("entry_entities") or [],
            "entities": graph_result.get("entities") or [],
            "edges": graph_result.get("edges") or [],
            "per_entity_chunks": graph_result.get("per_entity_chunks") or {},
            "per_edge_chunks": graph_result.get("per_edge_chunks") or [],
            "chunk_excerpts": graph_result.get("chunk_excerpts") or [],
        }

    _t_total_ms = (time.perf_counter() - _t_start) * 1000
    _per_task_str = " ".join(f"{k}={v}" for k, v in sorted(_per_task_ms.items())) if _per_task_ms else "-"
    logger.info(
        "TOOL_TIMING tool=graph_and_vector_search domains=%s embed_ms=%s fanout_ms=%s total_ms=%.1f tasks=[%s]",
        active_kbs,
        f"{_t_embed_ms:.1f}" if _t_embed_ms is not None else "-",
        f"{_t_fanout_ms:.1f}" if _t_fanout_ms is not None else "-",
        _t_total_ms,
        _per_task_str,
    )
    return "\n".join(out_parts).strip()

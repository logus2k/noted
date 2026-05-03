"""LLM Context Assembly - builds workspace context blocks for LLM prompts.

Reads live state from existing managers (notebook, MLflow, Hydra, DVC, Airflow)
and assembles it into a structured context message injected into the conversation.
"""

import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum characters for a single cell output before truncation
MAX_OUTPUT_CHARS = 2000
# Maximum number of cells to include in notebook context
MAX_CELLS = 20
# Maximum characters for the entire notebook context block
MAX_NOTEBOOK_CHARS = 12000


def strip_thinking(content: str) -> str:
    """Remove <think>...</think> blocks from assistant messages in history.

    Per Qwen 3 best practices, thinking content should not be included
    in conversation history sent back to the model.
    """
    return re.sub(r'<think>[\s\S]*?</think>\s*', '', content).strip()


def clean_history(messages: list[dict]) -> list[dict]:
    """Strip thinking blocks from assistant content in conversation history.

    Structured fields (`tool_calls`, `tool_call_id`, `name`) and non-string
    content (Anthropic content-block lists) pass through untouched so the
    asf0 chat template renders prior tool calls/responses in its native
    pipe-marker format.
    """
    cleaned = []
    for msg in messages:
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
            cleaned.append({**msg, "content": strip_thinking(msg["content"])})
        else:
            cleaned.append(msg)
    return cleaned


async def build_context_message(ctx: dict, managers: dict) -> Optional[dict]:
    """Build a context block injected as the first user message.

    Args:
        ctx: Context descriptor from the frontend, with keys like
             notebook_path, selected_cell_index, active_run_id, etc.
        managers: Dict of manager instances keyed by name:
                  {"notebook": NotebookManager, "mlflow": MlflowManager,
                   "hydra": HydraManager, "dvc": DvcManager, "airflow": AirflowManager}

    Returns:
        A message dict {"role": "user", "content": "WORKSPACE CONTEXT:..."}
        or None if no context is available.
    """
    # Layout split for KV prefix-cache friendliness:
    #   static_blocks   - byte-stable across turns within a session
    #                      (active domains, ACTIVE SKILLS rendered later)
    #   volatile_blocks - may change turn-to-turn (notebook content, file,
    #                      run state, hydra config)
    # Final content order: header + manifest -> static_blocks -> volatile_blocks
    # Putting volatile AFTER static means a notebook edit only invalidates the
    # cache from the notebook block onward, leaving the (often large) skills
    # block cached.
    static_blocks: list[str] = []
    volatile_blocks: list[str] = []
    # Short descriptions of content already inlined below - surfaced at the top
    # of the context as a "read-this-first" manifest so the model doesn't reach
    # for get_file_contents / get_notebook_cells when the answer is already in
    # its own context (lost-in-the-middle mitigation for long contexts).
    inlined_manifest: list[str] = []

    # ACTIVE DOMAINS block - tells the assistant which Knowledge Bases are
    # currently active. The general Domain (always active) covers universal
    # behavior; other Domains expose their own knowledge + skills + tools.
    # The assistant should consult this list to decide which tools to call
    # and which subjects it can answer authoritatively.
    domains_block = await _active_domains_block()
    if domains_block:
        static_blocks.append(domains_block)

    # Notebook context
    if ctx.get("notebook_path") and ctx.get("project_id"):
        block, inlined = _notebook_block(ctx, managers.get("notebook"))
        if block:
            volatile_blocks.append(block)
        if inlined:
            inlined_manifest.append(inlined)

        # Local project imports referenced by the notebook (src/**.py etc.)
        imports_block, imports_inlined = _project_imports_block(ctx, managers.get("notebook"))
        if imports_block:
            volatile_blocks.append(imports_block)
        if imports_inlined:
            inlined_manifest.append(imports_inlined)

    # File context (non-notebook files: .py, .yaml, .json, .md, etc.)
    if ctx.get("file_path") and not ctx.get("notebook_path"):
        block = _file_block(ctx)
        if block:
            volatile_blocks.append(block)

    # MLflow run context (specific run if active, otherwise experiment summary)
    if ctx.get("active_run_id"):
        block = _run_block(ctx, managers.get("mlflow"))
        if block:
            volatile_blocks.append(block)
    elif ctx.get("project_id"):
        block = _experiment_summary_block(ctx, managers.get("mlflow"))
        if block:
            volatile_blocks.append(block)

    # Hydra config context
    if ctx.get("hydra_config_hash") and ctx.get("project_id"):
        block = _config_block(ctx, managers.get("hydra"))
        if block:
            volatile_blocks.append(block)

    # Match skills against context+blocks. Skills themselves are stable per
    # session; we render them into static_blocks so they sit in the cache-
    # friendly prefix. _get_matched_skills inspects block content for
    # keywords like "MLFLOW EXPERIMENT" / "HYDRA" - pass the full set so
    # the keyword-driven skill triggers still fire.
    skill_names: list[str] = []
    matched_skills = _get_matched_skills(ctx, static_blocks + volatile_blocks)
    if matched_skills:
        skill_names = [name for name, _ in matched_skills]
        lines = ["ACTIVE SKILLS (authoritative instructions for current context):"]
        for name, skill_content in matched_skills:
            lines.append(f"\n[{name}]\n{skill_content}")
        static_blocks.append("\n".join(lines))

    if not static_blocks and not volatile_blocks:
        return None, []

    header = "WORKSPACE CONTEXT:"
    if inlined_manifest:
        header += (
            "\n\nALREADY INLINED BELOW (answer from this content directly; do NOT "
            "call get_notebook_cells or get_file_contents for any of these):"
        )
        for entry in inlined_manifest:
            header += f"\n  - {entry}"
    content = header + "\n\n" + "\n\n".join(static_blocks + volatile_blocks)

    return {"role": "user", "content": content}, skill_names


async def _active_domains_block() -> Optional[str]:
    """List the active Knowledge Bases (Domains) with their descriptions.

    Returns the formatted block string, or None if the call fails (e.g.
    backend Domain registry unreachable). The assistant uses this list
    to decide which knowledge sources are available for the current turn.

    Async + AsyncClient + direct noted-graph call. Earlier version used
    sync httpx.Client against the localhost noted endpoint - that blocks
    the event loop AND tries to call noted itself (single worker = near-
    deadlock until the 5-second timeout fires). Caused +5000ms per turn
    in the chat handler. See feedback_async_proxy_no_sync_io.md.
    """
    try:
        from app.routers.kb import get_active_domains, NOTED_GRAPH_BASE
        import httpx
        active_ids = set(get_active_domains())
        if not active_ids:
            return None
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{NOTED_GRAPH_BASE}/domains")
            if r.status_code != 200:
                return None
            data = r.json()
            domains = data.get('domains') or []
        # Sort by domain_id so the rendered block is byte-stable regardless
        # of the upstream /domains API response order. Critical for KV-cache
        # prefix reuse - ANY ordering wobble here invalidates the cached
        # tokens for everything that follows.
        active_domains = sorted(
            (d for d in domains if d.get('domain_id') in active_ids),
            key=lambda d: d.get('domain_id') or '',
        )
        if not active_domains:
            return None
        lines = [
            "ACTIVE KNOWLEDGE BASES (Domains the assistant currently knows about):",
            "  Format: <human-readable name> (slug=<domain_id>) [scope]: description",
            "  Scoping rules:",
            "    - search_docs / search across docs queries ALL active Domains automatically. Do NOT try to scope it.",
            "    - graph_and_vector_search / research_topic accept a `domain_id` parameter that takes the SLUG (e.g. `sw_arch`), not the human-readable name.",
            "    - Human-readable names are LABELS for the user, never filter values for tools.",
        ]
        for d in active_domains:
            name = d.get('name') or d.get('domain_id')
            slug = d.get('domain_id')
            desc = d.get('description') or '(no description)'
            has_k = d.get('has_knowledge', False)
            cap = ' [knowledge + skills/tools]' if has_k else ' [skills/tools only]'
            lines.append(f"  - {name} (slug={slug}){cap}: {desc}")
        return "\n".join(lines)
    except Exception:
        return None


def _get_matched_skills(ctx: dict, blocks: list) -> list:
    """Determine context conditions and return matching priority-1 skills."""
    try:
        from app.managers.llm_skills import get_registry
        registry = get_registry()
    except Exception:
        return []

    # Build set of active context conditions from what's present.
    # `always` is unconditionally true - skills with triggers=[always] fire
    # on every turn (used by Domain-foundational behavior like fairness,
    # tool-call discipline, voice format).
    conditions = set()
    conditions.add("always")

    # Generic: a project is open (any workspace active). Skills that are
    # about the noted platform itself - overview, help, troubleshooting -
    # use this as their auto-inject trigger since "what is noted?" style
    # questions can come up any time a workspace is active.
    if ctx.get("project_id"):
        conditions.add("workspace_active")

    # Check notebook or file context
    if ctx.get("notebook_path"):
        conditions.add("notebook_cell_selected")
    if ctx.get("file_path"):
        conditions.add("file_open_in_editor")

    # Check MLflow context - detect from blocks content
    blocks_text = "\n".join(blocks) if blocks else ""
    if "MLFLOW EXPERIMENT" in blocks_text or ctx.get("active_run_id"):
        conditions.add("mlflow_experiment_in_context")
    if ctx.get("active_run_id"):
        conditions.add("mlflow_run_in_context")
    # Check for failed run in context
    if "FAILED" in blocks_text:
        conditions.add("mlflow_run_failed")

    # Check linter context - Python file open with LSP
    if ctx.get("file_path") and str(ctx.get("file_path", "")).endswith(".py"):
        conditions.add("linter_rule")

    # Check Hydra context
    if ctx.get("hydra_config_hash") or "HYDRA" in blocks_text:
        conditions.add("hydra_config_in_context")

    # Check for Hydra + DAG combination
    if "hydra_config_in_context" in conditions and "dag" in blocks_text.lower():
        conditions.add("hydra_and_dag_in_context")

    # Filesystem-derived project feature signals. Each gates priority-1
    # skills about that domain; skills only load when the user actually has
    # a surface to work on (dags/, config/, .dvc, monitoring).
    project_id = ctx.get("project_id")
    if project_id:
        try:
            from app.config import PROJECTS_DIR
            import os as _os

            project_root = _os.path.join(PROJECTS_DIR, project_id)

            # Airflow: dags/*.py
            dags_dir = _os.path.join(project_root, "dags")
            if _os.path.isdir(dags_dir):
                for entry in _os.listdir(dags_dir):
                    if entry.endswith(".py"):
                        conditions.add("airflow_in_context")
                        break

            # Hydra: config/config.yaml or any config/*.yaml
            config_dir = _os.path.join(project_root, "config")
            if _os.path.isdir(config_dir):
                for entry in _os.listdir(config_dir):
                    if entry.endswith((".yaml", ".yml")):
                        conditions.add("hydra_in_context")
                        break

            # DVC: .dvc/ directory or any *.dvc file at the project root
            dvc_meta = _os.path.join(project_root, ".dvc")
            if _os.path.isdir(dvc_meta):
                conditions.add("dvc_in_context")
            else:
                try:
                    for entry in _os.listdir(project_root):
                        if entry.endswith(".dvc"):
                            conditions.add("dvc_in_context")
                            break
                except Exception:
                    pass
                # Also inspect data/ (DVC files often live there)
                data_dir = _os.path.join(project_root, "data")
                if _os.path.isdir(data_dir):
                    for entry in _os.listdir(data_dir):
                        if entry.endswith(".dvc"):
                            conditions.add("dvc_in_context")
                            break

            # Evidently: monitor/ folder or any evidently config file
            monitor_dir = _os.path.join(project_root, "monitor")
            if _os.path.isdir(monitor_dir):
                conditions.add("evidently_in_context")
        except Exception:
            pass

    if not conditions:
        return []

    # Filter by active Domains so toggling a Domain off also silences its
    # auto-injected skills. Legacy data/skills/ entries are tagged
    # domain_id='noted' and surface only when 'noted' is active.
    try:
        from app.routers.kb import get_active_domains
        active_domains = get_active_domains()
    except Exception:
        active_domains = None

    return registry.get_static_skills(conditions, active_domains=active_domains)


# ── Individual context block builders ─────────────────────────────


FILE_CONTEXT_MAX_CHARS = 20000  # ~5k tokens; truncate very large files


def _file_block(ctx: dict) -> Optional[str]:
    """Build file context for the currently open non-notebook file.

    Inlines the in-memory (potentially unsaved) content directly so the model
    always sees the current editor state without needing a get_file_contents call.
    Falls back to a tool-call hint if content was not provided.
    """
    file_path = ctx.get("file_path", "")
    file_content = ctx.get("file_content", "")

    if not file_path:
        return None

    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    lang_map = {
        'py': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript',
        'yaml': 'YAML', 'yml': 'YAML', 'json': 'JSON', 'md': 'Markdown',
        'html': 'HTML', 'css': 'CSS', 'sh': 'Shell', 'bash': 'Shell',
        'toml': 'TOML', 'cfg': 'Config', 'ini': 'Config', 'txt': 'Text',
        'r': 'R', 'sql': 'SQL', 'dockerfile': 'Dockerfile',
    }
    lang = lang_map.get(ext, ext.upper() or 'Text')

    project_id = ctx.get("project_id", "")
    full_path = f"{project_id}/{file_path}" if project_id else file_path

    logger.info("FILE CONTEXT: project_id=%r file_path=%r full_path=%r", project_id, file_path, full_path)

    lines = ["FILE CONTEXT:"]
    lines.append(f"File: {file_path} ({lang})")
    lines.append(f"Project: {project_id}")
    lines.append(f"Full path for tools: {full_path}")
    lines.append(f"To edit this file, use update_file with the complete new content. Do NOT use get_file_contents - the content is already below.")

    if file_content:
        truncated = len(file_content) > FILE_CONTEXT_MAX_CHARS
        display = file_content[:FILE_CONTEXT_MAX_CHARS] if truncated else file_content
        lines.append("Content (current in-memory state, may include unsaved changes):")
        lines.append(f"```{ext}")
        lines.append(display)
        lines.append("```")
        if truncated:
            lines.append("[truncated - use get_file_contents for lines beyond this point]")
    else:
        lines.append(f"Use get_file_contents with path=\"{ctx.get('project_id', '')}/{file_path}\" to read the content.")

    return "\n".join(lines)


# Inline the whole notebook into the context block when total cell source is at or
# under this many characters (~15K tokens). Above it, fall back to metadata +
# a fetch-on-demand hint so the model calls get_notebook_cells.
NOTEBOOK_INLINE_THRESHOLD_CHARS = 60000
NOTEBOOK_INLINE_MAX_CELL_CHARS = 8000


def _notebook_block(ctx: dict, notebook_mgr) -> tuple[Optional[str], Optional[str]]:
    """Build the notebook context block.

    Small notebooks (total source <= NOTEBOOK_INLINE_THRESHOLD_CHARS) are
    inlined in full so the model does not need a get_notebook_cells call.
    Larger notebooks fall back to a metadata summary + instruction to fetch
    cells on demand.

    Returns (block_text, manifest_entry). manifest_entry is non-None only when
    the block actually inlines the notebook content (so it can be surfaced in
    the top-of-context manifest).
    """
    if not notebook_mgr:
        return None, None

    project_id = ctx.get("project_id", "")
    notebook_path = ctx.get("notebook_path", "")
    if not project_id or not notebook_path:
        return None, None

    # Prefer in-memory cells from the browser (unsaved changes); fall back to disk.
    cells = ctx.get("notebook_cells")
    if cells is None:
        try:
            notebook = notebook_mgr.get_notebook(project_id, notebook_path)
            cells = notebook.get("cells", [])
        except Exception as e:
            logger.warning("Failed to load notebook for LLM context: %s", e)
            return None, None

    total = len(cells)
    if total == 0:
        return None, None

    selected_indices = sorted(ctx.get("selected_cell_indices") or [])
    selected_line = (
        f"User's current selection: cell(s) {[i + 1 for i in selected_indices]}"
        if selected_indices else "No cell currently selected."
    )

    def _cell_source(c):
        s = c.get("source", "")
        return ("".join(s) if isinstance(s, list) else s).rstrip()

    sources = [_cell_source(c) for c in cells]
    total_source_chars = sum(len(s) for s in sources)

    if total_source_chars <= NOTEBOOK_INLINE_THRESHOLD_CHARS:
        lines = [
            "NOTEBOOK CONTEXT (full source inlined below - do NOT call get_notebook_cells):",
            f"File: {notebook_path} | MLflow experiment: {project_id} | Total cells: {total}",
            selected_line,
            "",
        ]
        for i, (cell, src) in enumerate(zip(cells, sources)):
            cell_type = cell.get("cell_type", "code")
            if len(src) > NOTEBOOK_INLINE_MAX_CELL_CHARS:
                overflow = len(src) - NOTEBOOK_INLINE_MAX_CELL_CHARS
                src = src[:NOTEBOOK_INLINE_MAX_CELL_CHARS] + f"\n...(cell source truncated, {overflow} more chars)"
            lines.append(f"[Cell {i + 1} - {cell_type}]")
            lines.append(src if src else "(empty)")
            lines.append("")
        manifest = f"Notebook `{notebook_path}` - all {total} cells inlined verbatim below"
        return "\n".join(lines).rstrip(), manifest

    # Fallback: metadata + fetch-on-demand
    lines = [
        "NOTEBOOK CONTEXT:",
        f"File: {notebook_path} | MLflow experiment: {project_id} | Total cells: {total}",
        selected_line,
        f"Cell contents are NOT included here (notebook exceeds inline threshold of "
        f"{NOTEBOOK_INLINE_THRESHOLD_CHARS:,} chars; this notebook is ~{total_source_chars:,}). "
        f"You MUST call get_notebook_cells immediately - do NOT say you are waiting or that "
        f"contents are loading. Call: "
        f"get_notebook_cells(project_id=\"{project_id}\", notebook_path=\"{notebook_path}\"). "
        f"Use indices=[...] for specific cells, from_index/to_index for a range, or omit "
        f"index params to get all cells. Add include_outputs=true to see outputs.",
    ]
    return "\n".join(lines), None


# Budgets for the local-imports block (Fix 5).
IMPORTS_TOTAL_CHAR_BUDGET = 40000  # Skip inlining if total exceeds this.
IMPORTS_PER_FILE_CHAR_CAP = 8000   # Truncate any single file above this.


_IMPORT_RE = None


def _get_import_re():
    global _IMPORT_RE
    if _IMPORT_RE is None:
        import re
        # Matches top-level `import X.Y` and `from X.Y import ...`
        # Captures the dotted module name in either case.
        _IMPORT_RE = re.compile(
            r'^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))',
            re.MULTILINE,
        )
    return _IMPORT_RE


def _extract_imported_modules(cells: list) -> set[str]:
    """Scan every code cell for import statements and return the set of
    dotted module names referenced (e.g. {'src.data.ingestion', 'numpy'})."""
    regex = _get_import_re()
    modules: set[str] = set()
    for c in cells:
        if c.get("cell_type") != "code":
            continue
        src = c.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        for m in regex.finditer(src):
            mod = m.group(1) or m.group(2)
            if mod:
                modules.add(mod)
    return modules


def _resolve_local_module(project_root: str, mod: str) -> Optional[str]:
    """Resolve a dotted module name to an absolute file path under project_root
    if it corresponds to a user-local .py module. Returns None for third-party
    modules (which do not exist on disk inside the project)."""
    import os
    parts = mod.split(".")
    if not parts:
        return None
    # 1. Module as a single .py file (e.g. src.data.ingestion -> src/data/ingestion.py)
    candidate = os.path.join(project_root, *parts) + ".py"
    real = os.path.realpath(candidate)
    project_real = os.path.realpath(project_root)
    if (os.path.isfile(candidate)
            and (real == project_real or real.startswith(project_real + os.sep))):
        return candidate
    # 2. Module as a package (e.g. src.data -> src/data/__init__.py)
    candidate_init = os.path.join(project_root, *parts, "__init__.py")
    real_init = os.path.realpath(candidate_init)
    if (os.path.isfile(candidate_init)
            and (real_init == project_real or real_init.startswith(project_real + os.sep))):
        return candidate_init
    return None


def _project_imports_block(ctx: dict, notebook_mgr) -> tuple[Optional[str], Optional[str]]:
    """Inline the user's own Python modules that the notebook imports.

    Returns (block_text, manifest_entry). manifest_entry is non-None only when
    files are actually inlined (not when we fall back to the over-budget file
    list).
    """
    if not notebook_mgr:
        return None, None
    project_id = ctx.get("project_id", "")
    if not project_id:
        return None, None

    try:
        from app.managers.project_registry import get_registry
        project_root = get_registry().resolve(project_id)
    except Exception as e:
        logger.warning("Failed to resolve project root for imports block: %s", e)
        return None, None

    cells = ctx.get("notebook_cells")
    if cells is None:
        notebook_path = ctx.get("notebook_path", "")
        if not notebook_path:
            return None, None
        try:
            notebook = notebook_mgr.get_notebook(project_id, notebook_path)
            cells = notebook.get("cells", [])
        except Exception as e:
            logger.warning("Failed to load notebook for imports block: %s", e)
            return None, None

    if not cells:
        return None, None

    modules = _extract_imported_modules(cells)
    if not modules:
        return None, None

    resolved: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for mod in sorted(modules):
        path = _resolve_local_module(project_root, mod)
        if path and path not in seen_paths:
            seen_paths.add(path)
            resolved.append((mod, path))

    if not resolved:
        return None, None

    import os
    pieces: list[tuple[str, str, str]] = []
    total_chars = 0
    for mod, abs_path in resolved:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read imported module %s: %s", abs_path, e)
            continue
        if not content.strip():
            continue
        if len(content) > IMPORTS_PER_FILE_CHAR_CAP:
            overflow = len(content) - IMPORTS_PER_FILE_CHAR_CAP
            content = content[:IMPORTS_PER_FILE_CHAR_CAP] + f"\n# ...({overflow} more chars truncated)"
        total_chars += len(content)
        rel_path = os.path.relpath(abs_path, project_root)
        pieces.append((mod, rel_path, content))

    if not pieces:
        return None, None

    if total_chars > IMPORTS_TOTAL_CHAR_BUDGET:
        lines = [
            f"LOCAL PROJECT IMPORTS (referenced by the open notebook, NOT inlined - "
            f"total would be {total_chars:,} chars, over the {IMPORTS_TOTAL_CHAR_BUDGET:,} budget):",
        ]
        for _, rel_path, content in pieces:
            lines.append(f"  - {rel_path} ({len(content):,} chars)")
        lines.append(
            "Call get_file_contents with the relative path to read any of these on demand."
        )
        return "\n".join(lines), None

    lines = [
        "LOCAL PROJECT IMPORTS (user's own modules referenced by the open notebook; "
        "read-only reference - do NOT call get_file_contents for these):",
    ]
    for mod, rel_path, content in pieces:
        lines.append("")
        lines.append(f"[{rel_path}]  (imported as `{mod}`)")
        lines.append("```python")
        lines.append(content.rstrip())
        lines.append("```")

    rel_paths_preview = ", ".join(rp for _, rp, _ in pieces[:4])
    if len(pieces) > 4:
        rel_paths_preview += f", +{len(pieces) - 4} more"
    manifest = (
        f"{len(pieces)} local Python module{'s' if len(pieces) != 1 else ''} "
        f"imported by the notebook inlined verbatim below ({rel_paths_preview})"
    )
    return "\n".join(lines), manifest


def _select_cells(cells: list, selected_indices: set[int]) -> list[tuple[int, dict]]:
    """Select which cells to include based on relevance heuristics.

    Args:
        cells: Full list of notebook cells.
        selected_indices: Set of cell indices currently selected by the user
                          (single click, Shift+click range, or Ctrl+click multi-select).
    """
    if not cells:
        return []

    included = set()

    # Always include all explicitly selected cells
    for idx in selected_indices:
        if 0 <= idx < len(cells):
            included.add(idx)

    # For each selected cell, include 2 preceding cells for context
    for idx in sorted(selected_indices):
        for i in range(max(0, idx - 2), idx):
            if len(included) < MAX_CELLS:
                included.add(i)

    # Include cells with errors
    for i, cell in enumerate(cells):
        if len(included) >= MAX_CELLS:
            break
        outputs = cell.get("outputs", [])
        for out in outputs:
            if out.get("output_type") == "error":
                included.add(i)
                break

    # If we still have room, expand around selected cells
    if selected_indices:
        anchor = min(selected_indices)
        for i in range(max(0, anchor - 5), min(len(cells), max(selected_indices) + 3)):
            if len(included) >= MAX_CELLS:
                break
            included.add(i)

    # No selection at all - include first cells as a general overview
    if not included:
        for i in range(min(len(cells), MAX_CELLS)):
            included.add(i)

    return [(i, cells[i]) for i in sorted(included) if i < len(cells)]


def _format_outputs(outputs: list) -> Optional[str]:
    """Format cell outputs into a readable string."""
    parts = []
    for out in outputs:
        out_type = out.get("output_type", "")
        if out_type == "stream":
            text = out.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            parts.append(text.rstrip())
        elif out_type == "execute_result" or out_type == "display_data":
            data = out.get("data", {})
            text = data.get("text/plain", "")
            if isinstance(text, list):
                text = "".join(text)
            parts.append(text.rstrip())
        elif out_type == "error":
            traceback = out.get("traceback", [])
            # Strip ANSI codes from traceback
            tb_text = "\n".join(traceback)
            tb_text = re.sub(r'\x1b\[[0-9;]*m', '', tb_text)
            parts.append(tb_text.rstrip())

    if not parts:
        return None

    text = "\n".join(parts)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n...(truncated, {len(text) - MAX_OUTPUT_CHARS} more chars)"
    return text


def _run_block(ctx: dict, mlflow_mgr) -> Optional[str]:
    """Build MLflow run context from an active run ID."""
    if not mlflow_mgr:
        return None

    try:
        run = mlflow_mgr.get_run(ctx["active_run_id"])
    except Exception as e:
        logger.warning("Failed to load MLflow run for LLM context: %s", e)
        return None

    lines = ["ACTIVE MLFLOW RUN:"]
    lines.append(f"Run ID: {run['run_id']}  |  Status: {run['status']}")

    if run.get("run_name"):
        lines.append(f"Run name: {run['run_name']}")

    # Params (compact)
    params = run.get("params", {})
    if params:
        param_str = ", ".join(f"{k}={v}" for k, v in list(params.items())[:15])
        lines.append(f"Params: {param_str}")

    # Metrics (compact)
    metrics = run.get("metrics", {})
    if metrics:
        metric_str = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:15])
        lines.append(f"Latest metrics: {metric_str}")

    # Tags (non-system, compact)
    tags = run.get("tags", {})
    if tags:
        tag_str = ", ".join(f"{k}={v}" for k, v in list(tags.items())[:10])
        lines.append(f"Tags: {tag_str}")

    return "\n".join(lines)


def _experiment_summary_block(ctx: dict, mlflow_mgr) -> Optional[str]:
    """Emit a pointer to the MLflow experiment (name + run count + tool hint),
    not a data dump. Auto-injected context holds actionable state; data is
    fetched on demand via get_experiment_runs / get_run_details."""
    if not mlflow_mgr:
        return None

    project_id = ctx["project_id"]

    try:
        experiments = mlflow_mgr.list_experiments()
        experiment = next((e for e in experiments if e["name"] == project_id), None)
        if not experiment:
            return None
        # We only need the count (constant-size info). Cap the lookup so an
        # experiment with thousands of runs doesn't pay a query cost here.
        runs = mlflow_mgr.list_runs(experiment["experiment_id"], max_results=100)
        n_runs = len(runs)
        if n_runs == 0:
            return None
    except Exception as e:
        logger.warning("Failed to load MLflow experiment summary for LLM context: %s", e)
        return None

    lines = [
        f"MLFLOW EXPERIMENT: {project_id} ({n_runs}{'+' if n_runs == 100 else ''} runs)",
        "(In noted, runs are created via auto-instrumentation and Run Manager - no explicit MLflow code is needed in notebook cells.)",
        "Use get_experiment_runs(experiment_name=\"" + project_id + "\") to list recent runs, or "
        "get_run_details(run_id=...) for a specific one. Do NOT assume run params / metrics without fetching them.",
    ]
    return "\n".join(lines)


def _config_block(ctx: dict, hydra_mgr) -> Optional[str]:
    """Build Hydra config context from the active project."""
    if not hydra_mgr:
        return None

    try:
        result = hydra_mgr.compose(ctx["project_id"])
        yaml_str = result.get("yaml", "")
    except Exception as e:
        logger.warning("Failed to load Hydra config for LLM context: %s", e)
        return None

    if not yaml_str:
        return None

    # Truncate if very long
    if len(yaml_str) > 2000:
        yaml_str = yaml_str[:2000] + "\n...(config truncated)"

    return f"HYDRA CONFIG (resolved):\n```yaml\n{yaml_str}\n```"

"""Dynamic Context Router - selects relevant tool schemas per user message.

Instead of sending all 24 tool schemas on every LLM turn (~3000 tokens),
the router classifies the user's message into relevant domains and injects
only the matching tools (typically 5-8, ~500-800 tokens).

If the LLM calls a tool that wasn't in scope, the router expands the
tool set and retries the turn.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# -- Domain definitions and tool-to-domain mapping --------------------------

DOMAINS = {
    "mlflow": {
        "tools": {"get_experiment_runs", "get_run_details", "list_run_artifacts", "get_serving_status", "get_serving_schema", "invoke_model", "deploy_model", "list_registered_models", "list_model_versions", "register_model", "set_model_alias", "compare_runs"},
        "keywords": [
            r"\bmlflow\b", r"\bexperiment[s]?\b", r"\brun[s]?\b", r"\bmetric[s]?\b",
            r"\bparameter[s]?\b", r"\bparam[s]?\b", r"\bhyperparameter[s]?\b",
            r"\bloss\b", r"\baccuracy\b", r"\bmae\b", r"\brmse\b", r"\br[2²]\b",
            r"\bepoch[s]?\b", r"\btraining curve[s]?\b", r"\bmodel registr",
            r"\bartifact[s]?\b", r"\bcompare\b.*\brun",
        ],
    },
    "airflow": {
        "tools": {"list_dags", "get_dag_status", "get_task_log"},
        "keywords": [
            r"\bairflow\b", r"\bdag[s]?\b", r"\bpipeline[s]?\b", r"\btask[s]?\b",
            r"\bschedul", r"\borchestrat", r"\btrigger\b",r"\btask.?log\b",
            r"\bdag.?run\b",
        ],
    },
    "dvc": {
        "tools": {"get_dvc_data_overview", "get_dvc_file_history"},
        "keywords": [
            r"\bdvc\b", r"\bdata version", r"\btracked file[s]?\b", r"\bdata lineage\b",
            r"\bversion history\b", r"\bdata.?set\b.*\bversion", r"\bpush\b.*\bdata\b",
            r"\bpull\b.*\bdata\b",
        ],
    },
    "files": {
        "tools": {"get_file_contents", "list_files", "search_files", "create_file", "update_file"},
        "keywords": [
            r"\bfile[s]?\b", r"\bread\b.*\b(file|code|script|module)\b",
            r"\bcreate\b.*\bfile\b", r"\bwrite\b.*\bfile\b", r"\bsearch\b.*\b(file|code|content)\b",
            r"\bgrep\b", r"\bfind\b.*\b(in|across)\b", r"\blist\b.*\bfile\b",
            r"\bsrc/\b", r"\b\.py\b", r"\bimport[s]?\b.*\bfrom\b",
            r"\bmodify\b.*\bfile\b", r"\bedit\b.*\bfile\b",
        ],
    },
    "hydra": {
        "tools": {"get_hydra_config"},
        "keywords": [
            r"\bhydra\b", r"\bconfig(uration)?\b", r"\boverride[s]?\b",
            r"\byaml\b", r"\bcompose\b.*\bconfig",
        ],
    },
    "notebook": {
        "tools": {"get_notebook_cells", "scroll_to_cell", "update_cell", "insert_cell", "batch_update_cells", "find_replace_in_cells"},
        "keywords": [
            r"\bcell[s]?\b", r"\bnotebook\b", r"\bshow\b.*\bcell\b",
            r"\bscroll\b", r"\bnavigate\b", r"\bgo\s+to\b",
            r"\bfix\b", r"\brefactor\b", r"\bimprove\b", r"\bchange\b",
            r"\badd\b.*\b(cell|code)\b", r"\binsert\b", r"\bupdate\b.*\bcell\b",
            r"\bmodify\b.*\bcell\b", r"\brewrite\b",
        ],
    },
    "linting": {
        "tools": {"get_lint_diagnostics", "fix_lint_issues"},
        "keywords": [
            r"\blint", r"\bdiagnostic[s]?\b", r"\berror[s]?\b.*\b(code|fix)\b",
            r"\bwarning[s]?\b", r"\bruff\b", r"\bbiome\b", r"\bformat",
            r"\bcode\s+quality\b", r"\bauto.?fix\b",
        ],
    },
    "knowledge": {
        "tools": {"query_knowledge_graph"},
        "keywords": [
            r"\bknowledge\b.*\bgraph\b", r"\bentit(y|ies)\b", r"\brelationship[s]?\b",
            r"\bgraph\b.*\bquery\b",
        ],
    },
    "skills": {
        "tools": {"get_skill", "run_agent"},
        "keywords": [
            r"\bskill[s]?\b", r"\bagent\b", r"\bdelegate\b", r"\bsubagent\b",
            r"\bexplore\b.*\bnotebook\b", r"\bsummarize\b.*\bnotebook\b",
        ],
    },
    "web": {
        "tools": {"fetch_url"},
        "keywords": [
            r"\burl\b", r"\bhttp[s]?://", r"\bfetch\b.*\b(url|page|site|link)\b",
            r"\bread\b.*\b(url|page|site|link|article|doc)\b",
            r"\bweb\b.*\b(page|site|content)\b", r"\blink\b",
            r"\bdocumentation\b", r"\bapi\b.*\b(doc|reference)\b",
        ],
    },
}

# Always-included tools (cheap, universally useful)
_ALWAYS_INCLUDE = {"get_file_contents", "get_notebook_cells", "scroll_to_cell"}

# Pre-compile keyword patterns per domain
_COMPILED_KEYWORDS: dict[str, list[re.Pattern]] = {}
for domain, config in DOMAINS.items():
    _COMPILED_KEYWORDS[domain] = [re.compile(kw, re.IGNORECASE) for kw in config["keywords"]]


# -- Domain classifier ------------------------------------------------------

def classify_domains(message: str, context: Optional[dict] = None) -> set[str]:
    """Classify a user message into relevant tool domains.

    Args:
        message: The user's message text.
        context: Optional context descriptor (project_id, notebook_path, etc.)
                 Used to boost domain relevance based on active workspace state.

    Returns:
        Set of domain names that matched.
    """
    matched = set()

    for domain, patterns in _COMPILED_KEYWORDS.items():
        for pattern in patterns:
            if pattern.search(message):
                matched.add(domain)
                break

    # Context-based boosting: if notebook is open, include notebook domain
    if context:
        if context.get("notebook_path"):
            matched.add("notebook")
        if context.get("file_path"):
            matched.add("files")

    # If nothing matched, include broad defaults
    if not matched:
        matched = {"notebook", "files", "mlflow"}

    return matched


def select_tools(message: str, context: Optional[dict] = None,
                 all_tools: Optional[list] = None) -> list:
    """Select relevant tool schemas for a user message.

    Args:
        message: The user's message text.
        context: Optional context descriptor.
        all_tools: Full list of tool schema dicts (Anthropic or OpenAI format).
                   Each must have a "name" key (Anthropic) or
                   "function"."name" key (OpenAI).

    Returns:
        Filtered list of tool schemas relevant to the message.
    """
    if not all_tools:
        return []

    domains = classify_domains(message, context)
    logger.info("Dynamic Context Router: domains=%s for message=%r",
                sorted(domains), message[:80])

    # Collect tool names from matched domains + always-included
    selected_names = set(_ALWAYS_INCLUDE)
    for domain in domains:
        domain_config = DOMAINS.get(domain, {})
        selected_names.update(domain_config.get("tools", set()))

    # Filter the tool schemas
    result = []
    for tool in all_tools:
        # Handle both Anthropic format {"name": "..."} and OpenAI format {"function": {"name": "..."}}
        name = tool.get("name") or tool.get("function", {}).get("name", "")
        if name in selected_names:
            result.append(tool)

    logger.info("Dynamic Context Router: %d/%d tools selected (%s)",
                len(result), len(all_tools), sorted(selected_names))

    return result


def expand_tools_for_retry(current_tools: list, missing_tool_name: str,
                           all_tools: list) -> list:
    """Expand the tool set when the LLM called an out-of-scope tool.

    Finds the domain containing the missing tool, adds all tools from
    that domain, and returns the expanded list.

    Args:
        current_tools: Currently selected tool schemas.
        missing_tool_name: Name of the tool the LLM tried to call.
        all_tools: Full list of all tool schemas.

    Returns:
        Expanded tool list including the missing tool's domain.
    """
    # Find which domain the missing tool belongs to
    missing_domain = None
    for domain, config in DOMAINS.items():
        if missing_tool_name in config["tools"]:
            missing_domain = domain
            break

    if not missing_domain:
        logger.warning("Dynamic Context Router: unknown tool '%s' requested, adding all tools",
                       missing_tool_name)
        return all_tools

    # Collect names to add
    names_to_add = DOMAINS[missing_domain]["tools"]
    current_names = set()
    for tool in current_tools:
        name = tool.get("name") or tool.get("function", {}).get("name", "")
        current_names.add(name)

    # Add missing tools from the domain
    expanded = list(current_tools)
    for tool in all_tools:
        name = tool.get("name") or tool.get("function", {}).get("name", "")
        if name in names_to_add and name not in current_names:
            expanded.append(tool)

    logger.info("Dynamic Context Router: expanded with domain '%s' (%d -> %d tools)",
                missing_domain, len(current_tools), len(expanded))

    return expanded

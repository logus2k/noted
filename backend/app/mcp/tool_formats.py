"""Convert MCP tool schemas to LLM-native tool calling formats.

MCP tool schemas (defined in tools.py) are the single source of truth.
This module converts them to the formats expected by each LLM backend:

  - Anthropic: tools array for the Messages API
  - OpenAI: tools array for chat completions (used by llama-cpp-python / agent_server)
"""

from app.mcp.tools import get_all_tools, is_write_tier, tools_for_domains
from app.mcp.user_tools_client import get_user_tools_client


def to_anthropic_tools(
    include_write: bool = True,
    active_domains: list[str] | None = None,
) -> list[dict]:
    """Convert MCP tools to Anthropic Messages API format.

    Anthropic format:
    {
        "name": "tool_name",
        "description": "...",
        "input_schema": { JSON Schema }
    }

    Args:
        include_write: If False, exclude write-tier tools from the list.
        active_domains: If provided, only include tools whose owning Domain
            is in this list. None = all tools (legacy behavior).
    """
    source = tools_for_domains(active_domains) if active_domains else get_all_tools()
    tools = []
    for t in source:
        if not include_write and is_write_tier(t.name):
            continue
        tools.append({
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        })
    # User tools (Phase A.5 federation). User tools are read-tier in V1
    # and not domain-scoped — they're always available regardless of
    # active_domains. _meta is stripped here; the LLM never sees it.
    for t in get_user_tools_client().get_user_tools():
        tools.append({
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        })
    return tools


def to_openai_tools(
    include_write: bool = True,
    active_domains: list[str] | None = None,
) -> list[dict]:
    """Convert MCP tools to OpenAI chat completions format.

    OpenAI format (also used by llama-cpp-python):
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "...",
            "parameters": { JSON Schema }
        }
    }

    Args:
        include_write: If False, exclude write-tier tools from the list.
        active_domains: If provided, only include tools whose owning Domain
            is in this list. None = all tools (legacy behavior).
    """
    source = tools_for_domains(active_domains) if active_domains else get_all_tools()
    tools = []
    for t in source:
        if not include_write and is_write_tier(t.name):
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        })
    for t in get_user_tools_client().get_user_tools():
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        })
    return tools

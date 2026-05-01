"""noted MCP Server - low-level Server API implementation.

Uses the mcp SDK's low-level Server to maintain full control over tool
schemas (defined in tools.py) and route tools/call to the existing
execute_tool() dispatcher in llm_tools.py.

This module creates the server instance and registers the protocol handlers.
Mounting into FastAPI is done in mount.py.
"""

import logging
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.shared.exceptions import McpError

from app.mcp.tools import get_all_tools, is_write_tier, WRITE_TOOL_NAMES
from app.mcp.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Shared rate limiter instance (per-process, per-session buckets)
_rate_limiter = RateLimiter()


def _mcp_error(code: int, message: str, skill: str, detail: str, recoverable: bool, **extra):
    """Create a structured MCP error with noted's error taxonomy."""
    data = {"skill": skill, "detail": detail, "recoverable": recoverable, **extra}
    return McpError(types.ErrorData(code=code, message=message, data=data))


def create_mcp_server(managers: dict, ctx_provider=None) -> Server:
    """Create and configure the noted MCP server.

    Args:
        managers: Dict of manager instances (same dict passed to execute_tool)
        ctx_provider: Optional callable that returns the current context dict
                      for tool execution (project_id, file_path, etc.)

    Returns:
        Configured mcp.server.lowlevel.Server instance
    """
    server = Server("noted")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return get_all_tools()

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        arguments = arguments or {}

        # Validate tool exists
        tool_names = {t.name for t in get_all_tools()}
        if name not in tool_names:
            raise _mcp_error(
                code=-32006,
                message=f"Validation error: unknown tool '{name}'",
                skill=name,
                detail=f"No tool named '{name}' is registered. Use tools/list to see available tools.",
                recoverable=False,
            )

        # Write-tier check
        write = is_write_tier(name)
        if write:
            raise _mcp_error(
                code=-32001,
                message=f"Authorization error: '{name}' requires user approval",
                skill=name,
                detail="Write-tier tools require explicit user approval. Enable write access for this client in noted settings.",
                recoverable=True,
            )

        # Rate limiting (stateless mode - use "default" as session id for now)
        # TODO: extract real session id when session management is added
        session_id = "default"
        allowed, retry_after = _rate_limiter.check(session_id, name, write)
        if not allowed:
            raise _mcp_error(
                code=-32005,
                message="Rate limited",
                skill=name,
                detail=f"Rate limit exceeded for {'write' if write else 'read'}-tier tools",
                recoverable=True,
                retry_after=round(retry_after),
            )

        # Execute read-tier tool via existing dispatcher
        from app.managers.llm_tools import execute_tool
        ctx = ctx_provider() if ctx_provider else None
        tool_call = {"name": name, "args": arguments}

        try:
            result = await execute_tool(tool_call, managers, ctx)
        except Exception as e:
            logger.exception("MCP tool execution failed: %s", name)
            raise _mcp_error(
                code=-32002,
                message=f"Execution error: {name}",
                skill=name,
                detail=f"{type(e).__name__}: {e}",
                recoverable=True,
            )

        # Check for dispatcher-level errors (returned as strings starting with "Error:")
        result_str = str(result)
        if result_str.startswith("Error:") and "not available" in result_str:
            raise _mcp_error(
                code=-32004,
                message=f"Resource unavailable: {name}",
                skill=name,
                detail=result_str,
                recoverable=False,
            )

        return [types.TextContent(type="text", text=result_str)]

    logger.info(
        "MCP server created: %d tools (%d read, %d write)",
        len(get_all_tools()),
        len(get_all_tools()) - len(WRITE_TOOL_NAMES),
        len(WRITE_TOOL_NAMES),
    )

    return server

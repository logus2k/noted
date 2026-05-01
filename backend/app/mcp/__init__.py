"""noted MCP Server - Model Context Protocol integration.

This package exposes noted's existing tool dispatcher through the MCP protocol,
enabling external clients (Claude Desktop, Cursor, Claude Code) to discover
and invoke noted's tools.

Architecture: one-directional dependency. This package imports from
app.managers.llm_tools but nothing outside this package imports from app.mcp.
If the MCP server fails to load, noted continues operating normally.
"""

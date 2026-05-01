"""Mount the MCP server into an existing FastAPI application.

Provides mount_mcp() which adds the Streamable HTTP transport at /mcp/.
Call this from main.py within a try/except to ensure MCP failures
never prevent noted from starting.

The session manager must be started in the FastAPI lifespan via run().
"""

import logging

from fastapi import FastAPI
from starlette.routing import Mount

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

logger = logging.getLogger(__name__)


def mount_mcp(app: FastAPI, server: Server) -> StreamableHTTPSessionManager:
    """Mount the MCP Streamable HTTP transport into the FastAPI app.

    The MCP endpoint will be available at /mcp/ (single endpoint,
    Streamable HTTP transport).

    IMPORTANT: the caller must run the returned session_manager in the
    FastAPI lifespan:
        async with session_manager.run():
            yield

    Args:
        app: The existing FastAPI application
        server: The configured MCP server instance

    Returns:
        The StreamableHTTPSessionManager (must be started in lifespan)
    """
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
    )

    async def mcp_asgi_app(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    app.router.routes.append(
        Mount("/mcp", app=mcp_asgi_app)
    )

    logger.info("MCP server mounted at /mcp (Streamable HTTP)")
    return session_manager

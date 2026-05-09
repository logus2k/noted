"""noted-tools FastAPI app.

MCP server hosting self-authored tools. Phase A.1 ships the container
skeleton with an empty registry; Phase A.2 wires the file watcher,
Phase A.4 wires the subprocess executor, Phase A.5 federates this
server into noted's MCP client list.

Endpoints:
  GET  /health   - liveness probe + tool count
  /mcp/          - MCP Streamable HTTP transport (tools/list, tools/call)
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import mcp.types as types
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import McpError
from starlette.routing import Mount

from . import audit, executor
from .registry import get_registry
from .watcher import initial_scan, watch_user_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _create_mcp_server() -> Server:
    server = Server("noted-tools")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        registry = get_registry()
        out: list[types.Tool] = []
        for entry in registry.list_tools():
            kwargs: dict = {
                "name": entry.name,
                "description": entry.description,
                "inputSchema": entry.input_schema,
            }
            if entry.meta:
                kwargs["_meta"] = entry.meta
            out.append(types.Tool(**kwargs))
        return out

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> list[types.TextContent]:
        registry = get_registry()
        entry = registry.get(name)
        if entry is None:
            raise McpError(types.ErrorData(
                code=-32601,
                message=f"Tool not found: {name}",
                data={"detail": f"No user tool named '{name}' is registered."},
            ))

        started_at = audit.now_iso()
        try:
            result = await executor.execute(entry, arguments or {})
        except Exception as e:
            logger.exception("infra error executing tool %s", name)
            raise McpError(types.ErrorData(
                code=-32603,
                message=f"Tool infrastructure error: {name}: {type(e).__name__}: {e}",
            ))
        finished_at = audit.now_iso()
        audit.record(entry, arguments or {}, result, started_at, finished_at)

        if result.timed_out:
            tail = result.stderr.strip()[-500:] or "(no stderr)"
            raise McpError(types.ErrorData(
                code=-32008,
                message=f"Tool {name} timed out after {result.elapsed_s:.1f}s. stderr: {tail}",
            ))
        if not result.ok:
            tail = result.stderr.strip()[-500:] or "(no stderr)"
            oom = " [OOM killed]" if result.oom_killed else ""
            raise McpError(types.ErrorData(
                code=-32002,
                message=f"Tool {name} failed (exit={result.exit_code}){oom}. stderr: {tail}",
            ))
        return [types.TextContent(type="text", text=result.stdout)]

    return server


_session_manager: StreamableHTTPSessionManager | None = None

USER_TOOLS_DIR = Path(os.environ.get("USER_TOOLS_DIR", "/app/data/user_tools"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session_manager
    logger.info("noted-tools starting on port 7702")
    loaded = initial_scan(USER_TOOLS_DIR)
    logger.info("initial scan: %d tool(s) loaded from %s", loaded, USER_TOOLS_DIR)
    stop_event = asyncio.Event()
    watcher_task = asyncio.create_task(watch_user_tools(USER_TOOLS_DIR, stop_event))
    server = _create_mcp_server()
    _session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
    )
    async with _session_manager.run():
        try:
            yield
        finally:
            stop_event.set()
            try:
                await asyncio.wait_for(watcher_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                watcher_task.cancel()
    logger.info("noted-tools shutting down")


app = FastAPI(title="noted-tools", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    registry = get_registry()
    return {
        "status": "ok",
        "service": "noted-tools",
        "tool_count": len(registry.list_tools()),
        "phase": "A.1",
    }


@app.post("/admin/run-smoke-tests/{tool_name}")
async def run_smoke_tests(tool_name: str) -> dict:
    """F3.5: build the tool's venv (idempotent), ensure pytest is installed,
    then `pytest smoke.py` inside the tool directory. Returns the verdict.

    Called by noted backend's `run_smoke_tests` workflow step after publish_tool
    + api_tester have authored smoke.py. Failure non-zero exit → caller treats
    as step failure → workflow suspends with the validator complaint.
    """
    import asyncio as _asyncio
    import subprocess
    from pathlib import Path as _Path
    from . import venv_manager
    from fastapi import HTTPException

    registry = get_registry()
    # Tolerate a brief race: publish_tool may have just written the files
    # but the watcher's ~50-200ms debounce hasn't fired yet. Retry up to ~1s.
    entry = registry.get(tool_name)
    for _ in range(10):
        if entry is not None:
            break
        await _asyncio.sleep(0.1)
        entry = registry.get(tool_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name!r}")
    if entry.language != "python":
        raise HTTPException(status_code=400, detail=f"smoke tests for language {entry.language!r} not supported yet")

    tool_dir = _Path(entry.tool_dir)
    smoke_py = tool_dir / "smoke.py"
    if not smoke_py.is_file():
        raise HTTPException(status_code=404, detail="smoke.py not found in tool dir")

    # Build (or reuse) the venv. ensure_python_venv is sync; run in thread.
    try:
        py = await _asyncio.to_thread(venv_manager.ensure_python_venv, tool_dir)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"venv build failed: {e}")

    # Ensure pytest is importable in the venv. The venv is built by `uv venv`
    # which does NOT seed pip; `python -m pip install` would fail. The api_tester
    # preset is supposed to add `pytest==X` to additional_requirements (merged
    # into requirements.txt by publish_tool), so it's typically installed at
    # venv-build time. Fall back to `uv pip install` if it's missing.
    try:
        check = await _asyncio.to_thread(
            subprocess.run,
            [str(py), "-c", "import pytest"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pytest probe timed out")
    if check.returncode != 0:
        try:
            install = await _asyncio.to_thread(
                subprocess.run,
                ["uv", "pip", "install", "--python", str(py), "--quiet", "pytest"],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="pytest install timed out")
        if install.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"pytest install failed: {install.stderr.strip()[-500:] or install.stdout.strip()[-500:]}",
            )

    # Run pytest. -x = stop on first failure. Increase timeout for slow tests.
    try:
        result = await _asyncio.to_thread(
            subprocess.run,
            [str(py), "-m", "pytest", "-x", "smoke.py"],
            cwd=str(tool_dir),
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {
            "tool_name": tool_name,
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "pytest timed out after 120s",
            "timed_out": True,
        }

    return {
        "tool_name": tool_name,
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "timed_out": False,
    }


async def _mcp_asgi_app(scope, receive, send):
    if _session_manager is None:
        raise RuntimeError("MCP session manager not initialized")
    await _session_manager.handle_request(scope, receive, send)


app.router.routes.append(Mount("/mcp", app=_mcp_asgi_app))

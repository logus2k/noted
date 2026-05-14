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

    # Secret-gating: an api_key / oauth2 tool declares its required
    # secrets in `_meta.allowed_secrets`. smoke.py runs the tool via a
    # DIRECT `subprocess.run([python, tool.py])` — that subprocess
    # inherits this process's env, NOT the executor's secret-injected
    # env. So before running pytest:
    #   - if a declared secret is unset → SKIP with a conditional pass.
    #     A missing credential is not a tool-author defect; the
    #     framework must not rewind api_tester / tool_author for it.
    #   - if all declared secrets are present → resolve them and pass
    #     them into the pytest subprocess env so smoke.py's nested
    #     `subprocess.run` inherits SECRET_<NAME> and the tool authenticates.
    from . import secret_resolver
    allowed_secrets = list(entry.meta.get("allowed_secrets") or [])
    secret_env: dict[str, str] = {}
    if allowed_secrets:
        missing = secret_resolver.missing_secrets(allowed_secrets)
        if missing:
            logger.info(
                "smoke tests for %s skipped: declared secrets %s not set (%s missing)",
                tool_name, allowed_secrets, missing,
            )
            return {
                "tool_name": tool_name,
                "ok": True,
                "skipped": True,
                "reason": "secrets_not_set",
                "pending_secrets": missing,
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            }
        secret_env = secret_resolver.resolve(allowed_secrets)

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
    # `secret_env` carries SECRET_<NAME> for any declared allowed_secrets
    # (empty for anonymous tools) so smoke.py's nested tool subprocess
    # can authenticate.
    pytest_env = {**os.environ, **secret_env}
    try:
        result = await _asyncio.to_thread(
            subprocess.run,
            [str(py), "-m", "pytest", "-x", "smoke.py"],
            cwd=str(tool_dir),
            capture_output=True, text=True, timeout=120,
            env=pytest_env,
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


@app.post("/admin/run-draft/{tool_name}")
async def run_draft(tool_name: str, args: dict | None = None) -> dict:
    """Build (or reuse) the draft tool's venv and run `python tool.py`
    once with the request body as stdin JSON. Returns stdout/stderr/exit.

    Unlike /admin/run-smoke-tests this does NOT go through the registry
    or pytest - it is the raw "run the code and see what happens" step
    of the agentic builder loop. The tool dir need not be a registered
    tool; it just has to exist on disk under USER_TOOLS_DIR with a
    tool.py. Secrets declared in tool.json `_meta.allowed_secrets` are
    injected when present in the vault; when absent they are simply not
    injected (the builder sees the failure in stderr and reacts).
    """
    import asyncio as _asyncio
    import json as _json
    import subprocess
    from fastapi import HTTPException
    from . import secret_resolver, venv_manager

    # Resolve the draft dir directly from the path convention - no
    # registry dependency (the tool may not be registered yet).
    if "/" in tool_name or tool_name.startswith("."):
        raise HTTPException(status_code=400, detail=f"invalid tool_name: {tool_name!r}")
    tool_dir = USER_TOOLS_DIR / tool_name
    tool_py = tool_dir / "tool.py"
    if not tool_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"draft dir not found: {tool_dir}")
    if not tool_py.is_file():
        raise HTTPException(status_code=404, detail=f"tool.py not found in {tool_dir}")

    # Build / reuse the venv. Sync - run in a thread.
    try:
        py = await _asyncio.to_thread(venv_manager.ensure_python_venv, tool_dir)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"venv build failed: {e}")

    # Best-effort secret injection. allowed_secrets comes from tool.json
    # if present; a missing secret is NOT fatal here - the draft run is
    # meant to surface that to the builder.
    secret_env: dict[str, str] = {}
    try:
        tj = _json.loads((tool_dir / "tool.json").read_text())
        allowed = list((tj.get("_meta") or {}).get("allowed_secrets") or [])
        present = [s for s in allowed if s not in secret_resolver.missing_secrets(allowed)]
        if present:
            secret_env = secret_resolver.resolve(present)
    except (OSError, _json.JSONDecodeError):
        pass  # no tool.json yet, or malformed - run without secrets

    run_env = {**os.environ, **secret_env}
    payload = _json.dumps(args or {})
    try:
        result = await _asyncio.to_thread(
            subprocess.run,
            [str(py), "tool.py"],
            cwd=str(tool_dir),
            input=payload,
            capture_output=True, text=True, timeout=60,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "tool_name": tool_name,
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "draft run timed out after 60s",
            "timed_out": True,
        }

    return {
        "tool_name": tool_name,
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
        "timed_out": False,
    }


async def _mcp_asgi_app(scope, receive, send):
    if _session_manager is None:
        raise RuntimeError("MCP session manager not initialized")
    await _session_manager.handle_request(scope, receive, send)


app.router.routes.append(Mount("/mcp", app=_mcp_asgi_app))

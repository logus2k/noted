import asyncio
import logging
import uuid
import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import os
from app.config import FRONTEND_DIR, PROJECTS_DIR, MOUNTS_DIR
from app.routers import notebooks, venvs, documents, git, files, dvc, minio, projects, mlflow, export, hydra, airflow, snapshots, registry, serving, reports, graph_proxy, llm, lsp, dap, evidently, rag, kb, citations, models as models_router, buffers, health
from app.managers.kernel_manager import KernelManagerService
from app.managers.execution_bridge import ExecutionBridge
from app.managers.auto_instrumentation import AutoInstrumentation
from app.managers.collaboration import CollaborationManager
from app.managers.notebook_manager import NotebookManager
from app.managers.venv_manager import VenvManager
from app.managers.terminal_manager import TerminalManager
from app.managers.hydra_manager import HydraManager
from app.managers.lsp_manager import LSPProxyManager
from app.managers.dap_manager import DAPProxyManager
from app.managers.notebook_lsp_bridge import NotebookLSPManager
from app.managers.llm_debug import init_debug_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    max_http_buffer_size=100 * 1024 * 1024,  # 100 MB
)

# Managers
kernel_mgr = KernelManagerService()
collab_mgr = CollaborationManager(sio)
auto_inst = AutoInstrumentation()
execution_bridge = ExecutionBridge(kernel_mgr, sio, auto_instrumentation=auto_inst)
notebook_mgr = NotebookManager()
venv_mgr = VenvManager()
terminal_mgr = TerminalManager(sio)
hydra_mgr = HydraManager()
lsp_mgr = LSPProxyManager(env_manager=venv_mgr)
dap_mgr = DAPProxyManager()
nb_lsp_mgr = NotebookLSPManager()
llm_debug = init_debug_log(sio)

# Track client context: sid -> { room_key -> {project_id, notebook_path, user_name, ...} }
client_rooms: dict[str, dict[str, dict]] = {}


def _make_room_key(project_id: str, notebook_path: str) -> str:
    return f"notebook:{project_id}:{notebook_path}"


def _get_ctx(sid: str, data: dict) -> tuple[dict, str]:
    """Extract notebook context from event data or fall back to single-room lookup.

    Returns (ctx_dict, room_key). ctx_dict may be empty if not found.
    """
    rooms = client_rooms.get(sid, {})
    project_id = data.get("project_id")
    notebook_path = data.get("notebook_path")
    notebook_key = data.get("notebook_key")
    # Derive room key from explicit fields
    if notebook_key and notebook_key in rooms:
        return rooms[notebook_key], notebook_key
    if project_id and notebook_path:
        key = _make_room_key(project_id, notebook_path)
        if key in rooms:
            return rooms[key], key
    # Fallback: if client has exactly one room, use it (backward compat)
    if len(rooms) == 1:
        key = next(iter(rooms))
        return rooms[key], key
    return {}, ""

# Pending disconnect cleanup tasks: sid -> asyncio.Task
_pending_disconnects: dict[str, asyncio.Task] = {}

DISCONNECT_GRACE_SECONDS = 15


@asynccontextmanager
async def lifespan(app: FastAPI):
    notebook_mgr.ensure_welcome_notebook()
    await kernel_mgr.start()
    # Pre-warm MLflow client to avoid slow first request
    mlflow.mlflow_mgr.warm_up()
    # Service-health monitor — probes hard dependencies (noted-graph,
    # noted-rag, llama-vision proxy, bge-m3, ArcadeDB, agent_server) on
    # a 30s cadence and pushes state changes to clients via Socket.IO
    # `services:health`. Surfaces upstream failures (bge-m3 zombie,
    # services down) on the LED strip in the KB Monitor instead of
    # waiting for a multi-hour build to fail with a cryptic message.
    from app.services.health_monitor import HealthMonitor, set_monitor
    _health_monitor = HealthMonitor(sio)
    set_monitor(_health_monitor)
    await _health_monitor.start()
    # Generate compose mounts file on startup
    from app.managers import config_manager
    try:
        config_manager.generate_compose_mounts_file()
    except Exception as e:
        logger.warning(f"Failed to generate compose mounts file: {e}")
    # Start MCP session manager if available
    _mcp_cm = None
    if _mcp_session_manager is not None:
        try:
            _mcp_cm = _mcp_session_manager.run()
            await _mcp_cm.__aenter__()
            logger.info("MCP session manager started")
        except Exception as e:
            logger.warning("MCP session manager failed to start: %s", e)
            _mcp_cm = None
    logger.info("Notebook server started")
    yield
    if _mcp_cm is not None:
        try:
            await _mcp_cm.__aexit__(None, None, None)
        except Exception:
            pass
    # Stop health monitor before tearing the rest down
    try:
        if _health_monitor is not None:
            await _health_monitor.stop()
    except Exception:
        pass
    await lsp_mgr.stop_all()
    await dap_mgr.disconnect_all()
    await terminal_mgr.kill_all()
    await kernel_mgr.stop()
    # Shut down persistent browser if running
    try:
        from app.managers.web_fetch_manager import shutdown as _web_shutdown
        _web_shutdown()
    except Exception:
        pass
    logger.info("Notebook server stopped")


app = FastAPI(title="Notebook Collaboration Platform", lifespan=lifespan)
app.include_router(notebooks.router)
app.include_router(venvs.router)
app.include_router(documents.router)
app.include_router(git.router)
app.include_router(files.router)
app.include_router(buffers.router)
app.include_router(dvc.router)
app.include_router(minio.router)
app.include_router(projects.router)
app.include_router(mlflow.router)
app.include_router(export.router)
app.include_router(hydra.router)
app.include_router(airflow.router)
airflow.set_sio(sio)
app.include_router(snapshots.router)
app.include_router(registry.router)
app.include_router(serving.router)
app.include_router(reports.router)
app.include_router(graph_proxy.router)
app.include_router(llm.router)
app.include_router(lsp.router)
lsp.set_lsp_manager(lsp_mgr)
app.include_router(dap.router)
dap.set_managers(dap_mgr, kernel_mgr, execution_bridge)
app.include_router(evidently.router)
app.include_router(rag.router)
app.include_router(kb.router)
app.include_router(citations.router)
app.include_router(models_router.router)
app.include_router(health.router)
from app.routers import file_debug
app.include_router(file_debug.router)

# --- MCP Server (failure-isolated, one-directional dependency) ---
from app.config import MCP_ENABLED
_mcp_session_manager = None
try:
    if not MCP_ENABLED:
        logger.info("MCP server disabled (NOTED_MCP_ENABLED=false)")
        raise RuntimeError("disabled by config")
    from app.mcp.server import create_mcp_server
    from app.mcp.mount import mount_mcp

    _mcp_managers = {
        "kernel": kernel_mgr,
        "execution_bridge": execution_bridge,
        "notebook": notebook_mgr,
        "venv": venv_mgr,
        "hydra": hydra_mgr,
        "lsp": lsp_mgr,
        "dap": dap_mgr,
        "nb_lsp": nb_lsp_mgr,
        "mlflow": mlflow.mlflow_mgr,
        "terminal": terminal_mgr,
        "sio": sio,
    }
    _mcp_server = create_mcp_server(_mcp_managers)
    _mcp_session_manager = mount_mcp(app, _mcp_server)
except Exception as e:
    logger.warning("MCP server failed to initialize - noted continues without MCP: %s", e)


# --- Socket.IO Events ---

@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    # Push the current service-health snapshot so the LED strip paints
    # immediately on first frame. Subsequent updates arrive on state-
    # change via the HealthMonitor's emit.
    try:
        from app.services.health_monitor import get_monitor
        m = get_monitor()
        if m is not None:
            await sio.emit('services:health', m.get_state(), to=sid)
    except Exception as e:
        logger.warning(f"failed to send initial services:health to {sid}: {e}")


@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    # Schedule delayed cleanup to allow reconnection
    task = asyncio.create_task(_delayed_disconnect_cleanup(sid))
    _pending_disconnects[sid] = task


async def _delayed_disconnect_cleanup(sid):
    """Wait before cleaning up, allowing the client to reconnect."""
    try:
        await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
        # Grace period expired — client didn't reconnect
        logger.info(f"Disconnect grace period expired for {sid}, cleaning up")
        await collab_mgr.leave_all_rooms(sid)
        # Stop all kernels owned by this SID
        while True:
            session = kernel_mgr.get_session_by_sid(sid)
            if not session:
                break
            execution_bridge.stop_iopub_listener(session.session_id)
            await kernel_mgr.stop_kernel(session.session_id)
        client_rooms.pop(sid, None)
    except asyncio.CancelledError:
        # Reconnection happened — cleanup was cancelled
        logger.info(f"Disconnect cleanup cancelled for {sid} (reconnected)")
    finally:
        _pending_disconnects.pop(sid, None)


# --- Notebook events ---

@sio.on("notebook:open")
async def on_notebook_open(sid, data):
    project_id = data.get("project_id")
    notebook_path = data.get("notebook_path")
    user_name = data.get("user_name", "Anonymous")

    if not project_id or not notebook_path:
        await sio.emit("error", {
            "message": "project_id and notebook_path required",
            "code": "INVALID_REQUEST"
        }, to=sid)
        return

    room_key = _make_room_key(project_id, notebook_path)

    # Check for pending disconnects from same user (reconnection scenario).
    # Transfer kernel session and cancel cleanup.
    for old_sid, old_rooms in list(client_rooms.items()):
        if old_sid == sid:
            continue
        old_ctx = old_rooms.get(room_key)
        if old_ctx and old_ctx.get("user_name") == user_name:
            # Cancel pending disconnect cleanup
            pending = _pending_disconnects.get(old_sid)
            if pending:
                pending.cancel()
                _pending_disconnects.pop(old_sid, None)
            # Transfer kernel session to new sid
            session = kernel_mgr.get_session_by_room(room_key)
            if session:
                session.client_sid = sid
                logger.info(f"Transferred kernel {session.session_id} from {old_sid} to {sid}")
            # Clean up old context for this room
            await collab_mgr.leave_room(old_sid, project_id, notebook_path)
            old_rooms.pop(room_key, None)
            if not old_rooms:
                client_rooms.pop(old_sid, None)

    # Add this room to the client's room set
    if sid not in client_rooms:
        client_rooms[sid] = {}
    client_rooms[sid][room_key] = {
        "project_id": project_id,
        "notebook_path": notebook_path,
        "user_name": user_name
    }

    await collab_mgr.join_room(sid, project_id, notebook_path, user_name)

    try:
        nb = notebook_mgr.get_notebook(project_id, notebook_path)
        wire_nb = notebook_mgr.prepare_for_wire(nb)
        room_state = collab_mgr.get_room_state(project_id, notebook_path)
        await sio.emit("notebook:state", {
            "notebook": wire_nb,
            "locks": room_state["cell_locks"],
            "connected_users": room_state["clients"],
            "notebook_key": room_key
        }, to=sid)

        # If kernel was transferred or exists for this room, notify about its status
        session = kernel_mgr.get_session_by_room(room_key)
        if session:
            await sio.emit("kernel:status", {
                "status": session.status,
                "notebook_key": room_key
            }, to=sid)

        # Linting starts at kernel:start, not here, because we don't know
        # the notebook's language until an environment is selected.
    except FileNotFoundError:
        await sio.emit("error", {
            "message": f"Notebook not found: {notebook_path}",
            "code": "NOT_FOUND"
        }, to=sid)


async def _notebook_lsp_broadcast(lsp, message: dict):
    """Broadcast callback for the linter read loop when started by a notebook."""
    method = message.get("method", "")

    # Handle workspace/configuration requests (biome and tsserver send these)
    if message.get("method") == "workspace/configuration" and "id" in message:
        items = message.get("params", {}).get("items", [])
        # Respond with null for each requested config item (use defaults)
        await lsp.send({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": [None] * len(items) if items else [None],
        })
        return
    if not lsp._initialized and lsp._pending_init_id is not None:
        msg_id = message.get("id")
        if msg_id == lsp._pending_init_id and "result" in message:
            lsp._init_result = message["result"]
            lsp._initialized = True
            lsp._init_event.set()

    # Resolve pending request futures
    resp_id = message.get("id")
    if resp_id is not None and ("result" in message or "error" in message):
        lsp.resolve_pending(resp_id, message.get("result") or message.get("error"))
        if isinstance(resp_id, str) and (resp_id.startswith("req-") or resp_id.startswith("nb-")):
            return

    from app.routers.lsp import _enrich_diagnostics
    _enrich_diagnostics(message)

    clients = list(lsp._ws_clients)
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:
            lsp._ws_clients.discard(ws)

    for cb in getattr(lsp, '_nb_diagnostic_callbacks', []):
        try:
            await cb(message)
        except Exception as e:
            logger.debug("Notebook diagnostic callback error: %s", e)


async def _ensure_lsp_initialized(lsp, root_uri=None):
    """Send initialize/initialized handshake if the server hasn't been initialized yet."""
    if lsp._initialized:
        return
    lsp._pending_init_id = "nb-init-1"
    await lsp.send({
        "jsonrpc": "2.0",
        "id": "nb-init-1",
        "method": "initialize",
        "params": {
            "processId": None,
            "capabilities": {"textDocument": {
                "publishDiagnostics": {},
                "hover": {"contentFormat": ["markdown", "plaintext"]},
            }},
            "rootUri": root_uri,
        }
    })
    try:
        await asyncio.wait_for(lsp._init_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Notebook LSP init timed out")
    if lsp._initialized and not lsp._server_notified:
        await lsp.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        lsp._server_notified = True


async def _start_notebook_lsp(project_id: str, notebook_path: str,
                              notebook: dict, room_key: str,
                              language: str = "python",
                              runtime_id: str | None = None,
                              env_name: str | None = None):
    """Initialize notebook LSP linting for the given language.

    For Python and JavaScript, env_name is conventionally empty so the
    LSP is shared across all envs with the same project_id (one ruff,
    one biome per project). For R, env_name MUST be the active env so
    different R versions get separate languageserver processes with the
    right R_HOME / RENV_PATHS_* injected.
    """
    # Languages with notebook LSP support today: python, javascript, r.
    # Anything else returns - the kernel still runs but no IntelliSense.
    if language not in ("python", "javascript", "r"):
        return
    try:
        from app.managers.project_registry import get_registry
        try:
            project_root = get_registry().resolve(project_id)
        except Exception:
            project_root = f"/app/data/projects/{project_id}"

        bridge = nb_lsp_mgr.get_or_create(project_id, notebook_path, language)
        # Tag the bridge with the env/runtime so cell-update path can pick
        # the right LSP cache key (especially for R where each env gets
        # its own languageserver).
        bridge.env_name = env_name
        bridge.runtime_id = runtime_id
        shadow = bridge.generate(notebook)

        if language == "javascript":
            lint_type = "biome"
        elif language == "r":
            lint_type = "languageserver"
        else:
            lint_type = "ruff"

        # Ensure biome.json exists in the project root for Biome to discover
        if lint_type == "biome":
            import shutil
            biome_conf = os.path.join(project_root, "biome.json")
            if not os.path.exists(biome_conf):
                template = "/app/data/templates/javascript/biome.json"
                if os.path.exists(template):
                    shutil.copy2(template, biome_conf)
                    logger.info("Created default biome.json in %s", project_root)

        # Per-language LSP cache key strategy:
        #   - Python and JavaScript: env_name="" so the LSP is shared across
        #     envs in the same project (one ruff/biome per project, the
        #     historical behavior).
        #   - R: env_name = the actual env name, so each R env gets its own
        #     languageserver process. This is required because different R
        #     envs may use different R versions, and the per-version env
        #     vars (R_HOME, RENV_PATHS_*) are baked into the process at
        #     spawn time. Sharing one languageserver across R envs would
        #     produce wrong-version diagnostics.
        # runtime_id is always forwarded; lsp_manager only consults it for
        # languages whose strategies declare a kernel_env block.
        lsp_env_name = env_name if language == "r" else ""
        try:
            lsp = await lsp_mgr.get_or_start(
                project_id, lsp_env_name, lint_type, runtime_id=runtime_id
            )
        except RuntimeError as e:
            # R 3.6.3 / R 4.0.5 (and any future kernel-only R version)
            # land here via the lsp_manager languageserver-installed
            # check. Mark the bridge so subsequent cell-edit updates skip
            # the LSP path entirely instead of re-raising and logging an
            # ERROR per keystroke. Kernel itself is unaffected.
            bridge.lsp_unavailable = True
            logger.warning("Notebook LSP unavailable for %s/%s: %s",
                           project_id, notebook_path, e)
            return

        if not lsp._read_task or lsp._read_task.done():
            lsp._read_task = asyncio.create_task(
                lsp.read_loop(lambda msg: _notebook_lsp_broadcast(lsp, msg))
            )

        await _ensure_lsp_initialized(lsp, root_uri=f"file://{project_root}")

        async def on_notebook_diagnostics(message: dict):
            if message.get("method") != "textDocument/publishDiagnostics":
                return
            params = message.get("params", {})
            uri = params.get("uri", "")
            nb_bridge = nb_lsp_mgr.find_by_uri(uri)
            if not nb_bridge:
                return

            diagnostics = params.get("diagnostics", [])
            rk = _make_room_key(nb_bridge.project_id, nb_bridge.notebook_path)

            # JS per-cell shadows: URI identifies the cell directly
            cell_idx = nb_lsp_mgr.find_cell_by_uri(uri)
            if cell_idx is not None:
                # Diagnostics are already cell-local (no line offset needed)
                await sio.emit("cell:diagnostics", {
                    "cell_index": cell_idx,
                    "diagnostics": diagnostics,
                    "notebook_key": rk,
                }, room=rk)
                return

            # Python combined shadow: map global lines to per-cell
            per_cell = nb_bridge.map_diagnostics(diagnostics)
            all_code_cells = {r.cell_index for r in nb_bridge._cell_regions if r.cell_type == 'code'}
            for cidx in all_code_cells:
                cell_diags = per_cell.get(cidx, [])
                await sio.emit("cell:diagnostics", {
                    "cell_index": cidx,
                    "diagnostics": cell_diags,
                    "notebook_key": rk,
                }, room=rk)

        # Clean up stale callbacks and register new one
        if not hasattr(lsp, '_nb_diagnostic_callbacks'):
            lsp._nb_diagnostic_callbacks = []
        # Remove any previous callback for this notebook
        lsp._nb_diagnostic_callbacks = [
            cb for cb in lsp._nb_diagnostic_callbacks
            if getattr(cb, '_nb_key', None) != (project_id, notebook_path)
        ]
        on_notebook_diagnostics._nb_key = (project_id, notebook_path)
        lsp._nb_diagnostic_callbacks.append(on_notebook_diagnostics)

        # Open shadow files in the linter
        lang_id_map = {"javascript": "javascript", "r": "r"}
        lang_id = lang_id_map.get(language, "python")
        if language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
            # JS: open per-cell shadow files (isolates parse errors per cell)
            for cell_idx, cell_info in bridge._js_cell_shadows.items():
                await lsp.send({"jsonrpc": "2.0", "method": "textDocument/didClose",
                    "params": {"textDocument": {"uri": cell_info["uri"]}}})
                await lsp.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                    "params": {"textDocument": {
                        "uri": cell_info["uri"],
                        "languageId": "javascript",
                        "version": cell_info["version"],
                        "text": cell_info["text"],
                    }}})
        else:
            # Python and R: single combined shadow file
            did_close = {"jsonrpc": "2.0", "method": "textDocument/didClose",
                         "params": {"textDocument": {"uri": bridge.uri}}}
            did_open = {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                        "params": {"textDocument": {"uri": bridge.uri, "languageId": lang_id,
                                   "version": bridge.version, "text": shadow}}}
            await lsp.send(did_close)
            await lsp.send(did_open)

        # R is single-server (languageserver does both lint and completion).
        # Skip the separate completion-server block entirely.
        if language == "r":
            logger.info("Notebook LSP started: %s/%s (%d chars, R)",
                         project_id, notebook_path, len(shadow))
            return

        # Open in completion server (jedi for Python, tsserver for JS)
        completion_type = "tsserver" if language == "javascript" else "jedi"
        try:
            jedi_srv = await lsp_mgr.get_or_start(project_id, "", completion_type)
            if not jedi_srv._read_task or jedi_srv._read_task.done():
                jedi_srv._read_task = asyncio.create_task(
                    jedi_srv.read_loop(lambda msg: _notebook_lsp_broadcast(jedi_srv, msg))
                )
            if jedi_srv._initialized:
                # Build open messages for completion server
                if language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
                    for cell_info in bridge._js_cell_shadows.values():
                        await jedi_srv.send({"jsonrpc": "2.0", "method": "textDocument/didClose",
                            "params": {"textDocument": {"uri": cell_info["uri"]}}})
                        await jedi_srv.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                            "params": {"textDocument": {"uri": cell_info["uri"],
                                "languageId": "javascript", "version": cell_info["version"],
                                "text": cell_info["text"]}}})
                else:
                    await jedi_srv.send(did_close)
                    await jedi_srv.send(did_open)
            else:
                if language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
                    sync_msgs = []
                    for cell_info in bridge._js_cell_shadows.values():
                        sync_msgs.append({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                            "params": {"textDocument": {"uri": cell_info["uri"],
                                "languageId": "javascript", "version": cell_info["version"],
                                "text": cell_info["text"]}}})
                    jedi_srv._pending_sync = sync_msgs
                else:
                    jedi_srv._pending_sync = [did_open]
                async def _init_notebook_jedi():
                    await _ensure_lsp_initialized(jedi_srv, root_uri=f"file://{project_root}")
                    if jedi_srv._initialized:
                        for msg in getattr(jedi_srv, '_pending_sync', []):
                            await jedi_srv.send(msg)
                        jedi_srv._pending_sync = None
                        logger.info("Notebook jedi ready: %s/%s", project_id, notebook_path)
                asyncio.create_task(_init_notebook_jedi())
        except Exception:
            pass

        logger.info("Notebook LSP started: %s/%s (%d chars)",
                     project_id, notebook_path, len(shadow))
    except Exception as e:
        logger.error("Failed to start notebook LSP: %s", e)


async def _update_notebook_lsp(project_id: str, notebook_path: str,
                                cell_index: int, source: str):
    """Update the notebook shadow file after a cell edit."""
    bridge = nb_lsp_mgr.get(project_id, notebook_path)
    if not bridge:
        return
    # Languages with notebook LSP support: python, javascript, r.
    # For any other language, there is no bridge to update.
    if bridge.language not in ("python", "javascript", "r"):
        return
    # Kernel-only R envs (R 3.6.3, R 4.0.5) have no languageserver. The
    # initial _start_notebook_lsp call set this flag after the
    # RuntimeError; suppress further attempts so cell edits do not
    # repeatedly try-and-fail and spam the log with one ERROR per
    # keystroke.
    if getattr(bridge, "lsp_unavailable", False):
        return
    try:
        nb = notebook_mgr.get_notebook(project_id, notebook_path)
        wire_nb = notebook_mgr.prepare_for_wire(nb)
        shadow = bridge.update_cell(cell_index, source, wire_nb)

        if bridge.language == "javascript":
            lint_type = "biome"
        elif bridge.language == "r":
            lint_type = "languageserver"
        else:
            lint_type = "ruff"
        # Match the same cache-key strategy as _start_notebook_lsp:
        # R uses env_name (per-env LSP), Python and JS use "" (shared).
        lsp_env_name = bridge.env_name if bridge.language == "r" else ""
        try:
            lsp = await lsp_mgr.get_or_start(
                project_id, lsp_env_name, lint_type, runtime_id=bridge.runtime_id
            )
        except RuntimeError as e:
            # Kernel-only mode discovered late (e.g. _start_notebook_lsp
            # was not called for this bridge for some reason). Mark and
            # bail out silently going forward.
            bridge.lsp_unavailable = True
            logger.warning(
                "Notebook LSP unavailable for %s/%s: %s (suppressing further updates)",
                project_id, notebook_path, e,
            )
            return

        # Build the didChange payload(s) once and reuse for both the lint
        # server and the completion server (for languages that have one).
        # JS uses per-cell shadows so the payload targets the cell's URI;
        # Python and R use a single combined shadow URI.
        if bridge.language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
            cell_info = bridge._js_cell_shadows.get(cell_index)
            if cell_info:
                did_change = {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": cell_info["uri"], "version": cell_info["version"]},
                        "contentChanges": [{"text": cell_info["text"]}],
                    },
                }
            else:
                did_change = None
        else:
            did_change = {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {"uri": bridge.uri, "version": bridge.version},
                    "contentChanges": [{"text": shadow}],
                },
            }

        if did_change:
            await lsp.send(did_change)

        # R is single-server (languageserver does both lint + completion).
        # Python and JS push to a separate completion server which needs
        # the same didChange so its parse tree stays in sync.
        if bridge.language == "r":
            return
        completion_type = "tsserver" if bridge.language == "javascript" else "jedi"
        try:
            jedi_srv = await lsp_mgr.get_or_start(project_id, "", completion_type)
            if jedi_srv._initialized and did_change:
                await jedi_srv.send(did_change)
        except Exception:
            pass
    except Exception as e:
        logger.error("Failed to update notebook LSP: %s", e)


@sio.on("notebook:close")
async def on_notebook_close(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    project_id = ctx.get("project_id", data.get("project_id"))
    notebook_path = ctx.get("notebook_path", data.get("notebook_path"))
    if project_id and notebook_path:
        await collab_mgr.leave_room(sid, project_id, notebook_path)
        room_state = collab_mgr.get_room_state(project_id, notebook_path)
        if not room_state.get("clients"):
            nb_lsp_mgr.remove(project_id, notebook_path)
    # Remove this room from client's room set
    if sid in client_rooms and room_key:
        client_rooms[sid].pop(room_key, None)
        if not client_rooms[sid]:
            client_rooms.pop(sid, None)


@sio.on("notebook:save")
async def on_notebook_save(sid, data):
    logger.info("notebook:save received from %s", sid)
    ctx, room_key = _get_ctx(sid, data)
    project_id = ctx.get("project_id")
    notebook_path = ctx.get("notebook_path")
    content = data.get("content")

    if not project_id or not notebook_path or not content:
        await sio.emit("error", {
            "message": "Missing save data", "code": "INVALID_REQUEST"
        }, to=sid)
        return

    try:
        notebook_mgr.update_notebook(project_id, notebook_path, content)
        await sio.emit("notebook:saved", {
            "success": True, "notebook_key": room_key
        }, room=room_key)
    except Exception as e:
        await sio.emit("notebook:saved", {
            "success": False, "error": str(e), "notebook_key": room_key
        }, to=sid)


@sio.on("notebook:relint")
async def on_notebook_relint(sid, data):
    """Re-lint a notebook after its content changed on disk (e.g. discard)."""
    ctx, room_key = _get_ctx(sid, data)
    project_id = ctx.get("project_id")
    notebook_path = ctx.get("notebook_path")
    if project_id and notebook_path:
        # Only relint if a supported kernel is active for this notebook
        session = kernel_mgr.get_session_by_room(room_key)
        if not session or session.kernel_language not in ("python", "javascript", "r"):
            return
        try:
            nb = notebook_mgr.get_notebook(project_id, notebook_path)
            wire_nb = notebook_mgr.prepare_for_wire(nb)
            # runtime_id and env_name are forwarded for all languages so
            # the LSP layer can apply per-runtime env injection where it
            # makes sense (R uses both; Python and JS ignore them).
            asyncio.create_task(_start_notebook_lsp(
                project_id, notebook_path, wire_nb, room_key,
                language=session.kernel_language,
                runtime_id=ctx.get("runtime_id"),
                env_name=ctx.get("env_name")))
        except Exception as e:
            logger.error("notebook:relint failed: %s", e)


# --- Cell events ---

@sio.on("cell:lock")
async def on_cell_lock(sid, data):
    ctx, _ = _get_ctx(sid, data)
    success = await collab_mgr.acquire_lock(
        sid, ctx.get("project_id", ""), ctx.get("notebook_path", ""),
        data.get("cell_index", -1), ctx.get("user_name", "Anonymous")
    )
    if not success:
        await sio.emit("error", {
            "message": "Cell is locked by another user", "code": "LOCK_DENIED"
        }, to=sid)


@sio.on("cell:unlock")
async def on_cell_unlock(sid, data):
    ctx, _ = _get_ctx(sid, data)
    await collab_mgr.release_lock(
        sid, ctx.get("project_id", ""), ctx.get("notebook_path", ""),
        data.get("cell_index", -1)
    )


@sio.on("cell:update")
async def on_cell_update(sid, data):
    ctx, _ = _get_ctx(sid, data)
    project_id = ctx.get("project_id", "")
    notebook_path = ctx.get("notebook_path", "")
    cell_index = data.get("cell_index")
    source = data.get("source", "")
    await collab_mgr.broadcast_cell_update(
        sid, project_id, notebook_path, cell_index, source
    )
    if project_id and notebook_path and cell_index is not None:
        asyncio.create_task(_update_notebook_lsp(project_id, notebook_path, cell_index, source))


@sio.on("cell:add")
async def on_cell_add(sid, data):
    ctx, _ = _get_ctx(sid, data)
    cell_id = data.get("cell_id", str(uuid.uuid4())[:8])
    await collab_mgr.broadcast_cell_add(
        sid, ctx.get("project_id", ""), ctx.get("notebook_path", ""),
        data.get("cell_index"), data.get("cell_type", "code"), cell_id
    )


@sio.on("cell:delete")
async def on_cell_delete(sid, data):
    ctx, _ = _get_ctx(sid, data)
    await collab_mgr.broadcast_cell_delete(
        sid, ctx.get("project_id", ""), ctx.get("notebook_path", ""),
        data.get("cell_index")
    )


@sio.on("cell:move")
async def on_cell_move(sid, data):
    ctx, _ = _get_ctx(sid, data)
    await collab_mgr.broadcast_cell_move(
        sid, ctx.get("project_id", ""), ctx.get("notebook_path", ""),
        data.get("from_index"), data.get("to_index")
    )


@sio.on("cell:execute")
async def on_cell_execute(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    logger.info(f"Cell execute request from {sid}, cell_index={data.get('cell_index')}, room_key={room_key}")
    session = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
    if not session:
        logger.warning(f"No kernel session for {sid} / {room_key}")
        await sio.emit("error", {
            "message": "No active kernel. Start a kernel first.",
            "code": "NO_KERNEL",
            "notebook_key": room_key,
        }, to=sid)
        return

    logger.info(f"Using kernel session {session.session_id}, alive={session.kernel_manager.is_alive()}")
    # Fire and forget — don't block the event handler so other events can be processed
    asyncio.create_task(execution_bridge.execute_cell(
        session.session_id, data.get("cell_index"), data.get("code", ""), room_key,
        hydra_config=data.get("hydra_config"),
    ))


@sio.on("run:execute")
async def on_run_execute(sid, data):
    logger.info(f"Run execute request from {sid}, run_name={data.get('run_name')}, cells={len(data.get('cells', []))}")
    ctx, room_key = _get_ctx(sid, data)
    session = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
    if not session:
        await sio.emit("error", {
            "message": "No active kernel. Start a kernel first.",
            "code": "NO_KERNEL"
        }, to=sid)
        return

    run_name = data.get("run_name", "unnamed")
    cells = data.get("cells", [])
    datasets = data.get("datasets", [])
    hydra_config = data.get("hydra_config")

    # Resolve DVC hashes for selected datasets.
    #
    # When the notebook has an active Hydra config (i.e. cfg.data.file
    # drives which CSV the code actually loads), derive the dataset
    # lineage from cfg.data.file - this is the single source of truth,
    # matching what the notebook will actually read at run time. The
    # frontend's multi-select dataset picks are ignored for Hydra-using
    # notebooks so the two UIs cannot drift.
    #
    # Non-Hydra notebooks fall back to the manual multi-select as before.
    from app.managers.project_registry import get_registry
    registry = get_registry()
    project_id = registry.clean_id(ctx.get("project_id", ""))

    dataset_hashes = {}

    cfg_data_file = None
    if hydra_config:
        try:
            composed = hydra_mgr.compose(
                project_id,
                overrides=hydra_config.get("overrides") or None,
                group_selections=hydra_config.get("group_selections") or None,
            )
            resolved = (composed or {}).get("resolved", {}) or {}
            data_section = resolved.get("data") or {}
            cfg_data_file = data_section.get("file")
        except Exception as e:
            logger.warning(f"Failed to compose cfg to derive data lineage: {e}")

    if cfg_data_file:
        # Hydra-driven: look up ONLY the file cfg says we're using.
        try:
            repo_path = registry.resolve(project_id)
            dvc_status = dvc.dvc_mgr.status(repo_path)
            tracked = {f["path"]: f["hash"] for f in dvc_status.get("tracked_files", [])}
            if cfg_data_file in tracked:
                dataset_hashes[cfg_data_file] = tracked[cfg_data_file]
            else:
                logger.warning(
                    f"Hydra cfg.data.file '{cfg_data_file}' is not DVC-tracked; "
                    f"skipping lineage tag. Add it with `dvc add {cfg_data_file}`."
                )
        except Exception as e:
            logger.warning(f"Failed to resolve DVC hash for {cfg_data_file}: {e}")
    elif datasets:
        # Non-Hydra fallback: honor the Run Manager's manual picks
        try:
            repo_path = registry.resolve(project_id)
            dvc_status = dvc.dvc_mgr.status(repo_path)
            tracked = {f["path"]: f["hash"] for f in dvc_status.get("tracked_files", [])}
            for ds_path in datasets:
                if ds_path in tracked:
                    dataset_hashes[ds_path] = tracked[ds_path]
        except Exception as e:
            logger.warning(f"Failed to resolve DVC hashes: {e}")

    # Resolve Hydra config hash
    config_hash = None
    try:
        repo_path = registry.resolve(project_id)
        composed = hydra_mgr.compose(repo_path)
        if composed and composed.get("hash"):
            config_hash = composed["hash"]
    except Exception as e:
        logger.debug(f"No Hydra config for config hash: {e}")

    experiment_name = project_id
    logger.info(f"Run execute: {run_name}, experiment={experiment_name}, {len(cells)} cells, {len(dataset_hashes)} datasets, config_hash={config_hash is not None}, hydra={hydra_config is not None}")
    asyncio.create_task(execution_bridge.execute_run(
        session.session_id, cells, run_name, room_key,
        experiment_name=experiment_name,
        dataset_hashes=dataset_hashes or None,
        config_hash=config_hash,
        hydra_config=hydra_config
    ))


# --- Kernel events ---

@sio.on("kernel:start")
async def on_kernel_start(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    env_mgr = venv_mgr.env_manager
    runtime_id = data.get("runtime_id")
    env_name = data.get("env_name")

    # Backward compat: old frontend sends {venv_name}
    if not runtime_id and data.get("venv_name"):
        venv_name = data["venv_name"]
        found_runtime = venv_mgr._find_env(venv_name)
        if found_runtime:
            runtime_id = found_runtime
            env_name = venv_name

    if not runtime_id or not env_name:
        await sio.emit("error", {
            "message": "runtime_id and env_name required",
            "code": "INVALID_REQUEST",
        }, to=sid)
        return

    try:
        # Stop existing kernel for this notebook room before starting a new one
        existing = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
        if existing:
            logger.info(f"Stopping existing kernel {existing.session_id} for room {room_key}")
            execution_bridge.stop_iopub_listener(existing.session_id)
            await kernel_mgr.stop_kernel(existing.session_id)
            await asyncio.sleep(0.5)
        else:
            logger.info(f"No existing kernel for room {room_key}")

        kernel_cmd, kernel_language = env_mgr.get_kernel_cmd(runtime_id, env_name)
        runtime = env_mgr._registry.get_runtime(runtime_id)
        display_name = runtime["display_name"] if runtime else runtime_id
        runtime_kernel_env = runtime.get("kernel_env") if runtime else None
        env_path = env_mgr._env_path(runtime_id, env_name) if runtime else None

        logger.info(f"Starting kernel for {sid} room {room_key}: runtime={runtime_id}, env={env_name}")
        ctx["runtime_id"] = runtime_id
        ctx["env_name"] = env_name
        project_id = ctx.get("project_id")
        await sio.emit("kernel:status", {
            "status": "starting", "notebook_key": room_key
        }, room=room_key)
        session_id = f"{room_key}_{uuid.uuid4().hex[:8]}"
        await kernel_mgr.start_kernel(
            session_id, kernel_cmd, kernel_language, display_name,
            project_id, ctx.get("notebook_path", ""), sid,
            room_key=room_key,
            runtime_kernel_env=runtime_kernel_env,
            env_path=env_path,
        )
        await sio.emit("kernel:status", {
            "status": "idle", "notebook_key": room_key
        }, room=room_key)

        # Start language-appropriate linting now that we know the language.
        # If the new kernel is for a language that has no notebook LSP support
        # (currently: anything other than python/javascript/r), tear down any
        # stale bridge from a previous kernel so old diagnostics stop firing.
        notebook_path = ctx.get("notebook_path", "")
        if kernel_language in ("python", "javascript", "r") and project_id and notebook_path:
            try:
                nb = notebook_mgr.get_notebook(project_id, notebook_path)
                wire_nb = notebook_mgr.prepare_for_wire(nb)
                asyncio.create_task(_start_notebook_lsp(
                    project_id, notebook_path, wire_nb, room_key,
                    language=kernel_language,
                    runtime_id=runtime_id, env_name=env_name))
            except Exception as e:
                logger.warning("Failed to start notebook linting: %s", e)
        elif project_id and notebook_path:
            # Drop any stale notebook LSP bridge and stop sending the
            # frontend diagnostics that no longer apply.
            stale = nb_lsp_mgr.get(project_id, notebook_path)
            if stale:
                nb_lsp_mgr.remove(project_id, notebook_path)
                # Clear any cell-level diagnostics already shown
                try:
                    nb = notebook_mgr.get_notebook(project_id, notebook_path)
                    for cidx, cell in enumerate(nb.get("cells", [])):
                        if cell.get("cell_type") == "code":
                            await sio.emit("cell:diagnostics", {
                                "cell_index": cidx,
                                "diagnostics": [],
                                "notebook_key": room_key,
                            }, room=room_key)
                except Exception as e:
                    logger.debug("Failed to clear stale diagnostics: %s", e)

    except (FileNotFoundError, ValueError) as e:
        await sio.emit("error", {
            "message": str(e), "code": "ENV_NOT_FOUND"
        }, to=sid)
    except Exception as e:
        await sio.emit("error", {
            "message": f"Failed to start kernel: {e}", "code": "KERNEL_ERROR"
        }, to=sid)


@sio.on("kernel:stop")
async def on_kernel_stop(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    session = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
    if session:
        execution_bridge.stop_iopub_listener(session.session_id)
        await kernel_mgr.stop_kernel(session.session_id)
        await sio.emit("kernel:status", {
            "status": "dead", "notebook_key": room_key
        }, room=room_key)


@sio.on("kernel:restart")
async def on_kernel_restart(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    session = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
    if not session:
        # Session was stopped - do a fresh start if we have context
        runtime_id = ctx.get("runtime_id")
        env_name = ctx.get("env_name")
        if runtime_id and env_name:
            restart_data = {"runtime_id": runtime_id, "env_name": env_name}
            if room_key:
                restart_data["notebook_key"] = room_key
            await on_kernel_start(sid, restart_data)
        return

    execution_bridge.stop_iopub_listener(session.session_id)
    await sio.emit("kernel:status", {
        "status": "starting", "notebook_key": room_key
    }, room=room_key)
    try:
        result = await kernel_mgr.restart_kernel(session.session_id)
        if result:
            await sio.emit("kernel:status", {
                "status": "idle", "notebook_key": room_key
            }, room=room_key)
        else:
            await sio.emit("kernel:status", {
                "status": "dead", "notebook_key": room_key
            }, room=room_key)
            await sio.emit("error", {
                "message": "Kernel restart failed",
                "code": "RESTART_FAILED"
            }, room=room_key)
    except Exception as e:
        logger.error(f"Kernel restart error: {e}")
        await sio.emit("kernel:status", {
            "status": "dead", "notebook_key": room_key
        }, room=room_key)
        await sio.emit("error", {
            "message": f"Kernel restart failed: {e}",
            "code": "RESTART_FAILED"
        }, room=room_key)


@sio.on("kernel:interrupt")
async def on_kernel_interrupt(sid, data):
    ctx, room_key = _get_ctx(sid, data)
    session = kernel_mgr.get_session_by_room(room_key) if room_key else kernel_mgr.get_session_by_sid(sid)
    if session:
        await kernel_mgr.interrupt_kernel(session.session_id)


@sio.on("heartbeat")
async def on_heartbeat(sid, data):
    collab_mgr.renew_locks(sid)
    # Heartbeat all kernels for this client
    for room_key in client_rooms.get(sid, {}):
        session = kernel_mgr.get_session_by_room(room_key)
        if session:
            kernel_mgr.heartbeat(session.session_id)


# --- Terminal events ---

@sio.on("terminal:auth")
async def on_terminal_auth(sid, data):
    """Pre-auth check for terminal access. Returns ok or failed."""
    terminal_secret = os.environ.get("NOTED_TERMINAL_SECRET", "")
    if not terminal_secret:
        # No secret configured - terminal is open
        await sio.emit("terminal:auth_ok", {}, to=sid)
        return
    provided = data.get("secret", "")
    if provided == terminal_secret:
        await sio.emit("terminal:auth_ok", {}, to=sid)
    else:
        await sio.emit("terminal:auth_failed", {
            "message": "Invalid terminal access key",
        }, to=sid)


@sio.on("terminal:start")
async def on_terminal_start(sid, data):
    # Terminal secret gate
    terminal_secret = os.environ.get("NOTED_TERMINAL_SECRET", "")
    if terminal_secret:
        provided = data.get("secret", "")
        if provided != terminal_secret:
            await sio.emit("terminal:auth_failed", {
                "message": "Invalid terminal access key",
            }, to=sid)
            return

    session_id = data.get("session_id")
    cmd = data.get("cmd")
    cwd = data.get("cwd")
    env = data.get("env")
    cols = data.get("cols", 120)
    rows = data.get("rows", 24)

    logger.info(f"Terminal start request: session_id={session_id}, cmd={cmd}, cwd={cwd}, env_keys={list(env.keys()) if env else None}")

    if not session_id or not cmd:
        await sio.emit("error", {
            "message": "session_id and cmd required",
            "code": "INVALID_REQUEST",
        }, to=sid)
        return

    # Kill existing session with same id
    existing = terminal_mgr.get_session(session_id)
    if existing:
        await terminal_mgr.kill_session(session_id)

    try:
        await terminal_mgr.create_session(
            session_id, sid, cmd, cwd=cwd, env=env, cols=cols, rows=rows,
        )
        await sio.emit("terminal:started", {
            "session_id": session_id,
        }, to=sid)
    except Exception as e:
        logger.error(f"Terminal start failed: {e}")
        await sio.emit("error", {
            "message": f"Terminal start failed: {e}",
            "code": "TERMINAL_ERROR",
        }, to=sid)


@sio.on("terminal:input")
async def on_terminal_input(sid, data):
    session_id = data.get("session_id")
    text = data.get("data", "")
    session = terminal_mgr.get_session(session_id)
    if session:
        session.write(text)


@sio.on("terminal:resize")
async def on_terminal_resize(sid, data):
    session_id = data.get("session_id")
    cols = data.get("cols", 120)
    rows = data.get("rows", 24)
    session = terminal_mgr.get_session(session_id)
    if session:
        session.resize(cols, rows)


@sio.on("terminal:kill")
async def on_terminal_kill(sid, data):
    session_id = data.get("session_id")
    if session_id:
        await terminal_mgr.kill_session(session_id)


# --- Static files ---

WALLPAPERS_DIR = os.path.join(FRONTEND_DIR, "wallpapers")
if os.path.isdir(WALLPAPERS_DIR):
    app.mount("/wallpapers", StaticFiles(directory=WALLPAPERS_DIR), name="wallpapers")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/wallpapers")
async def list_wallpapers():
    """List available image wallpapers."""
    exts = {'.webp', '.jpg', '.jpeg', '.png'}
    files = []
    if os.path.isdir(WALLPAPERS_DIR):
        for f in sorted(os.listdir(WALLPAPERS_DIR)):
            if os.path.splitext(f)[1].lower() in exts:
                name = os.path.splitext(f)[0].replace('-', ' ').replace('_', ' ')
                files.append({"name": name, "filename": f, "url": f"wallpapers/{f}"})
    return files


@app.get("/api/system/info")
async def system_info():
    """Return container and host OS info for the status bar."""
    import platform
    container_os = "Unknown"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    container_os = line.split("=", 1)[1].strip().strip('"')
                    break
    except FileNotFoundError:
        pass
    kernel = platform.release()
    host_os = "Windows" if "microsoft" in kernel.lower() else "Linux"
    return {
        "container_os": container_os,
        "host_os": host_os,
        "kernel": kernel,
        "python": platform.python_version(),
    }


@app.get("/")
async def index():
    return FileResponse(f"{FRONTEND_DIR}/index.html")


@app.get("/viewer")
async def viewer():
    return FileResponse(f"{FRONTEND_DIR}/viewer.html")


@app.get("/player")
async def player():
    return FileResponse(f"{FRONTEND_DIR}/player.html")


# Wrap FastAPI with Socket.IO ASGI app
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

"""DAP WebSocket endpoint - multi-language debug support.

Language-agnostic: delegates all language-specific behavior to
LanguageStrategy (language_strategies.py). The WebSocket handler
is a generic DAP JSON relay between the browser and the transport.

Supports:
- Python: DAP over Jupyter control channel (ipykernel + debugpy)
- JavaScript: DAP over TCP (vscode-js-debug + V8 Inspector)
"""

import asyncio
import hashlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from app.managers.language_strategies import get_strategy

router = APIRouter()
logger = logging.getLogger(__name__)

_kernel_mgr = None
_exec_bridge = None


def set_managers(dap_manager, kernel_mgr, execution_bridge=None):
    """Called from main.py to inject manager instances."""
    global _kernel_mgr, _exec_bridge
    _kernel_mgr = kernel_mgr
    _exec_bridge = execution_bridge


class ControlChannelDispatcher:
    """Single-reader dispatcher for the Jupyter control channel.

    Reads all messages from the control channel in a background task
    and routes replies to the correct waiting future by msg_id.
    This prevents concurrent get_msg() calls from stealing each other's replies.
    """

    def __init__(self, kc):
        self._kc = kc
        self._pending = {}  # msg_id -> asyncio.Future
        self._stop = asyncio.Event()
        self._task = None

    def start(self):
        self._task = asyncio.create_task(self._read_loop())

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(asyncio.CancelledError())
        self._pending.clear()

    async def _read_loop(self):
        """Background reader for control channel replies."""
        loop = asyncio.get_event_loop()
        while not self._stop.is_set():
            try:
                reply = await loop.run_in_executor(
                    None,
                    lambda: self._kc.control_channel.get_msg(timeout=0.5),
                )
                msg_id = reply.get("parent_header", {}).get("msg_id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(reply.get("content", {}))
            except Exception:
                if self._stop.is_set():
                    break

    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        """Send a debug_request and wait for its reply."""
        content = {
            "type": "request",
            "command": command,
            "seq": seq,
            "arguments": arguments or {},
        }

        msg = self._kc.session.msg("debug_request", content)
        msg_id = msg["header"]["msg_id"]

        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        self._kc.control_channel.send(msg)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"debug_request timed out: {command}")


@router.websocket("/ws/dap")
async def dap_websocket(
    websocket: WebSocket,
    session: str = Query(...),
):
    """WebSocket endpoint for DAP communication.

    Language-agnostic: all language-specific behavior is delegated
    to the LanguageStrategy obtained from the kernel session.
    """
    await websocket.accept()

    if not _kernel_mgr:
        await websocket.close(code=1011, reason="Kernel manager not available")
        return

    kernel_session = _kernel_mgr.get_session(session)
    if not kernel_session:
        await websocket.close(code=1011, reason=f"Kernel session not found: {session}")
        return

    language = kernel_session.kernel_language
    try:
        strategy = get_strategy(language)
    except KeyError:
        await websocket.close(
            code=1011, reason=f"Debugging not supported for language: {language}"
        )
        return

    # Language-specific transport setup
    context = None
    try:
        context = await strategy.setup_debug(kernel_session, websocket)
    except Exception as e:
        logger.error("DAP setup failed for %s (%s): %s", session, language, e)
        await websocket.close(code=1011, reason=str(e))
        return

    transport = context["transport"]
    logger.info("DAP session started: %s (%s)", session, language)

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command", "")
            seq = data.get("seq", 0)
            args = data.get("arguments", {})

            # Initialize: delegate handshake to strategy
            if command == "initialize":
                responses = await strategy.handle_handshake(
                    transport, kernel_session, args, seq
                )
                for resp in responses:
                    await websocket.send_json(resp)
                continue

            # Let strategy filter/suppress commands
            result = strategy.filter_command(command, args)
            if result is None:
                # Suppressed - send synthetic success
                await websocket.send_json({
                    "type": "response",
                    "request_seq": seq,
                    "command": command,
                    "success": True,
                    "body": {},
                })
                continue

            command, args = result

            # Language-specific pre-processing (e.g. dumpCell for Python)
            await strategy.pre_process_command(command, args, transport)

            # Send the DAP request via the transport
            reply = await transport.send_request(command, args, seq=seq)
            if reply:
                # Ensure request_seq matches the frontend's seq so the
                # client can match responses to pending requests
                if "request_seq" in reply:
                    reply["request_seq"] = seq
                await websocket.send_json(reply)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("DAP WebSocket error: %s", e)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        if context:
            await strategy.cleanup_debug(context, kernel_session, session)
        if kernel_session:
            kernel_session.debug_active = False
            kernel_session._debug_kc = None
            kernel_session.debug_shadow_path = ""
            kernel_session.debug_cell_map = []
        logger.info("DAP session ended: %s (%s)", session, language)


@router.get("/api/dap/status")
async def dap_status():
    """Get debug status for all kernel sessions."""
    if not _kernel_mgr:
        return {"sessions": []}

    sessions = []
    for sid, ks in _kernel_mgr._kernels.items():
        sessions.append({
            "session_id": sid,
            "debugpy_ready": True,
            "language": ks.kernel_language,
        })
    return {"sessions": sessions}


class DebugNotebookRequest(BaseModel):
    project_id: str
    notebook_path: str
    cells: list[dict]  # [{cell_type, source}, ...]


@router.post("/api/dap/debug-notebook")
async def debug_notebook(req: DebugNotebookRequest):
    """Generate a shadow file for Debug All Cells.

    Concatenates code cells into a single file with cell markers.
    Uses the LanguageStrategy to determine markers and extension.
    """
    # Determine language from the active kernel session
    language = "python"
    if _kernel_mgr:
        for ks in _kernel_mgr._kernels.values():
            if req.project_id in ks.session_id:
                language = ks.kernel_language
                break

    strategy = get_strategy(language)
    extension = strategy.get_extension()
    marker = strategy.get_shadow_marker()

    lines = []
    cell_map = []
    current_line = 0  # 0-based

    for i, cell in enumerate(req.cells):
        cell_type = cell.get("cell_type", "code")
        source = cell.get("source", "")

        if cell_type != "code":
            continue

        # Marker line
        cell_marker = f"{marker} Cell {i + 1}"
        lines.append(cell_marker)
        current_line += 1

        # Content lines (1-based start for debugger)
        content_start = current_line + 1  # 1-based
        cell_lines = source.split('\n') if source else ['']
        for cl in cell_lines:
            lines.append(cl)
            current_line += 1
        content_end = current_line  # 1-based

        cell_map.append({
            "cell_index": i,
            "start_line": content_start,
            "end_line": content_end,
        })

        # Blank separator
        lines.append('')
        current_line += 1

    shadow_text = '\n'.join(lines)

    # Stable path based on project + notebook
    key = f"{req.project_id}:{req.notebook_path}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    shadow_path = f"/tmp/noted_debug_{h}{extension}"

    with open(shadow_path, 'w', encoding='utf-8') as f:
        f.write(shadow_text)

    # Store on kernel session for execution_bridge to use
    if _kernel_mgr:
        for ks in _kernel_mgr._kernels.values():
            if req.project_id in ks.session_id:
                ks.debug_shadow_path = shadow_path
                ks.debug_cell_map = cell_map
                break

    return {"shadow_path": shadow_path, "cell_map": cell_map}

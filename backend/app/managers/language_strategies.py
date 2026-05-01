"""Language Strategy Pattern for multi-language notebook support.

Each language provides a strategy that encapsulates:
- Debug code wrapping (filename injection for Debug All)
- Shadow file conventions (markers, extension)
- DAP transport setup, handshake, command filtering, and cleanup

Adding a new language requires implementing BaseLanguageStrategy
and registering it in STRATEGIES. No changes to dap.py or
execution_bridge.py needed.
"""

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseLanguageStrategy(ABC):
    """Abstract interface for language-specific behavior."""

    # --- Shadow file / code wrapping ---

    @abstractmethod
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        """Wrap cell code with filename/line injection for Debug All."""
        pass

    @abstractmethod
    def get_extension(self) -> str:
        """Shadow file extension (e.g., '.py', '.js')."""
        pass

    @abstractmethod
    def get_shadow_marker(self) -> str:
        """Cell separator marker for the shadow file (e.g., '# %%', '// %%')."""
        pass

    # --- DAP transport and lifecycle ---

    @abstractmethod
    async def setup_debug(self, kernel_session, websocket):
        """Set up the debug transport and any adapter processes.

        Returns a context dict with at least 'transport' key.
        The dict may contain additional language-specific state
        needed by cleanup_debug().
        """
        pass

    @abstractmethod
    async def handle_handshake(self, transport, kernel_session, init_args, seq):
        """Handle the DAP initialize/attach handshake.

        Called when the frontend sends 'initialize'. Returns a list
        of (response_dict) to send back to the frontend.
        """
        pass

    def filter_command(self, command, args):
        """Filter or modify a DAP command before sending to the adapter.

        Returns:
            (command, args) - possibly modified
            None - to suppress the command (a synthetic success is sent)
        """
        return command, args

    async def pre_process_command(self, command, args, transport):
        """Async pre-processing before a command is sent to the adapter.

        Called after filter_command. Can modify args in-place or send
        additional requests via the transport (e.g. dumpCell for Python).
        """
        pass

    @abstractmethod
    async def cleanup_debug(self, context, kernel_session, session_id):
        """Tear down the debug session. context is from setup_debug()."""
        pass


class PythonStrategy(BaseLanguageStrategy):
    """Python: IPython + debugpy via Jupyter control channel (ZMQ)."""

    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        return f"""
import ast as _ast
from IPython import get_ipython as _get_ipython

_shell = _get_ipython()
_code = {repr(code)}
_path = {repr(shadow_path)}
_offset = {start_line}

_transformed = _shell.input_transformer_manager.transform_cell(_code)
_padded = ("\\n" * (_offset - 1)) + _transformed

_tree = _ast.parse(_padded)
if _tree.body and isinstance(_tree.body[-1], _ast.Expr):
    _last = _tree.body.pop()
    _exec_node = _ast.Module(body=_tree.body, type_ignore_list=[])
    _eval_node = _ast.Interactive(body=[_last])
else:
    _exec_node = _tree
    _eval_node = None

try:
    _compiled = compile(_exec_node, _path, 'exec')
    exec(_compiled, _shell.user_ns)
    if _eval_node:
        _compiled_eval = compile(_eval_node, _path, 'single')
        exec(_compiled_eval, _shell.user_ns)
except Exception:
    _shell.showtraceback()
"""

    def get_extension(self) -> str:
        return ".py"

    def get_shadow_marker(self) -> str:
        return "# %%"

    async def setup_debug(self, kernel_session, websocket):
        from jupyter_client import BlockingKernelClient
        from app.managers.dap_transport import ZMQDebugTransport

        km = kernel_session.kernel_manager
        debug_kc = BlockingKernelClient()
        debug_kc.load_connection_file(km.connection_file)
        debug_kc.start_channels()

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: debug_kc.wait_for_ready(timeout=10)
            )
        except RuntimeError as e:
            debug_kc.stop_channels()
            raise RuntimeError(f"Kernel not ready: {e}")

        kernel_session.debug_active = True
        kernel_session._debug_kc = debug_kc

        # Import here to avoid circular imports
        from app.routers.dap import ControlChannelDispatcher
        dispatcher = ControlChannelDispatcher(debug_kc)
        transport = ZMQDebugTransport(dispatcher)

        stop_event = asyncio.Event()
        was_paused = [False]

        async def forward_debug_events():
            loop = asyncio.get_event_loop()
            while not stop_event.is_set():
                try:
                    msg = await loop.run_in_executor(
                        None,
                        lambda: debug_kc.iopub_channel.get_msg(timeout=0.5),
                    )
                    msg_type = msg.get("msg_type", "?")
                    if msg_type == "debug_event":
                        content = msg.get("content", {})
                        if content.get("event") == "stopped":
                            was_paused[0] = True
                        try:
                            await websocket.send_json(content)
                        except Exception:
                            break
                    elif msg_type == "error":
                        content = msg.get("content", {})
                        logger.warning(
                            "DAP iopub error: %s: %s",
                            content.get("ename", "?"),
                            content.get("evalue", "?"),
                        )
                        try:
                            await websocket.send_json({
                                "type": "event",
                                "event": "output",
                                "body": {
                                    "category": "stderr",
                                    "output": (
                                        f"{content.get('ename', 'Error')}: "
                                        f"{content.get('evalue', '')}"
                                    ),
                                },
                            })
                        except Exception:
                            pass
                except Exception:
                    if stop_event.is_set():
                        break

        event_task = asyncio.create_task(forward_debug_events())
        await transport.start()

        return {
            "transport": transport,
            "debug_kc": debug_kc,
            "event_task": event_task,
            "stop_event": stop_event,
            "was_paused": was_paused,
        }

    async def handle_handshake(self, transport, kernel_session, init_args, seq):
        """Python: just forward initialize. Frontend handles attach + configurationDone."""
        reply = await transport.send_request("initialize", init_args, seq=seq)
        return [reply] if reply else []

    async def pre_process_command(self, command, args, transport):
        """Python: call dumpCell before setBreakpoints to create temp files."""
        if command == "setBreakpoints":
            source = args.get("source", {})
            cell_code = source.pop("cellCode", None)
            if cell_code:
                dump_reply = await transport.send_request(
                    "dumpCell", {"code": cell_code}, timeout=10
                )
                body = dump_reply.get("body", {})
                source_path = body.get("sourcePath", "")
                if source_path:
                    source["path"] = source_path

    async def cleanup_debug(self, context, kernel_session, session_id):
        transport = context["transport"]
        debug_kc = context["debug_kc"]
        event_task = context["event_task"]
        stop_event = context["stop_event"]
        was_paused = context["was_paused"]

        # Send continue + disconnect BEFORE stopping dispatcher
        cleanup_ok = True
        if was_paused[0]:
            try:
                await transport.send_request("continue", {"threadId": 1}, timeout=3)
            except Exception:
                cleanup_ok = False
        try:
            await transport.send_request(
                "disconnect", {"restart": False, "terminateDebuggee": False}, timeout=3
            )
        except Exception:
            cleanup_ok = False

        stop_event.set()
        event_task.cancel()
        try:
            await event_task
        except asyncio.CancelledError:
            pass
        await transport.stop()

        if cleanup_ok:
            try:
                kernel_session.kernel_manager.interrupt_kernel()
            except Exception:
                pass

            # Lazy import to avoid circular dependency
            from app.routers.dap import _exec_bridge
            if _exec_bridge:
                _exec_bridge.stop_iopub_listener(session_id)

            from jupyter_client import BlockingKernelClient
            try:
                old_kc = kernel_session._cached_client
                if old_kc:
                    old_kc.stop_channels()
                new_kc = BlockingKernelClient()
                new_kc.load_connection_file(kernel_session.kernel_manager.connection_file)
                new_kc.start_channels()
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: new_kc.wait_for_ready(timeout=10)
                )
                kernel_session._cached_client = new_kc
            except Exception as e:
                logger.error("DAP: failed to recreate client: %s", e)
        else:
            logger.warning("DAP: control thread stuck, restarting kernel for %s", session_id)
            from app.routers.dap import _exec_bridge
            if _exec_bridge:
                _exec_bridge.stop_iopub_listener(session_id)
            try:
                km = kernel_session.kernel_manager
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: km.restart_kernel(now=True)
                )
                from jupyter_client import BlockingKernelClient
                old_kc = kernel_session._cached_client
                if old_kc:
                    try:
                        old_kc.stop_channels()
                    except Exception:
                        pass
                new_kc = BlockingKernelClient()
                new_kc.load_connection_file(km.connection_file)
                new_kc.start_channels()
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: new_kc.wait_for_ready(timeout=15)
                )
                kernel_session._cached_client = new_kc
                logger.info("DAP: kernel restarted for %s", session_id)
            except Exception as e:
                logger.error("DAP: kernel restart failed: %s", e)

        debug_kc.stop_channels()


class JavaScriptStrategy(BaseLanguageStrategy):
    """JavaScript: vscode-js-debug adapter + V8 Inspector over TCP."""

    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        # Not used for Debug All (single-execution handles it).
        # Kept for potential future use.
        padding = "\n" * max(0, start_line - 2)
        return (
            f"{padding}debugger;\n"
            f"{code}\n"
            f"//# sourceURL={shadow_path}"
        )

    def build_debug_all_script(self, shadow_path: str, cell_map: list) -> str:
        """Build a single JS script for Debug All execution.

        Reads the shadow file and replaces // %% comment markers with
        executable console.log boundary markers. This lets the iopub
        handler route output to the correct cell. Line count stays
        the same since each marker replaces one comment line.

        V8 compiles it once, all breakpoints bind atomically.
        """
        with open(shadow_path) as f:
            lines = f.readlines()

        # Build a set of marker lines -> cell index
        marker_lines = {}  # 0-based line number -> cell_index
        for entry in cell_map:
            # The marker line is the line before start_line (1-based)
            marker_line = entry["start_line"] - 2  # convert to 0-based
            if marker_line >= 0:
                marker_lines[marker_line] = entry["cell_index"]

        # Replace comment markers with executable boundary markers.
        # First marker also opens a block scope { to avoid const/let
        # re-declaration errors from previous normal runs.
        first = True
        for line_num, cell_idx in sorted(marker_lines.items()):
            if line_num < len(lines):
                prefix = "{ " if first else ""
                first = False
                lines[line_num] = f'{prefix}console.log("__NOTED_CELL:{cell_idx}__");\n'

        content = "".join(lines)
        return f"{content}}}\n//# sourceURL={shadow_path}"

    def get_extension(self) -> str:
        return ".js"

    def get_shadow_marker(self) -> str:
        return "// %%"

    async def setup_debug(self, kernel_session, websocket):
        from app.managers.dap_transport import TCPDebugTransport
        from app.managers.js_debug_adapter import JSDebugAdapter

        inspect_port = kernel_session.debug_port
        if not inspect_port:
            raise RuntimeError(
                "V8 Inspector port not available. "
                "Kernel may not have started with --inspect."
            )

        kernel_session.debug_active = True

        adapter = JSDebugAdapter()
        dap_port = await adapter.start()

        transport = TCPDebugTransport("127.0.0.1", dap_port)

        async def on_event(event):
            try:
                await websocket.send_json(event)
            except Exception:
                pass

        transport.set_event_handler(on_event)
        await transport.start()

        return {
            "transport": transport,
            "adapter": adapter,
        }

    async def handle_handshake(self, transport, kernel_session, init_args, seq):
        """JS: initialize -> attach -> configurationDone (full handshake).

        The frontend doesn't need to send attach/configurationDone separately;
        the backend handles the entire handshake with the adapter.
        """
        responses = []

        # 1. Initialize
        reply = await transport.send_request("initialize", init_args, seq=seq)
        if reply:
            responses.append(reply)

        # 2. Attach (non-blocking - response comes after configurationDone)
        attach_fut = asyncio.ensure_future(
            transport.send_request("attach", {
                "type": "pwa-node",
                "request": "attach",
                "name": "Attach to Kernel",
                "address": "127.0.0.1",
                "port": kernel_session.debug_port,
                "sourceMaps": False,
                "resolveSourceMapLocations": [],
            }, seq=seq + 1, timeout=30)
        )

        # 3. Wait for initialized event, then send configurationDone
        await asyncio.sleep(0.2)
        await transport.send_request("configurationDone", {}, seq=seq + 2)

        # 4. Await attach response
        attach_reply = await attach_fut
        if attach_reply:
            responses.append(attach_reply)

        # 5. Brief wait for the adapter to detect and attach to the child
        # evaluator process. The startDebugging reverse request is
        # handled by TCPDebugTransport which opens a child session.
        await asyncio.sleep(0.3)

        return responses

    def filter_command(self, command, args):
        """JS: suppress frontend's attach and configurationDone (already handled)."""
        if command in ("attach", "configurationDone"):
            return None  # suppress
        return command, args

    async def pre_process_command(self, command, args, transport):
        """JS: write cell code to a temp file for breakpoint binding.

        The V8 debugger needs a real file path to bind breakpoints.
        We write the cell code to a temp .js file and set the source
        path so the adapter can find it. The cell execution will use
        //# sourceURL= pointing to the same path.
        """
        if command == "setBreakpoints":
            source = args.get("source", {})
            cell_code = source.pop("cellCode", None)
            if cell_code:
                import hashlib, os
                h = hashlib.md5(cell_code.encode()).hexdigest()[:12]
                temp_path = f"/tmp/noted_js_cell_{h}.js"
                with open(temp_path, "w") as f:
                    f.write(cell_code)
                source["path"] = temp_path
                # Store for execution_bridge to use as sourceURL
                self._last_cell_path = temp_path

    async def cleanup_debug(self, context, kernel_session, session_id):
        transport = context["transport"]
        adapter = context["adapter"]

        try:
            await transport.send_request(
                "disconnect", {"restart": False, "terminateDebuggee": False}, timeout=3
            )
        except Exception:
            pass
        await transport.stop()
        await adapter.stop()


class RStrategy(BaseLanguageStrategy):
    """R: ark kernel + renv environment isolation.

    Phase 1 implements only the shadow file / wrap_code surface so cells
    execute via the strategy. Debugger methods are stubbed - R debug is
    deferred until ark exposes its DAP outside Positron.
    """

    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        # R uses 1-based lines and treats the leading newline as line 1, so
        # padding (start_line - 1) blank lines aligns srcrefs with the
        # original cell content. Used by Debug All in the future; the basic
        # cell run path uses .noted_run_cell() defined in the .Rprofile.
        padding = "\n" * max(0, start_line - 1)
        return f"{padding}{code}\n"

    def get_extension(self) -> str:
        return ".R"

    def get_shadow_marker(self) -> str:
        return "# %%"

    async def setup_debug(self, kernel_session, websocket):
        raise NotImplementedError(
            "R debug is not yet supported (Phase 3 - awaiting ark DAP exposure)"
        )

    async def handle_handshake(self, transport, kernel_session, init_args, seq):
        raise NotImplementedError(
            "R debug is not yet supported (Phase 3 - awaiting ark DAP exposure)"
        )

    async def cleanup_debug(self, context, kernel_session, session_id):
        # No-op: R sessions never enter debug mode in Phase 1/2
        return


# Registry of available strategies, keyed by kernel_language
STRATEGIES = {
    "python": PythonStrategy(),
    "javascript": JavaScriptStrategy(),
    "r": RStrategy(),
}


def get_strategy(language: str) -> BaseLanguageStrategy:
    """Get the strategy for a given kernel language.

    Raises KeyError if the language is not supported.
    """
    if language not in STRATEGIES:
        raise KeyError(f"No language strategy for: {language}")
    return STRATEGIES[language]

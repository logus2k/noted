import asyncio
import logging
import re
from jupyter_client import KernelClient
from app.managers.kernel_manager import KernelManagerService
from app.managers.auto_instrumentation import AutoInstrumentation
from app.managers.language_strategies import get_strategy

logger = logging.getLogger(__name__)

# Patterns for extracting top-level JS declarations
_JS_DECL_SIMPLE = re.compile(r'^\s*(?:const|let|var)\s+(\w+)', re.MULTILINE)
_JS_DECL_DESTRUCTURE_OBJ = re.compile(r'^\s*(?:const|let|var)\s+\{([^}]+)\}', re.MULTILINE)
_JS_DECL_DESTRUCTURE_ARR = re.compile(r'^\s*(?:const|let|var)\s+\[([^\]]+)\]', re.MULTILINE)
_JS_DECL_FUNC = re.compile(r'^\s*function\s+(\w+)', re.MULTILINE)
_JS_DECL_CLASS = re.compile(r'^\s*class\s+(\w+)', re.MULTILINE)


def _extract_js_declarations(code: str) -> list[str]:
    """Extract variable/function/class names from top-level JS declarations."""
    names = []
    names.extend(_JS_DECL_SIMPLE.findall(code))
    for match in _JS_DECL_DESTRUCTURE_OBJ.findall(code):
        for part in match.split(','):
            part = part.strip()
            if ':' in part:
                part = part.split(':')[-1].strip()  # { key: alias }
            if part and part.isidentifier():
                names.append(part)
    for match in _JS_DECL_DESTRUCTURE_ARR.findall(code):
        for part in match.split(','):
            part = part.strip()
            if part and part.isidentifier():
                names.append(part)
    names.extend(_JS_DECL_FUNC.findall(code))
    names.extend(_JS_DECL_CLASS.findall(code))
    return list(dict.fromkeys(names))  # dedupe preserving order


def _wrap_js_cell(code: str) -> str:
    """Wrap JS cell in IIFE with globalThis exports for re-runnability."""
    has_await = "await " in code and not code.lstrip().startswith("(async")

    declared = _extract_js_declarations(code)
    if not declared and not has_await:
        return code  # no declarations, no wrapping needed

    exports = "\n".join(f"    globalThis.{n} = {n};" for n in declared)
    if exports:
        exports = "\n" + exports

    if has_await:
        return f"(async () => {{\n{code}{exports}\n}})()"
    else:
        return f"void function() {{\n{code}{exports}\n}}();"


class _CellHandler:
    """Tracks state for a single cell execution."""
    __slots__ = ('cell_index', 'room', 'execution_count', 'done', 'errored', '_cell_start')

    def __init__(self, cell_index: int, room: str):
        self.cell_index = cell_index
        self.room = room
        self.execution_count = None
        self.done = asyncio.Event()
        self.errored = False
        self._cell_start = None


class ExecutionBridge:
    """Bridges Socket.IO events with Jupyter kernel ZMQ channels.

    Uses a single iopub listener per kernel session that dispatches
    messages to the correct cell handler based on parent msg_id.
    """

    def __init__(self, kernel_manager: KernelManagerService, sio,
                 auto_instrumentation: AutoInstrumentation = None):
        self._kernel_manager = kernel_manager
        self._sio = sio
        self._auto_inst = auto_instrumentation
        # session_id -> asyncio.Task running the iopub listener
        self._iopub_tasks: dict[str, asyncio.Task] = {}
        # session_id -> { msg_id: _CellHandler }
        self._pending: dict[str, dict[str, _CellHandler]] = {}

    async def execute_cell(self, session_id: str, cell_index: int,
                           code: str, room: str,
                           hydra_config: dict | None = None):
        session = self._kernel_manager.get_session(session_id)
        if not session:
            await self._sio.emit("error", {
                "message": "No active kernel",
                "code": "NO_KERNEL",
                "notebook_key": room
            }, room=room)
            return

        # Stash hydra_config on session so the iopub listener can look it up
        # when a new MLflow run is detected (for bundle logging - M2).
        if hydra_config:
            session.current_hydra_config = hydra_config
            session.current_notebook_uid = hydra_config.get('notebook_uid')

        kc = await self._kernel_manager.get_kernel_client(session_id)
        if not kc:
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "error",
                    "ename": "KernelError",
                    "evalue": "Kernel is not running or not responding. Try restarting the kernel.",
                    "traceback": ["Kernel is not running or not responding. Try restarting the kernel."]
                }
            }, room=room)
            await self._sio.emit("cell:execute_complete", {
                "cell_index": cell_index,
                "notebook_key": room,
                "execution_count": None
            }, room=room)
            return

        # Ensure iopub listener is running for this session
        self._ensure_iopub_listener(session_id, kc)

        self._kernel_manager.update_status(session_id, "busy")
        await self._sio.emit("kernel:status", {"status": "busy", "notebook_key": room}, room=room)

        handler = _CellHandler(cell_index, room)

        try:
            # During debug sessions, use the debug kernel client to avoid
            # ZMQ identity conflicts, and skip silent pre-executions
            # (debugpy tracing makes them very slow).
            if session.debug_active:
                if session._debug_kc:
                    kc = session._debug_kc
                logger.info("Debug session active - using debug kernel client, skipping silent execs")
            else:
                # Python-specific pre-execution hooks
                is_python = session.kernel_language == "python"

                # Install metrics hook (streams live metrics to UI via IPython)
                if is_python and self._auto_inst:
                    await self._execute_silent(kc, self._auto_inst.get_metrics_hook_code())

            # Hydra config injection (Python/Hydra only)
            is_python = session.kernel_language == "python"
            logger.info("Hydra config for cell %d: %s", cell_index, hydra_config)
            if is_python and hydra_config and not session.debug_active:
                if self._has_hydra_import(code):
                    # Cell uses @hydra.main or OmegaConf directly - inject as CLI overrides
                    cli_code = self._build_hydra_cli_overrides(hydra_config, session)
                    if cli_code:
                        await self._execute_silent(kc, cli_code)
                else:
                    # Regular cell - inject resolved config as Python object
                    config_code = self._build_hydra_injection(hydra_config, session)
                    logger.info("Hydra injection for cell %d: %s", cell_index,
                                'generated' if config_code else 'NONE (failed)')
                    if config_code:
                        await self._execute_silent(kc, config_code)

            # If Debug All is active, wrap the code with filename injection
            # so the debugger sees the shadow file path for breakpoint matching
            exec_code = code
            if session.debug_shadow_path and session.debug_active and \
                    session.kernel_language == "javascript":
                # JS Debug All: single-execution mode.
                # Execute the entire shadow file as one script on the first cell.
                # Skip subsequent cells (they're included in the single script).
                if cell_index == session.debug_cell_map[0]["cell_index"]:
                    strategy = get_strategy("javascript")
                    exec_code = strategy.build_debug_all_script(
                        session.debug_shadow_path, session.debug_cell_map
                    )
                else:
                    # JS Debug All: frontend only sends the first cell.
                    # This shouldn't be reached, but guard just in case.
                    logger.warning("JS Debug All: unexpected cell %d execution", cell_index)
                    return
            elif session.debug_shadow_path and session.debug_active:
                exec_code = self._wrap_for_debug(
                    code, session.debug_shadow_path,
                    session.debug_cell_map, cell_index,
                    kernel_language=session.kernel_language,
                )
            elif session.debug_active and session.kernel_language == "javascript":
                # Single-cell JS debug: IIFE wrapper with debugger; sync point.
                # The debugger; pauses V8 so breakpoints bind to the loaded
                # script. Frontend auto-continues past this internal pause.
                import hashlib
                h = hashlib.md5(code.encode()).hexdigest()[:12]
                source_url = f"/tmp/noted_js_cell_{h}.js"
                exec_code = (
                    f"(function() {{\n"
                    f"debugger;\n"
                    f"{code}\n"
                    f"}})();\n"
                    f"//# sourceURL={source_url}"
                )

            # JS: wrap in IIFE to allow re-running cells with const/let.
            # Export declared variables to globalThis for cross-cell access.
            if session.kernel_language == "javascript" and not session.debug_active:
                exec_code = _wrap_js_cell(exec_code)

            msg_id = kc.execute(exec_code)
            logger.info(f"Execute sent for cell {cell_index}, msg_id={msg_id}")

            # Register handler so the iopub listener can dispatch to it
            self._pending.setdefault(session_id, {})[msg_id] = handler

            # Wait for completion.
            # File debug (cell_index == -1): short timeout since debug
            # lifecycle is managed by DAP, not iopub completion.
            # Regular cells: no timeout (training can take hours).
            try:
                if cell_index == -1:
                    try:
                        await asyncio.wait_for(handler.done.wait(), timeout=2)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await handler.done.wait()
            finally:
                # Clean up handler
                pending = self._pending.get(session_id, {})
                pending.pop(msg_id, None)

        except Exception as e:
            logger.error(f"Execution error: {e}")
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "error",
                    "ename": type(e).__name__,
                    "evalue": str(e),
                    "traceback": [str(e)]
                }
            }, room=room)
        finally:
            # Always emit cell:execute_complete so the frontend never
            # gets stuck on "Running..." — even if the iopub loop crashed
            # before it could send the status:idle completion signal.
            if not handler.execution_count:
                logger.warning(
                    f"Cell {cell_index} completed without execution_count "
                    f"(iopub listener may have crashed)"
                )
            # For JS Debug All: send execute_complete for the last cell
            # before the final execute_complete (which triggers termination)
            if handler._cell_start is not None and handler.cell_index != cell_index:
                import time
                elapsed = time.time() - handler._cell_start
                await self._sio.emit("cell:execute_complete", {
                    "cell_index": handler.cell_index,
                    "notebook_key": room,
                    "execution_count": handler.execution_count,
                    "elapsed": round(elapsed, 1),
                }, room=room)

            await self._sio.emit("cell:execute_complete", {
                "cell_index": cell_index,
                "notebook_key": room,
                "execution_count": handler.execution_count
            }, room=room)

            # If no more pending executions, mark kernel idle
            if not self._pending.get(session_id):
                self._kernel_manager.update_status(session_id, "idle")
                await self._sio.emit("kernel:status", {"status": "idle", "notebook_key": room}, room=room)

    async def execute_run(self, session_id: str, cells: list,
                          run_name: str, room: str,
                          experiment_name: str = '',
                          dataset_hashes: dict = None,
                          config_hash: str = None,
                          hydra_config: dict | None = None):
        """Execute a sequence of cells wrapped in a single MLflow run.

        Args:
            cells: list of {"cell_index": int, "code": str}
            run_name: name for the MLflow run
        """
        session = self._kernel_manager.get_session(session_id)
        if not session:
            await self._sio.emit("error", {
                "message": "No active kernel", "code": "NO_KERNEL"
            }, room=room)
            return

        # Stash hydra_config on session so the iopub listener can log the
        # per-run Hydra bundle when a new MLflow run is detected (M2).
        if hydra_config:
            session.current_hydra_config = hydra_config
            session.current_notebook_uid = hydra_config.get('notebook_uid')

        kc = await self._kernel_manager.get_kernel_client(session_id)
        if not kc:
            await self._sio.emit("error", {
                "message": "Kernel not responding", "code": "KERNEL_ERROR",
                "notebook_key": room
            }, room=room)
            return

        self._ensure_iopub_listener(session_id, kc)
        self._kernel_manager.update_status(session_id, "busy")
        await self._sio.emit("kernel:status", {"status": "busy", "notebook_key": room}, room=room)
        await self._sio.emit("run:started", {"run_name": run_name, "notebook_key": room}, room=room)

        errored = False
        try:
            # Inject mlflow.start_run() silently (+ dataset hashes if selected)
            if self._auto_inst:
                await self._execute_silent(
                    kc, self._auto_inst.get_run_start_code(run_name, experiment_name, dataset_hashes, config_hash)
                )

            # Inject metrics hook once before all cells
            if self._auto_inst:
                await self._execute_silent(kc, self._auto_inst.get_metrics_hook_code())

            # Inject Hydra config once before all cells
            if hydra_config:
                session = self._kernel_manager.get_session(session_id)
                config_code = self._build_hydra_injection(hydra_config, session)
                if config_code:
                    await self._execute_silent(kc, config_code)

            # Run Manager path: the backend just silently executed
            # mlflow.start_run() above. Ask the kernel for the resulting
            # run_id and log the Hydra bundle directly from the backend.
            # (Monkey-patch hooks do not help here because silent execution
            # suppresses display_data messages to iopub.)
            if hydra_config:
                rid = await self._query_active_mlflow_run(kc)
                if rid:
                    asyncio.create_task(
                        self._log_hydra_bundle_for_run(session_id, rid)
                    )

            # Execute each cell sequentially
            for cell_info in cells:
                cell_index = cell_info["cell_index"]
                code = cell_info["code"]

                # Notify frontend that cell is starting (for timing + UI)
                await self._sio.emit("cell:execute_start", {
                    "cell_index": cell_index,
                    "notebook_key": room,
                }, room=room)

                handler = _CellHandler(cell_index, room)
                msg_id = kc.execute(code)
                self._pending.setdefault(session_id, {})[msg_id] = handler

                try:
                    await handler.done.wait()
                finally:
                    self._pending.get(session_id, {}).pop(msg_id, None)

                await self._sio.emit("cell:execute_complete", {
                    "cell_index": cell_index,
                    "notebook_key": room,
                    "execution_count": handler.execution_count
                }, room=room)

                if handler.errored:
                    errored = True
                    break

            # Inject mlflow.end_run() (includes autolog activation)
            if self._auto_inst and not errored:
                kc.execute(self._auto_inst.get_run_end_code(),
                           silent=True, store_history=False)

        except Exception as e:
            logger.error(f"Run execution error: {e}")
            errored = True
        finally:
            await self._sio.emit("run:complete", {
                "run_name": run_name,
                "notebook_key": room,
                "errored": errored,
            }, room=room)

            if not self._pending.get(session_id):
                self._kernel_manager.update_status(session_id, "idle")
                await self._sio.emit("kernel:status", {"status": "idle", "notebook_key": room}, room=room)

    def _wrap_for_debug(self, code: str, shadow_path: str,
                        cell_map: list, cell_index: int,
                        kernel_language: str = "python") -> str:
        """Wrap cell code with filename injection for Debug All.

        Delegates to the LanguageStrategy for the given kernel_language.
        """
        start_line = 1
        for entry in cell_map:
            if entry["cell_index"] == cell_index:
                start_line = entry["start_line"]
                break

        strategy = get_strategy(kernel_language)
        return strategy.wrap_code(code, shadow_path, start_line)

    async def _execute_silent(self, kc: KernelClient, code: str,
                              timeout: float = 10.0):
        """Execute code silently and wait for the shell reply."""
        msg_id = kc.execute(code, silent=True, store_history=False)
        try:
            # Wait for shell reply in executor (blocking ZMQ call)
            while True:
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: kc.get_shell_msg(timeout=timeout)
                )
                if reply.get("parent_header", {}).get("msg_id") == msg_id:
                    status = reply.get("content", {}).get("status")
                    if status != "ok":
                        ename = reply.get("content", {}).get("ename", "")
                        evalue = reply.get("content", {}).get("evalue", "")
                        logger.warning("Silent execution error: %s: %s", ename, evalue)
                    return status == "ok"
        except Exception as e:
            logger.warning(f"Silent execution timed out or failed: {e}")
            return False

    async def _query_active_mlflow_run(self, kc: KernelClient,
                                       timeout: float = 5.0) -> str | None:
        """Ask the kernel for the currently-active MLflow run_id.

        Uses Jupyter's `user_expressions` on a silent execute_request: the
        kernel evaluates the expression in user namespace and returns the
        repr() in the shell reply. This lets the backend retrieve a value
        from the kernel without going through iopub display_data.

        Returns the run_id string, or None if no active run or on error.
        """
        expr = (
            "__import__('mlflow').active_run().info.run_id "
            "if __import__('mlflow').active_run() is not None else ''"
        )
        msg_id = kc.execute(
            'pass', silent=True, store_history=False,
            user_expressions={'noted_active_run': expr},
        )
        try:
            while True:
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: kc.get_shell_msg(timeout=timeout)
                )
                if reply.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                content = reply.get("content", {})
                if content.get("status") != "ok":
                    return None
                ue = content.get("user_expressions", {}) or {}
                entry = ue.get("noted_active_run", {})
                if not isinstance(entry, dict):
                    return None
                if entry.get("status") != "ok":
                    return None
                data = entry.get("data", {}) or {}
                repr_text = data.get("text/plain", "")
                # repr() wraps strings in quotes; strip them.
                rid = repr_text.strip().strip("'").strip('"')
                return rid if rid else None
        except Exception as e:
            logger.warning("Query active MLflow run failed: %s", e)
            return None

    def _ensure_iopub_listener(self, session_id: str, kc: KernelClient):
        """Start the iopub listener task if not already running."""
        task = self._iopub_tasks.get(session_id)
        if task and not task.done():
            return
        self._pending.setdefault(session_id, {})
        task = asyncio.create_task(self._iopub_loop(session_id, kc))
        self._iopub_tasks[session_id] = task

    async def _iopub_loop(self, session_id: str, kc: KernelClient):
        """Single iopub listener that dispatches messages to cell handlers."""
        logger.info(f"IOPub listener started for session {session_id}")
        try:
            while True:
                try:
                    msg = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: kc.get_iopub_msg(timeout=60)
                    )
                except Exception:
                    # Timeout with no message — check if we should keep running
                    if not self._pending.get(session_id):
                        logger.info(f"IOPub listener idle, stopping for session {session_id}")
                        break
                    continue

                # Process each message in its own try/except so one bad
                # message never kills the listener (e.g. serialization
                # errors on large display_data payloads).
                try:
                    await self._dispatch_iopub_msg(session_id, msg)
                except Exception as e:
                    parent_msg_id = msg.get("parent_header", {}).get("msg_id")
                    msg_type = msg.get("msg_type", "")
                    logger.error(
                        f"Error dispatching IOPub {msg_type} for session "
                        f"{session_id}, parent={parent_msg_id}: {e}",
                        exc_info=True,
                    )

        except asyncio.CancelledError:
            logger.info(f"IOPub listener cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"IOPub listener fatal error for session {session_id}: {e}", exc_info=True)
            # Signal all pending handlers so they don't hang
            for handler in list(self._pending.get(session_id, {}).values()):
                handler.done.set()
        finally:
            self._iopub_tasks.pop(session_id, None)

    async def _dispatch_iopub_msg(self, session_id: str, msg: dict):
        """Dispatch a single iopub message to the appropriate cell handler."""
        parent_msg_id = msg.get("parent_header", {}).get("msg_id")
        msg_type = msg.get("msg_type", "")
        content = msg.get("content", {})

        # Find the handler for this message
        pending = self._pending.get(session_id, {})
        handler = pending.get(parent_msg_id)
        if not handler:
            return

        cell_index = handler.cell_index
        room = handler.room
        logger.info(f"IOPub msg: type={msg_type}, cell={cell_index}")

        if msg_type == "execute_input":
            handler.execution_count = content.get("execution_count")

        elif msg_type == "stream":
            text = content.get("text", "")
            # JS Debug All: intercept cell boundary markers to route
            # output to the correct cell in single-execution mode.
            import re
            boundary = re.match(r'^__NOTED_CELL:(\d+)__\n?$', text)
            if boundary:
                import time
                new_cell = int(boundary.group(1))
                prev_cell = handler.cell_index
                # Send execute_complete for the previous cell so its timer shows.
                # For cell 0 (== cell_index), send elapsed but use a flag
                # so the frontend uses backend timing instead of its own.
                if prev_cell != new_cell and handler._cell_start is not None:
                    elapsed = time.time() - handler._cell_start
                    await self._sio.emit("cell:execute_complete", {
                        "cell_index": prev_cell,
                        "notebook_key": room,
                        "execution_count": handler.execution_count,
                        "elapsed": round(elapsed, 1),
                    }, room=room)
                handler.cell_index = new_cell
                handler._cell_start = time.time()
                return
            cell_index = handler.cell_index  # may have been updated by boundary
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "stream",
                    "name": content.get("name", "stdout"),
                    "text": text
                }
            }, room=room)

        elif msg_type == "display_data":
            data = content.get("data", {})
            # Intercept live metric events from the mlflow monkey-patch
            metric_json = data.get("application/x-noted-metric")
            if metric_json:
                import json
                try:
                    metric = json.loads(metric_json)
                    await self._sio.emit("metrics:update", {
                        "cell_index": cell_index,
                        "notebook_key": room,
                        "metric": metric
                    }, room=room)
                except (json.JSONDecodeError, TypeError):
                    pass
                return  # suppress from cell output

            # Intercept run-start events from the mlflow monkey-patch.
            # When a new MLflow run becomes active in the kernel, upload the
            # per-run Hydra bundle (M2).
            run_start_json = data.get("application/x-noted-run-start")
            if run_start_json:
                import json
                try:
                    payload = json.loads(run_start_json)
                    run_id = payload.get("run_id")
                    if run_id:
                        # Fire-and-forget bundle logging; failures do NOT
                        # affect cell execution (see plan 4.8 mitigation).
                        asyncio.create_task(
                            self._log_hydra_bundle_for_run(session_id, run_id)
                        )
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("noted run-start payload parse failed: %s", e)
                return  # suppress from cell output

            transient = content.get("transient", {}) or msg.get("transient", {})
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "display_data",
                    "data": data,
                    "metadata": content.get("metadata", {}),
                    "transient": transient
                }
            }, room=room)

        elif msg_type == "execute_result":
            handler.execution_count = content.get("execution_count")
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "execute_result",
                    "data": content.get("data", {}),
                    "metadata": content.get("metadata", {}),
                    "execution_count": handler.execution_count
                }
            }, room=room)

        elif msg_type == "error":
            handler.errored = True
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "error",
                    "ename": content.get("ename", ""),
                    "evalue": content.get("evalue", ""),
                    "traceback": content.get("traceback", [])
                }
            }, room=room)

        elif msg_type == "update_display_data":
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "update_display_data",
                    "data": content.get("data", {}),
                    "metadata": content.get("metadata", {}),
                    "transient": content.get("transient", {})
                }
            }, room=room)

        elif msg_type == "clear_output":
            await self._sio.emit("cell:output", {
                "cell_index": cell_index,
                "notebook_key": room,
                "output": {
                    "output_type": "clear_output",
                    "wait": content.get("wait", False)
                }
            }, room=room)

        elif msg_type == "status":
            if content.get("execution_state") == "idle":
                logger.info(f"Execution complete for cell {cell_index}, session {session_id}")
                handler.done.set()

    def stop_iopub_listener(self, session_id: str):
        task = self._iopub_tasks.pop(session_id, None)
        if task:
            task.cancel()
        # Signal all pending handlers
        for handler in list(self._pending.pop(session_id, {}).values()):
            handler.done.set()

    # ── Hydra Config Injection ────────────────────────────────────

    @staticmethod
    def _has_hydra_import(code: str) -> bool:
        """Check if cell already imports Hydra (back-off to avoid conflicts)."""
        return 'from hydra' in code or 'import hydra' in code or 'OmegaConf' in code

    async def _log_hydra_bundle_for_run(self, session_id: str, run_id: str) -> None:
        """Upload the per-run Hydra bundle (config/ + selections.json +
        resolved.yaml) to MLflow as artifacts under `hydra/`.

        Triggered by the `application/x-noted-run-start` display_data event
        emitted by the kernel's monkey-patched mlflow.start_run. Fire-and-
        forget: failures are logged but do NOT affect cell execution (per
        Hydra unification plan 4.8 Mitigation).
        """
        # Avoid logging the same run twice per session.
        session = self._kernel_manager.get_session(session_id)
        if not session:
            return
        logged = getattr(session, '_hydra_bundle_logged_runs', None)
        if logged is None:
            logged = set()
            session._hydra_bundle_logged_runs = logged
        if run_id in logged:
            return
        logged.add(run_id)

        hydra_config = session.current_hydra_config
        project_id = session.project_id
        if not hydra_config or not project_id:
            return

        baseline_source_str = hydra_config.get('baseline_source', 'project://config/')
        notebook_uid = hydra_config.get('notebook_uid')

        # Normalize selections from the stashed payload
        group_selections = {}
        saved_selections = hydra_config.get('group_selections', {})
        if isinstance(saved_selections, dict):
            group_selections.update(saved_selections)

        overrides = {}
        raw_overrides = hydra_config.get('overrides', {})
        if isinstance(raw_overrides, dict):
            for key, val in raw_overrides.items():
                overrides[str(key)] = val
        elif isinstance(raw_overrides, list):
            for ov in raw_overrides:
                if '=' in str(ov):
                    key, val = str(ov).split('=', 1)
                    overrides[key] = val

        # Assemble and upload the bundle. Every run is self-contained (D5):
        # re-log the full config/ tree regardless of whether the baseline
        # was local or from a past MLflow run.
        import tempfile
        try:
            from app.managers.hydra_manager import HydraManager
            from app.managers.mlflow_manager import MlflowManager
            from app.managers.hydra_source import parse_source
            mgr = HydraManager()

            source = parse_source(
                baseline_source_str,
                project_id=project_id,
                notebook_uid=notebook_uid,
            )
            bundle = mgr.assemble_bundle_from_source(
                source,
                group_selections=group_selections or None,
                overrides=overrides or None,
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                mgr.write_bundle_to_dir(bundle, tmpdir)
                mlf = MlflowManager()
                mlf.log_artifacts(run_id, tmpdir, 'hydra')

                # Tag the run with the config hash for easy lookup.
                try:
                    result = mgr.compose_from_source(
                        source,
                        overrides=overrides or None,
                        group_selections=group_selections or None,
                    )
                    config_hash = result.get('hash', '')
                    if config_hash:
                        mlf.set_tag(run_id, 'noted.hydra_config_hash', config_hash)
                    # Also tag the project for experiment filtering in the
                    # Composer's Time Machine dropdown.
                    mlf.set_tag(run_id, 'noted.project_id', project_id)
                except Exception as e:
                    logger.warning(
                        "Could not tag run %s with hydra_config_hash: %s",
                        run_id, e,
                    )

                # Tag the run with git commit + branch. Notebook kernels run
                # inside the noted container with cwd=/app, so MLflow's
                # built-in autologging cannot detect the git context; we
                # resolve the project path via the project registry and
                # run git ourselves. Every branch below logs its outcome
                # so future runs leave a visible trace in the noted log
                # for this specific step.
                try:
                    from app.managers.project_registry import get_registry
                    import subprocess
                    import os as _os
                    logger.info(
                        "Git tag: resolving project %r for run %s",
                        project_id, run_id,
                    )
                    project_path = get_registry().resolve(project_id)
                    logger.info(
                        "Git tag: project_registry.resolve(%r) = %r",
                        project_id, project_path,
                    )
                    if not project_path:
                        logger.warning(
                            "Git tag SKIPPED for run %s: project_registry "
                            "returned no path for project %r",
                            run_id, project_id,
                        )
                    elif not _os.path.exists(_os.path.join(project_path, '.git')):
                        logger.warning(
                            "Git tag SKIPPED for run %s: no .git directory "
                            "at %s (project is not a git working tree)",
                            run_id, project_path,
                        )
                    else:
                        commit = subprocess.run(
                            ['git', 'rev-parse', 'HEAD'],
                            cwd=project_path, capture_output=True, text=True, timeout=5,
                        )
                        branch = subprocess.run(
                            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                            cwd=project_path, capture_output=True, text=True, timeout=5,
                        )
                        logger.info(
                            "Git tag: rev-parse HEAD rc=%d stdout=%r stderr=%r",
                            commit.returncode,
                            commit.stdout.strip(),
                            commit.stderr.strip()[:200],
                        )
                        if commit.returncode == 0 and commit.stdout.strip():
                            sha = commit.stdout.strip()
                            mlf.set_tag(run_id, 'noted.git_commit', sha)
                            mlf.set_tag(run_id, 'mlflow.source.git.commit', sha)
                            logger.info(
                                "Git tag SET for run %s: noted.git_commit=%s",
                                run_id, sha[:12],
                            )
                        else:
                            logger.warning(
                                "Git tag SKIPPED for run %s: rev-parse HEAD "
                                "failed (rc=%d, stderr=%r)",
                                run_id, commit.returncode,
                                commit.stderr.strip()[:200],
                            )
                        if branch.returncode == 0 and branch.stdout.strip():
                            mlf.set_tag(
                                run_id, 'mlflow.source.git.branch',
                                branch.stdout.strip(),
                            )
                            logger.info(
                                "Git tag SET for run %s: branch=%s",
                                run_id, branch.stdout.strip(),
                            )
                        else:
                            logger.warning(
                                "Git tag SKIPPED branch for run %s: "
                                "rev-parse --abbrev-ref failed (rc=%d)",
                                run_id, branch.returncode,
                            )
                except Exception as e:
                    logger.warning(
                        "Git tag FAILED for run %s: %s: %s",
                        run_id, type(e).__name__, e,
                        exc_info=True,
                    )
            logger.info("Logged Hydra bundle to run %s", run_id)
        except Exception as e:
            # Fire-and-forget: log and move on.
            logger.warning(
                "Hydra bundle logging failed for run %s: %s",
                run_id, e,
                exc_info=True,
            )

    def _build_hydra_injection(self, hydra_config: dict, session) -> str | None:
        """Build Python code to inject resolved Hydra config into the kernel.

        The config becomes available as:
          - __noted_hydra_config__: dict with the resolved config
          - cfg: OmegaConf DictConfig (if omegaconf is available)
        """
        from app.managers.hydra_manager import HydraManager

        project_id = session.project_id if session else None
        if not project_id:
            return None

        try:
            from app.managers.hydra_source import parse_source
            mgr = HydraManager()
            config_type = hydra_config.get('type', '')
            group_selections = {}
            overrides = {}

            # Baseline source (per Hydra unification plan, D3).
            # Supports LocalSource (project://config/) and MlflowSource
            # (mlflow://<run_id>). MlflowSource requires a notebook_uid.
            baseline_source_str = hydra_config.get(
                'baseline_source', 'project://config/'
            )
            notebook_uid = hydra_config.get('notebook_uid')
            try:
                source = parse_source(
                    baseline_source_str,
                    project_id=project_id,
                    notebook_uid=notebook_uid,
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid Hydra baseline source '{baseline_source_str}': {e}. "
                    "Open the Configuration Composer and switch to Local Baseline."
                ) from e

            # For MlflowSource, ensure the bundle is in the cache (fail loud
            # if it cannot be fetched - per D21).
            if baseline_source_str.startswith('mlflow://'):
                from app.managers.hydra_cache import get_cache
                run_id = baseline_source_str[len('mlflow://'):].strip('/')
                try:
                    get_cache().fetch_from_mlflow(notebook_uid, run_id)
                except RuntimeError as fetch_err:
                    raise ValueError(str(fetch_err)) from fetch_err

            # Multi-group selections (from Compose panel)
            saved_selections = hydra_config.get('group_selections', {})
            if isinstance(saved_selections, dict):
                group_selections.update(saved_selections)

            # Legacy single-group selection (backward compatibility)
            if config_type == 'group':
                group = hydra_config.get('group', '')
                option = hydra_config.get('option', '')
                if group and option:
                    group_selections[group] = option

            # Overrides can arrive as either:
            #  - a dict {"training.epochs": "99", "model.units": "128"} (new format from Composer)
            #  - a list ["training.epochs=99", "model.units=128"] (legacy CLI-style)
            raw_overrides = hydra_config.get('overrides', {})
            if isinstance(raw_overrides, dict):
                for key, val in raw_overrides.items():
                    overrides[str(key)] = val
            elif isinstance(raw_overrides, list):
                for ov in raw_overrides:
                    if '=' in str(ov):
                        key, val = str(ov).split('=', 1)
                        overrides[key] = val

            result = mgr.compose_from_source(
                source,
                overrides=overrides or None,
                group_selections=group_selections or None,
            )
            resolved = result.get('resolved', {})
            config_hash = result.get('hash', '')

            if not resolved:
                return None

            # Build injection code - use json.loads to avoid null/true/false issues
            import json
            config_json = json.dumps(resolved).replace("'", "\\'")
            return (
                "# [noted] Hydra config injection\n"
                "import json as _json\n"
                f"__noted_hydra_config__ = _json.loads('''{config_json}''')\n"
                f"__noted_hydra_hash__ = '{config_hash}'\n"
                "try:\n"
                "    from omegaconf import OmegaConf as _OC\n"
                "    cfg = _OC.create(__noted_hydra_config__)\n"
                "except ImportError:\n"
                "    cfg = type('Config', (), __noted_hydra_config__)()\n"
            )
        except Exception as e:
            logger.warning("Hydra config injection failed: %s", e, exc_info=True)
            return None

    def _build_hydra_cli_overrides(self, hydra_config: dict, session) -> str | None:
        """Build sys.argv overrides for cells using @hydra.main.

        Sets sys.argv so that Hydra's own initialization picks up the config
        selection from the notebook config selector as CLI overrides.
        """
        from app.managers.hydra_manager import HydraManager

        project_id = session.project_id if session else None
        if not project_id:
            return None

        try:
            mgr = HydraManager()
            config_type = hydra_config.get('type', '')
            overrides = []

            if config_type == 'group':
                group = hydra_config.get('group', '')
                option = hydra_config.get('option', '')
                if group and option:
                    overrides.append(f'{group}={option}')

            # Resolve config to get individual key=value pairs for flat overrides
            group_selections = {}
            if config_type == 'group':
                g = hydra_config.get('group', '')
                o = hydra_config.get('option', '')
                if g and o:
                    group_selections[g] = o

            result = mgr.compose(project_id, group_selections=group_selections or None)
            resolved = result.get('resolved', {})

            # Flatten resolved config into dot-notation overrides
            def _flatten(d, prefix=''):
                items = []
                for k, v in d.items():
                    key = f'{prefix}{k}' if not prefix else f'{prefix}.{k}'
                    if isinstance(v, dict):
                        items.extend(_flatten(v, key))
                    else:
                        items.append(f'{key}={v}')
                return items

            flat_overrides = _flatten(resolved)
            if not flat_overrides:
                return None

            import json
            argv_list = ['script.py'] + flat_overrides
            return (
                f"# [noted] Hydra CLI overrides from config selector\n"
                f"import sys as _sys\n"
                f"_sys.argv = {json.dumps(argv_list)}\n"
            )
        except Exception as e:
            logger.debug("Hydra CLI overrides skipped: %s", e)
            return None

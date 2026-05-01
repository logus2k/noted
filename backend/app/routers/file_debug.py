"""File Debug - terminal-based debugging for Python, JavaScript, and R files.

Launches the file in a subprocess with debug flags, starts a DAP adapter,
and provides a WebSocket for DAP communication. The file runs in its own
process (not the kernel), so stdout/stderr appear in the terminal.

Flow:
1. POST /api/dap/file-debug -> launches process + adapter, returns session info
2. WebSocket /ws/dap-file -> DAP proxy to the adapter
3. DELETE /api/dap/file-debug/{session_id} -> stops the session

Language-specific debug paths:
- Python: debugpy --listen <port> --wait-for-client <file>
- JavaScript: node --inspect-brk=<port> <file> + vscode-js-debug adapter
- R: Rscript wrapper that loads vscDebugger, opens a DAP listener on
  <port>, then source()s the file. vscDebugger speaks standard DAP over
  TCP (Content-Length headers + JSON), same wire protocol as debugpy.
"""

import asyncio
import json
import logging
import os
import re
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from app.managers.dap_transport import TCPDebugTransport
from app.managers.js_debug_adapter import JSDebugAdapter, find_free_port

router = APIRouter()
logger = logging.getLogger(__name__)

# Active file debug sessions
_sessions = {}  # session_id -> FileDebugSession


def _write_to_r_terminal(text: str):
    """Write text to the most recent terminal session.

    R's vscDebugger requires stdin writes for flow control and listen
    re-entry during Browse mode debugging.

    Note: the commands (n, c, vscDebugger::.vsc.listenForDAP()) are
    visible in the terminal because R echoes stdin in interactive mode.
    Suppressing echo via termios breaks the PTY data flow, so we
    accept the cosmetic noise for now. A future improvement could
    filter these lines from the terminal output relay instead.
    """
    from app.main import terminal_mgr
    for session in reversed(list(terminal_mgr._sessions.values())):
        if hasattr(session, 'write'):
            session.write(text)
            return True
    return False


class FileDebugSession:
    """Tracks state for a file debug session."""
    def __init__(self, session_id, language, file_path, process, adapter, inspect_port):
        self.session_id = session_id
        self.language = language
        self.file_path = file_path
        self.process = process      # the file's subprocess (for cleanup)
        self.adapter = adapter      # JSDebugAdapter or debugpy adapter
        self.inspect_port = inspect_port
        self.dap_port = adapter.dap_port if adapter else 0
        self._temp_files: list[str] = []  # temp files to clean up on stop

    async def stop(self):
        if self.adapter:
            await self.adapter.stop()
            self.adapter = None
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.process.kill()
        for f in self._temp_files:
            try:
                os.remove(f)
            except OSError:
                pass
        # The terminal-launched process exits naturally when the
        # debugger disconnects (--wait-for-client / --inspect-brk).


class FileDebugRequest(BaseModel):
    file_path: str        # absolute path to the file
    language: str         # "python", "javascript", or "r"
    runtime_path: str     # e.g., "/app/data/environments/javascript/22/js_test_env"
    cwd: str              # working directory


@router.post("/api/dap/file-debug")
async def start_file_debug(req: FileDebugRequest):
    """Prepare a file debug session using the runInTerminal pattern.

    1. Picks a free debug port deterministically
    2. Builds the terminal command with that port
    3. Starts the DAP adapter (for JS) or returns the port (for Python/debugpy)
    4. Returns session_id, terminal_command, and dap_port

    The frontend runs the command in a terminal, then connects DAP.
    """
    session_id = f"file-debug-{uuid.uuid4().hex[:8]}"
    debug_port = find_free_port()

    if req.language == "javascript":
        # JS: terminal runs the process, adapter attaches via attachSimplePort
        terminal_cmd = f"node --inspect-brk={debug_port} {req.file_path}"
        adapter = JSDebugAdapter()
        await adapter.start()
        session = FileDebugSession(
            session_id, "javascript", req.file_path,
            None, adapter, debug_port,
        )
    elif req.language == "python":
        # Build debugpy command with deterministic port
        python_bin = os.path.join(req.runtime_path, "bin", "python")
        if not os.path.exists(python_bin):
            python_bin = "python3"
        terminal_cmd = (
            f"{python_bin} -Xfrozen_modules=off -m debugpy "
            f"--listen 127.0.0.1:{debug_port} "
            f"--wait-for-client {req.file_path}"
        )
        # debugpy is its own DAP server - no separate adapter needed
        adapter = _DebugpyAdapter(debug_port)
        session = FileDebugSession(
            session_id, "python", req.file_path,
            None, adapter, debug_port,
        )
    elif req.language == "r":
        # R debug uses vscDebugger which speaks DAP over TCP.
        #
        # Architecture (Option D - "R_PROFILE_USER injection"):
        #
        # vscDebugger requires R to be in interactive mode with a live
        # event loop for two critical reasons:
        #   1. R's browser() (used by vscDebugger for breakpoints)
        #      checks the C-level R_Interactive flag and silently
        #      skips breakpoints when interactive() == FALSE (i.e.
        #      Rscript / batch mode). This is hardcoded in R's
        #      src/main/eval.c and cannot be worked around.
        #   2. vscDebugger's DAP socket listener uses R's
        #      addTaskCallback() / socketSelect() to process incoming
        #      TCP messages while paused at a breakpoint. These only
        #      fire when R's event loop is running (idle at the REPL
        #      prompt with stdin open).
        #
        # The solution: launch `R --interactive` in the terminal
        # (PTY keeps stdin open, R_Interactive flag is TRUE), and
        # inject vscDebugger setup via a temporary R_PROFILE_USER
        # file. R sources this file at startup BEFORE showing the
        # first prompt, but AFTER the PTY/interactive state is
        # initialized. The file also sources the env's .Rprofile
        # for renv activation so the user's packages are visible.
        #
        # After the profile runs, R sits at the `>` prompt with the
        # DAP port open. The backend polls for the port, connects,
        # sends initialize + launch (with file path) + breakpoints +
        # configurationDone, and vscDebugger sources the file.
        #
        # Resolve R version from runtime_path structure:
        # /app/data/environments/r/<version>/<env_name>
        r_version = os.path.basename(os.path.dirname(req.runtime_path))
        r_bin = f"/opt/R/{r_version}/bin/R"
        r_lib = f"/opt/R/{r_version}/lib/R/library"
        r_home = f"/opt/R/{r_version}/lib/R"
        r_ld = f"/opt/R/{r_version}/lib/R/lib"

        # Create temp debug profile that loads vscDebugger and opens
        # the DAP listener. We intentionally do NOT source the env's
        # .Rprofile here - the env vars (RENV_PATHS_LIBRARY,
        # RENV_CONFIG_EXTERNAL_LIBRARIES, etc.) already configure
        # .libPaths() correctly, and calling renv::load() from within
        # R_PROFILE_USER triggers errors because base R functions
        # like packageDescription() aren't available yet during early
        # profile sourcing. The env vars are sufficient for the debug
        # session to find both user packages and system packages.
        # Two-command approach: the terminal_cmd starts R in
        # interactive mode. A second command (r_inject_cmd) is sent
        # to R's stdin after R is at the prompt. This avoids the
        # R 3.6.x R_PROFILE_USER startup race condition where
        # library() is called before utils is on the search path.
        #
        # The inject command is stored on the session so the
        # frontend can send it after a delay.
        r_inject = (
            f"library(vscDebugger); "
            f"options(vsc.showUnlistedElements = FALSE); "
            f".vsc.listenForDAP(port = {debug_port}L)"
        )

        terminal_cmd = (
            f"env "
            f"R_HOME={r_home} "
            f"LD_LIBRARY_PATH={r_ld} "
            f"RENV_PATHS_LIBRARY={req.runtime_path}/renv/library "
            f"RENV_PATHS_LOCKFILE={req.runtime_path}/renv.lock "
            f"RENV_CONFIG_EXTERNAL_LIBRARIES={r_lib} "
            f"RENV_CONFIG_SYNCHRONIZED_CHECK=FALSE "
            f"RENV_CONFIG_AUTOLOADER=FALSE "
            f"{r_bin} --interactive --quiet --no-save"
        )
        adapter = _DebugpyAdapter(debug_port)
        session = FileDebugSession(
            session_id, "r", req.file_path,
            None, adapter, debug_port,
        )
        session.r_inject_cmd = r_inject
    else:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": f"Unsupported language: {req.language}"}, 400)

    _sessions[session_id] = session
    logger.info("File debug prepared: %s (%s) port=%d cmd=%s",
                session_id, req.language, debug_port, terminal_cmd)

    return {
        "session_id": session_id,
        "dap_port": session.dap_port,
        "debug_port": debug_port,
        "terminal_cmd": terminal_cmd,
        # R debug: a second command to inject into R's stdin after
        # R is at the prompt. Sent by the frontend after a delay.
        "r_inject_cmd": getattr(session, "r_inject_cmd", None),
    }


class _DebugpyAdapter:
    """Minimal adapter wrapper for debugpy (direct TCP, no separate process)."""
    def __init__(self, port):
        self.dap_port = port

    async def start(self):
        pass

    async def stop(self):
        pass


@router.get("/api/dap/file-debug/{session_id}/wait")
async def wait_for_debug_ready(session_id: str):
    """Poll until the debug port is accepting connections.

    Called after the terminal launches the process. Returns when
    the debugger (debugpy or --inspect-brk) is ready for attachment.
    """
    session = _sessions.get(session_id)
    if not session:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Session not found"}, 404)

    # Check if the port is listening by scanning /proc/net/tcp.
    # We don't connect directly because debugpy's --wait-for-client
    # only accepts one connection (the actual debugger client).
    target_port_hex = f'{session.inspect_port:04X}'
    for _ in range(20):  # up to 10 seconds
        try:
            with open('/proc/net/tcp') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        local = parts[1]
                        port_hex = local.split(':')[1] if ':' in local else ''
                        if port_hex.upper() == target_port_hex:
                            logger.info("Debug port %d ready for session %s",
                                        session.inspect_port, session_id)
                            return {"ready": True}
        except Exception:
            pass
        await asyncio.sleep(0.5)

    logger.warning("Debug port %d not ready after 10s for session %s",
                    session.inspect_port, session_id)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "Debug process did not start in time"}, 504)


@router.delete("/api/dap/file-debug/{session_id}")
async def stop_file_debug(session_id: str):
    """Stop a file debug session."""
    session = _sessions.pop(session_id, None)
    if session:
        await session.stop()
        return {"stopped": True}
    return {"stopped": False}


@router.websocket("/ws/dap-file")
async def dap_file_websocket(
    websocket: WebSocket,
    session: str = Query(...),
):
    """WebSocket endpoint for file debug DAP communication.

    Proxies DAP JSON between the browser and the debug adapter
    (vscode-js-debug for JS, debugpy for Python).
    """
    await websocket.accept()

    debug_session = _sessions.get(session)
    if not debug_session:
        await websocket.close(code=1011, reason=f"File debug session not found: {session}")
        return

    transport = TCPDebugTransport("127.0.0.1", debug_session.dap_port)
    # JS uses child sessions (vscode-js-debug delegates via
    # startDebugging). R and Python use direct single-session.
    if debug_session.language != "javascript":
        transport.enable_child_sessions = False

    async def on_event(event):
        try:
            if debug_session.language == "r":
                evt_type = event.get("type", "?")
                evt_cmd = event.get("command", event.get("event", "?"))
                logger.info("R DAP <<< %s: %s", evt_type, evt_cmd)
                # vscDebugger sends "writeToStdin" events when it needs
                # the client to write text to R's PTY stdin. Events
                # come in pairs: first the flow control command ("n"),
                # then the listen re-entry call
                # ("vscDebugger::.vsc.listenForDAP()"). Both must be
                # written to the PTY, but we must wait briefly so R's
                # TCP socket has time to flush both events before we
                # write to stdin (which causes R to step and exit the
                # current listenForDAP loop iteration).
                if event.get("event") == "custom" and \
                        event.get("body", {}).get("reason") == "writeToStdin":
                    text = event.get("body", {}).get("text", "")
                    when = event.get("body", {}).get("when", "now")
                    if text:
                        logger.info("R DAP writeToStdin: %s (when=%s)", text.strip()[:80], when)
                        # Write the command to the PTY, then ALWAYS
                        # re-enter vscDebugger's listen loop so the
                        # TCP socket is live for subsequent DAP
                        # requests (stackTrace, scopes, variables).
                        # vscDebugger is supposed to send a second
                        # writeToStdin with .vsc.listenForDAP() but
                        # it often doesn't arrive before R steps and
                        # exits the current loop iteration. So we
                        # inject it ourselves after a tiny delay.
                        async def _write_and_relisten(cmd, reenter):
                            if reenter:
                                # Stepping: write command, re-enter listen loop
                                _write_to_r_terminal(cmd + "\n")
                                await asyncio.sleep(0.2)
                                _write_to_r_terminal("invisible(vscDebugger::.vsc.listenForDAP())\n")
                                logger.info("R DAP re-entered listenForDAP")
                            else:
                                # Continue: restore stdout to PTY via sink()
                                # so remaining cat()/print() output goes
                                # directly to the terminal instead of through
                                # the DAP TCP socket (which is about to die).
                                _write_to_r_terminal("sink(); " + cmd + "\n")
                                logger.info("R DAP continue with sink restore")
                        # Re-enter listenForDAP only for stepping (when=now).
                        # For continue (when=browserPrompt), restore stdout
                        # to the PTY so output doesn't depend on the dying
                        # DAP connection.
                        reenter = (when == "now")
                        asyncio.ensure_future(_write_and_relisten(text, reenter))
                    return  # don't forward to frontend
            await websocket.send_json(event)
        except Exception:
            pass

    transport.set_event_handler(on_event)

    try:
        await transport.start()
    except Exception as e:
        await websocket.close(code=1011, reason=f"Failed to connect to adapter: {e}")
        return

    logger.info("File debug DAP session started: %s (%s)",
                session, debug_session.language)

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command", "")
            seq = data.get("seq", 0)
            args = data.get("arguments", {})
            if debug_session.language == "r":
                logger.info("R DAP >>> %s (seq=%s)", command, seq)

            # JS file debug: intercept initialize to do the full
            # attach handshake (same pattern as notebook JS debug)
            if debug_session.language == "javascript" and command == "initialize":
                reply = await transport.send_request(command, args, seq=seq)
                if reply:
                    if "request_seq" in reply:
                        reply["request_seq"] = seq
                    await websocket.send_json(reply)
                # Attach to the inspector. The adapter will send a
                # startDebugging reverse request to create the real
                # debug session (child). Breakpoints go to that child.
                asyncio.ensure_future(
                    transport.send_request("attach", {
                        "type": "pwa-node",
                        "request": "attach",
                        "name": "Attach to File",
                        "address": "127.0.0.1",
                        "port": debug_session.inspect_port,
                        "autoAttachChildProcesses": False,
                        "sourceMaps": False,
                        "resolveSourceMapLocations": [],
                    }, timeout=30)
                )
                # Wait for child session to be established via startDebugging
                await asyncio.sleep(1)
                continue

            # JS: suppress frontend's attach (handled above in initialize)
            if debug_session.language == "javascript" and command == "attach":
                await websocket.send_json({
                    "type": "response",
                    "request_seq": seq,
                    "command": command,
                    "success": True,
                    "body": {},
                })
                continue

            # Python file debug: intercept initialize to do the full
            # attach handshake (debugpy expects 'connect' in attach args)
            if debug_session.language == "python" and command == "initialize":
                reply = await transport.send_request(command, args, seq=seq)
                if reply:
                    if "request_seq" in reply:
                        reply["request_seq"] = seq
                    await websocket.send_json(reply)
                # Attach with the connect info debugpy expects
                asyncio.ensure_future(
                    transport.send_request("attach", {
                        "type": "debugpy",
                        "request": "attach",
                        "connect": {
                            "host": "127.0.0.1",
                            "port": debug_session.inspect_port,
                        },
                        "justMyCode": False,
                        "subProcess": False,
                    }, timeout=30)
                )
                # Wait for initialized event, then send configurationDone
                await asyncio.sleep(0.5)
                await transport.send_request("configurationDone", {})
                continue

            # Python: suppress frontend's attach/configurationDone (handled above)
            if debug_session.language == "python" and \
                    command in ("attach", "configurationDone"):
                await websocket.send_json({
                    "type": "response",
                    "request_seq": seq,
                    "command": command,
                    "success": True,
                    "body": {},
                })
                continue

            # R file debug: vscDebugger speaks DAP directly over TCP.
            #
            # The DebugClient frontend sends: initialize -> attach ->
            # setBreakpoints -> configurationDone (same flow as Python).
            #
            # vscDebugger expects: initialize -> launch -> setBreakpoints
            # -> configurationDone (it uses "launch" to know which file
            # to source, not "attach").
            #
            # The backend translates: proxy initialize as-is, replace
            # "attach" with "launch" (adding the file path), and proxy
            # setBreakpoints + configurationDone as-is. This way each
            # request is processed one at a time in the WebSocket loop
            # without blocking.
            if debug_session.language == "r" and command == "initialize":
                reply = await transport.send_request(command, args, seq=seq)
                if reply:
                    if "request_seq" in reply:
                        reply["request_seq"] = seq
                    await websocket.send_json(reply)
                continue

            # R: replace frontend's "attach" with vscDebugger's "launch"
            if debug_session.language == "r" and command == "attach":
                reply = await transport.send_request("launch", {
                    "type": "R-Debugger",
                    "request": "launch",
                    "name": "Debug R File",
                    "debugMode": "file",
                    "file": debug_session.file_path,
                    "allowGlobalDebugging": True,
                    "supportsWriteToStdinEvent": True,
                }, timeout=30)
                logger.info("R debug launch reply: %s",
                            reply.get("success") if reply else "None")
                # Send back as if it were an "attach" response so the
                # frontend's DebugClient sees the expected shape
                if reply:
                    reply["command"] = "attach"
                    if "request_seq" in reply:
                        reply["request_seq"] = seq
                    await websocket.send_json(reply)
                continue

            # R Browse mode: dual-channel DAP architecture.
            #
            # When R is paused at a breakpoint (Browse[1]> prompt), its
            # main thread is blocked on stdin readline(). vscDebugger's
            # TCP socket callbacks don't fire because R's event loop is
            # suspended. Two mechanisms work around this:
            #
            # Route A - Flow control (continue/next/step): write the
            #   corresponding R browser command directly to the PTY
            #   stdin. R processes it immediately because it's reading
            #   stdin. Synthesize the DAP response back to the frontend.
            #
            # Route B - State requests (stackTrace/scopes/variables):
            #   send the DAP JSON over TCP, then "nudge" the PTY with
            #   invisible()\n which forces R to evaluate an expression,
            #   unblocking readline() for a moment. During that moment,
            #   vscDebugger's socket hooks fire, process the pending
            #   TCP request, and send the response. R returns to
            #   Browse[1]> cleanly.
            #
            # This is exactly how VS Code's R Debugger extension works.
            # R: all DAP commands (flow control + state requests) go
            # through TCP when R is inside .vsc.listenForDAP(). The
            # re-entry into listenForDAP (triggered by the writeToStdin
            # handler above) ensures the TCP read loop is active.

            # Default: proxy the request
            reply = await transport.send_request(command, args, seq=seq)
            if reply:
                if "request_seq" in reply:
                    reply["request_seq"] = seq
                await websocket.send_json(reply)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("File debug DAP error: %s", e)
        if debug_session.language == "r":
            # R debug: the TCP connection dropped because R exited
            # after Continue. Send a synthetic terminated event so the
            # frontend tears down cleanly, then wait so the browser
            # has time to process any remaining output messages that
            # were already sent before this error.
            try:
                await websocket.send_json({
                    "type": "event",
                    "event": "terminated",
                    "seq": 9999,
                    "body": {},
                })
                await asyncio.sleep(1.5)
            except Exception:
                pass
        try:
            await websocket.close(code=1000, reason="Session ended")
        except Exception:
            pass
    finally:
        try:
            await transport.send_request(
                "disconnect", {"restart": False, "terminateDebuggee": True}, timeout=3
            )
        except Exception:
            pass
        await transport.stop()
        # Stop the session
        session_obj = _sessions.pop(session, None)
        if session_obj:
            await session_obj.stop()
        logger.info("File debug DAP session ended: %s", session)

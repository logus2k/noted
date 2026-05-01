"""LSP Proxy Manager - spawns and manages language server processes.

Each (project_id, env_name) pair gets its own language server process.
The manager relays JSON-RPC messages between WebSocket clients and the
language server's stdio, handling Content-Length framing on the stdio side.
"""

import asyncio
import json
import logging
import os
import signal
import time
from typing import Optional

logger = logging.getLogger(__name__)


class LSPServerProcess:
    """Wraps a language server subprocess with Content-Length stdio framing."""

    def __init__(self, process: asyncio.subprocess.Process, server_type: str):
        self.process = process
        self.server_type = server_type
        self.started_at = time.time()
        self._ws_clients: set = set()
        self._read_task: Optional[asyncio.Task] = None
        self._broadcast_callback = None
        self._initialized = False
        self._init_event = asyncio.Event()  # signaled when initialize response is received
        self._init_result = None      # cached initialize response
        self._pending_init_id = None  # JSON-RPC id of the initialize request
        self._server_notified = False # True after 'initialized' notification sent to server
        self._pending_requests: dict[str, asyncio.Future] = {}  # id -> Future for request/response

    @property
    def alive(self) -> bool:
        return self.process.returncode is None

    def resolve_pending(self, msg_id, result):
        """Resolve a pending request future if one exists for this id."""
        fut = self._pending_requests.pop(str(msg_id), None)
        if fut and not fut.done():
            fut.set_result(result)

    async def request(self, method: str, params: dict, timeout: float = 10.0) -> Optional[dict]:
        """Send a JSON-RPC request and wait for the response."""
        import uuid
        req_id = f"req-{uuid.uuid4().hex[:8]}"
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut
        await self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            return None

    async def send(self, message: dict):
        """Send a JSON-RPC message to the language server via stdio."""
        if not self.alive:
            return
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self.process.stdin.write(header.encode() + body.encode())
        await self.process.stdin.drain()

    async def read_loop(self, on_message):
        """Read JSON-RPC messages from the language server's stdout."""
        reader = self.process.stdout
        try:
            while self.alive:
                # Read headers until blank line
                content_length = None
                while True:
                    header_line = await reader.readline()
                    if not header_line:
                        return  # EOF
                    header = header_line.decode().strip()
                    if not header:
                        break  # Blank line = end of headers
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())

                if content_length is None:
                    continue

                # Read body
                body = await reader.readexactly(content_length)
                try:
                    message = json.loads(body)
                    await on_message(message)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON-RPC from language server")

        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("Language server stdout closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("LSP read loop error: %s", e)

    async def shutdown(self):
        """Gracefully shut down the language server."""
        if not self.alive:
            return
        try:
            # Send LSP shutdown request
            await self.send({"jsonrpc": "2.0", "id": "shutdown", "method": "shutdown", "params": None})
            await asyncio.sleep(0.2)
            # Send exit notification
            await self.send({"jsonrpc": "2.0", "method": "exit", "params": None})
            await asyncio.sleep(0.3)
        except Exception:
            pass
        # Force kill if still alive
        if self.alive:
            try:
                self.process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()


class LSPProxyManager:
    """Manages language server processes for project/env combinations."""

    def __init__(self, env_manager=None):
        # Key: (project_id, env_name, server_type) -> LSPServerProcess
        self._servers: dict[tuple, LSPServerProcess] = {}
        self._env_manager = env_manager
        self._idle_timeout = 300  # 5 minutes

    async def get_or_start(self, project_id: str, env_name: str,
                           server_type: str = "ruff",
                           runtime_id: Optional[str] = None) -> LSPServerProcess:
        """Get an existing server or start a new one.

        runtime_id, when provided, lets the manager look up per-runtime
        environment variables (declared as `kernel_env` in runtime.json)
        and inject them into the LSP subprocess. R uses this to select the
        right R version via R_HOME / LD_LIBRARY_PATH at process spawn time,
        mirroring the Phase 1 kernel dispatch.
        """
        key = (project_id, env_name, server_type)
        server = self._servers.get(key)
        if server and server.alive:
            return server

        # Clean up dead server
        if server:
            del self._servers[key]

        # Build command
        cmd = self._build_command(server_type, env_name)
        cwd = self._project_root(project_id)

        # Resolve per-runtime env vars (R needs R_HOME, LD_LIBRARY_PATH,
        # NOTED_PROJECT_ROOT). For Python and JS this returns None and
        # the subprocess inherits the parent environment unchanged.
        subprocess_env = self._resolve_runtime_env(runtime_id, env_name, cwd)

        # For R envs without an installed languageserver (e.g. R 3.6.3),
        # bail out early with a clear error so the WebSocket router falls
        # back to "kernel-only mode" instead of hanging on a process that
        # will never become responsive.
        if runtime_id and runtime_id.startswith("r/"):
            if not self._r_languageserver_available(runtime_id):
                raise RuntimeError(
                    f"languageserver R package is not installed for {runtime_id}; "
                    f"this R version runs in kernel-only mode (no LSP)."
                )
            # /usr/local/bin/R is a wrapper script that prints
            # "WARNING: ignoring environment value of R_HOME" and forces its
            # own hardcoded R version. To dispatch to the env's R version we
            # must invoke the per-version binary directly. The strategy
            # leaves cmd[0]="R" as a placeholder; substitute it here where
            # we know the runtime_id.
            if cmd and cmd[0] == "R":
                version = runtime_id.split("/", 1)[1]
                cmd[0] = f"/opt/R/{version}/bin/R"

        logger.info("Starting %s language server for %s/%s (cwd=%s, runtime=%s)",
                     server_type, project_id, env_name, cwd, runtime_id)

        # Spawn process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=subprocess_env,
        )

        server = LSPServerProcess(process, server_type)
        self._servers[key] = server

        # Log stderr in background
        asyncio.create_task(self._log_stderr(server, key))

        logger.info("Language server %s started (pid=%d)", server_type, process.pid)
        return server

    def _build_command(self, server_type: str, env_name: str) -> list[str]:
        """Build the command to launch a language server.

        Delegated to the per-language strategy registry. Adding a new
        language means creating a new strategy file and registering it in
        app.managers.lsp.__init__; no changes needed here.
        """
        from app.managers.lsp import build_command_for
        try:
            return build_command_for(server_type)
        except KeyError:
            raise ValueError(f"Unknown server type: {server_type}")

    def _resolve_runtime_env(self, runtime_id: Optional[str],
                              env_name: str,
                              project_root: Optional[str] = None) -> Optional[dict]:
        """Build the subprocess env dict for an LSP launch, merging the
        runtime's `kernel_env` field over `os.environ`. Returns None when
        there is no per-runtime env to inject (Python and JS today).

        The runtime spec's `kernel_env` may use `{env_path}` and
        `{project_root}` placeholders. The project_root argument lets the
        caller pass the same cwd it set on the LSP subprocess so the env
        var matches what the kernel sees in Phase 1 (NOTED_PROJECT_ROOT).
        """
        if not runtime_id or not self._env_manager:
            return None
        # Some EnvironmentManager facades wrap the real registry/env_manager
        # behind a sibling attribute (e.g. VenvManager.env_manager) - peel
        # one layer if needed.
        env_mgr = self._env_manager
        inner = getattr(env_mgr, "env_manager", env_mgr)
        try:
            runtime = inner._registry.get_runtime(runtime_id)
        except Exception:
            return None
        if not runtime or "kernel_env" not in runtime:
            return None
        kernel_env = runtime["kernel_env"]
        if not isinstance(kernel_env, dict) or not kernel_env:
            return None

        env_path = ""
        if env_name:
            try:
                env_path = inner._env_path(runtime_id, env_name)
            except Exception:
                env_path = ""

        merged = os.environ.copy()
        for key, raw in kernel_env.items():
            value = raw
            if env_path:
                value = value.replace("{env_path}", env_path)
            if project_root:
                value = value.replace("{project_root}", project_root)
            merged[key] = value
        # R LSP: expose the per-version system library to renv via its
        # native RENV_CONFIG_EXTERNAL_LIBRARIES hook. This is the renv-
        # blessed mechanism for "let me see one extra library after the
        # project library is set up" - renv appends it to .libPaths()
        # at the end of renv::load(), which keeps env-installed packages
        # first (so completions reflect what the user actually installed)
        # but makes the system library reachable as a fallback.
        #
        # Without this the LSP process exits immediately because
        # languageserver itself - installed system-wide at image-build
        # time, not in any user env's renv library - is invisible after
        # renv::load() narrows .libPaths() to the env library only:
        #     Error in loadNamespace(x) :
        #         there is no package called 'languageserver'
        #
        # Using RENV_CONFIG_EXTERNAL_LIBRARIES (instead of overriding
        # R_PROFILE_USER or skipping init with --no-init-file) means the
        # LSP and the kernel share the exact same noted_rprofile.R, and
        # renv handles the platform-specific subpath resolution itself.
        if runtime_id and runtime_id.startswith("r/"):
            version = runtime_id.split("/", 1)[1]
            sys_lib = f"/opt/R/{version}/lib/R/library"
            if os.path.isdir(sys_lib):
                merged["RENV_CONFIG_EXTERNAL_LIBRARIES"] = sys_lib
        return merged

    def _r_languageserver_available(self, runtime_id: str) -> bool:
        """Cheap filesystem check: does this R version have the
        languageserver package installed under its system library?

        We do not call into R itself to ask - that would add a slow
        process spawn to the LSP startup hot path. Instead we look at
        /opt/R/<version>/lib/R/library/languageserver/DESCRIPTION which
        the Dockerfile creates exactly when install.packages succeeds."""
        # runtime_id format: "r/<version>", e.g. "r/4.0.5"
        parts = runtime_id.split("/", 1)
        if len(parts) != 2 or parts[0] != "r":
            return False
        version = parts[1]
        marker = f"/opt/R/{version}/lib/R/library/languageserver/DESCRIPTION"
        return os.path.isfile(marker)

    def _get_python(self, env_name: str) -> str:
        """Get the Python path for a venv."""
        if self._env_manager and env_name:
            try:
                envs = self._env_manager.list_all_envs()
                for e in envs:
                    if e.get("name") == env_name:
                        return e.get("python_path", "python3")
            except Exception:
                pass
        return "python3"

    def _project_root(self, project_id: str) -> str:
        """Resolve project ID to filesystem path."""
        from app.managers.project_registry import get_registry
        try:
            return get_registry().resolve(project_id)
        except FileNotFoundError:
            return "/app/data"

    async def stop(self, project_id: str, env_name: str,
                   server_type: str = "ruff"):
        """Stop a specific language server."""
        key = (project_id, env_name, server_type)
        server = self._servers.pop(key, None)
        if server:
            await server.shutdown()
            logger.info("Stopped %s for %s/%s", server_type, project_id, env_name)

    async def stop_all(self):
        """Stop all language servers."""
        for key in list(self._servers):
            server = self._servers.pop(key)
            await server.shutdown()

    async def cleanup_idle(self):
        """Stop servers with no active WebSocket clients for > idle_timeout."""
        now = time.time()
        for key in list(self._servers):
            server = self._servers[key]
            if not server._ws_clients and (now - server.started_at) > self._idle_timeout:
                logger.info("Stopping idle server: %s", key)
                await self.stop(*key)

    async def _log_stderr(self, server: LSPServerProcess, key: tuple):
        """Log stderr output from the language server."""
        try:
            while server.alive:
                line = await server.process.stderr.readline()
                if not line:
                    break
                logger.debug("[%s/%s] %s", key[2], key[0], line.decode().rstrip())
        except Exception:
            pass

    def get_status(self) -> list[dict]:
        """Return status of all running language servers."""
        return [
            {
                "project_id": k[0],
                "env_name": k[1],
                "server_type": k[2],
                "alive": s.alive,
                "pid": s.process.pid,
                "clients": len(s._ws_clients),
                "uptime": time.time() - s.started_at,
            }
            for k, s in self._servers.items()
        ]

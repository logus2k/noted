"""JavaScript Debug Adapter Manager.

Launches and manages vscode-js-debug (dapDebugServer.js) processes.
Each JS debug session gets its own adapter process that bridges DAP
commands to the V8 Inspector Protocol on the kernel's --inspect port.

Architecture:
    Frontend (WebSocket) -> dap.py (proxy) -> dapDebugServer.js (adapter)
        -> Chrome DevTools Protocol -> V8 Inspector (Node --inspect)
"""

import asyncio
import logging
import os
import socket

logger = logging.getLogger(__name__)

# Path to the vendored vscode-js-debug DAP server
_JS_DEBUG_SERVER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "vendor", "js-debug", "src", "dapDebugServer.js"
)


def find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class JSDebugAdapter:
    """Manages a single vscode-js-debug adapter process.

    Lifecycle:
        adapter = JSDebugAdapter()
        dap_port = await adapter.start()  # launches dapDebugServer.js
        # ... TCPDebugTransport connects to dap_port ...
        await adapter.stop()              # kills the process
    """

    def __init__(self):
        self._proc = None
        self._dap_port = 0

    @property
    def dap_port(self) -> int:
        """The TCP port where the adapter listens for DAP connections."""
        return self._dap_port

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> int:
        """Start the dapDebugServer.js process on a free port.

        Returns the DAP TCP port the adapter is listening on.
        """
        if not os.path.isfile(_JS_DEBUG_SERVER):
            raise FileNotFoundError(
                f"vscode-js-debug not found at {_JS_DEBUG_SERVER}. "
                "Ensure vendor/js-debug/ is present in the container."
            )

        self._dap_port = find_free_port()

        self._proc = await asyncio.create_subprocess_exec(
            "node", _JS_DEBUG_SERVER, str(self._dap_port), "127.0.0.1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait briefly for the server to start listening
        try:
            await asyncio.wait_for(self._wait_for_ready(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("JS debug adapter did not report ready in 5s, proceeding anyway")

        # Log any stderr output from the adapter for debugging
        asyncio.create_task(self._log_stderr())

        logger.info(
            "JS debug adapter started: pid=%d, dap_port=%d",
            self._proc.pid, self._dap_port,
        )
        return self._dap_port

    async def _wait_for_ready(self):
        """Wait for the adapter to start listening on its port."""
        # dapDebugServer.js prints to stdout when ready.
        # Also poll the port as a fallback.
        for _ in range(50):  # up to 5 seconds
            await asyncio.sleep(0.1)
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", self._dap_port)
                writer.close()
                await writer.wait_closed()
                return
            except (ConnectionRefusedError, OSError):
                continue

    async def _log_stderr(self):
        """Read and log adapter stderr for debugging."""
        try:
            while self._proc and self._proc.returncode is None:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                logger.info("js-debug stderr: %s", line.decode().rstrip())
        except Exception:
            pass

    async def stop(self):
        """Stop the adapter process."""
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
            logger.info("JS debug adapter stopped: pid=%d", self._proc.pid)
        self._proc = None
        self._dap_port = 0

"""DAP Transport Abstraction Layer.

Provides a unified interface for DAP communication across different
debug backends:

- ZMQDebugTransport: Python/ipykernel (DAP over Jupyter control channel)
- TCPDebugTransport: vscode-js-debug and future adapters (DAP over TCP)

The transport is selected by kernel_language in dap.py. The WebSocket
handler calls transport.send_request() regardless of the underlying
protocol, keeping dap.py language-agnostic.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseDebugTransport(ABC):
    """Abstract transport for DAP communication."""

    @abstractmethod
    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        """Send a DAP request and wait for the response."""
        pass

    @abstractmethod
    async def start(self):
        """Start reading from the transport."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop reading and clean up resources."""
        pass

    def set_event_handler(self, handler):
        """Set a callback for DAP events (stopped, terminated, etc.).

        handler is an async callable: async def handler(event_dict)
        """
        self._on_event = handler


class ZMQDebugTransport(BaseDebugTransport):
    """DAP over Jupyter control channel (ipykernel/Python).

    Wraps the existing ControlChannelDispatcher logic. DAP messages
    are encoded as debug_request/debug_reply on the ZMQ control channel.
    """

    def __init__(self, dispatcher):
        """Args:
            dispatcher: ControlChannelDispatcher instance (from dap.py)
        """
        self._dispatcher = dispatcher
        self._on_event = None

    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        return await self._dispatcher.send_request(command, arguments, seq, timeout)

    async def start(self):
        self._dispatcher.start()

    async def stop(self):
        await self._dispatcher.stop()


class TCPDebugTransport(BaseDebugTransport):
    """DAP over raw TCP (vscode-js-debug and future standalone adapters).

    Uses Content-Length framed JSON, the standard DAP wire protocol.
    Connects to a local TCP port where a DAP adapter (e.g. dapDebugServer.js)
    is listening.
    """

    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._reader = None
        self._writer = None
        self._pending = {}  # seq -> asyncio.Future
        self._read_task = None
        self._seq = 1
        self._on_event = None
        self._child_transport = None  # child session for multi-process debugging
        self.enable_child_sessions = True
        self._pending_breakpoints = None  # cached setBreakpoints for child replay

    async def start(self):
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port
        )
        self._read_task = asyncio.create_task(self._read_loop())
        logger.info("TCPDebugTransport connected to %s:%d", self._host, self._port)

    async def stop(self):
        if self._child_transport:
            await self._child_transport.stop()
            self._child_transport = None
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(asyncio.CancelledError())
        self._pending.clear()
        logger.info("TCPDebugTransport disconnected")

    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        # Route execution-related commands to the child session if available.
        # The child session is where user code actually runs.
        if self._child_transport and command in (
            "setBreakpoints", "continue", "next", "stepIn", "stepOut",
            "stackTrace", "scopes", "variables", "evaluate", "pause",
        ):
            return await self._child_transport.send_request(
                command, arguments, seq, timeout
            )

        # If child sessions are enabled but child doesn't exist yet,
        # cache setBreakpoints for replay after the child is created.
        if command == "setBreakpoints" and not self._child_transport \
                and self.enable_child_sessions \
                and not getattr(self, '_is_child', False):
            self._pending_breakpoints = (command, arguments)
            # Send to parent as provisional (adapter returns unverified)
            # AND cache for replay to child later

        msg = {
            "type": "request",
            "command": command,
            "seq": self._seq,
            "arguments": arguments or {},
        }
        self._seq += 1

        fut = asyncio.get_event_loop().create_future()
        self._pending[msg["seq"]] = fut

        logger.debug("TCP DAP send: cmd=%s seq=%s", command, msg["seq"])
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._writer.write(header.encode() + body.encode())
        await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg["seq"], None)
            raise TimeoutError(f"DAP TCP request timed out: {command}")

    async def _read_loop(self):
        """Read Content-Length framed DAP messages from TCP."""
        try:
            while True:
                # Read headers until blank line
                content_length = None
                while True:
                    line = await self._reader.readline()
                    if not line:
                        return  # connection closed
                    header = line.decode().strip()
                    if not header:
                        break  # end of headers
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())

                if content_length is None:
                    continue

                body = await self._reader.readexactly(content_length)
                msg = json.loads(body)

                logger.debug("TCP DAP recv: type=%s cmd=%s",
                             msg.get("type"), msg.get("command", msg.get("event")))

                if msg.get("type") == "response":
                    req_seq = msg.get("request_seq")
                    if req_seq in self._pending:
                        fut = self._pending.pop(req_seq)
                        if not fut.done():
                            fut.set_result(msg)
                elif msg.get("type") == "event":
                    if self._on_event:
                        try:
                            await self._on_event(msg)
                        except Exception as e:
                            logger.warning("Event handler error: %s", e)
                elif msg.get("type") == "request":
                    # Reverse request from the adapter (e.g. startDebugging
                    # when vscode-js-debug detects a child process).
                    # Respond with success so the adapter proceeds.
                    await self._handle_reverse_request(msg)
        except asyncio.IncompleteReadError:
            logger.info("TCPDebugTransport: connection closed by adapter")
        except ConnectionError as e:
            logger.info("TCPDebugTransport: connection error: %s", e)
        except asyncio.CancelledError:
            pass

    async def _handle_reverse_request(self, msg):
        """Handle reverse requests from the adapter (adapter -> client).

        vscode-js-debug sends 'startDebugging' when it detects a child
        process (e.g. NEL's worker). We open a second TCP connection
        to the adapter for the child session, making it the active
        session for breakpoints and execution.
        """
        command = msg.get("command", "")
        seq = msg.get("seq", 0)
        logger.info("TCP DAP reverse request: %s (seq=%d)", command, seq)

        if command == "startDebugging" and self.enable_child_sessions:
            config = msg.get("arguments", {}).get("configuration", {})
            # Spawn a child session on a new TCP connection to the same adapter
            child = TCPDebugTransport(self._host, self._port)
            child._is_child = True
            child.set_event_handler(self._on_event)
            await child.start()

            # Handshake on the child connection
            await child.send_request("initialize", {
                "clientID": "noted",
                "clientName": "noted",
                "adapterID": "js-debug",
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
            })
            await asyncio.sleep(0.1)
            # Attach with the config from startDebugging
            attach_fut = asyncio.ensure_future(
                child.send_request("attach", config, timeout=30)
            )
            await asyncio.sleep(0.2)

            # Store child BEFORE configurationDone so breakpoint
            # replay goes to the child
            self._child_transport = child

            # Replay cached breakpoints on the child session
            if self._pending_breakpoints:
                bp_cmd, bp_args = self._pending_breakpoints
                self._pending_breakpoints = None
                await child.send_request(bp_cmd, bp_args)
                logger.info("TCP DAP replayed breakpoints to child session")

            await child.send_request("configurationDone", {})
            await attach_fut

            logger.info("TCP DAP child session attached for: %s", config.get("name", "?"))

        # Respond to the reverse request
        response = {
            "type": "response",
            "request_seq": seq,
            "command": command,
            "success": True,
            "body": {},
        }
        body = json.dumps(response)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._writer.write(header.encode() + body.encode())
        await self._writer.drain()

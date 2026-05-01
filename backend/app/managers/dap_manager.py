"""DAP Proxy Manager - connects to debugpy in kernel processes.

Manages TCP connections to debugpy and relays DAP messages between
WebSocket clients (browser) and the debugpy debug adapter.

DAP uses Content-Length framed JSON messages over TCP, same as LSP.
"""

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DAPSession:
    """A debug session connected to debugpy in a kernel process."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 session_id: str):
        self.reader = reader
        self.writer = writer
        self.session_id = session_id
        self._ws_client = None  # WebSocket client for this session
        self._read_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._seq = 1  # DAP sequence counter

    @property
    def alive(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def send(self, message: dict):
        """Send a DAP message to debugpy via TCP."""
        if not self.alive:
            return
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self.writer.write(header.encode() + body.encode())
        await self.writer.drain()

    async def read_loop(self, on_message):
        """Read DAP messages from debugpy's TCP stream."""
        try:
            while self.alive:
                # Read headers until blank line
                content_length = None
                while True:
                    header_line = await self.reader.readline()
                    if not header_line:
                        return  # EOF
                    header = header_line.decode().strip()
                    if not header:
                        break
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())

                if content_length is None:
                    continue

                body = await self.reader.readexactly(content_length)
                try:
                    message = json.loads(body)
                    await on_message(message)
                except json.JSONDecodeError:
                    logger.warning("Malformed DAP JSON from debugpy")

        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("debugpy TCP connection closed for %s", self.session_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("DAP read loop error: %s", e)

    async def close(self):
        """Close the TCP connection to debugpy."""
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()

    def next_seq(self) -> int:
        """Get the next DAP sequence number."""
        seq = self._seq
        self._seq += 1
        return seq


def get_cell_tmp_path(kernel_pid: int, cell_code: str) -> str:
    """Compute the temp file path ipykernel uses for a cell's code.

    ipykernel 7+ writes cell code to /tmp/ipykernel_{pid}/{murmur2_hash}.py
    The hash is computed from the raw source code.
    """
    import tempfile

    def murmur2_x86(data, seed):
        m = 0x5BD1E995
        data_bytes = [chr(d) for d in str.encode(data, "utf8")]
        length = len(data_bytes)
        h = seed ^ length
        rounded_end = length & 0xFFFFFFFC
        for i in range(0, rounded_end, 4):
            k = (
                (ord(data_bytes[i]) & 0xFF)
                | ((ord(data_bytes[i + 1]) & 0xFF) << 8)
                | ((ord(data_bytes[i + 2]) & 0xFF) << 16)
                | (ord(data_bytes[i + 3]) << 24)
            )
            k = (k * m) & 0xFFFFFFFF
            k ^= k >> 24
            k = (k * m) & 0xFFFFFFFF
            h = (h * m) & 0xFFFFFFFF
            h ^= k
        val = length & 0x03
        k = 0
        if val == 3:
            k = (ord(data_bytes[rounded_end + 2]) & 0xFF) << 16
        if val in [2, 3]:
            k |= (ord(data_bytes[rounded_end + 1]) & 0xFF) << 8
        if val in [1, 2, 3]:
            k |= ord(data_bytes[rounded_end]) & 0xFF
            h ^= k
            h = (h * m) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * m) & 0xFFFFFFFF
        h ^= h >> 15
        return h

    seed = int.from_bytes(kernel_pid.to_bytes(4, 'big'), 'big')
    name = murmur2_x86(cell_code, seed)
    tmp_dir = tempfile.gettempdir()
    return f"{tmp_dir}/ipykernel_{kernel_pid}/{name}.py"


class DAPProxyManager:
    """Manages debug sessions for kernel processes."""

    def __init__(self):
        # Key: session_id -> DAPSession
        self._sessions: dict[str, DAPSession] = {}

    async def connect(self, session_id: str, debug_port: int) -> DAPSession:
        """Connect to debugpy in a kernel process.

        Args:
            session_id: The kernel session ID
            debug_port: The TCP port debugpy is listening on

        Returns:
            A DAPSession connected to debugpy
        """
        # Close existing session if any
        existing = self._sessions.pop(session_id, None)
        if existing:
            await existing.close()

        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', debug_port)
            session = DAPSession(reader, writer, session_id)
            self._sessions[session_id] = session
            logger.info("DAP connected to debugpy on port %d for %s", debug_port, session_id)
            return session
        except Exception as e:
            logger.error("Failed to connect to debugpy port %d: %s", debug_port, e)
            raise

    def get(self, session_id: str) -> Optional[DAPSession]:
        """Get an existing debug session."""
        return self._sessions.get(session_id)

    async def disconnect(self, session_id: str):
        """Disconnect and clean up a debug session."""
        session = self._sessions.pop(session_id, None)
        if session:
            await session.close()
            logger.info("DAP session closed for %s", session_id)

    async def disconnect_all(self):
        """Close all debug sessions."""
        for sid in list(self._sessions):
            await self.disconnect(sid)

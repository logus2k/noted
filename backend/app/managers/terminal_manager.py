"""
TerminalManager - Manages interactive PTY sessions over Socket.IO.

Each session spawns a process (e.g. bash) in a PTY and relays
stdin/stdout between the browser (via Socket.IO) and the PTY.
"""
import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import termios

logger = logging.getLogger(__name__)


class TerminalSession:
    """A single interactive PTY session."""

    __slots__ = (
        "session_id", "master_fd", "pid", "cols", "rows",
        "_reader_task", "_sio", "_sid",
    )

    def __init__(self, session_id: str, master_fd: int, pid: int,
                 cols: int, rows: int, sio, sid: str):
        self.session_id = session_id
        self.master_fd = master_fd
        self.pid = pid
        self.cols = cols
        self.rows = rows
        self._sio = sio
        self._sid = sid
        self._reader_task: asyncio.Task | None = None

    async def start_reader(self):
        """Read PTY output and emit to the client."""
        loop = asyncio.get_event_loop()
        self._reader_task = asyncio.create_task(self._read_loop(loop))

    async def _read_loop(self, loop: asyncio.AbstractEventLoop):
        try:
            while True:
                data = await loop.run_in_executor(
                    None, self._blocking_read
                )
                if data is None:
                    break
                await self._sio.emit("terminal:output", {
                    "session_id": self.session_id,
                    "data": data,
                }, to=self._sid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Terminal read error [{self.session_id}]: {e}")
        finally:
            await self._sio.emit("terminal:exit", {
                "session_id": self.session_id,
            }, to=self._sid)

    def _blocking_read(self) -> str | None:
        """Blocking read from master_fd. Returns None on EOF/error."""
        try:
            data = os.read(self.master_fd, 4096)
            if not data:
                return None
            return data.decode("utf-8", errors="replace")
        except OSError:
            return None

    def write_silent(self, data: str):
        """Write to the PTY with echo temporarily disabled.

        Used by the R debug flow to inject commands (n, c,
        vscDebugger::.vsc.listenForDAP()) into R's Browse prompt
        without them being echoed to the user's terminal.
        """
        try:
            import termios
            attrs = termios.tcgetattr(self.master_fd)
            saved = list(attrs)
            attrs[3] &= ~termios.ECHO  # disable echo
            termios.tcsetattr(self.master_fd, termios.TCSANOW, attrs)
            os.write(self.master_fd, data.encode("utf-8"))
            attrs[3] = saved[3]  # restore echo
            termios.tcsetattr(self.master_fd, termios.TCSANOW, attrs)
        except (OSError, termios.error) as e:
            # Fallback to normal write if echo control fails
            logger.debug("write_silent fallback: %s", e)
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except OSError:
                pass

    def write(self, data: str):
        """Write user input to the PTY."""
        try:
            os.write(self.master_fd, data.encode("utf-8"))
        except OSError as e:
            logger.warning(f"Terminal write error [{self.session_id}]: {e}")

    def resize(self, cols: int, rows: int):
        """Resize the PTY."""
        self.cols = cols
        self.rows = rows
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError as e:
            logger.warning(f"Terminal resize error [{self.session_id}]: {e}")

    async def kill(self):
        """Terminate the PTY process and clean up."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        try:
            os.kill(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait briefly, then force-kill
        for _ in range(10):
            try:
                pid, _ = os.waitpid(self.pid, os.WNOHANG)
                if pid != 0:
                    break
            except ChildProcessError:
                break
            await asyncio.sleep(0.1)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass

        try:
            os.close(self.master_fd)
        except OSError:
            pass


class TerminalManager:
    """Manages multiple interactive PTY sessions."""

    def __init__(self, sio):
        self._sio = sio
        self._sessions: dict[str, TerminalSession] = {}

    async def create_session(
        self,
        session_id: str,
        sid: str,
        cmd: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cols: int = 120,
        rows: int = 24,
    ) -> TerminalSession:
        """Spawn a process in a new PTY and start relaying I/O."""
        master_fd, slave_fd = pty.openpty()

        # Set initial window size
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        # Build environment
        proc_env = os.environ.copy()
        proc_env["TERM"] = "xterm-256color"
        proc_env["COLUMNS"] = str(cols)
        proc_env["LINES"] = str(rows)
        if env:
            proc_env.update(env)

        pid = os.fork()
        if pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()

            # Set slave as controlling terminal
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            # Redirect stdio to slave PTY
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            if cwd:
                os.chdir(cwd)

            os.execvpe(cmd[0], cmd, proc_env)
            # execvpe never returns

        # Parent process
        os.close(slave_fd)

        session = TerminalSession(
            session_id, master_fd, pid, cols, rows, self._sio, sid
        )
        self._sessions[session_id] = session
        await session.start_reader()

        logger.info(
            f"Terminal session started: {session_id} "
            f"(pid={pid}, cmd={cmd}, cwd={cwd})"
        )
        return session

    def get_session(self, session_id: str) -> TerminalSession | None:
        return self._sessions.get(session_id)

    async def kill_session(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session:
            await session.kill()
            logger.info(f"Terminal session killed: {session_id}")

    async def kill_all(self):
        for session_id in list(self._sessions):
            await self.kill_session(session_id)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

"""Python package manager (pip / uv).

Verbatim extraction of the Python branch that previously lived directly in
EnvironmentManager. Behavior must remain identical so the existing UI flows
(install, remove, stream, cancel) work without changes.
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import AsyncIterator

from .base import BasePackageManager, PmContext

logger = logging.getLogger(__name__)


class PipPackageManager(BasePackageManager):
    """Python package management via pip / uv as declared in runtime.json.

    Reads the per-runtime `package_manager` block:
      - list_cmd: command that emits `pip list --format=json`-style JSON
      - install_cmd: pip install (positional package names appended)
      - uv_install_cmd: uv pip install (preferred when installer == "uv")
      - remove_cmd: pip uninstall -y (positional package names appended)
    """

    language_id = "python"

    async def list_packages(self, ctx: PmContext) -> list[dict]:
        pm = ctx.runtime["package_manager"]
        cmd = ctx.resolve_template(pm["list_cmd"])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to list packages: {stderr.decode()}")
        return json.loads(stdout.decode())

    async def install_packages(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "uv",
    ) -> dict:
        cmd = self._select_install_cmd(ctx, installer)
        proc = await asyncio.create_subprocess_exec(
            *cmd, *packages,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Package install failed:\n{stderr.decode()}\n{stdout.decode()}"
            )
        return {"installed": packages, "output": stdout.decode()}

    async def install_stream(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "uv",
    ) -> AsyncIterator[str]:
        cmd = self._select_install_cmd(ctx, installer)

        # Use a pty so pip thinks it's in a real terminal (enables progress bars)
        import pty
        import struct
        import fcntl
        import termios

        master_fd, slave_fd = pty.openpty()
        # Set terminal width so pip formats progress bars reasonably
        winsize = struct.pack('HHHH', 24, 120, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
        }
        clean_env.update({
            "PYTHONUNBUFFERED": "1",
            "TERM": "xterm-256color",
            "UV_LINK_MODE": "copy",
        })

        proc = await asyncio.create_subprocess_exec(
            *cmd, *packages,
            stdout=slave_fd,
            stderr=slave_fd,
            stdin=subprocess.DEVNULL,
            env=clean_env,
        )
        os.close(slave_fd)

        if ctx.register_proc:
            ctx.register_proc(proc)

        loop = asyncio.get_event_loop()
        try:
            while True:
                try:
                    chunk = await loop.run_in_executor(
                        None, lambda: os.read(master_fd, 4096)
                    )
                    if not chunk:
                        break
                    yield chunk.decode(errors="replace")
                except OSError:
                    break
            await proc.wait()
            if proc.returncode != 0:
                yield f"\n[ERROR] Install exited with code {proc.returncode}\n"
        finally:
            os.close(master_fd)
            if ctx.unregister_proc:
                ctx.unregister_proc(proc)

    async def remove_packages(
        self,
        ctx: PmContext,
        packages: list[str],
    ) -> dict:
        pm = ctx.runtime["package_manager"]
        cmd = ctx.resolve_template(pm["remove_cmd"])
        proc = await asyncio.create_subprocess_exec(
            *cmd, *packages,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to remove packages: {stderr.decode()}")
        return {"removed": packages, "output": stdout.decode()}

    # ── helpers ─────────────────────────────────────────────────────

    def _select_install_cmd(self, ctx: PmContext, installer: str) -> list[str]:
        """Pick uv_install_cmd if installer is 'uv' and the field is present;
        otherwise fall back to install_cmd. Matches the prior EnvironmentManager
        behavior verbatim."""
        pm = ctx.runtime["package_manager"]
        if installer == "uv" and "uv_install_cmd" in pm:
            return ctx.resolve_template(pm["uv_install_cmd"])
        return ctx.resolve_template(pm["install_cmd"])

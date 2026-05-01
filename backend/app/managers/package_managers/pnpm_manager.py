"""JavaScript package manager (pnpm).

Verbatim extraction of the JS branch that previously lived directly in
EnvironmentManager. The notable difference from pip is that pnpm's
`list --json` returns a top-level array with a single object whose
`dependencies` field is a name -> {version, ...} dict. We normalize that
into the standard [{name, version}, ...] shape so the frontend's package
list rendering does not need to know about the pnpm-specific layout.
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import AsyncIterator

from .base import BasePackageManager, PmContext

logger = logging.getLogger(__name__)


class PnpmPackageManager(BasePackageManager):
    """JavaScript / Node package management via pnpm."""

    language_id = "javascript"

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
        raw = json.loads(stdout.decode())

        # pnpm returns [{dependencies: {name: {version}}}] - flatten to [{name, version}]
        packages = []
        deps = raw[0].get("dependencies", {}) if raw else {}
        for pkg_name, pkg_info in deps.items():
            packages.append({
                "name": pkg_name,
                "version": pkg_info.get("version", "?"),
            })
        return packages

    async def install_packages(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "uv",
    ) -> dict:
        pm = ctx.runtime["package_manager"]
        cmd = ctx.resolve_template(pm["install_cmd"])
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
        pm = ctx.runtime["package_manager"]
        cmd = ctx.resolve_template(pm["install_cmd"])

        import pty
        import struct
        import fcntl
        import termios

        master_fd, slave_fd = pty.openpty()
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

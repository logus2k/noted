"""R package manager via renv.

Installs R packages using the per-env Rscript launcher which sets up
R_HOME, RENV_PATHS_*, and RENV_CONFIG_EXTERNAL_LIBRARIES so renv
installs into the correct env library. Package listing reads the
renv.lock file directly.
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator

from .base import BasePackageManager, PmContext

logger = logging.getLogger(__name__)


class RenvPackageManager(BasePackageManager):
    language_id = "r"

    def _rscript_bin(self, ctx: PmContext) -> str:
        launcher = os.path.join(ctx.env_path, "bin", "Rscript")
        if os.path.isfile(launcher):
            return launcher
        version = ctx.runtime.get("version", "")
        return f"/opt/R/{version}/bin/Rscript" if version else "Rscript"

    async def list_packages(self, ctx: PmContext) -> list[dict]:
        # Read installed packages from the renv library. renv uses
        # symlinks into a global cache, so we can't rely on os.walk
        # (broken symlinks are silently skipped). Instead we find the
        # leaf package directory (the one containing the actual package
        # dirs or symlinks) and list entries, reading DESCRIPTION from
        # each valid one.
        lib_root = os.path.join(ctx.env_path, "renv", "library")
        if not os.path.isdir(lib_root):
            return []
        # Find the leaf directory containing package dirs/symlinks.
        # Walk real dirs only until we find one that contains entries
        # with DESCRIPTION files (or symlinks to dirs with them).
        pkg_dirs = []
        for dirpath, dirnames, _ in os.walk(lib_root):
            # Check if any child is a package (has DESCRIPTION or is
            # a symlink to a dir that would have one)
            entries = []
            for name in os.listdir(dirpath):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or os.path.isdir(full):
                    entries.append((name, full))
            if entries:
                # If the first real dir entry has a DESCRIPTION or is
                # a symlink, we're at the package level
                for name, full in entries:
                    desc = os.path.join(full, "DESCRIPTION")
                    if os.path.isfile(desc):
                        pkg_dirs = entries
                        break
                    # Broken symlink — still counts as a package entry
                    if os.path.islink(full) and not os.path.exists(full):
                        pkg_dirs = entries
                        break
                if pkg_dirs:
                    break
        packages = []
        for name, full in pkg_dirs:
            desc = os.path.join(full, "DESCRIPTION")
            version = ""
            valid = False
            if os.path.isfile(desc):
                valid = True
                try:
                    with open(desc) as f:
                        for line in f:
                            if line.startswith("Version:"):
                                version = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass
            elif os.path.islink(full):
                # Broken symlink — cache was cleared. Show name only.
                valid = True
            if valid:
                packages.append({"name": name, "version": version})
        return sorted(packages, key=lambda p: p["name"].lower())

    async def install_packages(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "renv",
    ) -> dict:
        result = {"installed": [], "failed": []}
        for pkg in packages:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._rscript_bin(ctx), "-e",
                    f"renv::install('{pkg}')",
                    cwd=ctx.env_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                if proc.returncode == 0:
                    result["installed"].append(pkg)
                else:
                    result["failed"].append({"name": pkg, "error": stderr.decode()[-200:]})
            except Exception as e:
                result["failed"].append({"name": pkg, "error": str(e)})
        return result

    async def install_stream(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "renv",
    ) -> AsyncIterator[str]:
        pkg_list = ", ".join(f"'{p}'" for p in packages)
        r_code = f"renv::install(c({pkg_list}))"
        proc = await asyncio.create_subprocess_exec(
            self._rscript_bin(ctx), "-e", r_code,
            cwd=ctx.env_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode(errors="replace")
        await proc.wait()
        if proc.returncode != 0:
            yield f"\n[renv] Install exited with code {proc.returncode}\n"
        else:
            # Update the lockfile so list_packages reflects the new state
            snap = await asyncio.create_subprocess_exec(
                self._rscript_bin(ctx), "-e",
                "renv::snapshot(prompt=FALSE)",
                cwd=ctx.env_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await snap.wait()
            yield "\n[renv] Install completed successfully\n"

    async def remove_packages(
        self,
        ctx: PmContext,
        packages: list[str],
    ) -> dict:
        result = {"removed": [], "failed": []}
        for pkg in packages:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._rscript_bin(ctx), "-e",
                    f"renv::remove('{pkg}')",
                    cwd=ctx.env_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)
                if proc.returncode == 0:
                    result["removed"].append(pkg)
                else:
                    result["failed"].append(pkg)
            except Exception:
                result["failed"].append(pkg)
        return result

"""Subprocess executor for user tools.

Phase A.4: each tool invocation spawns a fresh subprocess inside the
tool's own venv (Python) or via the bundled Node runtime (JavaScript).
JSON arguments are passed on stdin; the tool writes its JSON result to
stdout. Anything on stderr is captured for the audit log + the MCP
error payload on non-zero exit.

Resource guards:
- Wall-clock timeout (default 60s, configurable via _meta.limits.timeout_s).
- Address-space cap (default 512MB, via RLIMIT_AS in a preexec hook).
- Process cap (32, prevents fork bombs).
- Read-only network access NOT enforced here — that's deferred to V2's
  per-tool egress allow-list (see plan deferred list).

Crash containment: subprocess crashes never propagate. The MCP handler
turns them into structured errors and the noted-tools server stays up.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import resource
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import venv_manager
from .registry import ToolEntry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60
DEFAULT_MEM_BYTES = 512 * 1024 * 1024
DEFAULT_NPROC = 32


@dataclass
class ExecResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    elapsed_s: float
    timed_out: bool = False
    oom_killed: bool = False


def _make_preexec(mem_bytes: int, nproc: int):
    def _apply() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        # Detach from parent's process group so a kill doesn't ricochet.
        os.setsid()
    return _apply


def _limits_from_meta(meta: dict[str, Any]) -> tuple[int, int, int]:
    limits = meta.get("limits") or {}
    timeout_s = int(limits.get("timeout_s") or DEFAULT_TIMEOUT_S)
    mem_bytes = int(limits.get("memory_mb") or 512) * 1024 * 1024
    nproc = int(limits.get("max_processes") or DEFAULT_NPROC)
    return timeout_s, mem_bytes, nproc


async def execute(entry: ToolEntry, arguments: dict[str, Any]) -> ExecResult:
    """Spawn the tool subprocess. Never raises for tool-level failures —
    returns a structured ExecResult instead. Raises only on infrastructure
    errors (venv build failure, missing executable, etc.).
    """
    tool_dir = Path(entry.tool_dir)
    timeout_s, mem_bytes, nproc = _limits_from_meta(entry.meta)

    # Build venv / node_modules lazily. Blocking; offload to thread.
    if entry.language == "python":
        interpreter = await asyncio.to_thread(venv_manager.ensure_python_venv, tool_dir)
        cmd = [str(interpreter), "tool.py"]
    elif entry.language == "javascript":
        await asyncio.to_thread(venv_manager.ensure_node_modules, tool_dir)
        cmd = ["node", "tool.js"]
    else:
        raise RuntimeError(f"unsupported language: {entry.language}")

    payload = json.dumps(arguments).encode("utf-8")
    loop = asyncio.get_running_loop()
    started = loop.time()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tool_dir),
        env={
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(tool_dir),
            "TOOL_NAME": entry.name,
            "TOOL_DIR": str(tool_dir),
            "ACTOR_ID": "system",
        },
        preexec_fn=_make_preexec(mem_bytes, nproc),
    )

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=payload),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        except asyncio.TimeoutError:
            stdout_b, stderr_b = b"", b""

    elapsed = loop.time() - started
    exit_code = proc.returncode if proc.returncode is not None else -1
    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""

    # OOM detection heuristic: RLIMIT_AS makes Python allocations raise
    # MemoryError; the resulting traceback ends up on stderr with exit 1.
    # A more reliable signal would be cgroup memory.events.
    oom_killed = (
        not timed_out
        and exit_code != 0
        and ("MemoryError" in stderr or "Cannot allocate memory" in stderr)
    )

    ok = (not timed_out) and exit_code == 0

    if timed_out:
        logger.warning("tool %s timed out after %ds", entry.name, timeout_s)
    elif not ok:
        logger.warning("tool %s exit=%d stderr=%s", entry.name, exit_code, stderr[:500])
    else:
        logger.info("tool %s ok (%.2fs)", entry.name, elapsed)

    return ExecResult(
        ok=ok,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        elapsed_s=elapsed,
        timed_out=timed_out,
        oom_killed=oom_killed,
    )

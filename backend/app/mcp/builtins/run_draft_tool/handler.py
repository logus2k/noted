"""`run_draft_tool` MCP tool handler.

Calls noted-tools' `POST /admin/run-draft/<tool_name>` endpoint, which
builds/reuses the draft tool's venv and runs `python tool.py` with the
given args as stdin JSON. Returns a readable summary (exit code, stdout,
stderr) so the tool_builder agent can analyze the result and decide
whether to revise.

This is the 'run it' half of the agentic build loop. The verdict text
is deliberately plain so the model reads it directly.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_NOTED_TOOLS_URL = os.environ.get("NOTED_TOOLS_URL", "http://noted-tools:7702")


async def handler(
    args: dict,
    managers: dict | None = None,
    ctx: dict | None = None,
) -> str:
    tool_name = (args.get("tool_name") or "").strip()
    sample_args = args.get("args") or {}

    if not tool_name:
        return "Error: 'tool_name' is required."
    if not isinstance(sample_args, dict):
        return "Error: 'args' must be an object (it is passed to the tool as stdin JSON)."

    url = f"{_NOTED_TOOLS_URL}/admin/run-draft/{tool_name}"
    timeout = httpx.Timeout(connect=5.0, read=90.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=sample_args)
    except httpx.HTTPError as e:
        return f"Error: could not reach noted-tools to run the draft: {type(e).__name__}: {e}"

    if resp.status_code == 404:
        return (
            f"Error: draft {tool_name!r} not found on disk. "
            "Call write_tool_files first (it must write at least tool.py)."
        )
    if resp.status_code != 200:
        return f"Error: run-draft returned HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        v = resp.json()
    except ValueError:
        return f"Error: run-draft returned non-JSON: {resp.text[:300]}"

    exit_code = v.get("exit_code")
    stdout = v.get("stdout") or ""
    stderr = v.get("stderr") or ""
    timed_out = v.get("timed_out")

    verdict = "PASS" if v.get("ok") else "FAIL"
    parts = [
        f"run-draft {tool_name}: {verdict} (exit_code={exit_code}"
        + (", timed_out=true" if timed_out else "") + ")",
        f"--- stdout ---\n{stdout if stdout else '(empty)'}",
        f"--- stderr ---\n{stderr if stderr else '(empty)'}",
    ]
    if v.get("ok") and stdout:
        # Surface whether stdout is valid JSON - the contract is one JSON
        # document on stdout, so this is a direct signal for the builder.
        try:
            json.loads(stdout)
            parts.append("stdout parsed as JSON: yes")
        except ValueError:
            parts.append(
                "stdout parsed as JSON: NO - the tool must emit exactly one "
                "JSON document on stdout and nothing else."
            )
    return "\n".join(parts)

"""`write_tool_files` MCP tool handler.

Writes a tool-under-construction's files to
`data/tenants/<tenant>/user_tools/<tool_name>/`. Part of the agentic
tool_builder loop: the builder agent calls this to lay down (or revise)
tool.py + requirements.txt + tool.json, then calls run_draft_tool to
exercise them.

The directory is chowned to noted-tools' runtime UID:GID (1000:1000)
so noted-tools can build a venv inside it - same reason publish_tool
chowns. Best-effort: if the workflow process isn't root, the chown is
skipped silently (host-test path).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# Filenames must be plain - letters, digits, dot, underscore, hyphen.
# No slashes, no spaces, no token-artifact junk.
_FNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_NOTED_TOOLS_UID = 1000
_NOTED_TOOLS_GID = 1000


def _chown_tree(path: Path) -> None:
    try:
        os.chown(path, _NOTED_TOOLS_UID, _NOTED_TOOLS_GID)
        for child in path.rglob("*"):
            try:
                os.chown(child, _NOTED_TOOLS_UID, _NOTED_TOOLS_GID)
            except OSError:
                pass
    except OSError as e:
        logger.warning("write_tool_files: chown skipped for %s: %s", path, e)


async def handler(
    args: dict,
    managers: dict | None = None,
    ctx: dict | None = None,
) -> str:
    tool_name = (args.get("tool_name") or "").strip()
    files = args.get("files")

    if not _NAME_RE.match(tool_name):
        return (
            f"Error: invalid tool_name {tool_name!r}: must be snake_case "
            "(lowercase, digits, underscores; starts with a letter)."
        )
    # `files` is a list of {name, content} objects. This shape keeps the
    # dict keys (`name`, `content`) as plain identifiers and the filename
    # as a string VALUE - which is in-distribution for Gemma's tool-call
    # format. A {filename: content} dict put filenames in key position,
    # which Gemma wrapped in `<|"|>` string-delimiter tokens (off-spec;
    # Google's reference parser keys are bare `\w+`).
    if not isinstance(files, list) or not files:
        return (
            "Error: 'files' must be a non-empty list of objects, each "
            '{"name": "<filename>", "content": "<file text>"}.'
        )

    # Validate every entry - plain filenames only, no path traversal.
    # Hard-reject anything else so the builder gets a clear retry signal
    # instead of a garbage-named file silently landing on disk. A repeated
    # name is last-wins (later entry overwrites the earlier one).
    cleaned: dict[str, str] = {}
    for i, entry in enumerate(files):
        if not isinstance(entry, dict):
            return f"Error: files[{i}] must be an object with 'name' and 'content'."
        fname = entry.get("name")
        content = entry.get("content")
        if not isinstance(fname, str) or not _FNAME_RE.match(fname) or ".." in fname:
            return (
                f"Error: invalid filename {fname!r} in files[{i}]. "
                "Use plain filenames only - tool.py, requirements.txt, "
                "tool.json - letters/digits/dot/underscore/hyphen."
            )
        if not isinstance(content, str):
            return f"Error: content for {fname!r} (files[{i}]) must be a string."
        cleaned[fname] = content
    files = cleaned

    tenant_id = "default"
    if isinstance(ctx, dict) and ctx.get("tenant_id"):
        tenant_id = str(ctx["tenant_id"])

    tool_dir = Path(DATA_DIR) / "tenants" / tenant_id / "user_tools" / tool_name
    try:
        tool_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for fname, content in files.items():
            (tool_dir / fname).write_text(content, encoding="utf-8")
            written.append(fname)
        _chown_tree(tool_dir)
    except OSError as e:
        logger.warning("write_tool_files %s failed: %s", tool_name, e)
        return f"Error: failed to write files for {tool_name}: {e}"

    logger.info("write_tool_files: %s wrote %s", tool_name, written)
    return (
        f"Wrote {len(written)} file(s) to user_tools/{tool_name}/: "
        f"{', '.join(sorted(written))}. Next: call run_draft_tool to execute it."
    )

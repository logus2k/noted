"""Per-tool folder convention for built-in MCP tools (adopted 2026-05-12).

Each tool lives in its own subdirectory:

    builtins/
      <tool_name>/
        tool.json     # name + description + inputSchema + tier (read/write)
        handler.py    # async def handler(args, managers=None, ctx=None) -> str

Import-time discovery: this `__init__.py` walks the immediate subdirs,
reads each `tool.json`, imports each `handler.py`, and builds two
exports:

  BUILTIN_TOOLS    list[types.Tool]
  BUILTIN_HANDLERS dict[name, callable]

Both are consumed by `app.mcp.tools` (schema list) and
`app.managers.llm_tools.execute_tool` (dispatch). Each tool ships its
own contract — adding a new built-in is a drop-in folder, no editing of
the shared monolithic files.

Handler signature is `async def handler(args, managers=None, ctx=None)
-> str` so per-tool code can opt into the managers / ctx context when it
needs them without forcing every tool to thread them. Callers always
pass all three.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

import mcp.types as types

logger = logging.getLogger(__name__)

# Handler signature. `managers` and `ctx` are optional so simple tools
# can declare `async def handler(args)` and the dispatcher's adapter
# still routes correctly.
BuiltinHandler = Callable[..., Awaitable[str]]


def _load_builtins() -> tuple[list[types.Tool], dict[str, BuiltinHandler], dict[str, str]]:
    """Walk subdirectories of this package, load tool.json + handler.py
    from each, and return the registry. Skips:
      - private dirs (leading underscore)
      - dirs missing tool.json or handler.py
    Logs (and continues) on per-tool errors so one broken built-in
    doesn't prevent the rest from registering.
    """
    here = Path(__file__).resolve().parent
    tools: list[types.Tool] = []
    handlers: dict[str, BuiltinHandler] = {}
    tiers: dict[str, str] = {}

    for sub in sorted(here.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name == "__pycache__":
            continue
        manifest_path = sub / "tool.json"
        handler_path = sub / "handler.py"
        if not (manifest_path.is_file() and handler_path.is_file()):
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            logger.error("builtins/%s: tool.json invalid: %s", sub.name, e)
            continue

        name = manifest.get("name")
        if not name or name != sub.name:
            logger.error(
                "builtins/%s: tool.json 'name' (%r) must match folder name",
                sub.name, name,
            )
            continue
        description = manifest.get("description") or ""
        input_schema = manifest.get("inputSchema") or manifest.get("input_schema") or {}
        tier = (manifest.get("tier") or "read").strip().lower()
        if tier not in ("read", "write"):
            logger.error(
                "builtins/%s: tier must be 'read' or 'write', got %r",
                sub.name, tier,
            )
            continue

        module_name = f"{__name__}.{sub.name}.handler"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("builtins/%s: failed to import handler.py", sub.name)
            continue
        handler = getattr(module, "handler", None)
        if not callable(handler):
            logger.error(
                "builtins/%s: handler.py must define `async def handler(...)`",
                sub.name,
            )
            continue

        tools.append(types.Tool(
            name=name,
            description=description,
            inputSchema=input_schema,
        ))
        handlers[name] = handler
        tiers[name] = tier
        logger.info("builtins: loaded %r (tier=%s) from %s", name, tier, sub.name)

    return tools, handlers, tiers


BUILTIN_TOOLS, BUILTIN_HANDLERS, BUILTIN_TIERS = _load_builtins()


__all__ = ["BUILTIN_TOOLS", "BUILTIN_HANDLERS", "BUILTIN_TIERS"]

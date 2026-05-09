"""Federation client for the noted-tools sidecar.

Phase A.5: noted backend pulls the user-tool list from `noted-tools` over
its MCP HTTP transport, caches it, and serves dispatches by forwarding
`tools/call` to the same endpoint.

Why poll instead of push? Pushing would require Socket.IO between the
two services (extra plumbing, ordering concerns). A 30s poll gives
acceptable latency for a single-user setup. Phase C's `create_tool`
orchestrator can call `force_refresh()` directly after publishing a new
tool so the LLM sees it on the very next chat turn (sub-second instead
of 30s).

Failure mode: if noted-tools is down or returns an error, the cached
list stays as-is (last good snapshot). Calls to user tools while down
return a clear error string. Native tools are unaffected.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
import mcp.types as types

logger = logging.getLogger(__name__)

NOTED_TOOLS_URL = os.environ.get("NOTED_TOOLS_URL", "http://noted-tools:7702")
REFRESH_INTERVAL_S = float(os.environ.get("NOTED_TOOLS_REFRESH_S", "30"))
CALL_TIMEOUT_S = float(os.environ.get("NOTED_TOOLS_CALL_TIMEOUT_S", "120"))


class UserToolsClient:
    def __init__(self, base_url: str = NOTED_TOOLS_URL) -> None:
        self._base = base_url.rstrip("/")
        self._tools: list[types.Tool] = []
        self._meta_by_name: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_refresh_ok = False
        self._last_error: str | None = None

    async def _post_mcp(self, method: str, params: dict[str, Any] | None, timeout: float) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base}/mcp/",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh(self) -> bool:
        try:
            data = await self._post_mcp("tools/list", {}, timeout=10.0)
        except Exception as e:
            self._last_refresh_ok = False
            self._last_error = f"{type(e).__name__}: {e}"
            logger.warning("user tools refresh failed: %s", self._last_error)
            return False

        if "result" not in data or "tools" not in (data.get("result") or {}):
            self._last_refresh_ok = False
            self._last_error = f"unexpected payload: {data}"
            return False

        new_tools: list[types.Tool] = []
        new_meta: dict[str, dict[str, Any]] = {}
        for raw in data["result"]["tools"]:
            try:
                name = raw["name"]
                tool = types.Tool(
                    name=name,
                    description=raw.get("description") or "",
                    inputSchema=raw.get("inputSchema") or {"type": "object"},
                )
                new_tools.append(tool)
                if isinstance(raw.get("_meta"), dict):
                    new_meta[name] = raw["_meta"]
            except (KeyError, TypeError) as e:
                logger.warning("malformed user tool %r: %s", raw, e)

        new_tools.sort(key=lambda t: t.name)
        self._tools = new_tools
        self._meta_by_name = new_meta
        self._last_refresh_ok = True
        self._last_error = None
        return True

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            data = await self._post_mcp(
                "tools/call",
                {"name": name, "arguments": arguments or {}},
                timeout=CALL_TIMEOUT_S,
            )
        except httpx.RequestError as e:
            return f"Error: noted-tools unreachable ({type(e).__name__}: {e})"
        except httpx.HTTPStatusError as e:
            return f"Error: noted-tools HTTP {e.response.status_code}"

        result = data.get("result") or {}
        is_error = bool(result.get("isError"))
        content = result.get("content") or []
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n".join(text_parts).strip() or "(no output)"
        if is_error:
            return f"Error: {text}"
        return text

    def get_user_tools(self) -> list[types.Tool]:
        return list(self._tools)

    def has_tool(self, name: str) -> bool:
        return any(t.name == name for t in self._tools)

    def get_meta(self, name: str) -> dict[str, Any]:
        return dict(self._meta_by_name.get(name) or {})

    def status(self) -> dict[str, Any]:
        return {
            "base_url": self._base,
            "tool_count": len(self._tools),
            "last_refresh_ok": self._last_refresh_ok,
            "last_error": self._last_error,
        }

    async def _refresh_loop(self) -> None:
        try:
            await self.refresh()
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=REFRESH_INTERVAL_S)
                except asyncio.TimeoutError:
                    pass
                if self._stop.is_set():
                    break
                await self.refresh()
        except asyncio.CancelledError:
            raise

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._refresh_loop())
            logger.info("user-tools federation client started (poll=%.0fs)", REFRESH_INTERVAL_S)

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


_client: UserToolsClient | None = None


def get_user_tools_client() -> UserToolsClient:
    global _client
    if _client is None:
        _client = UserToolsClient()
    return _client

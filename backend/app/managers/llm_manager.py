"""LLM Manager - async client to agent_server's OpenAI-compatible API."""

import os
import json
import logging
import aiohttp

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://agent_server:7701")
LLM_AGENT_NAME = os.environ.get("LLM_AGENT_NAME", "noted")

# Context window for the local Gemma engine. agent_server doesn't surface
# the model's n_ctx through /v1/models, so we declare it here. Env-overridable
# so a swap to a different local model can update this without code changes.
LOCAL_CONTEXT_WINDOW = int(os.environ.get("LOCAL_LLM_CONTEXT_WINDOW", "131072"))


class LLMManager:
    """Async client for agent_server's /v1/chat/completions endpoint."""

    def __init__(self, base_url: str = LLM_BASE_URL, agent_name: str = LLM_AGENT_NAME):
        self.base_url = base_url
        self.agent_name = agent_name
        self._session: aiohttp.ClientSession | None = None
        self.context_window = LOCAL_CONTEXT_WINDOW

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Streaming chat ────────────────────────────────────────────

    async def chat_stream(self, messages: list[dict], temperature: float = 0.5,
                          max_tokens: int = 2048,
                          tools: list[dict] | None = None,
                          extra_body: dict | None = None):
        """POST /v1/chat/completions with stream=True.

        Yields parsed SSE chunk dicts as they arrive. `extra_body` is merged
        into the request payload after the standard fields, letting callers
        pass through Gemma-specific extras like
        `{"chat_template_kwargs": {"enable_thinking": False}}` without
        widening the signature for every new template flag.
        """
        session = await self._get_session()
        payload = {
            "model": self.agent_name,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            # Stop at Gemma 4's tool call closing token.
            # WHY KEPT (2026-04-22): we tried removing this to enable multi-
            # tool-call emission per the Analytics Vidhya Gemma 4 article, and
            # it lifted batch_update_cells::S2 + insert_cell::S4 - but it also
            # caused Gemma to continue past the tool call into orphan token
            # sequences (e.g. `thought ...<channel|>` without the opening
            # `<|channel>`) that broke the thinking-block UI rendering and
            # leaked stray tokens into chat. The stop is the cleanest line of
            # defense; we accept that mixed insert+update and 3-of-same-op
            # cases stay escalated. gemma_tool_parser strips hallucinated
            # <|tool_response>/tool_output blocks downstream as a safety net.
            # NOTE: no stop sequence. The defensive truncation in
            # routers/llm.py::_prepare_text_for_frontend strips anything
            # after the last <tool_call|> so speculative/post-call text
            # cannot leak into the UI regardless of what the model emits.
            # Multi-tool-call in a single response is supported per Gemma 4's
            # documented design; noted's backend batches multi-write-call
            # turns into one approval.
        if extra_body:
            payload.update(extra_body)
        async with session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    yield json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed SSE chunk: %s", data_str[:120])

    # ── Non-streaming chat ────────────────────────────────────────

    async def chat(self, messages: list[dict], temperature: float = 0.5,
                   max_tokens: int = 2048,
                   tools: list[dict] | None = None) -> dict:
        """POST /v1/chat/completions without streaming. Returns full response."""
        session = await self._get_session()
        payload = {
            "model": self.agent_name,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            # Stop at Gemma 4's tool call closing token. See chat_stream() above for rationale.
            # NOTE: no stop sequence. The defensive truncation in
            # routers/llm.py::_prepare_text_for_frontend strips anything
            # after the last <tool_call|> so speculative/post-call text
            # cannot leak into the UI regardless of what the model emits.
            # Multi-tool-call in a single response is supported per Gemma 4's
            # documented design; noted's backend batches multi-write-call
            # turns into one approval.
        async with session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ── Code completion (Phase E) ─────────────────────────────────

    async def complete(self, prompt: str, max_tokens: int = 256) -> dict:
        """Code completion with /no_think for fast direct output."""
        messages = [
            {"role": "system", "content": "Complete the following code. Output only code, no explanation. /no_think"},
            {"role": "user", "content": prompt},
        ]
        return await self.chat(messages, temperature=0.7, max_tokens=max_tokens)

    # ── Health check ──────────────────────────────────────────────

    async def health(self) -> dict:
        """GET /v1/models - verify agent_server is reachable."""
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/v1/models") as resp:
                resp.raise_for_status()
                data = await resp.json()
                model_list = data.get("data", [])
                models = [m["id"] for m in model_list]
                # First model is the base engine; use display_name if available
                active_model = (model_list[0].get("display_name") or models[0]) if model_list else "unknown"
                return {"status": "ok", "models": models, "active_model": active_model}
        except Exception as e:
            return {"status": "error", "message": str(e)}

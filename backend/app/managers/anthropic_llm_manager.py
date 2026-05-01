"""Anthropic LLM Manager - calls the Anthropic Messages API with native tool use.

Implements the same interface as LLMManager (chat_stream, chat, complete, health)
so it can be used as a drop-in backend via LLMRouter.

Streaming translation:
  Anthropic content_block_delta (thinking_delta) -> <think>...</think> tokens
  Anthropic content_block_delta (text_delta)     -> plain tokens
  Anthropic content_block (tool_use)             -> {"tool_call": {...}} events
Both text chunks are emitted as: {"choices": [{"delta": {"content": "..."}}]}
Tool calls are emitted as:      {"tool_call": {"id": "...", "name": "...", "args": {...}}}
"""

import os
import json
import logging
import aiohttp

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI assistant embedded in noted.

The WORKSPACE CONTEXT block (sent on every turn) lists the ACTIVE KNOWLEDGE BASES
(Domains) you currently know about, plus any ACTIVE SKILLS pulled in by the
context conditions. Behavior rules - tool-call discipline, voice format,
citation conventions, fairness, honesty - live in those skills. The ACTIVE
SKILLS section is authoritative; follow its instructions for the current turn.

If a Domain provides skills or tools relevant to the user's question, use them.
If the question falls outside any active Domain's coverage, say so explicitly
rather than guessing or fabricating."""

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

ANTHROPIC_MODELS = [
    {"id": "claude-sonnet-4-6",          "display_name": "Claude Sonnet 4.6", "context_window": 200000},
    {"id": "claude-opus-4-6",            "display_name": "Claude Opus 4.6",   "context_window": 200000},
    {"id": "claude-haiku-4-5-20251001",  "display_name": "Claude Haiku 4.5",  "context_window": 200000},
]

_MODEL_CONTEXT = {m["id"]: m["context_window"] for m in ANTHROPIC_MODELS}

THINKING_BUDGET_TOKENS = 8000


class AnthropicLLMManager:
    """Async client for the Anthropic Messages API with native tool use."""

    def __init__(self, api_key: str = ANTHROPIC_API_KEY):
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # -- Think directive stripping -----------------------------------------

    @staticmethod
    def _strip_think_directive(messages: list[dict]) -> tuple[list[dict], bool]:
        """Strip /think or /no_think from the last user message.

        Returns (cleaned_messages, think_enabled).
        Defaults to think_enabled=False when no directive is found.
        """
        think_enabled = False
        cleaned = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and i == len(messages) - 1:
                content = msg.get("content", "")
                if isinstance(content, str):
                    if content.endswith(" /no_think"):
                        content = content[: -len(" /no_think")].rstrip()
                        think_enabled = False
                    elif content.endswith(" /think"):
                        content = content[: -len(" /think")].rstrip()
                        think_enabled = True
                    cleaned.append({**msg, "content": content})
                else:
                    cleaned.append(msg)
            else:
                cleaned.append(msg)
        return cleaned, think_enabled

    # -- Message normalisation ---------------------------------------------

    @staticmethod
    def _normalize_messages(messages: list[dict]) -> list[dict]:
        """Merge consecutive same-role messages.

        Anthropic requires strict user/assistant alternation.
        Only merges messages where both have string content (not content arrays
        used for tool_result blocks).
        """
        if not messages:
            return messages
        normalized = [{**messages[0]}]
        for msg in messages[1:]:
            prev = normalized[-1]
            if (msg.get("role") == prev.get("role")
                    and isinstance(msg.get("content"), str)
                    and isinstance(prev.get("content"), str)):
                normalized[-1] = {
                    **prev,
                    "content": prev["content"] + "\n\n" + msg["content"],
                }
            else:
                normalized.append({**msg})
        return normalized

    # -- Request helpers ---------------------------------------------------

    def _build_payload(self, messages: list[dict], model: str,
                       max_tokens: int, temperature: float,
                       think_enabled: bool, stream: bool,
                       system: str | None = None,
                       tools: list[dict] | None = None) -> dict:
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system if system is not None else SYSTEM_PROMPT,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if think_enabled:
            effective_max = max(max_tokens, THINKING_BUDGET_TOKENS + 1024)
            payload["max_tokens"] = effective_max
            payload["thinking"] = {"type": "enabled", "budget_tokens": THINKING_BUDGET_TOKENS}
            payload["temperature"] = 1.0
        else:
            payload["temperature"] = temperature
        return payload

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    # -- Streaming chat ----------------------------------------------------

    async def chat_stream(self, messages: list[dict], temperature: float = 0.5,
                          max_tokens: int = 2048, model: str | None = None,
                          system: str | None = None,
                          tools: list[dict] | None = None):
        """Stream a chat response, yielding chunk dicts.

        Yields three kinds of events:
          {"choices": [{"delta": {"content": "..."}}]}  - text tokens (incl thinking)
          {"tool_call": {"id": "...", "name": "...", "args": {...}}}  - completed tool call
          {"usage_tokens": {...}}  - token usage at end of stream

        Args:
            system: Optional system prompt override.
            tools: Optional list of tools in Anthropic format.
        """
        model = model or ANTHROPIC_MODELS[0]["id"]
        messages, think_enabled = self._strip_think_directive(messages)
        messages = self._normalize_messages(messages)
        payload = self._build_payload(messages, model, max_tokens, temperature,
                                      think_enabled, stream=True, system=system,
                                      tools=tools)

        session = await self._get_session()
        async with session.post(ANTHROPIC_API_URL, json=payload,
                                headers=self._headers()) as resp:
            if not resp.ok:
                body = await resp.text()
                logger.error("Anthropic API error %s: %s", resp.status, body)
            resp.raise_for_status()

            current_block_type: str | None = None
            current_block_id: str | None = None
            current_tool_name: str | None = None
            current_tool_json: str = ""
            thinking_open = False
            line_buffer = ""
            input_tokens = 0
            output_tokens = 0

            async for chunk in resp.content:
                line_buffer += chunk.decode("utf-8")
                while "\n" in line_buffer:
                    raw_line, line_buffer = line_buffer.split("\n", 1)
                    line = raw_line.strip()

                    if not line or line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed Anthropic SSE: %s", data_str[:120])
                        continue

                    dtype = data.get("type")

                    if dtype == "message_start":
                        usage = data.get("message", {}).get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)

                    elif dtype == "content_block_start":
                        block = data.get("content_block", {})
                        current_block_type = block.get("type")
                        if current_block_type == "thinking" and not thinking_open:
                            thinking_open = True
                            yield {"choices": [{"delta": {"content": "<think>"}}]}
                        elif current_block_type == "tool_use":
                            current_block_id = block.get("id", "")
                            current_tool_name = block.get("name", "")
                            current_tool_json = ""

                    elif dtype == "content_block_delta":
                        delta = data.get("delta", {})
                        delta_type = delta.get("type", "")
                        if delta_type == "thinking_delta":
                            text = delta.get("thinking", "")
                            if text:
                                yield {"choices": [{"delta": {"content": text}}]}
                        elif delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield {"choices": [{"delta": {"content": text}}]}
                        elif delta_type == "input_json_delta":
                            current_tool_json += delta.get("partial_json", "")

                    elif dtype == "content_block_stop":
                        if current_block_type == "thinking" and thinking_open:
                            yield {"choices": [{"delta": {"content": "</think>\n"}}]}
                            thinking_open = False
                        elif current_block_type == "tool_use" and current_tool_name:
                            try:
                                args = json.loads(current_tool_json) if current_tool_json else {}
                            except json.JSONDecodeError:
                                logger.warning("Failed to parse tool args: %s", current_tool_json[:200])
                                args = {}
                            yield {
                                "tool_call": {
                                    "id": current_block_id,
                                    "name": current_tool_name,
                                    "args": args,
                                }
                            }
                            current_tool_name = None
                            current_tool_json = ""
                            current_block_id = None
                        current_block_type = None

                    elif dtype == "message_delta":
                        usage = data.get("usage", {})
                        output_tokens = usage.get("output_tokens", 0)

            if input_tokens or output_tokens:
                yield {"usage_tokens": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "context_budget": _MODEL_CONTEXT.get(model, 200000),
                }}

    # -- Non-streaming chat ------------------------------------------------

    async def chat(self, messages: list[dict], temperature: float = 0.5,
                   max_tokens: int = 2048, model: str | None = None,
                   tools: list[dict] | None = None) -> dict:
        """Non-streaming chat. Returns a response dict with text and tool calls."""
        model = model or ANTHROPIC_MODELS[0]["id"]
        messages, think_enabled = self._strip_think_directive(messages)
        messages = self._normalize_messages(messages)
        payload = self._build_payload(messages, model, max_tokens, temperature,
                                      think_enabled, stream=False, tools=tools)

        session = await self._get_session()
        async with session.post(ANTHROPIC_API_URL, json=payload,
                                headers=self._headers()) as resp:
            if not resp.ok:
                body = await resp.text()
                logger.error("Anthropic API error %s: %s", resp.status, body)
            resp.raise_for_status()
            data = await resp.json()

        text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "args": block.get("input", {}),
                })

        result = {"choices": [{"message": {"content": text}}]}
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    # -- Code completion ---------------------------------------------------

    async def complete(self, prompt: str, max_tokens: int = 256,
                       model: str | None = None) -> dict:
        """Single-turn completion without thinking or tools (used for compaction)."""
        model = model or ANTHROPIC_MODELS[0]["id"]
        messages = [{"role": "user", "content": prompt}]
        payload = self._build_payload(messages, model, max_tokens,
                                      temperature=0.5, think_enabled=False, stream=False)
        session = await self._get_session()
        async with session.post(ANTHROPIC_API_URL, json=payload,
                                headers=self._headers()) as resp:
            resp.raise_for_status()
            data = await resp.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return {"choices": [{"message": {"content": text}}]}

    # -- Health / model list -----------------------------------------------

    async def health(self) -> dict:
        """Return available Anthropic models (no network call needed)."""
        if not self._api_key:
            return {"status": "error", "message": "ANTHROPIC_API_KEY not set", "models": []}
        return {"status": "ok", "models": list(ANTHROPIC_MODELS)}

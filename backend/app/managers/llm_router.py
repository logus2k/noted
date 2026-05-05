"""LLM Router - selects between local (agent_server) and Anthropic backends.

Exposes the same interface as LLMManager so llm.py needs no changes.
Model selection is persisted in memory for the lifetime of the process.
"""

import logging
from app.managers.llm_manager import LLMManager
from app.managers.anthropic_llm_manager import AnthropicLLMManager, ANTHROPIC_API_KEY, ANTHROPIC_MODELS

_ANTHROPIC_CONTEXT = {m["id"]: m["context_window"] for m in ANTHROPIC_MODELS}

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM calls to the active backend based on the selected model."""

    def __init__(self):
        self._local = LLMManager()
        self._anthropic = AnthropicLLMManager() if ANTHROPIC_API_KEY else None
        self._active_model: str | None = None  # None = use local default

    # ── Model management ──────────────────────────────────────────

    def set_model(self, model_id: str):
        """Switch the active model. Validated against available models."""
        self._active_model = model_id
        logger.info("Active model set to: %s", model_id)

    def _is_anthropic(self, model_id: str | None) -> bool:
        return bool(model_id and model_id.startswith("claude-"))

    def get_context_budget(self) -> int:
        """Real context window of the currently active model. Used by the
        chat router to populate the `usage.context_budget` SSE field when
        the upstream chunk does not carry it (local Gemma path)."""
        if self._is_anthropic(self._active_model):
            return _ANTHROPIC_CONTEXT.get(self._active_model, 200000)
        return self._local.context_window

    def _active_manager(self):
        if self._is_anthropic(self._active_model):
            if self._anthropic is None:
                raise RuntimeError("Anthropic model selected but ANTHROPIC_API_KEY is not set")
            return self._anthropic
        return self._local

    # ── Passthrough interface (matches LLMManager) ────────────────

    async def chat_stream(self, messages: list[dict], temperature: float = 0.5,
                          max_tokens: int = 2048, system: str | None = None,
                          tools: list[dict] | None = None,
                          extra_body: dict | None = None):
        manager = self._active_manager()
        if isinstance(manager, AnthropicLLMManager):
            # Anthropic doesn't accept Gemma's chat_template_kwargs; drop
            # the field on this branch. If we ever need Anthropic-specific
            # extras (e.g. thinking config), wire them through here.
            async for chunk in manager.chat_stream(
                messages, temperature=temperature, max_tokens=max_tokens,
                model=self._active_model, system=system, tools=tools,
            ):
                yield chunk
        else:
            async for chunk in manager.chat_stream(
                messages, temperature=temperature, max_tokens=max_tokens,
                tools=tools, extra_body=extra_body,
            ):
                yield chunk

    async def chat(self, messages: list[dict], temperature: float = 0.5,
                   max_tokens: int = 2048,
                   tools: list[dict] | None = None) -> dict:
        manager = self._active_manager()
        if isinstance(manager, AnthropicLLMManager):
            return await manager.chat(messages, temperature=temperature,
                                      max_tokens=max_tokens, model=self._active_model,
                                      tools=tools)
        return await manager.chat(messages, temperature=temperature, max_tokens=max_tokens,
                                  tools=tools)

    async def complete(self, prompt: str, max_tokens: int = 256) -> dict:
        manager = self._active_manager()
        if isinstance(manager, AnthropicLLMManager):
            return await manager.complete(prompt, max_tokens=max_tokens,
                                          model=self._active_model)
        return await manager.complete(prompt, max_tokens=max_tokens)

    async def close(self):
        await self._local.close()
        if self._anthropic:
            await self._anthropic.close()

    # ── Health / model list ───────────────────────────────────────

    async def health(self) -> dict:
        """Return combined status and model list from all configured backends."""
        local_health = await self._local.health()
        local_ok = local_health.get("status") == "ok"

        models = []

        # Local backend: expose only the primary model (display_name from agent_server)
        if local_ok:
            display = local_health.get("active_model") or "Local Model"
            primary_id = (local_health.get("models") or [display])[0]
            models.append({"id": primary_id, "display_name": display, "backend": "local"})

        # Anthropic models (only if key is configured)
        if self._anthropic:
            for m in ANTHROPIC_MODELS:
                models.append({**m, "backend": "anthropic"})

        # Default active_model to first available model
        if not self._active_model and models:
            self._active_model = models[0]["id"]

        # Overall status: ok if at least one backend is reachable or Anthropic is configured
        overall_ok = local_ok or bool(self._anthropic)

        return {
            "status": "ok" if overall_ok else "error",
            "models": models,
            "active_model": self._active_model,
        }

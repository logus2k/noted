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
        """Switch the active model (in-memory selection only). Used for the
        Anthropic path; local picks should go through select_model() so the
        agent_server active model is switched too."""
        self._active_model = model_id
        logger.info("Active model set to: %s", model_id)

    async def select_model(self, model_id: str) -> dict:
        """Apply a dropdown selection. For a cloud (claude-*) model this is just
        the in-memory selection. For a LOCAL model it also asks agent_server to
        switch its active chat model (which restarts llama-vision + agent_server,
        ~10-20s) so every consumer - including this one - serves the new model."""
        self._active_model = model_id
        if self._is_anthropic(model_id):
            logger.info("Active model set to cloud model: %s", model_id)
            return {"backend": "anthropic", "active_model": model_id}
        logger.info("Switching agent_server active local model to: %s", model_id)
        result = await self._local.set_active_model(model_id)
        return {"backend": "local", **(result or {})}

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

        # Local backend: expose ALL local chat models (agent_server now lists
        # them all with display_name/family/active). The active one is the model
        # the router currently serves; selecting another switches agent_server.
        local_active = None
        if local_ok:
            for m in (local_health.get("models") or []):
                models.append({
                    "id": m["id"],
                    "display_name": m.get("display_name") or m["id"],
                    "backend": "local",
                })
            local_active = local_health.get("active_model")

        # Anthropic models (only if key is configured)
        if self._anthropic:
            for m in ANTHROPIC_MODELS:
                models.append({**m, "backend": "anthropic"})

        # Effective active model: a cloud pick sticks; otherwise track the REAL
        # agent_server active local model (so the dropdown reflects switches,
        # including ones made by other clients/operators, after a reconnect).
        if self._is_anthropic(self._active_model):
            effective_active = self._active_model
        else:
            effective_active = local_active or (models[0]["id"] if models else None)
            self._active_model = effective_active

        # Overall status: ok if at least one backend is reachable or Anthropic is configured
        overall_ok = local_ok or bool(self._anthropic)

        return {
            "status": "ok" if overall_ok else "error",
            "models": models,
            "active_model": effective_active,
        }

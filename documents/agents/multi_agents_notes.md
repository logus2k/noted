# Per-turn agent switching — notes

Idea: a frontend dropdown next to the model selector that lets the user pick which agent persona handles the next turn (system prompt, sampling params). Verified feasible against the v2 stack.

## What works out of the box

agent_server resolves the agent preset **per request** via the `model` field in `POST /v1/chat/completions`. [openai_compat.py:114-126](../../../agent_server/app/openai_compat.py#L114-L126):

```python
def _resolve_model(model_field: str):
    POOL, AGENTS, ACTIVE_MODEL, MODELS = _get_globals()
    key = model_field.strip().lower()
    if key in AGENTS:
        preset = AGENTS[key]
        return preset, preset.system_prompt_path, dict(preset.params_override), key
```

`_build_messages` reads the preset's system prompt **fresh from disk on every request**. So changing the `model` field per turn loads a different prompt + different sampling overrides for that turn. No state to update, no warm-up, no agent-specific worker — the worker pool is shared.

| Switches per turn? | Item | Source |
|---|---|---|
| ✅ | System prompt | preset's `system_prompt_path`, read from disk |
| ✅ | Sampling overrides (temperature, top_k/p, max_tokens, stop) | preset's `params_override` |
| ✅ shared | Worker pool | stateless from agent's POV |

## Three real gotchas

1. **Tools are not part of the agent preset.** noted's chat handler (`backend/app/routers/llm.py`) builds the MCP tool list per-request from active domains + user toggles. If different agents should expose different tools (e.g., a "Writer" agent shouldn't see `update_cell`), the gating lives noted-side, not in agent_server.

2. **Conversation memory persists across agent switches.** Memory is keyed by `(project_id, client_id)`, not by agent. If the user is debugging with "MLOps Engineer" and switches to "Documentation Writer", the writer inherits the entire debugging context. Could be a feature (continuity) or a footgun (writer asked to act on debugging directives that don't match its persona). Decide: shared memory (current behavior) vs per-agent memory (separate history scoped to the agent).

3. **Voice block / format conventions live in the prompt.** The voice-first design lives in noted's Diana prompt. Other agent presets in agent_server may or may not have the same conventions. Switching to an agent without `<voice>` rules would break the TTS pipeline silently. Either ensure all user-selectable agents follow the same output contract, or branch the frontend parser by agent.

## Currently registered agents

From agent_server startup logs:

```
docbro, floorplan, general, ml, noted, noted_graph,
noted_graph_answer, noted_judge, robot, router, succint, topic
```

Plus `voice_summary` for the Phase 1 voice-injection fallback. Not all are user-facing — `router`, `noted_judge`, `noted_graph_answer`, `voice_summary` are infrastructure. A dropdown would want to filter to user-facing presets only (or expose a `user_facing: true` flag in the agent JSON).

## Implementation cost

| Layer | Work | Estimated effort |
|---|---|---|
| Frontend | `<select>` next to existing model dropdown listing user-facing agents; on change, persist the choice; pass it as the `model` field in the next chat request | ~30 lines |
| Backend (noted) | `llm.py` already passes `model` through. Only changes if you want per-agent tool gating or per-agent memory scoping | 0 (basic) → 50-100 lines (with tool gating) |
| Agent prompts | Each user-facing agent's prompt file in `agent_server/data/prompts/` needs the voice-block convention to play nicely with the TTS pipeline | varies by agent count |
| Settings | Persist user's preferred agent across sessions (project-scoped or global) | small |

## Decisions to make before implementing

| Decision | Options |
|---|---|
| Memory scope on agent switch | Shared (current) / per-agent (cleaner but loses cross-agent context) |
| Tool gating per agent | Same tools always / per-agent tool whitelist in agent JSON / inferred from agent name |
| Voice block contract | All agents must emit `<voice>` (forced) / parser auto-detects per agent / TTS off when non-voice agent active |
| Default agent | "noted" (Diana) / configurable global default / per-project default |
| Surfacing in UI | Dropdown next to model / radio group in chat panel header / settings-only |

## Recommendation

**Start narrow:** dropdown, shared memory, all agents must follow the voice contract, all agents share the same MCP toolset. That's a one-day task. Add per-agent tool gating + per-agent memory only if you observe specific failure modes that warrant them.

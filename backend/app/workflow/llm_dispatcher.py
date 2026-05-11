"""LLM dispatcher for the workflow loop.

When a plan step's `worker` names an agent_server preset (`planner`,
`tool_author`, `api_tester`, `skill_author`, ...), the workflow loop
calls `dispatch()` here. The dispatcher:

1. Builds the user message from step inputs (workflow_inputs +
   previous_step output + validator_complaint when retrying).
2. POSTs to agent_server `/v1/chat/completions` with `model=<preset>`.
3. Strips `<think>...</think>` blocks from the response content.
4. Parses the cleaned content as JSON.
5. Returns the parsed dict; the loop validates against the step's
   `output_schema` and runs bounded retry on failure.

No GBNF (kills `<think>` and tool calls in current llama-server, see
`feedback_gbnf_kills_thinking_and_tool_calls.md`). Schema validation
happens AFTER the call returns; bounded retry feeds the validator's
complaint back via `inputs["validator_complaint"]` on the next attempt
(handled by the loop, not here).

F3 ships the Gemma path only. Claude cross-backend is a follow-on (would
read the preset's system_prompt + sampling and call Anthropic via noted's
existing `llm_manager`).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AGENT_SERVER_URL = os.environ.get("AGENT_SERVER_URL") or os.environ.get(
    "LLM_BASE_URL", "http://agent_server:7701"
)
DEFAULT_TIMEOUT_S = float(os.environ.get("WORKFLOW_LLM_TIMEOUT_S", "120"))

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_BLOCK = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_thinking(content: str) -> str:
    """Remove `<think>...</think>` blocks. Worker presets configured with
    `enable_thinking: false` won't emit these; presets with thinking on
    will. Either way, we strip before parsing."""
    return _THINK_BLOCK.sub("", content).strip()


def _strip_code_fence(content: str) -> str:
    """If the model wrapped JSON in a ```json ... ``` fence (against the
    prompt's instruction), peel it. Defensive only."""
    m = _FENCE_BLOCK.match(content.strip())
    if m:
        return m.group(1).strip()
    return content


def _build_user_message(step_inputs: dict[str, Any]) -> str:
    """Render the loop's per-step `inputs` dict into a single user-message
    string the worker preset can read.

    Worker preset prompts expect plain-text key/value pairs (e.g.
    `mission: ...`, `api_docs: ...`); this renderer formats accordingly.
    Lists become bullet lists. Dicts become indented JSON.
    """
    parts: list[str] = []

    # Workflow inputs first - the original user request shape.
    workflow_inputs = step_inputs.get("workflow_inputs") or {}
    if isinstance(workflow_inputs, dict):
        for k in sorted(workflow_inputs.keys()):
            v = workflow_inputs[k]
            parts.append(_format_field(k, v))

    # Previous step output (when applicable).
    prev = step_inputs.get("previous_step")
    if isinstance(prev, dict) and prev.get("output"):
        parts.append("")
        parts.append(f"previous_step ({prev.get('name', '')}):")
        parts.append(json.dumps(prev["output"], indent=2, default=str))

    # Validator complaint - on retry, the worker is told what failed.
    complaint = step_inputs.get("validator_complaint")
    if complaint:
        parts.append("")
        parts.append(f"previous_iteration_diagnostics: {complaint}")

    # A2: when a smoke-test failure caused a rewind, the loop injects the
    # failure tail here so the worker can target the actual problem
    # instead of reproducing the same broken output. Truncated for
    # context-window hygiene; the worker doesn't need the full pytest
    # noise, just the specific assertion / error.
    smoke_failure = step_inputs.get("previous_smoke_failure")
    if smoke_failure:
        tail = str(smoke_failure)[-2000:]
        parts.append("")
        parts.append(
            "previous_smoke_failure: smoke tests failed in the prior "
            "iteration. Read the failure carefully and fix the specific "
            "issue (e.g. SyntaxError from a multi-line assert, mock "
            "shape divergence, wrong expected output key). Failure "
            f"tail:\n{tail}"
        )

    return "\n".join(parts)


def _format_field(key: str, value: Any) -> str:
    if isinstance(value, str):
        return f"{key}: {value}"
    if isinstance(value, list):
        if all(isinstance(x, str) for x in value):
            return f"{key}:\n" + "\n".join(f"- {x}" for x in value)
        return f"{key}:\n{json.dumps(value, indent=2, default=str)}"
    if isinstance(value, dict):
        return f"{key}:\n{json.dumps(value, indent=2, default=str)}"
    return f"{key}: {value}"


async def _fetch_preset_config(preset_name: str, base_url: str, timeout_s: float) -> dict[str, Any]:
    """F2.6: pull a preset's system_prompt + sampling from agent_server.
    Used by the Claude dispatch path so noted backend doesn't need a
    bind mount on agent_server's data dir."""
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(f"{base_url}/v1/agents/{preset_name}")
        resp.raise_for_status()
        return resp.json()


async def dispatch_claude(
    preset_name: str,
    step_inputs: dict[str, Any],
    *,
    base_url: str = AGENT_SERVER_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """F2.6 / F3.11: Claude cross-backend path. Fetches the preset's
    system prompt + sampling from agent_server, then calls Anthropic via
    noted's existing AnthropicLLMManager. Same JSON-output contract as
    the Gemma path; the loop's bounded retry / validator complaint
    feedback works identically.

    Cost: every call burns Anthropic tokens. Caller is responsible for
    deciding when to use this vs the local Gemma path. See
    `feedback_check_active_model_first.md` for context.
    """
    try:
        preset = await _fetch_preset_config(preset_name, base_url, timeout_s)
    except httpx.HTTPError as e:
        raise ValueError(f"agent_server preset fetch failed: {e}") from e

    system_prompt = preset.get("system_prompt") or ""
    params = preset.get("params_override") or {}
    user_message = _build_user_message(step_inputs)

    # noted's AnthropicLLMManager handles the system prompt either via
    # an explicit /system header or via a pseudo "system" message - delegate
    # to it. Lazy import keeps noted's startup time unaffected when nobody
    # uses the Claude path.
    from app.managers.anthropic_llm_manager import AnthropicLLMManager
    mgr = AnthropicLLMManager()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        result = await mgr.chat(
            messages,
            temperature=float(params.get("temperature") or 0.2),
            max_tokens=int(params.get("max_tokens") or 2048),
        )
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"anthropic call failed: {type(e).__name__}: {e}") from e
    finally:
        try:
            await mgr.close()
        except Exception:
            pass

    content = ""
    try:
        content = result["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"anthropic response shape unexpected: {result!r}")
    cleaned = _strip_code_fence(_strip_thinking(content))
    if not cleaned:
        raise ValueError("anthropic returned empty content (after stripping <think> + fences)")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        head = cleaned[:300].replace("\n", "\\n")
        raise ValueError(
            f"anthropic output is not valid JSON ({e.msg} at line {e.lineno} col {e.colno}); "
            f"head: {head}"
        ) from e
    if not isinstance(parsed, dict):
        raise ValueError(f"anthropic output is JSON but not an object: {type(parsed).__name__}")
    return parsed


def _llm_log_path(tenant_id: str, workflow_id: str):
    """Per-workflow LLM-call log file. Sits next to audit.jsonl + state.json
    under data/tenants/<tenant>/workflows/<workflow_id>/. One JSON object
    per line (jsonl). Captures the full request user_message + the raw
    response + the parse outcome so we can read exactly what Gemma
    emitted on a failing run."""
    from app.config import DATA_DIR
    from pathlib import Path
    return Path(DATA_DIR) / "tenants" / tenant_id / "workflows" / workflow_id / "llm_calls.jsonl"


def _record_llm_call(
    state,
    *,
    preset: str,
    backend: str,
    duration_s: float,
    user_message: str,
    raw_content: str,
    stripped: str,
    parsed: dict[str, Any] | None,
    parse_error: str | None,
) -> None:
    """Append one LLM-call entry to the per-workflow log. Best-effort;
    logging failures are swallowed so a disk issue can't break the
    workflow itself."""
    if state is None:
        return
    try:
        from datetime import datetime, timezone
        path = _llm_log_path(state.tenant_id, state.workflow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "tenant_id": state.tenant_id,
            "workflow_id": state.workflow_id,
            "preset": preset,
            "backend": backend,
            "duration_s": round(duration_s, 3),
            "request": {"user_message": user_message},
            "response": {
                "raw_content": raw_content,
                "stripped": stripped,
                "parsed": parsed,
                "parse_error": parse_error,
            },
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("llm-call log write failed: %s", e)


async def dispatch(
    preset_name: str,
    step_inputs: dict[str, Any],
    *,
    base_url: str = AGENT_SERVER_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    state=None,
) -> dict[str, Any]:
    """Call the agent_server preset, return the parsed JSON output dict.

    Raises ValueError on transport / parse failure. The loop catches this
    and feeds it into the validator-complaint retry path.

    `state` (WorkspaceState) is optional but lets the dispatcher write
    every request/response into the per-workflow llm_calls.jsonl log.
    """
    # F2.6: backend hint via the inputs dict (any plan template can opt in
    # by passing `_backend: "claude"` in the workflow's inputs). Default
    # is the local Gemma path; explicit "claude" routes through Anthropic.
    backend = (step_inputs.get("_backend") or "gemma").lower()
    if backend == "claude":
        return await dispatch_claude(preset_name, step_inputs,
                                     base_url=base_url, timeout_s=timeout_s)

    user_message = _build_user_message(step_inputs)
    payload = {
        "model": preset_name,
        "messages": [{"role": "user", "content": user_message}],
        "stream": False,
    }
    import time as _time
    _t0 = _time.perf_counter()
    raw_content = ""
    stripped = ""
    parsed_out: dict[str, Any] | None = None
    parse_error: str | None = None
    try:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.RequestError as e:
            parse_error = f"agent_server unreachable: {type(e).__name__}: {e}"
            raise ValueError(parse_error) from e
        except httpx.HTTPStatusError as e:
            parse_error = f"agent_server HTTP {e.response.status_code}: {e.response.text[:300]}"
            raise ValueError(parse_error) from e

        choices = data.get("choices") or []
        if not choices:
            parse_error = "agent_server returned no choices"
            raise ValueError(parse_error)
        raw_content = (choices[0].get("message") or {}).get("content") or ""
        stripped = _strip_code_fence(_strip_thinking(raw_content))
        if not stripped:
            parse_error = "worker preset returned empty content (after stripping <think> and fences)"
            raise ValueError(parse_error)
        try:
            parsed_out = json.loads(stripped)
        except json.JSONDecodeError as e:
            head = stripped[:300].replace("\n", "\\n")
            parse_error = (
                f"worker output is not valid JSON ({e.msg} at line {e.lineno} col {e.colno}); "
                f"head: {head}"
            )
            raise ValueError(parse_error) from e
        if not isinstance(parsed_out, dict):
            tname = type(parsed_out).__name__
            parsed_out = None
            parse_error = f"worker output is JSON but not an object: {tname}"
            raise ValueError(parse_error)
    finally:
        _record_llm_call(
            state,
            preset=preset_name,
            backend="gemma",
            duration_s=_time.perf_counter() - _t0,
            user_message=user_message,
            raw_content=raw_content,
            stripped=stripped,
            parsed=parsed_out,
            parse_error=parse_error,
        )
    logger.info("worker %s returned %d top-level keys", preset_name, len(parsed_out))
    return parsed_out


# ── Tool-calling dispatch ─────────────────────────────────────────


async def dispatch_tool_calling(
    preset_name: str,
    user_message: str,
    tool_names: list[str],
    *,
    base_url: str = AGENT_SERVER_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    state=None,
    ctx: dict[str, Any] | None = None,
    max_turns: int = 12,
) -> dict[str, Any]:
    """Multi-turn tool-calling invocation of an agent_server preset.

    Sends an initial user message with a filtered tools schema to the
    preset (which carries its own system prompt at the agent_server side).
    If the model responds with `tool_calls`, executes each via the same
    `execute_tool()` the chat path uses, appends results as `tool`-role
    messages, and continues. Returns when the model emits a plain content
    response (final answer) or when `max_turns` is reached.

    Used by workflow handlers that need an agent capable of multi-step
    tool use (`researcher`) rather than one-shot structured output
    (`tool_author`, `api_tester`, `skill_author`, ...).

    Returns:
      {
        "final_content": str,       # the model's final answer, or "" if cap hit
        "turns_used": int,          # number of LLM round-trips
        "tool_call_log": [          # one entry per executed tool call
          {"turn": int, "name": str, "args": dict, "result_preview": str}
        ],
        "hit_cap": bool,            # True if max_turns reached without final
        "error": str | None,        # transport / parse error if any
      }
    """
    # Lazy imports to avoid circular dependency with routers.llm at module
    # import time. _managers carries the runtime manager singletons; the
    # filtered tools schema is built per call so per-tenant additions
    # (user tools) are reflected.
    from app.managers.llm_tools import execute_tool
    from app.mcp.tool_formats import to_openai_tools
    from app.routers.llm import _managers as router_managers

    import time as _time

    wanted = set(tool_names)
    all_tools = to_openai_tools()
    tools = [t for t in all_tools if t.get("function", {}).get("name") in wanted]
    if not tools:
        raise ValueError(
            f"dispatch_tool_calling: none of the requested tool_names "
            f"{sorted(wanted)} are registered"
        )

    req_managers = {**router_managers, "_tool_metadata": {}}
    call_ctx = ctx or {}

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]
    tool_call_log: list[dict[str, Any]] = []
    final_content = ""
    error: str | None = None
    turns_used = 0
    _t0 = _time.perf_counter()

    try:
        for turn in range(max_turns):
            turns_used = turn + 1
            payload = {
                "model": preset_name,
                "messages": messages,
                "tools": tools,
                "stream": False,
            }
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    resp = await client.post(
                        f"{base_url}/v1/chat/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.RequestError as e:
                error = f"agent_server unreachable: {type(e).__name__}: {e}"
                break
            except httpx.HTTPStatusError as e:
                error = (
                    f"agent_server HTTP {e.response.status_code}: "
                    f"{e.response.text[:300]}"
                )
                break

            choices = data.get("choices") or []
            if not choices:
                error = "agent_server returned no choices"
                break
            msg = choices[0].get("message") or {}
            calls = msg.get("tool_calls") or []

            if not calls:
                # Model produced a plain content response — final answer.
                final_content = msg.get("content") or ""
                final_content = _strip_thinking(final_content).strip()
                break

            # Echo the assistant's tool-call message back into the history,
            # then execute each call and append its result as a `tool`-role
            # message. Same shape OpenAI / llama-cpp-python expects so the
            # next round sees the model's own prior actions + the outcomes.
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": calls,
            })

            for tc in calls:
                fn = tc.get("function") or {}
                tool_name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    tool_args = {}
                tool_call = {"id": tc.get("id", ""), "name": tool_name, "args": tool_args}
                try:
                    result = await execute_tool(tool_call, req_managers, call_ctx)
                    if not isinstance(result, str):
                        result = json.dumps(result, default=str)
                except Exception as e:
                    result = f"tool {tool_name!r} failed: {type(e).__name__}: {e}"
                tool_call_log.append({
                    "turn": turn,
                    "name": tool_name,
                    "args": tool_args,
                    "result_preview": result[:200],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })
    finally:
        # Single rolled-up log entry; per-tool detail lives in tool_call_log.
        _record_llm_call(
            state,
            preset=preset_name,
            backend="gemma",
            duration_s=_time.perf_counter() - _t0,
            user_message=user_message,
            raw_content=final_content,
            stripped=final_content,
            parsed={"tool_call_log": tool_call_log, "turns_used": turns_used},
            parse_error=error,
        )

    hit_cap = (turns_used >= max_turns and not final_content and error is None)
    logger.info(
        "tool-calling preset %s: turns=%d, tool_calls=%d, hit_cap=%s, error=%s",
        preset_name, turns_used, len(tool_call_log), hit_cap, error,
    )
    return {
        "final_content": final_content,
        "turns_used": turns_used,
        "tool_call_log": tool_call_log,
        "hit_cap": hit_cap,
        "error": error,
    }

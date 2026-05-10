"""Free-text capability request -> planner-decided workflow dispatch.

Shared helper used by:
  - app.routers.workflows / POST /api/workflows/from-request
  - app.managers.llm_tools / `request_new_tool` MCP tool handler

The helper takes a natural-language request, calls the `planner` agent_server
preset to pick a workflow type and populate its inputs, validates the inputs
against the chosen workflow's `input_schema`, then dispatches the workflow
asynchronously. Returns a dict the caller can return as JSON.

On any structured failure (planner returned no JSON, picked an unknown
workflow, or filled inputs that fail input_schema validation) the helper
raises FromRequestError so the caller can choose its own HTTP / MCP error
mapping.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
from typing import Any

import httpx

from app.workflow.llm_dispatcher import (
    AGENT_SERVER_URL,
    DEFAULT_TIMEOUT_S,
    _strip_code_fence,
    _strip_thinking,
)
from app.workflow.loop import _new_workflow_id, _validate_output, run_workflow
from app.workflow.registry import get_workflow_registry

logger = logging.getLogger(__name__)


class FromRequestError(Exception):
    """Structured failure during the planner-mediated dispatch.

    `stage` names the failure phase: `planner_call`, `planner_parse`,
    `planner_no_match`, `planner_unknown_workflow`, `input_schema_validation`.
    `detail` is a serialisable dict the caller can echo to its response.
    """

    def __init__(self, stage: str, detail: dict[str, Any]):
        super().__init__(f"{stage}: {detail.get('error', '')}")
        self.stage = stage
        self.detail = detail


def render_planner_user_message(free_text: str) -> str:
    """Render the user-message the planner preset expects: a `mission` line
    plus the registered workflows' types, descriptions, outcomes, and
    input_schemas.

    Workflows without an `input_schema` (e.g. dev-only synthetic_probe) are
    excluded so the planner can't pick them.
    """
    registry = get_workflow_registry()
    available = [
        {
            "type": d.type,
            "description": d.description,
            "outcomes": [o.name for o in d.outcomes],
            "input_schema": d.input_schema,
        }
        for d in registry.list_definitions()
        if d.input_schema is not None
    ]
    return (
        f"mission: {free_text.strip()}\n\n"
        f"available_workflows:\n{_json.dumps(available, indent=2)}"
    )


async def call_planner(free_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """POST the rendered user-message to agent_server's `planner` preset and
    return (parsed_planner_output, capture). The capture dict contains the
    full request + response so the caller can persist it into the workflow
    log once a workflow_id is known."""
    import time as _time
    user_message = render_planner_user_message(free_text)
    payload = {
        "model": "planner",
        "messages": [{"role": "user", "content": user_message}],
        "stream": False,
    }
    capture: dict[str, Any] = {
        "preset": "planner",
        "user_message": user_message,
        "raw_content": "",
        "stripped": "",
        "parsed": None,
        "parse_error": None,
        "duration_s": 0.0,
    }
    _t0 = _time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{AGENT_SERVER_URL}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        capture["parse_error"] = f"agent_server unreachable: {type(e).__name__}: {e}"
        capture["duration_s"] = _time.perf_counter() - _t0
        raise FromRequestError(
            "planner_call",
            {"error": capture["parse_error"]},
        ) from e
    except httpx.HTTPStatusError as e:
        capture["parse_error"] = f"agent_server HTTP {e.response.status_code}: {e.response.text[:300]}"
        capture["duration_s"] = _time.perf_counter() - _t0
        raise FromRequestError(
            "planner_call",
            {"error": capture["parse_error"]},
        ) from e

    choices = data.get("choices") or []
    if not choices:
        capture["parse_error"] = "planner returned no choices"
        capture["duration_s"] = _time.perf_counter() - _t0
        raise FromRequestError(
            "planner_call", {"error": capture["parse_error"]},
        )
    raw = (choices[0].get("message") or {}).get("content") or ""
    cleaned = _strip_code_fence(_strip_thinking(raw))
    capture["raw_content"] = raw
    capture["stripped"] = cleaned
    capture["duration_s"] = _time.perf_counter() - _t0
    try:
        parsed = _json.loads(cleaned)
        capture["parsed"] = parsed
        return parsed, capture
    except _json.JSONDecodeError as e:
        capture["parse_error"] = f"planner output not valid JSON: {e.msg}"
        raise FromRequestError(
            "planner_parse",
            {
                "error": capture["parse_error"],
                "raw": cleaned[:1500],
            },
        ) from e


async def dispatch_from_request(
    free_text: str,
    *,
    tenant_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Run the planner against `free_text`, validate the inputs it produced,
    and kick off the chosen workflow.

    Returns:
        {
          "workflow_id": str,
          "workflow_type": str,
          "tenant_id": str,
          "status": "pending",
          "planner": {"reasoning": str, "inputs": dict},
        }
    Raises FromRequestError on any structured failure.
    """
    plan, planner_capture = await call_planner(free_text)

    workflow_type = plan.get("workflow_type") or ""
    inputs = plan.get("inputs") or {}
    reasoning = plan.get("reasoning") or ""

    if not workflow_type:
        raise FromRequestError(
            "planner_no_match",
            {
                "error": "planner returned empty workflow_type",
                "reasoning": reasoning,
            },
        )

    definition = get_workflow_registry().get(workflow_type)
    if definition is None:
        raise FromRequestError(
            "planner_unknown_workflow",
            {
                "error": f"planner picked unregistered workflow: {workflow_type!r}",
                "reasoning": reasoning,
            },
        )

    complaint = _validate_output(inputs, definition.input_schema)
    if complaint is not None:
        raise FromRequestError(
            "input_schema_validation",
            {
                "error": complaint,
                "workflow_type": workflow_type,
                "planner_inputs": inputs,
                "reasoning": reasoning,
            },
        )

    workflow_id = _new_workflow_id()

    # Persist the planner request/response into the workflow's log so the
    # full LLM trace (planner → tool_author → api_tester → skill_author)
    # lives in one place per workflow_id.
    try:
        from datetime import datetime, timezone
        from pathlib import Path
        from app.config import DATA_DIR
        log_path = Path(DATA_DIR) / "tenants" / tenant_id / "workflows" / workflow_id / "llm_calls.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "tenant_id": tenant_id,
            "workflow_id": workflow_id,
            "preset": "planner",
            "backend": "gemma",
            "duration_s": round(planner_capture.get("duration_s", 0.0), 3),
            "request": {"user_message": planner_capture.get("user_message", "")},
            "response": {
                "raw_content": planner_capture.get("raw_content", ""),
                "stripped": planner_capture.get("stripped", ""),
                "parsed": planner_capture.get("parsed"),
                "parse_error": planner_capture.get("parse_error"),
            },
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        logger.exception("planner llm-call log write failed for %s/%s", tenant_id, workflow_id)

    async def _run() -> None:
        try:
            await run_workflow(
                tenant_id=tenant_id,
                workflow_type=workflow_type,
                inputs=inputs,
                actor_id=actor_id,
                workflow_id=workflow_id,
            )
        except Exception:
            logger.exception("from_request spawned task failed for %s", workflow_id)

    asyncio.create_task(_run())

    return {
        "workflow_id": workflow_id,
        "workflow_type": workflow_type,
        "tenant_id": tenant_id,
        "status": "pending",
        "planner": {"reasoning": reasoning, "inputs": inputs},
    }

"""Call noted's /api/llm/chat endpoint and return the parsed response."""

from __future__ import annotations

import os
import time

import requests

from .stream_parser import ParsedResponse, parse_sse_stream


NOTED_BASE_URL = os.environ.get("NOTED_BASE_URL", "http://localhost:8123")


class DriverError(RuntimeError):
    pass


def call_chat(
    *,
    message: str,
    client_id: str,
    context_descriptor: dict,
    think_enabled: bool = True,
    temperature: float = 0.5,
    max_tokens: int = 8192,
    timeout: tuple[float, float] = (10.0, 600.0),
) -> tuple[ParsedResponse, float]:
    """POST to /api/llm/chat and parse the SSE stream. Returns (parsed, latency_ms)."""
    body = {
        "message": message,
        "client_id": client_id,
        "context_descriptor": context_descriptor,
        "think_enabled": think_enabled,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    url = f"{NOTED_BASE_URL}/api/llm/chat"
    t0 = time.perf_counter()
    try:
        with requests.post(url, json=body, stream=True, timeout=timeout) as resp:
            if resp.status_code >= 400:
                raise DriverError(f"POST {url} returned HTTP {resp.status_code}: {resp.text[:300]}")
            parsed = parse_sse_stream(resp.iter_lines())
    except requests.RequestException as e:
        raise DriverError(f"POST {url} failed: {e}")
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return parsed, latency_ms


def call_confirm(
    *,
    action_id: str,
    approved: bool = True,
    timeout: tuple[float, float] = (10.0, 600.0),
) -> tuple[ParsedResponse, float]:
    """POST to /api/llm/confirm to approve (or reject) a pending write tool call.
    The endpoint streams back the tool result + the assistant's follow-up response
    as an SSE stream (same format as /chat). Returns the parsed follow-up response."""
    body = {"action_id": action_id, "approved": approved}
    url = f"{NOTED_BASE_URL}/api/llm/confirm"
    t0 = time.perf_counter()
    try:
        with requests.post(url, json=body, stream=True, timeout=timeout) as resp:
            if resp.status_code >= 400:
                raise DriverError(f"POST {url} returned HTTP {resp.status_code}: {resp.text[:300]}")
            parsed = parse_sse_stream(resp.iter_lines())
    except requests.RequestException as e:
        raise DriverError(f"POST {url} failed: {e}")
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return parsed, latency_ms


def merge_followup(initial: ParsedResponse, followup: ParsedResponse) -> ParsedResponse:
    """Combine an initial chat response with a /confirm follow-up. The result
    represents the complete turn as a real user would see it end-to-end."""
    # Reconcile orphan tool_results: the /confirm stream emits tool_result
    # events for write tools, but the matching ToolCallRecord (with args)
    # lives in the initial response. If followup has a ToolCallRecord with
    # empty args + populated result, and initial has the matching name with
    # no result, copy the result onto initial and drop the orphan.
    # If no match exists (e.g. the initial call was a batch_update_cells that
    # expanded into N individual update_cell executions), the orphan carries
    # no model-decision information and is discarded.
    orphan_indices = [
        i for i, tc in enumerate(followup.tool_calls)
        if tc.result and not tc.args
    ]
    for i in reversed(orphan_indices):
        orphan = followup.tool_calls[i]
        matched = False
        for itc in reversed(initial.tool_calls):
            if itc.name == orphan.name and not itc.result:
                itc.result = orphan.result
                itc.result_truncated = orphan.result_truncated
                matched = True
                break
        del followup.tool_calls[i]  # always drop the orphan after processing
        if not matched:
            # Attach the execution result to the batch parent, if present,
            # so the per-scenario md shows what happened. We concatenate when
            # several orphans share one parent (batch expansions).
            parent_names = ("batch_update_cells", "find_replace_in_cells", "fix_lint_issues")
            for itc in reversed(initial.tool_calls):
                if itc.name in parent_names:
                    itc.result = (itc.result + "\n\n" if itc.result else "") + orphan.result
                    itc.result_truncated = itc.result_truncated or orphan.result_truncated
                    break
    merged = ParsedResponse(
        tool_calls=list(initial.tool_calls) + list(followup.tool_calls),
        skills=list(initial.skills) + [s for s in followup.skills if s not in initial.skills],
        # Concatenate reasoning (both phases are part of the turn's reasoning chain)
        reasoning=("\n".join(x for x in (initial.reasoning, followup.reasoning) if x)),
        # Post-approval answer is what the user actually ends up seeing.
        # Fall back to initial.answer if the follow-up stream produced nothing.
        answer=followup.answer or initial.answer,
        usage={
            "input_tokens": initial.usage.get("input_tokens", 0) + followup.usage.get("input_tokens", 0),
            "output_tokens": initial.usage.get("output_tokens", 0) + followup.usage.get("output_tokens", 0),
        },
        errors=list(initial.errors) + list(followup.errors),
        pending_action_id="",  # consumed
        raw_chunks=list(initial.raw_chunks) + list(followup.raw_chunks),
    )
    return merged

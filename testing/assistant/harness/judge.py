"""Format the TEST CASE + ASSISTANT OUTPUT envelope and invoke noted_judge.

Returns the parsed JSON verdict (strict schema per the judge's system prompt).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


AGENT_SERVER_URL = os.environ.get("AGENT_SERVER_URL", "http://localhost:7701")

# Search order for the judge prompt file (used to compute a reproducibility
# hash tagged into every report). The first path that exists wins. When the
# harness runs inside the noted container, none of these may be reachable -
# in that case the hash degrades gracefully to "unknown".
DEFAULT_JUDGE_PROMPT_PATHS = [
    # Explicit override via env var (highest priority)
    os.environ.get("JUDGE_PROMPT_HOST_PATH") or "",
    # Host default (when running from the user's workstation)
    str(Path.home() / "env" / "assets" / "agent_server" / "data" / "prompts" / "noted_judge_system_prompt.txt"),
    # Absolute host path (script invoked from a different home dir)
    "/home/logus/env/assets/agent_server/data/prompts/noted_judge_system_prompt.txt",
    # Container-side path (when agent_server's data is somehow mounted into ours)
    "/agent_server/app/data/prompts/noted_judge_system_prompt.txt",
]


class JudgeError(RuntimeError):
    pass


@dataclass
class JudgeVerdict:
    verdict: str                # "PASS" | "FAIL"
    tool_call_check: str        # "OK" | "BAD"
    answer_check: str           # "OK" | "BAD"
    procedural_check: str       # "OK" | "BAD"
    deficiencies: list[str]
    rationale: str
    raw: dict                   # the full JSON the judge returned
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0


def compute_judge_prompt_hash(explicit_path: Optional[str] = None) -> str:
    """Sha1[:12] of the current judge prompt so reports are reproducibility-tagged.

    Search order:
      1. explicit_path arg (from --judge-prompt-path)
      2. JUDGE_PROMPT_HOST_PATH env var
      3. DEFAULT_JUDGE_PROMPT_PATHS list (host + container defaults)

    Returns "unknown" if none of the paths are readable.
    """
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.extend(p for p in DEFAULT_JUDGE_PROMPT_PATHS if p)

    for path in candidates:
        try:
            with open(path, "rb") as f:
                return hashlib.sha1(f.read()).hexdigest()[:12]
        except OSError:
            continue
    return "unknown"


def build_envelope(
    *,
    scenario_id: str,
    user_request: str,
    expected_tools_called: list[dict],
    expected_tools_NOT_called: list[str],
    expected_answer_focus: str,
    setup_summary: str,
    actual_tools_called: list[dict],
    reasoning: str,
    answer: str,
    workspace_context: str = "",
    workspace_context_truncated: bool = False,
) -> str:
    """Format the user-message payload for the judge per the calibrated contract."""
    def _fmt_expected_tools(ts: list[dict]) -> str:
        if not ts:
            return "[]"
        parts = []
        for t in ts:
            name = t.get("name", "?")
            count = t.get("exact_count")
            args = t.get("args_match") or {}
            piece = name
            if count is not None:
                piece += f" (exactly {count}x)"
            if args:
                piece += f" args_match={json.dumps(args, ensure_ascii=False)}"
            parts.append(piece)
        return "[" + ", ".join(parts) + "]"

    def _fmt_actual_tools(calls: list[dict]) -> str:
        if not calls:
            return "[]"
        return "[" + ", ".join(
            f"{c.get('name', '?')}({json.dumps(c.get('args', {}), ensure_ascii=False)})"
            for c in calls
        ) + "]"

    def _fmt_tool_results(calls: list[dict]) -> str:
        """Render the tool results the Assistant received, so the judge can
        verify whether answer content is grounded in those results."""
        lines = []
        for idx, c in enumerate(calls):
            result = c.get("result") or ""
            if not result:
                continue
            truncated_mark = " [TRUNCATED]" if c.get("result_truncated") else ""
            lines.append(f"[call {idx + 1}: {c.get('name', '?')}]{truncated_mark}")
            lines.append(result)
            lines.append("")
        return "\n".join(lines).rstrip() or "(no tool results captured)"

    test_case = (
        "TEST CASE:\n"
        f"  scenario_id: {scenario_id}\n"
        f"  setup: {setup_summary}\n"
        f'  user_request: "{user_request}"\n'
        f"  expected_tools_called: {_fmt_expected_tools(expected_tools_called)}\n"
        f"  expected_tools_NOT_called: {expected_tools_NOT_called}\n"
        "  expected_answer_focus: |\n"
        + "\n".join(f"    {line}" for line in (expected_answer_focus or "").splitlines())
    )

    # The Assistant saw a workspace-context block with notebook cells, MLflow
    # runs, Hydra config, etc. before this turn started. Include it so the
    # judge can verify answer claims that reference context-injected data
    # (run params, active skill content, etc.) without flagging as hallucinated.
    context_section = ""
    if workspace_context:
        trunc_mark = " [TRUNCATED AT 40K CHARS]" if workspace_context_truncated else ""
        context_section = (
            f"\n\nWORKSPACE CONTEXT seen by the Assistant{trunc_mark}\n"
            "(authoritative - factual claims in the answer may reference anything here):\n"
            f"{workspace_context}\n"
        )

    assistant_output = (
        "\n\nASSISTANT OUTPUT:\n"
        f"  actual_tools_called: {_fmt_actual_tools(actual_tools_called)}\n\n"
        "  actual_tool_results (authoritative - compare answer claims against these):\n"
        f"{_fmt_tool_results(actual_tools_called)}"
        + context_section
        + f"\n\n<reasoning>\n{reasoning or '(none captured)'}\n</reasoning>\n\n"
        f"<answer>\n{answer or '(empty)'}\n</answer>\n"
    )

    return test_case + assistant_output


def invoke_judge(envelope: str, max_tokens: int = 512, timeout: float = 120.0) -> JudgeVerdict:
    """POST the envelope to noted_judge and parse its JSON verdict."""
    body = {
        "model": "noted_judge",
        "messages": [{"role": "user", "content": envelope}],
        "max_tokens": max_tokens,
    }
    url = f"{AGENT_SERVER_URL}/v1/chat/completions"
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise JudgeError(f"POST {url} failed: {e}")
    latency_ms = (time.perf_counter() - t0) * 1000.0

    try:
        resp = r.json()
    except ValueError:
        raise JudgeError(f"judge response was not JSON: {r.text[:300]}")

    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise JudgeError(f"judge response missing choices[0].message.content: {e}; body={resp}")

    # Strip possible wrapping whitespace / code fences just in case
    content_stripped = content.strip()
    if content_stripped.startswith("```"):
        # Remove first line (```json or ```) and last line (```)
        lines = content_stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content_stripped = "\n".join(lines).strip()

    try:
        verdict_json = json.loads(content_stripped)
    except json.JSONDecodeError as e:
        raise JudgeError(f"judge content was not JSON: {e}; content={content_stripped[:300]}")

    usage = resp.get("usage") or {}
    return JudgeVerdict(
        verdict=verdict_json.get("verdict", "FAIL"),
        tool_call_check=verdict_json.get("tool_call_check", "BAD"),
        answer_check=verdict_json.get("answer_check", "BAD"),
        procedural_check=verdict_json.get("procedural_check", "BAD"),
        deficiencies=list(verdict_json.get("deficiencies") or []),
        rationale=verdict_json.get("rationale", ""),
        raw=verdict_json,
        latency_ms=latency_ms,
        tokens_in=int(usage.get("prompt_tokens") or 0),
        tokens_out=int(usage.get("completion_tokens") or 0),
    )

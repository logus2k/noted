"""Layer-1 deterministic checks on the assistant's response vs scenario expectations.

This layer fires BEFORE the judge. If it fails, the judge is not invoked
(saves time and tokens). Layer-1 failures count as FAIL (not ERROR) because
the Assistant ran to completion; it just didn't meet the spec.

Checks:
  - Every expected tool was called (honoring `exact_count` if specified).
  - No forbidden tool was called.
  - Every expected tool's `args_match` is satisfied on at least one matching call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .scenario_loader import ExpectedToolCall, Turn
from .stream_parser import ToolCallRecord


@dataclass
class DeterministicCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def merge(self, other: "DeterministicCheck") -> "DeterministicCheck":
        return DeterministicCheck(
            ok=self.ok and other.ok,
            reasons=self.reasons + other.reasons,
        )


def _arg_matches(expected: Any, actual: Any) -> bool:
    """Match a single arg. String expected values are treated as substrings OR
    regexes (if enclosed in /.../); dicts recursively match keys."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, v in expected.items():
            if k not in actual or not _arg_matches(v, actual[k]):
                return False
        return True
    if isinstance(expected, str):
        if len(expected) >= 2 and expected.startswith("/") and expected.endswith("/"):
            return bool(re.search(expected[1:-1], str(actual)))
        return str(expected) == str(actual) or str(expected).lower() in str(actual).lower()
    return expected == actual


def _args_match_all(expected_args: dict, actual_args: dict) -> bool:
    return all(
        k in actual_args and _arg_matches(v, actual_args[k])
        for k, v in expected_args.items()
    )


def _count_calls(name: str, actual_calls: list[ToolCallRecord]) -> int:
    return sum(1 for c in actual_calls if c.name == name)


def _find_matching_calls(
    expected: ExpectedToolCall, actual_calls: list[ToolCallRecord]
) -> list[ToolCallRecord]:
    return [c for c in actual_calls if c.name == expected.name and _args_match_all(expected.args_match, c.args)]


def check_turn(turn: Turn, actual_calls: list[ToolCallRecord]) -> DeterministicCheck:
    """Run the Layer-1 evaluator on a single turn's captured tool calls."""
    ok = True
    reasons: list[str] = []

    # 1. Expected tools present (and arg-matching, if specified)
    for exp in turn.expected_tools_called:
        call_count = _count_calls(exp.name, actual_calls)
        if call_count == 0:
            ok = False
            reasons.append(f"expected tool '{exp.name}' was NOT called")
            continue

        if exp.exact_count is not None and call_count != exp.exact_count:
            ok = False
            reasons.append(
                f"expected tool '{exp.name}' called {call_count} times, wanted exactly {exp.exact_count}"
            )
            # continue - arg check below may still add detail

        if exp.args_match:
            matches = _find_matching_calls(exp, actual_calls)
            if not matches:
                ok = False
                actual_args_preview = [c.args for c in actual_calls if c.name == exp.name]
                reasons.append(
                    f"expected tool '{exp.name}' called but args_match={exp.args_match} "
                    f"not satisfied by any call; actual args: {actual_args_preview}"
                )

    # 2. Forbidden tools absent
    for forbidden in turn.expected_tools_NOT_called:
        if _count_calls(forbidden, actual_calls) > 0:
            ok = False
            reasons.append(f"forbidden tool '{forbidden}' WAS called")

    return DeterministicCheck(ok=ok, reasons=reasons)

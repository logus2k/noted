"""Parse scenario YAML files into typed dataclasses.

Two shapes are supported:
  - Single-turn: scenario has `user_request` / `expected_*` at top level.
  - Multi-turn:  scenario has `turns: [{user_request, expected_*}, ...]`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class Prerequisite:
    fixture: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Setup:
    project: Optional[str] = None
    notebook: Optional[str] = None
    file_path: Optional[str] = None  # project-relative path of an open non-notebook file (e.g. for lint scenarios)
    active_run_id: Optional[str] = None
    selected_cell_indices: list[int] = field(default_factory=list)
    prerequisites: list[Prerequisite] = field(default_factory=list)


@dataclass
class ExpectedToolCall:
    name: str
    exact_count: Optional[int] = None  # None = "at least once"
    args_match: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    user_request: str
    expected_tools_called: list[ExpectedToolCall] = field(default_factory=list)
    expected_tools_NOT_called: list[str] = field(default_factory=list)
    expected_answer_focus: str = ""


@dataclass
class Scenario:
    scenario_id: str
    title: str
    setup: Setup
    turns: list[Turn]
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def is_multi_turn(self) -> bool:
        return len(self.turns) > 1


@dataclass
class Doc:
    doc_id: str
    doc_type: str  # "skill" | "tool"
    source_path: Path
    scenarios: list[Scenario]


def _parse_prerequisite(d: dict) -> Prerequisite:
    return Prerequisite(fixture=d["fixture"], args=dict(d.get("args") or {}))


def _parse_setup(d: dict) -> Setup:
    return Setup(
        project=d.get("project"),
        notebook=d.get("notebook"),
        file_path=d.get("file_path"),
        active_run_id=d.get("active_run_id"),
        selected_cell_indices=list(d.get("selected_cell_indices") or []),
        prerequisites=[_parse_prerequisite(p) for p in (d.get("prerequisites") or [])],
    )


def _parse_expected_tool(d: dict) -> ExpectedToolCall:
    return ExpectedToolCall(
        name=d["name"],
        exact_count=d.get("exact_count"),
        args_match=dict(d.get("args_match") or {}),
    )


def _parse_turn(d: dict) -> Turn:
    return Turn(
        user_request=d["user_request"],
        expected_tools_called=[_parse_expected_tool(t) for t in (d.get("expected_tools_called") or [])],
        expected_tools_NOT_called=list(d.get("expected_tools_NOT_called") or []),
        expected_answer_focus=d.get("expected_answer_focus", "") or "",
    )


def _parse_scenario(d: dict) -> Scenario:
    setup = _parse_setup(d.get("setup") or {})
    if "turns" in d and d["turns"]:
        turns = [_parse_turn(t) for t in d["turns"]]
    else:
        # Flatten single-turn scenario into one Turn object
        turns = [_parse_turn({
            "user_request": d["user_request"],
            "expected_tools_called": d.get("expected_tools_called") or [],
            "expected_tools_NOT_called": d.get("expected_tools_NOT_called") or [],
            "expected_answer_focus": d.get("expected_answer_focus", ""),
        })]
    return Scenario(
        scenario_id=d["scenario_id"],
        title=d.get("title", d["scenario_id"]),
        setup=setup,
        turns=turns,
        tags=list(d.get("tags") or []),
        notes=d.get("notes", "") or "",
    )


def load_doc(path: Path) -> Doc:
    """Load a .yaml test doc into a typed Doc object. Raises ValueError on
    schema violations."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level must be a mapping, got {type(raw).__name__}")

    missing = [k for k in ("doc_id", "doc_type", "scenarios") if k not in raw]
    if missing:
        raise ValueError(f"{path}: missing required fields: {missing}")

    scenarios = [_parse_scenario(s) for s in raw["scenarios"]]

    # Unique scenario_ids within a doc
    ids = [s.scenario_id for s in scenarios]
    if len(ids) != len(set(ids)):
        dup = [x for x in ids if ids.count(x) > 1]
        raise ValueError(f"{path}: duplicate scenario_ids: {sorted(set(dup))}")

    return Doc(
        doc_id=raw["doc_id"],
        doc_type=raw["doc_type"],
        source_path=path.resolve(),
        scenarios=scenarios,
    )


def find_scenario(doc: Doc, scenario_id: str) -> Scenario:
    for s in doc.scenarios:
        if s.scenario_id == scenario_id:
            return s
    raise KeyError(f"scenario '{scenario_id}' not found in {doc.source_path}")

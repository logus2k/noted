"""Consistency lint between .md (human) and .yaml (machine) test docs, and
structural validation of .yaml schema.

Rules enforced:
  1. Every `.md` file under testing/assistant/{skills,tools}/ has a sibling `.yaml`.
  2. Every `.yaml` file has a sibling `.md` (or at least exists beside one).
  3. Every scenario_id mentioned in the `.md` (matched by the pattern "S\\d+")
     exists in the `.yaml` as a scenario.
  4. Every fixture name in the `.yaml` resolves to a registered fixture.
  5. Every scenario has required fields (scenario_id, title, at least user_request
     or turns).
  6. doc_id in the yaml matches the filename stem.

Returns a list of issues (strings). Empty list means clean.
"""

from __future__ import annotations

import re
from pathlib import Path

from .fixtures import _REGISTRY as FIXTURE_REGISTRY
from .scenario_loader import load_doc


SCENARIO_ID_IN_MD_RE = re.compile(r"^###\s*(S\d+)\b", re.MULTILINE)


def _scenarios_in_md(md_path: Path) -> set[str]:
    text = md_path.read_text(encoding="utf-8")
    return set(SCENARIO_ID_IN_MD_RE.findall(text))


def _lint_one(yaml_path: Path, issues: list[str]) -> None:
    """Structural checks on one YAML file + cross-check vs its sibling MD."""
    md_path = yaml_path.with_suffix(".md")

    # Rule 2: yaml has a sibling md
    if not md_path.is_file():
        issues.append(f"{yaml_path.name}: no sibling .md found at {md_path.name}")

    # Load + structural check
    try:
        doc = load_doc(yaml_path)
    except Exception as e:
        issues.append(f"{yaml_path.name}: failed to load ({type(e).__name__}: {e})")
        return

    # Rule 6: doc_id matches stem
    if doc.doc_id != yaml_path.stem:
        issues.append(f"{yaml_path.name}: doc_id '{doc.doc_id}' does not match filename stem '{yaml_path.stem}'")

    # Rule 5: each scenario has required fields
    for s in doc.scenarios:
        if not s.scenario_id:
            issues.append(f"{yaml_path.name}: scenario with empty scenario_id")
            continue
        if not s.turns:
            issues.append(f"{yaml_path.name}::{s.scenario_id}: no turns (missing user_request)")
            continue
        for i, t in enumerate(s.turns):
            if not t.user_request:
                issues.append(
                    f"{yaml_path.name}::{s.scenario_id} turn {i + 1}: empty user_request"
                )

    # Rule 4: all fixtures resolve
    for s in doc.scenarios:
        for p in s.setup.prerequisites:
            if p.fixture not in FIXTURE_REGISTRY:
                issues.append(
                    f"{yaml_path.name}::{s.scenario_id}: unknown fixture '{p.fixture}' "
                    f"(registered: {sorted(FIXTURE_REGISTRY)})"
                )

    # Rule 3: every scenario_id mentioned in MD appears in YAML
    if md_path.is_file():
        md_ids = _scenarios_in_md(md_path)
        yaml_ids = {s.scenario_id for s in doc.scenarios}
        missing = md_ids - yaml_ids
        if missing:
            issues.append(
                f"{yaml_path.name}: scenario_ids mentioned in {md_path.name} "
                f"but missing in yaml: {sorted(missing)}"
            )


def _lint_orphan_mds(roots: list[Path], issues: list[str]) -> None:
    """Rule 1: every .md under the roots has a sibling .yaml."""
    for root in roots:
        if not root.is_dir():
            continue
        for md in sorted(root.glob("*.md")):
            yaml = md.with_suffix(".yaml")
            if not yaml.is_file():
                issues.append(f"{md.name}: no sibling .yaml (at {yaml.name})")


def lint(testing_root: Path) -> list[str]:
    """Run all lint rules. Returns a list of issue strings (empty = clean)."""
    issues: list[str] = []
    roots = [testing_root / "skills", testing_root / "tools"]

    _lint_orphan_mds(roots, issues)

    for root in roots:
        if not root.is_dir():
            continue
        for yaml_path in sorted(root.glob("*.yaml")):
            _lint_one(yaml_path, issues)

    return issues


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="lint",
        description="Lint the Assistant test docs (.md + .yaml) for consistency.",
    )
    p.add_argument(
        "--testing-root",
        default="testing/assistant",
        help="Root directory of the test docs (default: testing/assistant)",
    )
    args = p.parse_args()

    root = Path(args.testing_root)
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", flush=True)
        return 2

    issues = lint(root)
    if not issues:
        print(f"lint OK ({root})")
        return 0

    print(f"lint found {len(issues)} issue(s) in {root}:\n")
    for i, msg in enumerate(issues, 1):
        print(f"  {i}. {msg}")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

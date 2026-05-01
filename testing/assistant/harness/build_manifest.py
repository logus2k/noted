"""Regenerate _scenarios.json from every YAML under testing/assistant/{skills,tools}/.

Run from host or from /tmp/harness_run inside the container:

    python3 -m testing.assistant.harness.build_manifest \
        --out data/testing/reports/_scenarios.json

The output is a flat list consumed by the static progress dashboard so it can
show PENDING rows for scenarios that have not yet appeared in _history.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def collect(testing_root: Path) -> list[dict]:
    entries: list[dict] = []
    for doc_type in ("skills", "tools"):
        doc_dir = testing_root / doc_type
        if not doc_dir.is_dir():
            continue
        for yaml_path in sorted(doc_dir.glob("*.yaml")):
            try:
                with yaml_path.open() as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"skip {yaml_path}: {e}", file=sys.stderr)
                continue
            doc_id = data.get("doc_id") or yaml_path.stem
            for s in data.get("scenarios") or []:
                entries.append({
                    "scenario_id": f"{doc_id}::{s.get('scenario_id', '?')}",
                    "doc_id": doc_id,
                    "doc_type": doc_type[:-1],
                    "title": s.get("title", ""),
                    "tags": s.get("tags", []),
                })
    return entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--testing-root", default="testing/assistant")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    testing_root = Path(args.testing_root)
    out_path = Path(args.out)

    entries = collect(testing_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(entries, f, indent=2)
    print(f"wrote {len(entries)} scenarios to {out_path}")


if __name__ == "__main__":
    main()

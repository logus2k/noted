"""A/B probe for KV prefix-cache reuse under workspace-context volatility.

Sends K consecutive turns over one client_id with a synthetic notebook
attached via context_descriptor, then reports wall_clock per turn.

Two scenarios:
  --stable   : same notebook content every turn (workspace context is stable;
               cache should hit on system+tools+history+context)
  --volatile : one cell rewritten per turn (workspace context changes each
               turn; under the OLD message ordering this collapsed the cache
               to system+tools only, since context sat BEFORE history. Under
               the NEW ordering, history stays cached and only the volatile
               tail re-prefills.)

If the change is doing its job, --stable and --volatile should be close in
per-turn wall clock for turns >= 2. Big delta would mean the volatile slot
is still invalidating cached history.

Usage:
  python3 kv_cache_workspace_probe.py --scenario stable   --turns 4
  python3 kv_cache_workspace_probe.py --scenario volatile --turns 4
"""
import argparse
import json
import sys
import time
import urllib.request

URL = "http://localhost:8123/api/llm/chat"

# Stay under NOTEBOOK_INLINE_THRESHOLD_CHARS (60000) so the notebook is
# inlined into the workspace-context block (otherwise it's just metadata,
# which defeats the point of the probe).
CELL_TEMPLATE = (
    "# Cell {idx} - synthetic content for KV cache probe\n"
    "import numpy as np\n"
    "import pandas as pd\n"
    "\n"
    "def transform_{idx}(df):\n"
    '    """Apply transform pass {idx}."""\n'
    "    out = df.copy()\n"
    "    for col in out.select_dtypes(include='number').columns:\n"
    "        out[col] = (out[col] - out[col].mean()) / (out[col].std() + 1e-9)\n"
    "    out['__pass_{idx}'] = np.arange(len(out)) % {idx}\n"
    "    return out\n"
    "\n"
    "result_{idx} = transform_{idx}(pd.DataFrame({{'x': range(100)}}))\n"
    "{filler}"
)
FILLER_LINE = "# pad pad pad pad pad pad pad pad pad pad pad pad pad pad pad pad\n"


def make_cell(idx: int, version: int = 0, target_chars: int = 800) -> dict:
    """Build a synthetic notebook cell. version > 0 mutates the body so the
    same `idx` produces different content across turns (volatile scenario)."""
    body = CELL_TEMPLATE.format(idx=idx, filler="")
    if version > 0:
        body += f"# version={version}\n"
        body += f"result_{idx}_v{version} = result_{idx}.head({version % 7 + 1})\n"
    while len(body) < target_chars:
        body += FILLER_LINE
    return {"cell_type": "code", "source": body}


def make_notebook(num_cells: int, mutated_cell: int = -1, version: int = 0) -> list:
    """Return a list of cell dicts. If mutated_cell >= 0, that single cell
    is rebuilt with the given version tag; all other cells stay identical
    across turns so only one cell's tokens differ."""
    cells = []
    for i in range(1, num_cells + 1):
        v = version if i == mutated_cell else 0
        cells.append(make_cell(i, version=v))
    return cells


def run_turn(client_id, question, cells, label):
    payload = {
        "message": question,
        "client_id": client_id,
        "think_enabled": False,
        "vector_rag_enabled": False,
        "graph_rag_enabled": False,
        "context_descriptor": {
            "project_id": "kv_probe_synthetic",
            "notebook_path": "kv_probe_synthetic.ipynb",
            "notebook_cells": cells,
        },
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    early = None
    final = None
    t_start = time.time()
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
            if not line.startswith("data:"):
                continue
            data = line[5:].lstrip()
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
            except json.JSONDecodeError:
                continue
            if "usage" in ev:
                if early is None:
                    early = ev["usage"]
                else:
                    final = ev["usage"]
    wall = time.time() - t_start
    in_tok = (early or {}).get("input_tokens", 0)
    out_tok = (final or early or {}).get("output_tokens", 0)
    return {
        "label": label, "wall": wall,
        "in": in_tok, "out": out_tok,
        "ms_per_out": (wall * 1000 / out_tok) if out_tok else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["stable", "volatile"], required=True)
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--cells", type=int, default=40,
                    help="Notebook size in cells. ~800 chars/cell.")
    ap.add_argument("--edit_position", choices=["top", "end"], default="top",
                    help="In volatile mode, where the mutated cell sits. "
                         "'top' (default) cycles cell 1, 2, 3 - worst case for "
                         "prefix cache. 'end' mutates the LAST cell - realistic "
                         "for a user editing the active cell.")
    args = ap.parse_args()

    client_id = f"kvws_{args.scenario}_{int(time.time())}"
    print(f"=== Scenario: {args.scenario} | client_id: {client_id} ===")

    questions = [
        "Reply with exactly: ack-1.",
        "Reply with exactly: ack-2.",
        "Reply with exactly: ack-3.",
        "Reply with exactly: ack-4.",
        "Reply with exactly: ack-5.",
        "Reply with exactly: ack-6.",
    ]

    rows = []
    for turn in range(1, args.turns + 1):
        if args.scenario == "stable":
            cells = make_notebook(args.cells, mutated_cell=-1, version=0)
        else:
            if args.edit_position == "end":
                # Mutate the LAST cell every turn. Realistic case: user is
                # editing the active cell at the bottom of the notebook.
                # Cache should still hit on everything before the last cell.
                mutated = args.cells
            else:
                # 'top': mutate cell 1, 2, 3, ... worst case for prefix cache.
                mutated = ((turn - 1) % args.cells) + 1
            cells = make_notebook(args.cells, mutated_cell=mutated, version=turn)
        try:
            row = run_turn(client_id, questions[turn - 1], cells, f"turn{turn}")
        except Exception as e:
            print(f"turn{turn} failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        rows.append(row)
        ms = f"{row['ms_per_out']:.1f}" if row["ms_per_out"] else "n/a"
        print(f"  turn{turn}: wall={row['wall']:.2f}s  in={row['in']}  out={row['out']}  ms/out={ms}")

    if len(rows) >= 2:
        warm = rows[1:]
        avg_wall = sum(r["wall"] for r in warm) / len(warm)
        avg_ms = [r["ms_per_out"] for r in warm if r["ms_per_out"]]
        avg_ms = (sum(avg_ms) / len(avg_ms)) if avg_ms else None
        ms_str = f"{avg_ms:.1f}" if avg_ms else "n/a"
        print(f"\n  [warm avg, turns 2..{len(rows)}] wall={avg_wall:.2f}s  ms/out={ms_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

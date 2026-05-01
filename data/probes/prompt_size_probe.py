"""Measure prompt size via the SSE `usage` events.

Two usage events fire per turn:
  - Early (right after context_block): input_tokens = prompt-only estimate,
    output_tokens = 0. This is the "what we sent to Gemma to start" size.
  - Final (before [DONE]): input_tokens = same, output_tokens = generated tokens.

Usage:
  python3 prompt_size_probe.py --question "What is the EU AI Act about?"
  python3 prompt_size_probe.py --question "Hi" --client_id same_session
"""
import argparse
import json
import sys
import time
import urllib.request

URL = "http://localhost:8123/api/llm/chat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--client_id", default=None,
                    help="Reuse to thread turns into the same conversation.")
    ap.add_argument("--vector", type=int, default=1)
    ap.add_argument("--graph", type=int, default=1)
    ap.add_argument("--think", type=int, default=1)
    ap.add_argument("--label", default="probe")
    args = ap.parse_args()

    client_id = args.client_id or f"size_{args.label}_{int(time.time())}"
    payload = {
        "message": args.question,
        "client_id": client_id,
        "think_enabled": bool(args.think),
        "vector_rag_enabled": bool(args.vector),
        "graph_rag_enabled": bool(args.graph),
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    early = None
    final = None
    tools = []
    t_start = time.time()

    try:
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
                elif "tool_badge" in ev:
                    tools.append(ev["tool_badge"]["name"])
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    total = time.time() - t_start
    if not early:
        print(f"[{args.label}] no usage event captured", file=sys.stderr)
        return 1

    budget = early.get("context_budget", 131072)
    in_tok = early.get("input_tokens", 0)
    out_tok = (final or early).get("output_tokens", 0)
    used = in_tok + out_tok

    print(f"[{args.label}] q={args.question[:60]!r}")
    print(f"  client_id        = {client_id}")
    print(f"  input_tokens     = {in_tok:>7}  ({in_tok/budget*100:.1f}% of {budget})")
    print(f"  output_tokens    = {out_tok:>7}")
    print(f"  total_this_turn  = {used:>7}  ({used/budget*100:.1f}% of {budget})")
    print(f"  tools            = {tools or 'none'}")
    print(f"  wall_clock       = {total:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

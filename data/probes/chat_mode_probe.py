"""Probe POST /api/llm/chat with vector_rag/graph_rag toggles, parse SSE, summarize.

Usage:
  python3 chat_mode_probe.py --label both --vector 1 --graph 1 --question "..."
  python3 chat_mode_probe.py --label vector --vector 1 --graph 0 --question "..."
  python3 chat_mode_probe.py --label graph --vector 0 --graph 1 --question "..."

Writes <label>.json next to this script. Prints a one-line summary on stdout.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

URL = "http://localhost:8123/api/llm/chat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--vector", type=int, required=True)
    ap.add_argument("--graph", type=int, required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--timeout", type=int, default=240)
    args = ap.parse_args()

    payload = {
        "message": args.question,
        "client_id": f"probe_{args.label}_{int(time.time())}",
        "think_enabled": True,
        "vector_rag_enabled": bool(args.vector),
        "graph_rag_enabled": bool(args.graph),
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    t_start = time.time()
    t_first_event = None
    t_first_thinking_token = None
    t_first_answer_token = None
    t_done = None

    raw_token_parts = []
    skills = []
    tool_badges = []
    tool_results = []
    graph_provenance = None
    context_block = None
    seen_close_think = False
    errors = []

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].lstrip()
                if data == "[DONE]":
                    t_done = time.time()
                    break
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue

                now = time.time()
                if t_first_event is None:
                    t_first_event = now

                if "skills" in ev:
                    skills = ev["skills"]
                elif "context_block" in ev:
                    context_block = ev["context_block"]
                elif "token" in ev:
                    tok = ev["token"]
                    raw_token_parts.append(tok)
                    if t_first_thinking_token is None:
                        t_first_thinking_token = now
                    if not seen_close_think:
                        joined_tail = "".join(raw_token_parts[-8:])
                        if "</think>" in joined_tail:
                            seen_close_think = True
                            t_first_answer_token = now
                elif "tool_badge" in ev:
                    tb = ev["tool_badge"]
                    tool_badges.append({"name": tb.get("name"),
                                        "args": tb.get("args", {})})
                elif "tool_result" in ev:
                    tr = ev["tool_result"]
                    res = tr.get("result", "")
                    preview = res if len(res) <= 800 else res[:800] + "...(truncated)"
                    tool_results.append({"name": tr.get("name"),
                                         "result_preview": preview,
                                         "truncated": tr.get("truncated", False),
                                         "result_length": len(res)})
                elif "graph_provenance" in ev:
                    graph_provenance = ev["graph_provenance"]
                elif "error" in ev:
                    errors.append(ev["error"])
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")

    t_end = time.time()
    if t_done is None:
        t_done = t_end

    full_text = "".join(raw_token_parts)
    answer_text = full_text
    for marker in ("</think>", "<|/think|>", "</thinking>"):
        if marker in answer_text:
            answer_text = answer_text.split(marker, 1)[1]
            break

    summary = {
        "label": args.label,
        "question": args.question,
        "flags": {"vector_rag": bool(args.vector),
                  "graph_rag": bool(args.graph)},
        "timings_seconds": {
            "to_first_event": round(t_first_event - t_start, 3) if t_first_event else None,
            "to_first_token": round(t_first_thinking_token - t_start, 3) if t_first_thinking_token else None,
            "to_first_answer_token": round(t_first_answer_token - t_start, 3) if t_first_answer_token else None,
            "to_done": round(t_done - t_start, 3),
            "total": round(t_end - t_start, 3),
        },
        "skills": skills,
        "tool_calls": tool_badges,
        "tool_results": tool_results,
        "has_graph_provenance": graph_provenance is not None,
        "graph_provenance_preview": (graph_provenance if graph_provenance is None
                                     else {k: (v if not isinstance(v, list)
                                              else f"<list len={len(v)}>")
                                          for k, v in graph_provenance.items()}),
        "raw_token_count": len(raw_token_parts),
        "full_text_length": len(full_text),
        "answer_text_length": len(answer_text),
        "answer_text": answer_text,
        "full_text": full_text,
        "errors": errors,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"{args.label}.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    t = summary["timings_seconds"]
    print(f"[{args.label}] events_in {t['to_first_event']}s | first_tok {t['to_first_token']}s | "
          f"answer_tok {t['to_first_answer_token']}s | done {t['to_done']}s | total {t['total']}s | "
          f"tools={[tb['name'] for tb in tool_badges]} | "
          f"answer_chars={summary['answer_text_length']} | errors={len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

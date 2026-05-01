"""Multi-question ablation suite: where does GraphRAG actually earn its keep?

Runs the FULL / VEC-only / GRAPH-only ablation across questions of
different shapes:
  - factual   : "What is X?" - chunks should dominate
  - relational: "How are X and Y connected?" - graph should help
  - multi-hop : "What's connected to X via Y?" - graph should excel
  - summary   : "Summarize X" - chunks should dominate
  - comparative: "How does X differ from Y?" - graph might help
  - thematic  : "What is X about?" - mixed

For each question, we capture:
  - Per-variant answer text + length
  - Jaccard(FULL, VEC) - overlap when graph is removed
  - FULL_only_words and VEC_only_words - the qualitative diff
  - GRAPH-alone answer length - signal of how much graph alone produces

Then we report which question types actually benefited from the graph.
The point is to know whether GraphRAG is earning its keep, not to
defend it.
"""

import json
import time
import urllib.request
import re
from pathlib import Path

NOTED = "http://localhost:8123/api/llm/chat"
AGENT = "http://localhost:7701/v1/chat/completions"
MODEL = "noted"
PROJECT = "Examples"

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

QUESTIONS = [
    ("factual",     "What is the noted-serving container for?"),
    ("factual",     "What does Hydra do in noted?"),
    ("relational",  "How are MLflow and DVC connected in noted?"),
    ("relational",  "How does the Run Manager relate to MLflow?"),
    ("multi_hop",   "How does data versioning flow from DVC through to a deployed model?"),
    ("summary",     "Summarize how noted handles experiment tracking."),
    ("comparative", "How does the notebook execution path differ from the Airflow DAG path?"),
    ("thematic",    "What is the overall MLOps story noted tells?"),
]


def _post_json(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _post_stream(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
            if line.startswith("data:"):
                payload = line[5:].lstrip()
                if payload == "[DONE]": break
                try: events.append(json.loads(payload))
                except Exception: pass
    return events


def get_real_tool_result(question: str) -> str:
    body = {
        "message": question, "client_id": f"ablate-{int(time.time()*1000)}",
        "think_enabled": False, "temperature": 0.5, "max_tokens": 32,
        "context_descriptor": {"project_id": PROJECT},
    }
    for ev in _post_stream(NOTED, body):
        if isinstance(ev, dict) and "tool_result" in ev:
            tr = ev["tool_result"]
            return tr.get("result") if isinstance(tr, dict) else str(tr)
    return ""


def split_tool_result(text: str) -> dict | None:
    chunks_idx = text.find("## Documentation chunks")
    graph_idx = text.find("## Knowledge graph context")
    if chunks_idx < 0 or graph_idx < 0:
        return None
    header = text[:chunks_idx].rstrip()
    chunks_section = text[chunks_idx:graph_idx].rstrip()
    graph_section = text[graph_idx:].rstrip()
    return {
        "FULL": text,
        "VEC": (header + "\n\n" + chunks_section + "\n\n## Knowledge graph context\n_(graph section removed for this ablation)_").strip(),
        "GRAPH": (header + "\n\n## Documentation chunks (vector RAG)\n_(chunks section removed for this ablation)_\n\n" + graph_section).strip(),
    }


def synthesize(question: str, tool_result: str) -> tuple[str, float]:
    sys_msg = (
        "You are answering a question about the noted MLOps platform. "
        "You are given a tool result with two sections (one may be marked "
        "as removed for this test). Synthesize ONE coherent answer from "
        "whatever sections are populated. Do not include raw entity IDs."
    )
    user_msg = f"Question: {question}\n\nTool result:\n\n{tool_result}\n\nNow write the answer."
    t0 = time.perf_counter()
    resp = _post_json(AGENT, {
        "model": MODEL, "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3, "max_tokens": 1500, "stream": False,
    })
    elapsed = time.perf_counter() - t0
    text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return text, elapsed


def tokenize(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def jaccard(a: set, b: set) -> float:
    if not a and not b: return 1.0
    return len(a & b) / max(1, len(a | b))


def main():
    rows = []
    print(f"{'qtype':12s} {'FULL':>5s} {'VEC':>5s} {'GRAPH':>5s} {'J(F,V)':>7s} {'F-only':>7s} {'V-only':>7s}  question")
    print("-" * 120)

    full_dump = []
    for qtype, q in QUESTIONS:
        tr = get_real_tool_result(q)
        if not tr:
            print(f"{qtype:12s}  TOOL DID NOT FIRE - skipping  {q!r}")
            continue
        variants = split_tool_result(tr)
        if not variants:
            print(f"{qtype:12s}  TOOL RESULT had unexpected format  {q!r}")
            continue

        answers = {}
        for label, text in variants.items():
            ans, dt = synthesize(q, text)
            answers[label] = {"text": ans, "len": len(ans), "elapsed": dt}

        tok = {k: tokenize(v["text"]) for k, v in answers.items()}
        j_fv = jaccard(tok["FULL"], tok["VEC"])
        full_only = tok["FULL"] - tok["VEC"]
        vec_only = tok["VEC"] - tok["FULL"]

        rows.append({
            "qtype": qtype, "question": q,
            "len_FULL": answers["FULL"]["len"],
            "len_VEC": answers["VEC"]["len"],
            "len_GRAPH": answers["GRAPH"]["len"],
            "jaccard_FULL_VEC": j_fv,
            "n_FULL_only_words": len(full_only),
            "n_VEC_only_words": len(vec_only),
            "FULL_only_sample": sorted(full_only)[:20],
            "answers": {k: v["text"] for k, v in answers.items()},
        })
        print(f"{qtype:12s} {answers['FULL']['len']:>5d} {answers['VEC']['len']:>5d} {answers['GRAPH']['len']:>5d} {j_fv:>7.3f} {len(full_only):>7d} {len(vec_only):>7d}  {q[:60]}")
        full_dump.append({"qtype": qtype, "q": q, "answers": {k: v["text"] for k, v in answers.items()}})

    out = {"rows": rows}
    with open(OUT_DIR / "ablation_suite_results.json", "w") as f:
        json.dump(out, f, indent=2)
    with open(OUT_DIR / "ablation_suite_answers.md", "w") as f:
        for d in full_dump:
            f.write(f"\n# [{d['qtype']}] {d['q']}\n\n")
            for label in ("VEC", "GRAPH", "FULL"):
                f.write(f"\n## {label}\n\n{d['answers'][label]}\n")

    print()
    print("Summary:")
    if not rows:
        print("  no data")
        return
    avg_jaccard = sum(r["jaccard_FULL_VEC"] for r in rows) / len(rows)
    avg_full_only = sum(r["n_FULL_only_words"] for r in rows) / len(rows)
    print(f"  avg Jaccard(FULL, VEC): {avg_jaccard:.3f}  (1.0 = identical, lower = graph changed answer more)")
    print(f"  avg unique-to-FULL words: {avg_full_only:.1f}")
    print()
    by_type = {}
    for r in rows:
        by_type.setdefault(r["qtype"], []).append(r["jaccard_FULL_VEC"])
    print("  Jaccard by question type (lower = graph helped more):")
    for qt, js in sorted(by_type.items()):
        avg = sum(js)/len(js)
        print(f"    {qt:12s}  avg J={avg:.3f}  (n={len(js)})")
    print()
    print(f"  full results -> {OUT_DIR/'ablation_suite_results.json'}")
    print(f"  raw answers  -> {OUT_DIR/'ablation_suite_answers.md'}  (read these to judge qualitatively)")


if __name__ == "__main__":
    main()

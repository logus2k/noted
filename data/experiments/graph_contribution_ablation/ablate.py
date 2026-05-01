"""Ablation test: does the LLM ACTUALLY consider the graph context, or
does it answer from chunks alone (with the graph section as decoration)?

Methodology:
  1. Run graph_and_vector_search to get the real two-section tool result.
  2. Split the tool result into:
     - FULL  (chunks + graph)         — what the user sees today
     - VEC   (chunks only)            — strip the "## Knowledge graph context" section
     - GRAPH (graph only)             — strip the "## Documentation chunks" section
  3. For each variant, ask Gemma directly via agent_server with the noted
     agent's standard system prompt and a synthetic tool-result message,
     so we control what context the model actually sees. (Bypasses the
     chat router's tool-loop so we know precisely what was fed in.)
  4. Compare the three answers:
     - If FULL ≈ VEC, the graph contributed nothing observable.
     - If FULL has facts/relationships not in VEC, graph IS being used.
     - GRAPH alone shows what the graph half can produce on its own.

  This is an ablation, not a judge: we read the actual prose and see what
  changes. Token-overlap stats are also reported as a quantitative cross-
  check, but the qualitative diff is the point.
"""

import json
import time
import urllib.request
import re
from pathlib import Path

NOTED = "http://localhost:8123/api/llm/chat"
AGENT = "http://localhost:7701/v1/chat/completions"
MODEL = "noted"  # the agent name (resolves to noted preset on agent_server)

QUESTION = "How are MLflow and DVC connected in noted?"
PROJECT = "Examples"

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _post_json(url, body, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _post_stream(url, body, timeout=180):
    """SSE stream consumer; returns list of parsed events."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
            if line.startswith("data:"):
                payload = line[5:].lstrip()
                if payload == "[DONE]":
                    break
                try:
                    events.append(json.loads(payload))
                except Exception:
                    pass
    return events


def get_real_tool_result() -> str:
    """Trigger graph_and_vector_search via the chat endpoint and capture
    the actual tool_result string fed to the LLM."""
    body = {
        "message": QUESTION,
        "client_id": f"ablate-{int(time.time())}",
        "think_enabled": False,
        "temperature": 0.5,
        "max_tokens": 32,  # small - we just need the tool to fire
        "context_descriptor": {"project_id": PROJECT},
    }
    for ev in _post_stream(NOTED, body):
        if isinstance(ev, dict) and "tool_result" in ev:
            tr = ev["tool_result"]
            return tr.get("result") if isinstance(tr, dict) else str(tr)
    return ""


def split_tool_result(text: str) -> dict:
    """Split into chunks-only / graph-only variants."""
    chunks_idx = text.find("## Documentation chunks")
    graph_idx = text.find("## Knowledge graph context")
    if chunks_idx < 0 or graph_idx < 0:
        raise ValueError(f"Could not find both sections (chunks={chunks_idx}, graph={graph_idx})")
    header = text[:chunks_idx].rstrip()
    chunks_section = text[chunks_idx:graph_idx].rstrip()
    graph_section = text[graph_idx:].rstrip()
    return {
        "FULL": text,
        "VEC": (header + "\n\n" + chunks_section + "\n\n## Knowledge graph context\n_(graph section removed for this ablation)_").strip(),
        "GRAPH": (header + "\n\n## Documentation chunks (vector RAG)\n_(chunks section removed for this ablation)_\n\n" + graph_section).strip(),
    }


def synthesize(tool_result: str, label: str) -> tuple[str, float]:
    """Ask Gemma to synthesize an answer from the given tool result. We
    construct a minimal message list - skip the noted system prompt and
    skill so we test the LLM's free behavior with the given context."""
    sys_msg = (
        "You are answering a question about the noted MLOps platform. "
        "You are given a tool result containing two sections: documentation "
        "chunks and knowledge graph context. Synthesize ONE coherent answer "
        "from whatever sections are populated. Do NOT include raw entity "
        "IDs (term:foo) in the answer - phrase entities naturally. End "
        "with a Sources block listing the specific chunk source_paths AND "
        "graph entity names you actually used."
    )
    user_msg = (
        f"Question: {QUESTION}\n\n"
        f"Tool result:\n\n{tool_result}\n\n"
        f"Now write the answer."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_msg},
    ]
    t0 = time.perf_counter()
    resp = _post_json(AGENT, {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1500,
        "stream": False,
    }, timeout=180)
    elapsed = time.perf_counter() - t0
    text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return text, elapsed


def tokenize(s: str) -> set:
    """Lower-case word set, alphanumeric only - rough but consistent."""
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def main():
    print(f"Question: {QUESTION!r}\n")
    print("Step 1: capture real tool result via chat endpoint...")
    full = get_real_tool_result()
    if not full:
        print("FAILED to capture tool_result. Is graph_and_vector_search firing?")
        return
    print(f"  got {len(full)} chars")

    print("Step 2: split into FULL / VEC / GRAPH variants...")
    variants = split_tool_result(full)
    for k, v in variants.items():
        print(f"  {k:>5s}: {len(v):>5d} chars")

    print("\nStep 3: synthesize from each variant via agent_server (Gemma)...")
    answers = {}
    for label, tool_result in variants.items():
        print(f"  {label}...", end=" ", flush=True)
        text, dt = synthesize(tool_result, label)
        answers[label] = {"text": text, "elapsed": dt, "len": len(text)}
        print(f"{dt:.1f}s, {len(text)} chars")

    # Quantitative diff
    print("\nStep 4: token-set overlap (Jaccard) — quick quantitative signal")
    tok = {k: tokenize(v["text"]) for k, v in answers.items()}
    print(f"  Jaccard(FULL, VEC):   {jaccard(tok['FULL'], tok['VEC']):.3f}")
    print(f"  Jaccard(FULL, GRAPH): {jaccard(tok['FULL'], tok['GRAPH']):.3f}")
    print(f"  Jaccard(VEC, GRAPH):  {jaccard(tok['VEC'], tok['GRAPH']):.3f}")
    print()
    full_only = tok["FULL"] - tok["VEC"]
    vec_only = tok["VEC"] - tok["FULL"]
    print(f"  Words in FULL not in VEC: {len(full_only)} (sample: {sorted(full_only)[:15]})")
    print(f"  Words in VEC not in FULL: {len(vec_only)} (sample: {sorted(vec_only)[:15]})")

    out = {
        "question": QUESTION,
        "tool_result_full_chars": len(full),
        "variants": {k: {"len": len(v)} for k, v in variants.items()},
        "answers": answers,
        "jaccard": {
            "FULL_vs_VEC": jaccard(tok['FULL'], tok['VEC']),
            "FULL_vs_GRAPH": jaccard(tok['FULL'], tok['GRAPH']),
            "VEC_vs_GRAPH": jaccard(tok['VEC'], tok['GRAPH']),
        },
        "FULL_only_words": sorted(full_only),
        "VEC_only_words": sorted(vec_only),
    }
    out_path = OUT_DIR / "ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}")

    print("\n" + "=" * 70)
    print("READ THE THREE ANSWERS BELOW (the qualitative test):")
    print("=" * 70)
    for label in ("VEC", "GRAPH", "FULL"):
        print(f"\n--- {label} ({answers[label]['len']} chars) ---")
        print(answers[label]["text"])


if __name__ == "__main__":
    main()

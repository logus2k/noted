"""Discrete per-operation timing profile for one assistant turn.

Probes each leaf operation independently (no code instrumentation needed)
plus times the full chat turn end-to-end via SSE. Then derives the
unattributed slices by subtraction.

Operations profiled:
  - /embed (bge-m3 query embedding)
  - /search_by_vector (chunk Chroma + reranker)
  - /cache/search_by_vector (entity Chroma, no reranker)
  - ArcadeDB BFS hop (Cypher)
  - ArcadeDB node fetch
  - ArcadeDB edge fetch
  - ArcadeDB chunk-text fetch
  - Full /research/retrieve (graph composite)
  - Full chat turn (SSE: badge / tool_result / first token / last token / done)

Each leaf is run TRIALS times (warm). Reports min/avg/max.
"""

import json
import time
import urllib.request
import statistics
from base64 import b64encode
from pathlib import Path

QUESTION = "what is noted about"
PROJECT = "Examples"
TRIALS = 5

NOTED   = "http://localhost:8123/api/llm/chat"
RAG     = "http://localhost:8201"
GRAPH   = "http://localhost:5523"
ARCADE  = "http://localhost:2480"
ARCADE_AUTH = "Basic " + b64encode(b"root:noted-dev").decode()
ARCADE_DB = "noted"

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)


def post_json(url: str, body: dict, headers: dict | None = None, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def cypher(command: str, params: dict | None = None):
    """Same shape the noted-graph ArcadeDBClient uses: language=cypher,
    POST /api/v1/query/{db} for read-only queries."""
    body = {"language": "cypher", "command": command}
    if params:
        body["params"] = params
    return post_json(
        f"{ARCADE}/api/v1/query/{ARCADE_DB}",
        body,
        headers={"Authorization": ARCADE_AUTH},
    )


def time_n(label: str, fn, n=TRIALS) -> dict:
    times = []
    # 1 warmup
    fn()
    for _ in range(n):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return {
        "label": label,
        "n": n,
        "min_ms": min(times),
        "avg_ms": sum(times) / len(times),
        "max_ms": max(times),
    }


def main():
    print(f"Question: {QUESTION!r}\n")

    # ── Step 0: embed once to get the vector for downstream probes
    embed_resp = post_json(f"{RAG}/embed", {"texts": [QUESTION]})
    vector = embed_resp["vectors"][0]

    rows = []

    # ── Group A: noted-rag operations ──────────────────────────────
    rows.append(time_n("/embed (1 text, bge-m3)", lambda: post_json(
        f"{RAG}/embed", {"texts": [QUESTION]})))

    rows.append(time_n("/search_by_vector top_k=5 (chroma + reranker)", lambda: post_json(
        f"{RAG}/search_by_vector",
        {"query_text": QUESTION, "vector": vector, "top_k": 5})))

    rows.append(time_n("/cache/search_by_vector top_k=5 (gr_entities, no reranker)", lambda: post_json(
        f"{RAG}/cache/search_by_vector",
        {"collection": "gr_entities", "vector": vector, "top_k": 5})))

    # Reranker isolated (search - cache_search on the same collection)
    chunk_only = time_n("/cache/search_by_vector top_k=20 (noted_corpus, no reranker)", lambda: post_json(
        f"{RAG}/cache/search_by_vector",
        {"collection": "noted_corpus", "vector": vector, "top_k": 20}))
    rows.append(chunk_only)

    # ── Group B: ArcadeDB direct queries (replicate retriever's pattern)
    # First fetch entry-entity ids so the rest of the BFS uses real data.
    entry = post_json(f"{RAG}/cache/search_by_vector",
        {"collection": "gr_entities", "vector": vector, "top_k": 5})
    entry_ids = [h["id"] for h in entry["hits"]]

    rows.append(time_n("ArcadeDB: BFS hop 1 (entry -> 1-hop neighbors)", lambda: cypher(
        '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
           WHERE a.id IN $front
             AND r.type IN $rtypes
             AND NOT b.id IN $seen
           RETURN DISTINCT b.id AS id, b.rank AS rank
           ORDER BY b.rank DESC
           LIMIT $cap''',
        {"front": entry_ids, "rtypes": ["sameAs", "similar_to", "member_of"],
         "seen": entry_ids, "cap": 30})))

    # Use a representative reached_ids set for the next 3 (entry + a small BFS expansion)
    bfs_resp = cypher(
        '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
           WHERE a.id IN $front AND r.type IN $rtypes
             AND NOT b.id IN $seen
           RETURN DISTINCT b.id AS id LIMIT $cap''',
        {"front": entry_ids, "rtypes": ["sameAs", "similar_to", "member_of"],
         "seen": entry_ids, "cap": 30})
    reached_ids = list(set(entry_ids + [r["id"] for r in bfs_resp.get("result") or []]))

    rows.append(time_n(f"ArcadeDB: node fetch (reached {len(reached_ids)} entities + props)", lambda: cypher(
        '''MATCH (n:Entity)
           WHERE n.id IN $ids
           RETURN n.id AS id, n.label AS label, n.type AS type, n.properties_json AS props''',
        {"ids": reached_ids})))

    rows.append(time_n("ArcadeDB: edge fetch (between reached entities)", lambda: cypher(
        '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
           WHERE a.id IN $ids AND b.id IN $ids
           RETURN a.id AS source, b.id AS target, r.type AS type''',
        {"ids": reached_ids})))

    # Sample chunk_ids from one of the entities' mentioned_in_chunks
    nodes_resp = cypher(
        '''MATCH (n:Entity) WHERE n.id IN $ids RETURN n.properties_json AS props LIMIT 5''',
        {"ids": reached_ids[:5]})
    chunk_ids: set[str] = set()
    for row in (nodes_resp.get("result") or []):
        try:
            p = json.loads(row.get("props") or "{}")
            for c in (p.get("mentioned_in_chunks") or [])[:3]:
                chunk_ids.add(c)
        except Exception:
            pass
    chunk_ids_list = list(chunk_ids)[:10]
    if chunk_ids_list:
        rows.append(time_n(f"ArcadeDB: chunk text fetch ({len(chunk_ids_list)} chunks)", lambda: cypher(
            '''MATCH (c:Entity {type: "markdown_chunk"})
               WHERE c.id IN $ids
               RETURN c.properties_json AS props''',
            {"ids": chunk_ids_list})))

    # ── Group C: composite - full /research/retrieve
    rows.append(time_n("/research/retrieve (full graph composite via vector)", lambda: post_json(
        f"{GRAPH}/research/retrieve",
        {"query_vector": vector, "mode": "local"})))

    # ── Group D: full chat turn via SSE
    print("Running full chat turn (3 trials)...")
    chat_milestones = []
    for i in range(3):
        body = {
            "message": QUESTION, "client_id": f"profile-{int(time.time()*1000)}",
            "think_enabled": False, "temperature": 0.5, "max_tokens": 1500,
            "context_descriptor": {"project_id": PROJECT},
        }
        req = urllib.request.Request(NOTED, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
        ms = {"badge": None, "tool_result": None, "first_token": None,
              "last_token": None, "done": None}
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].lstrip()
                if payload == "[DONE]":
                    ms["done"] = (time.perf_counter() - t0) * 1000
                    break
                try:
                    p = json.loads(payload)
                    if isinstance(p, dict):
                        if "tool_badge" in p and ms["badge"] is None:
                            ms["badge"] = (time.perf_counter() - t0) * 1000
                        elif "tool_result" in p and ms["tool_result"] is None:
                            ms["tool_result"] = (time.perf_counter() - t0) * 1000
                        elif "token" in p:
                            now = (time.perf_counter() - t0) * 1000
                            if ms["first_token"] is None:
                                ms["first_token"] = now
                            ms["last_token"] = now
                except Exception:
                    pass
        chat_milestones.append(ms)

    # ── Print report ───────────────────────────────────────────────
    print()
    print("=" * 88)
    print("LEAF OPERATIONS (warm, 5 trials each)")
    print("=" * 88)
    print(f"{'operation':70s} {'min':>6s} {'avg':>6s} {'max':>6s}")
    print("-" * 88)
    for r in rows:
        print(f"{r['label']:70s} {r['min_ms']:>6.0f} {r['avg_ms']:>6.0f} {r['max_ms']:>6.0f}")

    print()
    print("=" * 88)
    print("FULL CHAT TURN MILESTONES (3 trials, in ms from t0)")
    print("=" * 88)
    print(f"{'trial':>6s} {'badge':>7s} {'tool_result':>12s} {'first_tok':>10s} {'last_tok':>9s} {'done':>7s}  (badge->tool_result = tool exec; tool_result->first_tok = post-Gemma startup)")
    for i, ms in enumerate(chat_milestones, 1):
        def fmt(x): return f"{x:.0f}" if x is not None else "—"
        print(f"{i:>6d} {fmt(ms['badge']):>7s} {fmt(ms['tool_result']):>12s} {fmt(ms['first_token']):>10s} {fmt(ms['last_token']):>9s} {fmt(ms['done']):>7s}")

    # Derive segment averages
    pres   = [m["badge"] for m in chat_milestones if m["badge"] is not None]
    tres   = [m["tool_result"] - m["badge"] for m in chat_milestones if m["badge"] and m["tool_result"]]
    posts  = [m["first_token"] - m["tool_result"] for m in chat_milestones if m["tool_result"] and m["first_token"]]
    streams = [m["last_token"] - m["first_token"] for m in chat_milestones if m["first_token"] and m["last_token"]]
    totals = [m["done"] for m in chat_milestones if m["done"]]

    if pres and tres and posts and streams and totals:
        print()
        print("=" * 88)
        print("DERIVED SEGMENT BREAKDOWN (averages across 3 trials)")
        print("=" * 88)
        print(f"  Pre-Gemma decide (msg -> tool badge):    {sum(pres)/len(pres):>6.0f} ms  [skills load + LLM tool routing]")
        print(f"  Tool execution (badge -> tool_result):   {sum(tres)/len(tres):>6.0f} ms  [embed + parallel(rag, graph) + format]")
        print(f"  Post-Gemma startup (tool_result -> tok): {sum(posts)/len(posts):>6.0f} ms  [LLM prompt processing on tool result]")
        print(f"  Streaming generation (first -> last):    {sum(streams)/len(streams):>6.0f} ms  [LLM token-by-token]")
        print(f"  TOTAL turn (msg -> done):                {sum(totals)/len(totals):>6.0f} ms")
        print()
        # Tool execution attribution
        # leaf rag total = embed + search_by_vector
        embed_avg = next((r["avg_ms"] for r in rows if "/embed" in r["label"]), 0)
        rag_avg = next((r["avg_ms"] for r in rows if "/search_by_vector" in r["label"] and "noted_corpus" not in r["label"]), 0)
        chunk_only_avg = chunk_only["avg_ms"]
        graph_avg = next((r["avg_ms"] for r in rows if "/research/retrieve" in r["label"]), 0)
        rerank_est = max(0, rag_avg - chunk_only_avg)
        tool_exec_avg = sum(tres)/len(tres)
        in_parallel = max(rag_avg, graph_avg)
        orchestration = tool_exec_avg - embed_avg - in_parallel
        print(f"  Inside Tool execution ({tool_exec_avg:.0f} ms):")
        print(f"    embed (sequential up-front):       {embed_avg:>6.0f} ms")
        print(f"    parallel(rag {rag_avg:.0f} ms, graph {graph_avg:.0f} ms) = max =  {in_parallel:>6.0f} ms")
        print(f"      └─ rerank component (rag - chroma_only): ~{rerank_est:.0f} ms inside rag")
        print(f"    orchestration / format / HTTP overhead:  {orchestration:>6.0f} ms")

    # Save raw data
    out = {"question": QUESTION, "leaf_ops": rows, "chat_milestones": chat_milestones}
    with open(OUT_DIR / "profile_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nRaw data -> {OUT_DIR/'profile_results.json'}")


if __name__ == "__main__":
    main()

"""Benchmark gr_entities first-hop lookup: ChromaDB (via noted-rag) vs
ArcadeDB LSM_VECTOR.

Methodology:
  - 30 query strings (real GraphRAG-style questions)
  - Embed each ONCE up front via noted-rag /embed (bge-m3, 1024d)
  - Pre-warm both stores (3 throwaway calls each)
  - For each query, run TRIALS=5 calls against each path, top_k=10
  - Path A (Chroma_e2e): POST /cache/search with the text. This embeds
    on the rag side AND queries Chroma. Reflects production reality.
  - Path A' (Chroma_lookup): Chroma_e2e - Embed_alone, isolating the
    Chroma lookup from the embed cost.
  - Path B (Arcade_vec): SELECT vectorNeighbors(...) over HTTP with the
    pre-embedded vector. Pure lookup time.
  - Path B' (Arcade_e2e): Embed_alone + Arcade_vec. The "swap-in"
    production-equivalent comparison.
  - Embed_alone: POST /embed with one text. Same model both paths.
  - Top-K agreement: Jaccard overlap of the result-id sets between
    Chroma and Arcade for each query (ranking-quality sanity check).
"""

import json
import time
import urllib.request
import urllib.error
import statistics
from base64 import b64encode

ARCADE = "http://localhost:2480"
RAG = "http://localhost:8201"
AUTH_ARCADE = "Basic " + b64encode(b"root:noted-dev").decode()

TRIALS = 5
TOP_K = 10

QUERIES = [
    "what does noted do for model serving",
    "how does the assistant route between RAG and graph search",
    "describe the GraphRAG rebuild pipeline",
    "what is hydra used for in noted",
    "how do communities get summarized",
    "explain leiden clustering on entities",
    "how does the embedding cache work",
    "what is the role of mlflow in the stack",
    "what changes were made to the explorer panel",
    "how is airflow integrated with notebook runs",
    "what does the run manager wrap around mlflow",
    "explain the time machine feature",
    "how is dvc used for dataset versioning",
    "what is the role of arcadedb in graphrag",
    "how does pagerank get computed across entities",
    "what is the chunk size for documents",
    "describe the hybrid retrieval mode",
    "how does noted-rag rerank chunk results",
    "what is the gemma model used for",
    "how does the composer expose hydra overrides",
    "what monitoring stack is used for drift",
    "describe the tutorial 3 jena weather pipeline",
    "what is the agent server preset noted_judge",
    "how does the skill system route user questions",
    "what is the canonical key for entities",
    "explain sameAs vs similar_to edges",
    "how is the BFS retriever bounded",
    "what does the local mode of GraphRAG retrieve",
    "how are entity types classified",
    "what is the citation tag format used by gemma",
]


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 60.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def embed_one(text: str) -> tuple[list[float], float]:
    """Returns (vector, latency_seconds)."""
    t = time.perf_counter()
    out = post_json(f"{RAG}/embed", {"texts": [text]})
    dt = time.perf_counter() - t
    return out["vectors"][0], dt


def chroma_e2e(text: str) -> tuple[list[str], float]:
    """End-to-end: text -> /cache/search returns ranked ids."""
    t = time.perf_counter()
    out = post_json(
        f"{RAG}/cache/search",
        {"collection": "gr_entities", "query": text, "top_k": TOP_K},
    )
    dt = time.perf_counter() - t
    ids = [h["id"] for h in out.get("hits", [])]
    return ids, dt


def arcade_vec(vec: list[float]) -> tuple[list[str], float]:
    """Pure lookup: pre-embedded vector -> vectorNeighbors -> ranked ids."""
    body = {
        "language": "sql",
        "command": (
            "SELECT id FROM (SELECT expand(vectorNeighbors("
            f"'GrEntity[embedding]', :v, {TOP_K})))"
        ),
        "params": {"v": vec},
    }
    t = time.perf_counter()
    out = post_json(
        f"{ARCADE}/api/v1/command/vector_bench",
        body,
        headers={"Authorization": AUTH_ARCADE},
    )
    dt = time.perf_counter() - t
    ids = [r["id"] for r in out.get("result", [])]
    return ids, dt


def stats(xs: list[float]) -> dict:
    s = sorted(xs)
    n = len(s)
    p = lambda q: s[min(n - 1, int(round(q * (n - 1))))]
    return {
        "n": n,
        "mean_ms": 1000 * statistics.mean(s),
        "p50_ms": 1000 * p(0.50),
        "p95_ms": 1000 * p(0.95),
        "min_ms": 1000 * s[0],
        "max_ms": 1000 * s[-1],
    }


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0


def main():
    print("=== warmup (3 each) ===")
    for _ in range(3):
        chroma_e2e("warmup")
        v, _ = embed_one("warmup")
        arcade_vec(v)

    print("=== embedding queries ===")
    qvecs = []
    embed_lat = []
    for q in QUERIES:
        v, dt = embed_one(q)
        qvecs.append(v)
        embed_lat.append(dt)
    print(f"  embedded {len(QUERIES)} queries; embed p50={1000*statistics.median(embed_lat):.1f}ms")

    print(f"=== timing ({TRIALS} trials each, top_k={TOP_K}) ===")
    chroma_e2e_lat = []
    arcade_vec_lat = []
    jaccards = []

    for i, (q, v) in enumerate(zip(QUERIES, qvecs)):
        # Capture one set of ids per path for the overlap check
        ids_c_ref, ids_a_ref = None, None
        for t_i in range(TRIALS):
            ids_c, dt_c = chroma_e2e(q)
            chroma_e2e_lat.append(dt_c)
            ids_a, dt_a = arcade_vec(v)
            arcade_vec_lat.append(dt_a)
            if t_i == 0:
                ids_c_ref, ids_a_ref = ids_c, ids_a
        jaccards.append(jaccard(ids_c_ref, ids_a_ref))
        if i % 5 == 0:
            print(f"  q{i:02d}: chroma_e2e={1000*dt_c:.1f}ms arcade_vec={1000*dt_a:.1f}ms jaccard={jaccards[-1]:.2f}")

    # Embed-alone baseline (separately measured)
    print("=== embed-alone baseline ===")
    embed_only_lat = []
    for q in QUERIES:
        for _ in range(TRIALS):
            _, dt = embed_one(q)
            embed_only_lat.append(dt)

    s_chroma_e2e = stats(chroma_e2e_lat)
    s_embed = stats(embed_only_lat)
    s_arcade_vec = stats(arcade_vec_lat)

    # Derived: chroma_lookup = chroma_e2e - embed_alone; arcade_e2e = embed + arcade_vec
    chroma_lookup_lat = [
        c - e for c, e in zip(
            sorted(chroma_e2e_lat),
            sorted(embed_only_lat),
        )
    ]
    arcade_e2e_lat = [
        e + a for e, a in zip(
            sorted(embed_only_lat),
            sorted(arcade_vec_lat),
        )
    ]

    results = {
        "config": {
            "queries": len(QUERIES),
            "trials": TRIALS,
            "top_k": TOP_K,
            "n_entities": 1701,
            "embedding_dim": 1024,
            "embedder": "BAAI/bge-m3",
        },
        "embed_alone": s_embed,
        "chroma_e2e": s_chroma_e2e,
        "chroma_lookup_only_estimated": stats(chroma_lookup_lat),
        "arcade_vector_lookup_only": s_arcade_vec,
        "arcade_e2e_estimated": stats(arcade_e2e_lat),
        "jaccard_top10_overlap": {
            "mean": statistics.mean(jaccards),
            "median": statistics.median(jaccards),
            "min": min(jaccards),
            "max": max(jaccards),
            "n_perfect_match": sum(1 for j in jaccards if j == 1.0),
            "n_queries": len(jaccards),
        },
        "per_query_jaccard": dict(zip(QUERIES, jaccards)),
    }

    out_path = "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n=== results written to {out_path} ===")

    print("\n=== summary (median latencies) ===")
    print(f"  embed_alone:              {s_embed['p50_ms']:>7.1f} ms")
    print(f"  chroma_e2e (text->ids):   {s_chroma_e2e['p50_ms']:>7.1f} ms")
    print(f"  arcade_vec (vec->ids):    {s_arcade_vec['p50_ms']:>7.1f} ms")
    print(f"  jaccard top-10 mean:      {results['jaccard_top10_overlap']['mean']:.3f}")


if __name__ == "__main__":
    main()

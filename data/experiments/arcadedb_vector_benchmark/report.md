# ChromaDB vs ArcadeDB LSM_VECTOR — first-hop benchmark for noted's GraphRAG

Settle the question: would replacing the noted-rag/ChromaDB embedding cache
with an in-database `LSM_VECTOR` index in ArcadeDB measurably improve
first-hop retrieval latency for noted's GraphRAG path?

## Setup

- **Hardware**: same host as noted; both services on the same Docker bridge.
- **ArcadeDB**: 26.3.2 (one minor behind 26.4.2). Sandbox DB `vector_bench`,
  separate from `noted-graph` so the live thematic graph is untouched.
- **noted-rag**: in-place, talking to the live `gr_entities` collection
  (1701 entries, 1024-d `bge-m3`).
- **ArcadeDB schema**: `GrEntity {id, text, embedding ARRAY_OF_FLOATS}`,
  unique index on `id`, `LSM_VECTOR METADATA { dimensions: 1024,
  similarity: 'COSINE', maxConnections: 32, beamWidth: 200 }`.
  - **Default HNSW params on 26.3.2 under-recall on 1024-d normalized
    vectors.** With defaults the bench got top-K = pure noise on some
    queries (e.g. for "BFS retriever bounded", top hit was `concept:rlock`
    while the actual nearest by manual cosine was `concept:bfs` at
    distance 0.50). Bumping to `maxConnections: 32 / beamWidth: 200`
    restored top-3 = exact match against ChromaDB.
- **Mirror**: full 1701 entries dumped from ChromaDB and re-inserted with
  their precomputed `bge-m3` embeddings (3.5 s, single-threaded HTTP).

## Methodology

- 30 GraphRAG-style query strings (see `benchmark.py`).
- 3 warmup calls per path, then 5 trials per query per path.
- Same 30 query vectors, embedded once via `noted-rag /embed`, used for
  both paths.
- Paths timed:
  - **chroma_e2e** — `POST /cache/search` with the text. Includes the
    embedding step on the rag side. This is the production path today.
  - **arcade_vec** — `SELECT vectorNeighbors('GrEntity[embedding]', $vec, 10)`
    over HTTP, with the pre-embedded vector. Pure lookup time.
  - **embed_alone** — `POST /embed` with one text. Same model both paths.
  - Derived **chroma_lookup** (chroma_e2e − embed_alone) and
    **arcade_e2e** (embed_alone + arcade_vec) for an apples-to-apples
    swap-in comparison.
- Top-K agreement: Jaccard overlap of result-id sets between the two
  paths for each query, top-K = 10.

## Results

| Path | p50 | p95 | mean |
|---|---:|---:|---:|
| `embed_alone` | 10.2 ms | 12.4 ms | 10.7 ms |
| `chroma_e2e` (text → ids, prod path) | 13.1 ms | 16.4 ms | 13.9 ms |
| `chroma_lookup` (estimated, e2e − embed) | 3.4 ms | 4.2 ms | 3.5 ms |
| `arcade_vec` (vec → ids, pure lookup) | 3.2 ms | 3.6 ms | 3.2 ms |
| `arcade_e2e` (embed + arcade_vec) | 13.0 ms | 16.1 ms | 13.7 ms |

Top-10 Jaccard between paths (same query vectors):

- mean **0.79**, median 0.82, min 0.18
- 13 / 30 queries return identical top-10
- Where they disagree, top-3 still matches in nearly every case; the
  divergence is in the long tail (positions 4–10), expected behavior for
  two different ANN implementations on close-ranked items.

## Interpretation

1. **Pure lookup is essentially a tie.** ChromaDB ~3.4 ms vs ArcadeDB
   ~3.2 ms — within trial noise. Both are HNSW under the hood; both run
   on a localhost docker bridge. The store choice is not the bottleneck.

2. **Embedding dominates the production-path latency**: ~10 ms of the
   ~13 ms `cache_search` total is the `bge-m3` forward pass. Swapping
   stores changes the 3 ms portion, not the 10 ms portion.

3. **End-to-end equivalence**: `chroma_e2e` 13.1 ms ≈ `arcade_e2e`
   13.0 ms. A drop-in replacement saves no measurable wall-clock time
   on the first-hop lookup.

4. **Quality is comparable but not identical.** With tuned HNSW params,
   ArcadeDB returns the same top-3 for the queries inspected, but
   long-tail rankings drift (mean Jaccard 0.79). For the BFS retriever,
   first hop is `top_k=5`, so this almost certainly does not change
   downstream answers — but it would need a regression test against the
   GraphRAG validation suite before any production swap.

## Caveats

- **First hop only.** This benchmark does NOT measure community
  summary lookups, BFS expansion, or the rerank step. Those are mostly
  independent of where the vectors live, but a full end-to-end
  GraphRAG comparison is its own experiment.
- **noted-rag's reranker is bypassed.** The `gr_entities` cache path
  doesn't rerank, so this is a fair measurement of *that* path. The
  chat-RAG path (`noted_corpus`) does rerank, and replacing it would
  also replace the reranker, which is a much bigger architectural
  change.
- **HNSW recall depends on tuning.** ArcadeDB's defaults under-recall at
  1024d. Anyone evaluating a real migration must rebuild with explicit
  `maxConnections` / `beamWidth` (and potentially `efSearch` per query
  on 26.4.2; the 4-arg form 500-errored on 26.3.2 in this run).
- **Mirror was full-RW HTTP one-row-per-call.** Insert was 3.5 s for
  1701 entries — fast enough to ignore, but a real rebuild would want
  bulk insert.

## Recommendation

**Do not migrate `gr_entities` to ArcadeDB on latency grounds alone.**
The first-hop wall-clock saves ~0.2 ms; the production path is
embedding-bound and would not measurably improve.

The one defensible reason to consolidate is *architectural*: a single
hybrid query like `vectorHybridScore` or `vectorRRFScore` (26.4.2) could
fuse vector-similarity and graph-traversal scoring in one round-trip.
That's a different question from "is ArcadeDB's vector store faster
than Chroma's." Worth revisiting if/when:
- The GraphRAG retriever's BFS layer becomes the dominant latency, OR
- We move to ArcadeDB 26.4.2 and want to test `vectorHybridScore` end-to-end, OR
- We want to drop noted-rag entirely (the chat-RAG path also moves).

In its current shape, the cost of disrupting noted-rag (which serves
the chat-RAG reranker path) is not justified by a 0.2 ms first-hop saving.

## Reproduce

```
cd data/experiments/arcadedb_vector_benchmark
python3 mirror_to_arcadedb.py    # rebuilds the sandbox DB from the dump
python3 benchmark.py             # writes results.json
```

Sandbox DB `vector_bench` lives in the running noted-arcadedb container
and can be dropped at any time without touching `noted-graph`.

## Artifacts

- `gr_entities_dump.json` — full ChromaDB dump (1701 × 1024d, ~38 MB)
- `mirror_to_arcadedb.py` — schema + insert script (sandbox)
- `benchmark.py` — query set, timing harness, Jaccard check
- `results.json` — full per-path stats and per-query Jaccard scores

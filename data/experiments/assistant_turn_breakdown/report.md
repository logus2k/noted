# Assistant turn latency breakdown — measured, not guessed

End-to-end traces of `POST /api/llm/chat` (the same endpoint the chat UI
hits), with SSE timestamps captured per event, plus isolated timings of
the underlying tool endpoints.

Captured 2026-04-25 against the live noted stack (Examples project,
think_enabled=false, native tool calling).

## Method

`trace.py` posts to `/api/llm/chat`, reads the SSE stream chunk-by-chunk,
and timestamps every event. Three event boundaries matter:

1. `t_tool_call_emit` — Assistant Gemma finishes its pre-tool reasoning
   and emits the tool-call event. (Time spent: pre-Gemma)
2. `t_tool_result` — the tool returns and its result is fed back in.
   (Time spent: tool execution)
3. `t_done` — Assistant Gemma finishes streaming the user-facing reply.
   (Time spent: post-Gemma synthesis)

Tool endpoints (`/research/query` on noted-graph; `/search` on noted-rag)
are timed separately to confirm where the tool-execution time goes.

## Results

### Path A — research_topic (thematic question)

Question: *"summarize how MLflow and DVC connect in noted"*

| Stage | t (s) | Δ (s) | Share | What runs here |
|---|---:|---:|---:|---|
| Assistant Gemma decides + emits tool call | 0.00 → 1.33 | **1.33** | 12% | Skill-loaded LLM call, tool routing |
| `research_topic` tool execution | 1.33 → 8.24 | **6.91** | 64% | retriever (BFS + vec + summary fetch) + **internal Gemma synthesis** (the markdown answer) |
| Assistant Gemma writes user-facing reply | 8.24 → 10.72 | **2.48** | 23% | 208-token re-synthesis of what the tool already produced |
| **Total** | | **10.72** | | |

Confirmation: `/research/query` called directly returns in **7.66 s** for
the same question — matches the 6.91s tool-execution slice plus a bit of
HTTP overhead through the noted backend.

### Path B — search_docs (fact-lookup question)

Question: *"what is hydra used for in noted"*

| Stage | t (s) | Δ (s) | Share | What runs here |
|---|---:|---:|---:|---|
| Assistant Gemma decides + emits tool call | 0.00 → 1.91 | **1.91** | 20% | Skill-loaded LLM call, tool routing |
| `search_docs` tool execution | 1.91 → 3.59 | **1.69** | 18% | noted-rag `/search` (embed + Chroma + reranker) + HTTP |
| Assistant Gemma writes user-facing reply | 3.59 → 9.61 | **6.02** | 63% | 631-token synthesis from raw chunks |
| **Total** | | **9.61** | | |

Confirmation: noted-rag `/search` direct = **640 ms warm** (5 trials:
1787 / 646 / 633 / 643 / 640). The 1.69s vs 640ms gap is the noted
backend's tool dispatch + HTTP roundtrip.

## What the data says

1. **The data layer is invisible.** The 10ms ChromaDB lookup I keep
   citing is buried inside the 640ms reranker, which is buried inside
   the 1.69s tool slice, which is itself ~18% of the turn.
   Consolidation into ArcadeDB would chase a sub-percent saving.

2. **LLM compute is everything.** Both turns are 9-11s. Both are
   dominated by Gemma forward passes. The split differs by path:
   - research_topic: 64% of the turn IS Gemma (inside the tool's own synthesis)
   - search_docs: 63% of the turn IS Gemma (post-tool synthesis)

3. **research_topic literally does the work twice.** The tool's
   internal Gemma synthesis produces a ~1500-char answer with
   citations. Then Assistant Gemma re-reads that finished answer and
   writes a 208-token paraphrase. **6.91s of internal synthesis +
   2.48s of re-synthesis ≈ 9.4s of LLM compute to answer one
   question.** Collapsing this to one synthesis call would save ~2.5s
   per research_topic turn outright, with no quality loss (the
   tool's synthesis is already user-ready).

4. **search_docs is closer to optimal**: tool returns raw chunks, one
   post-tool Gemma pass synthesizes. The 6s post-synthesis is the
   token-generation cost for a 631-token answer. Cap the answer length
   and that drops linearly.

5. **Pre-Gemma deciding takes 1.3-1.9s for ~7 input tokens.** That's
   not generation cost — that's prompt-processing and tool-decision.
   This is the *cheapest* stage to attack (smaller tool list via
   dynamic context routing already exists for Anthropic; could extend
   to local Gemma).

## What "consolidation into ArcadeDB" would actually save

Given the breakdown above:
- **Best case** consolidation (single hybrid query, no double synthesis):
  shaves the data-layer overhead from ~50-100ms to ~10ms. Sub-1% of
  the turn.
- **NOT addressed by consolidation**: pre-Gemma decide (1.3-1.9s),
  internal Gemma synthesis (6.9s), post-Gemma synthesis (2.5-6.0s).

These are all LLM compute, all on the same hardware, all unaffected by
where vectors live.

## What WOULD measurably move the needle

In rough order of impact-per-effort:

| Fix | Estimated saving | Effort |
|---|---|---|
| **Streaming the post-Gemma reply** (already does emit but shows no incremental tokens here — investigate event flow) | -2 to -5s perceived | small |
| **Skip post-Gemma re-synthesis when the tool already returned a finished answer** (research_topic case) | -2.5s wall-clock | medium |
| **Cap synthesis length** for routine questions (drop max_tokens default) | linear in saved tokens | trivial |
| **Pre-warm Gemma KV cache on tool-call emit** (so post-tool resumption is faster) | -0.5 to -1s | medium |
| **Parallel tool calls** (call research_topic AND search_docs concurrently when both are plausible, fuse results) | +N seconds total compute, but overlaps with each other | medium |
| Migrate ChromaDB → ArcadeDB | ~0.05s | weeks |

## Reproduce

```
cd data/experiments/assistant_turn_breakdown
python3 trace.py
```

Question is hardcoded at the top of `trace.py`. Edit and re-run.
Outputs `trace_results.json` with full per-event SSE timeline.

## Files

- `trace.py` — SSE timing harness
- `trace_results_search_docs.json` — full event timeline, fact-lookup path
- `trace_results_research_topic.json` — full event timeline, thematic path

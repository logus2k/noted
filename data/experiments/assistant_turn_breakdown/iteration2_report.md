# Iteration 2 — presentation fixes + parallel `graph_and_vector_search`

After the three-phase latency fix landed, two issues surfaced:
1. Inline citation tags (`[E:...]`, `[R:...]`, `[Cn]`, `[markdown_chunk:hex]`)
   leaked into the user-visible stream because Phase 2/3 emit the raw
   research_topic answer.
2. Gemma's conversational lead-in to its tool call ("The user is asking
   for X. I will use research_topic...") leaked because the streaming
   bypassed the Assistant-Gemma re-synthesis that used to swallow it.

Plus a new architectural request: instead of XOR routing (search_docs
OR research_topic per turn), fan out to BOTH in parallel and let
Assistant Gemma synthesize from both sources at once.

This iteration ships both, measured.

## Presentation fixes

### Citation-tag strip

Added `CitationTagFilter` in [llm.py:208](backend/app/routers/llm.py#L208).
Holds back partial bracket sequences to avoid mid-stream flicker; only
matches the four GraphRAG tag forms (plain markdown `[link](url)` is
untouched). Applied to:
- Phase 3 deep-stream loop ([llm.py:734-749](backend/app/routers/llm.py#L734-L749))
  — strip per-token before yield
- Phase 2 bypass ([llm.py:782-784](backend/app/routers/llm.py#L782-L784))
  — strip the whole tool_result string before single yield

Tags remain in the upstream `tool_result` (memory + grounding) and in
the envelope's `citations` field for any future Sources/footer UI.

**Verification** — same question (`"summarize how MLflow and DVC connect"`):

| Metric | Before fix | After fix |
|---|---:|---:|
| Citation tags in user-visible answer | many (`[E:...]`, `[R:...]` everywhere) | **0** |

### Conversational lead-in drop

Modified `_prepare_text_for_frontend(intermediate=True)` at
[llm.py:526-535](backend/app/routers/llm.py#L526-L535). On tool-call
turns, keeps **only** the `<think>...</think>` block (if any) and drops
both the pre-think preamble AND the conversational lead-in to the tool
call ("I will use X to answer Y"). Non-tool turns are unaffected.

## Parallel retrieval — new tool `graph_and_vector_search`

### What changed

- **noted-graph**: new method
  [`Retriever.local_mode_retrieve`](graph/app/retrieval/retriever.py#L342)
  runs the BFS retrieval (entry vector hits + N-hop traversal + chunk
  excerpts) and returns a structured bundle WITHOUT calling Gemma.
  Eliminates the 2-3 s internal synthesis when the chat layer is going
  to synthesize anyway.
- **noted-graph**: new endpoint
  [`POST /research/retrieve`](graph/app/routers/research.py#L102)
  exposes the bundle. Local mode only; auto/global fall back to the
  existing `/query` (which DOES synthesize).
- **noted-backend**: new manager method
  [`GraphRagManager.retrieve`](backend/app/managers/graphrag_manager.py#L59)
  — async client for the new endpoint with the standard
  `{status: unavailable, ...}` graceful-degradation fallback.
- **noted-backend**: new tool definition
  [`graph_and_vector_search`](backend/app/mcp/tools.py#L301) +
  dispatch + handler
  [`_tool_graph_and_vector_search`](backend/app/managers/llm_tools.py#L2581).
  The handler fans out to noted-rag `/search` and noted-graph
  `/research/retrieve` in parallel via `asyncio.gather`, formats both
  result sets into a single markdown-ish payload, and returns one
  string for the Assistant Gemma to synthesize from.

### Retrieval timing (parallel vs sequential)

Same question against live services:

| Path | Latency |
|---|---:|
| noted-rag `/search` (cold) | 5582 ms |
| noted-graph `/research/retrieve` | 534 ms |
| **Parallel via `asyncio.gather`** | **1034 ms** (warm rag) vs 6116 ms sequential sum |

(First trial's noted-rag was cold; subsequent calls were sub-second.
The parallel branch took max(rag_warm, graph) ≈ 1s — exactly what fan-out
should achieve.)

### End-to-end chat trace using the new tool

Forced via `"Use graph_and_vector_search to answer: summarize how MLflow
and DVC connect in noted"` so the LLM picks the new tool (skill rubric
unchanged for this iteration — see "What's NOT changed" below):

| Metric | Phase 3 (research_topic) | Phase 3 fixed (research_topic, tags stripped) | New tool (graph_and_vector_search) |
|---|---:|---:|---:|
| Total turn | 5.49 s | 7.42 s | 11.68 s |
| Time-to-first-token | 4.10 s | 4.46 s | 9.27 s |
| Token events | 110-140 | 328 | 269 |
| Inline citation tags in answer | many | 0 | 0 |
| Answer source | graph synth only | graph synth only (cleaned) | **chunks + graph, fused by Assistant Gemma** |
| Answer structure | direct synth output | direct synth output (cleaned) | **structured numbered list with bold headings** |

### Trade-off captured

| Dimension | Phase 3 (single-source, deep-stream) | New tool (dual-source, post-synth) |
|---|---|---|
| Wall-clock | Faster (~5-7 s) | Slower (~11-12 s) |
| Quality | Raw graph synth output | **Structured, in-Assistant-voice, both sources** |
| Coverage | Graph only | **Vector chunks + graph entities/edges** |
| TTFT | Earlier (~4 s) | Later (~9 s) |
| Streaming | Live during graph synth | Live during Assistant synth (after parallel retrieve) |

The new tool trades ~4-5 s wall-clock for substantially better answer
quality + dual-source coverage. The XOR limitation that motivated
Phase 2/3 in the first place is gone: a single user question now gets
grounded in BOTH the documentation chunks AND the knowledge graph
context, in one Assistant-Gemma synthesis pass.

### Sample new-tool answer (clean structure, no tag noise)

```
MLflow and DVC connect in *noted* through a system of automatic
tagging and lineage tracking that ensures reproducibility across
different execution paths (notebook vs. Airflow DAG). Here is a
summary of the connection:

1. Data Provenance Tagging: When a notebook cell or DAG task
executes, *noted*'s Auto-instrumentation wraps the process in an
MLflow run. Crucially, if the code reads data tracked by DVC, the
platform automatically tags the resulting MLflow run with the DVC
content hash (`dvc.data_hash`).

2. Unified Lineage: This tagging mechanism ensures that the MLflow
run — which logs metrics, parameters, and the final model artifact
— is intrinsically linked to the exact version of the data used.

3. Knowledge Graph View: The Knowledge Graph synthesizes these
connections. ...
```

vs the prior raw graph synth output that was peppered with
`[E:concept:knowledge graph]`, `[R:term:airflow>similar_to>term:git]`
inline.

## What's NOT changed (per request to eyeball before committing)

- **docs-rag SKILL rubric** still tells Gemma to pick `search_docs` OR
  `research_topic` per turn. The new tool is registered and callable,
  but Gemma will only use it if you mention it by name (or you update
  the skill).
- **Phase 2 bypass + Phase 3 deep-stream** remain wired for direct
  `research_topic` calls — they're dormant for the new path, active for
  any caller still hitting research_topic by name.
- **Auto/global modes**: the new `/research/retrieve` endpoint
  supports `mode='local'` only and falls back to one-shot `/query` for
  other modes. Matches what auto picks for thematic noted-domain
  questions per baseline traces.

When you're ready to flip the routing: update
[data/skills/docs-rag/SKILL.md](data/skills/docs-rag/SKILL.md) to make
`graph_and_vector_search` the default for noted-domain questions, with
`search_docs` and `research_topic` reserved for "I want only chunks" /
"I want only graph synth" cases.

## Files changed (this iteration)

- `backend/app/routers/llm.py` — `CitationTagFilter` class + applied in
  Phase 2 bypass + Phase 3 stream; preamble drop in
  `_prepare_text_for_frontend`
- `backend/app/mcp/tools.py` — new `graph_and_vector_search` tool def
- `backend/app/managers/llm_tools.py` — dispatch + handler with
  `asyncio.gather` parallel fan-out
- `backend/app/managers/graphrag_manager.py` — new `retrieve()` method
- `graph/app/retrieval/retriever.py` — new `local_mode_retrieve()`
  method (retrieval-only)
- `graph/app/routers/research.py` — new `POST /research/retrieve` endpoint

Total: ~250 LOC.

## Reproduce

```
cd data/experiments/assistant_turn_breakdown

# Default trace (research_topic path with all fixes applied)
python3 trace.py

# Force the new tool by mentioning it in the question:
python3 -c "
import sys; sys.path.insert(0, '.')
import trace as t
t.QUESTION = 'Use graph_and_vector_search to answer: <your question>'
print(t.time_chat_turn(t.QUESTION))
"
```

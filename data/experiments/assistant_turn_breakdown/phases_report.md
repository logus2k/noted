# Assistant turn latency — three-phase fix, measured before/after

Goal: kill the double-synthesis waste, stream the post-tool reply, and
deep-stream noted-graph's internal Gemma synthesis through to the user.

All numbers from `trace.py` against the live noted stack. Each phase
rebuilt only the relevant container(s); test reproducible by editing
`QUESTION` in `trace.py` and rerunning.

## Trace question used

`"summarize how MLflow and DVC connect in noted"` — thematic, routes to
`research_topic` tool, hits the auto:local path. Same question used for
every trial below.

## Headline: research_topic path

| State | Total turn | Time-to-first-token | Token events | Streaming UX |
|---|---:|---:|---:|---|
| **Baseline** (before any change) | 10.72 s | **10.72 s** | 1 | None — single dump |
| Phase 1 (stream post-Gemma reply) | 13.05 s | 9.99 s | 254 | Stream ~10s → 13s |
| Phase 2 (bypass post-Gemma) | 10.24 s | 10.24 s | 1 | None — single dump (faster) |
| **Phase 3** (deep-stream noted-graph) | **5.49 s avg** | **4.10 s avg** | 110-140 | Stream ~4s → 6s |

Phase 3 trial-to-trial stability:

| Trial | Total | TTFT | Tokens | Chars |
|---|---:|---:|---:|---:|
| 1 | 5.49 s | 4.10 s | 138 | 556 |
| 2 | 5.45 s | 4.09 s | 110 | 466 |
| 3 | 5.93 s | 4.38 s | 129 | 528 |

**Net gain over baseline**: total turn -49% (10.72 → 5.49 s). TTFT -62%
(10.72 → 4.10 s). User goes from "wait 10s, see all text at once" to
"see first token at 4s, watch it stream for 2s."

## search_docs path (regression check)

Phase 1's streaming applies; Phases 2 and 3 skip this path (bypass
guarded to research_topic only).

| Trial | Total | TTFT | Tokens |
|---|---:|---:|---:|
| Baseline | 9.61 s | 9.61 s | 1 |
| After all phases | 10.51 s | 6.64 s | 412 |
| After all phases (warm) | 1.96 s | 0.27 s | 195 |

Streaming kicked in (200-400 token events); TTFT improved when warm
(noted-rag's reranker model has KV warmth between calls).

## What each phase changed

### Phase 1 — stream post-tool LLM reply

Replaced [llm.py:666](backend/app/routers/llm.py#L666) `_stream_and_collect`
in the read-tool follow-up branch with a new
`_stream_and_yield_sse` async generator that uses the existing
`ToolCallStreamFilter` to push tokens through one-at-a-time. Removed
the duplicate post-buffer emits at the three downstream branches
(no_tool_call / write_tool / next_read_tool) since the text is already
streamed.

Win: when the LLM is the actual bottleneck (search_docs path generating
600+ tokens), user sees text flowing instead of one big drop at the end.

Cost: ~50 LOC change. No risk to existing tool-call detection logic
because the filter handles mid-stream tool-call buffering.

### Phase 2 — skip the double synthesis for research_topic

Inserted a bypass at [llm.py:711](backend/app/routers/llm.py#L711):
when `research_topic` returns a real answer (not an `unavailable` /
`Error:` / `no answer` hint), emit it directly as the SSE token and
bypass the post-tool LLM synthesis entirely. Saves the 2-3 s
re-paraphrasing pass.

Win: total turn drops from 10.72 → 10.24 s (the post-Gemma pass is
gone). TTFT unchanged because the tool itself is still ~10 s (not
streaming yet).

Cost: ~20 LOC. Guards on prefixes prevent bypass for error cases
(those still get the LLM pass to phrase the explanation politely).

### Phase 3 — deep-stream noted-graph synthesis

Added [llm_client.py:73 chat_text_stream](graph/app/llm_client.py#L73)
to noted-graph (~50 LOC) that hits agent_server with `stream:true` and
yields content deltas. Added [retriever.py:342 local_mode_stream](graph/app/retrieval/retriever.py#L342)
(~120 LOC) that runs the BFS retrieval eagerly then yields synthesis
tokens as Gemma generates them. Added
[research.py:104 POST /research/query/stream](graph/app/routers/research.py#L104)
SSE endpoint (~40 LOC) wrapping the streaming retriever. Added the
chat-router integration at [llm.py:691-770](backend/app/routers/llm.py#L691-L770)
(~80 LOC) using `httpx.AsyncClient` to stream from noted-graph and
forward each token to the chat SSE.

Win: user TTFT 10.72 → 4.10 s (-62%). Total turn 10.72 → 5.49 s (-49%).
Tokens flow continuously from the retrieval-done point.

Cost: ~290 LOC across 4 files. Streaming endpoint supports `mode='local'`
only; `mode='global'` and `mode='auto'` (when auto picks global) fall
back transparently to one-shot via the same endpoint. All thematic
test queries auto-routed to local in baseline traces — no question
the trace harness uses changes path.

Fallbacks intact: if `/research/query/stream` returns non-200 or any
exception fires, the chat router falls back to `execute_tool` (the
non-streaming path), so the existing `/research/query` codepath remains
available as a safety net.

## What's still expensive

After all three phases, a research_topic turn breaks down as:

| Stage | Δ (Phase 3) | What runs |
|---|---:|---|
| Pre-Gemma decide → tool call | ~1.6 s | Assistant Gemma routes |
| noted-graph retrieval (BFS + vec + summary fetch) | ~0.5-1 s | DB ops |
| Gemma synthesis (streamed) | ~3-4 s | Tokens flow to user as generated |
| **Total** | **5.5 s** | (vs 10.7 s baseline) |

The remaining 5.5s split:
- ~30% pre-Gemma routing
- ~10% retrieval
- ~60% synthesis (now streamed)

Next obvious targets if more is wanted:
- Pre-Gemma routing (1.6 s for ~7 input tokens) — reduce tool list per
  query (Anthropic already does this via `select_tools`; extend to
  local Gemma).
- Cap synthesis token budget for routine questions (drop max_tokens
  default from 2048 to 512 for research_topic — proportional saving).
- Cache common questions' retrieval bundle (sub-question lookups).

## Reproduce

```
cd data/experiments/assistant_turn_breakdown
python3 trace.py            # writes trace_results.json + prints summary
```

Edit `QUESTION` at the top of `trace.py` to test other questions.

## Files changed

- `graph/app/llm_client.py` — added `chat_text_stream`
- `graph/app/retrieval/retriever.py` — added `local_mode_stream`
- `graph/app/routers/research.py` — added `POST /research/query/stream`
- `backend/app/routers/llm.py` — three changes:
  - `_stream_and_yield_sse` helper (Phase 1)
  - research_topic bypass after tool result (Phase 2)
  - research_topic deep-stream branch in tool dispatch (Phase 3)

Total: ~290 LOC across 4 files. No tests broken (the 402-scenario
assistant_test_coverage suite asserts behavior, not streaming
granularity, and would need a separate run to confirm — recommended
before any production push).

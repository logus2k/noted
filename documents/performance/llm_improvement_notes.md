# LLM chat-path latency improvement notes

Working notes for the next round of chat-latency optimization. Captured
2026-05-02 after the GGUF Q8 + agent_server FA + ArcadeDB native SQL wins
brought tool-call total time to ~200 ms and end-to-end chat to ~2-5 s.

## Open issue

When the model decides to call a tool, the user perceives a **1-2 second
gap** between the end of the first thinking section and the start of the
final answer. The thinking stream stops, nothing visible happens for
~1.5 s, then the answer streams. This breaks the perception of "always
something being written".

UX patches (e.g. "Searching documents..." indicator) and tool-result
trimming are explicitly out of scope per user direction — focus is on
making the actual gap shorter, not masking it.

## Hypothesised breakdown

For a `graph_and_vector_search` tool call:

| Segment | Estimated duration | Notes |
|---|---|---|
| Round-1 stream end → tool dispatch | 50-100 ms | Parser sees `</tool_call>`, server dispatches |
| Tool execution (graph + RAG, parallel) | 200-300 ms | Already optimised: graph ~70 ms, rag ~200 ms |
| Format tool result + build round-2 messages | 50-100 ms | String concatenation, message list construction |
| **Round-2 prefill** (NEW tokens only) | **700-1500 ms** | **Suspected dominant cost.** ~3-5K new tokens at ~3500 tok/s |
| Round-2 first decode token | (included above) | First token after prefill completes |

The KV cache (`LlamaRAMCache 2 GB` in agent_server) reuses K/V state for the
stable prefix (system prompt + workspace context + user message), so
round-2 only prefills the NEW content: the assistant's tool-call message
plus the formatted tool result. That tool result is non-trivial — top
entities, edges, chunk excerpts, all rendered as text.

The prefill estimate is HYPOTHESIS. It needs measurement before we commit
to a fix.

## Step 1 — instrumentation (write before guessing)

Add four timestamps in `noted/backend/app/routers/llm.py` and emit one
log line per tool-calling turn that breaks the gap into segments.

### Patch sketch (apply when noted can be rebuilt)

In the chat handler's tool-loop body, around the existing
`Tool call (round %d)` log line near [llm.py:1215](../../backend/app/routers/llm.py#L1215):

```python
import time as _t

# Just AFTER the round-N stream ends (after `_final` sentinel processed,
# before tool dispatch begins):
_round_end_ts = _t.perf_counter()

# At "Tool call (round X)" line — already exists. Add before it:
_tool_dispatch_ts = _t.perf_counter()
logger.info("Tool call (round %d): ...", ...)  # existing line

# Just AFTER `tool_result = await execute_tool(...)` returns (around llm.py:1372):
_tool_returned_ts = _t.perf_counter()

# Inside `_stream_and_yield_sse`'s token loop, on the FIRST yielded token of
# the next round, capture and emit the ROUND_GAP_TIMING line. Easiest: track
# a `_round_idx` counter outside the generator; on first token of round >= 2,
# emit and clear the captured timestamps:
_round2_first_token_ts = _t.perf_counter()
logger.info(
    "ROUND_GAP_TIMING tool=%s "
    "dispatch_ms=%.1f exec_ms=%.1f format_ms=%.1f prefill_ms=%.1f total_ms=%.1f",
    tool_name,
    (_tool_dispatch_ts - _round_end_ts) * 1000,
    (_tool_returned_ts - _tool_dispatch_ts) * 1000,
    # format + round-2 message build is between _tool_returned_ts and
    # the next chat_stream() call's first token; we approximate by
    # measuring from tool_returned to _round2_first_token_ts and
    # subtracting an estimated prefill (or just bundle them):
    0.0,  # if we don't separate, set to 0 and put it all in prefill
    (_round2_first_token_ts - _tool_returned_ts) * 1000,
    (_round2_first_token_ts - _round_end_ts) * 1000,
)
```

A cleaner version threads a small `_GapTiming` dataclass through the loop
instead of free variables. Either way, ONE log line per round-2 start
gives us the actual breakdown.

After rebuilding noted with this in place:
- Send 3-5 representative chat questions that trigger graph_and_vector_search
- `docker logs noted --since 5m | grep ROUND_GAP_TIMING` — read the
  numbers
- Decide which segment to attack

## Step 2 — interpret the numbers, decide the lever

If `prefill_ms` IS the dominant chunk (>1000 ms), the speculative-prefill
path becomes the main bet:

### Speculative round-2 prefill (the candidate fix)

The idea: the moment the tool dispatch starts, begin streaming the
assistant's tool-call message into Gemma's context as a prefill operation.
By the time the tool returns, only the tool result tokens are new and
need prefill — the assistant's tool-call message is already absorbed.

**What this requires:**
- A way to pre-warm the KV cache with partial round-2 messages while the
  tool is still running. llama-cpp-python's `Llama.eval(...)` accepts raw
  tokens and updates KV state — usable from the chat handler if we can
  reach the underlying engine.
- The tool-call message text is known at dispatch time (it's the
  assistant message we already extracted from round 1's stream).
- Once the tool returns, append the tool_result message and run normal
  `create_chat_completion` — which will reuse the speculatively prefilled
  K/V state and only need to prefill the NEW tool_result tokens.

**Honest expected win:** ~30-50% of the prefill segment. If prefill is
1000 ms, speculative could shave ~300-500 ms off it. Not free — adds
complexity, requires careful interlock with the existing prefix-cache,
and the speculation can be wasted if Gemma decides not to call a tool
(but in our chat flow, by the time we know there's a tool call, the
speculation has already been triggered, so waste is bounded).

**Alternative if prefill ISN'T the dominant chunk:** the breakdown will
point us to the actual offender. Possibilities: tool dispatch overhead
(unlikely at 50-100 ms), tool execution itself (would mean our 200 ms
estimate is wrong), or some Python orchestration cost we missed.

## Step 3 — bench the fix

If we ship speculative prefill:
- Re-bench with the same instrumentation
- Compare `prefill_ms` before/after
- Measure end-to-end: did the user-perceived gap shrink?

## Pre-conditions before resuming this work

1. Canonical / Launchpad recovers (otherwise no noted rebuild possible).
2. Domain rebuilds (started with ml) are complete — running both at
   once would ruin the measurement (rebuild competes with chat for GPU).

## Linked context

- `feedback_arcadedb_cypher_to_sql_hot_path` — earlier optimization that
  made graph traversal 25-49× faster. The 70 ms graph timing in the
  table above reflects that win.
- `project_session_2026_05_02_findings` — full session record including
  the GGUF Q8 swap, agent_server FA, citation pipeline fixes.
- `agent_server/app/llm_engine.py` — where `LlamaRAMCache(2 GB)` is
  configured. The prefix cache that makes round-2 only prefill the
  delta tokens (not the full conversation).
- `noted/backend/app/routers/llm.py` — where the tool loop runs. The
  exact place where the instrumentation goes.

# KV Cache: How It Works in This Stack

## Setup

The local-Gemma chat path runs through agent_server's OpenAI-compat endpoint
(`POST /v1/chat/completions`). agent_server enables llama_cpp's `LlamaRAMCache`
at startup with a 2 GB capacity:

```python
# agent_server/app/llm_engine.py
self.llm.set_cache(LlamaRAMCache(capacity_bytes=2 << 30))
```

There is exactly one cache surface in the entire chat path. agent_server has
no caching layer of its own (its `MemoryStrategy` system is for the Socket.IO
SDK clients only and is bypassed by noted's traffic). Pool size is 1 worker,
so all noted chat traffic hits the same `Llama` instance and therefore the
same cache.

## Two cooperating cache mechanisms

llama_cpp speeds up consecutive calls via two distinct paths:

**1. In-memory eval-state shortcut.** Inside `Llama.generate()`, before any
prefill, it computes the longest token-level prefix that matches the model's
*current* state (`self._input_ids`, left over from the previous call), then
calls `kv_cache_seq_rm` to truncate the on-GPU KV to that boundary. Only the
suffix gets prefilled. This is the fast path for "turn N+1 immediately after
turn N of the same conversation."

**2. `LlamaRAMCache` restore.** Inside `_create_completion`, before
`generate`, a separate lookup scans the RAM cache for the longest cached
prompt prefix. If the cached match is *longer* than the current eval state,
the cached state is restored via `load_state(...)`. Useful for switching
between distinct conversations on the same worker.

Both run on every call. In the dominant case (single user, single worker,
sequential turns), mechanism (1) carries the load.

## Critical rule: stable prefix, volatile suffix

KV cache matches are contiguous from token 0. ONE byte of difference at
position k invalidates every cached token from k onward. Prompt assembly must
therefore put cache-stable content first and volatile content last:

```
[BOS + chat template skeleton]
[system prompt + tool schemas]      <- byte-stable per session
[active domains]                    <- byte-stable per session
[active skills]                     <- byte-stable per session
[conversation history]              <- locked-in once each turn finalizes
[notebook | file | run | hydra]     <- volatile when user edits
[current user message]              <- always new
```

## Layout enforcement in noted

`build_context_message()` in
[`backend/app/managers/llm_context.py`](../../backend/app/managers/llm_context.py)
splits the workspace context into two lists:

- `static_blocks`  - active domains, then ACTIVE SKILLS.
- `volatile_blocks` - notebook, project imports, file, MLflow run, Hydra.

Final assembled order: `header + manifest -> static_blocks -> volatile_blocks`.

**The skills block must remain in static_blocks, not appended at the end.**
Earlier code appended skills last (after the volatile notebook block); a cell
edit then invalidated the cache for the entire ~17 K-token skills payload
sitting downstream. The static-first layout keeps the skills tokens in the
cache-friendly prefix where they belong.

## Tools array byte-stability

`payload["tools"] = tools` in `LLMManager.chat_stream`. The tools list is
deterministically ordered (verified by md5-comparison across consecutive
turns); 39 tools, identical bytes turn to turn. Anything that destabilises
this (sorting differently, dict-iteration nondeterminism, conditional tool
inclusion that flips per turn) silently destroys the cache because tools
render INTO the system block, before any user message.

## What the cache cannot do

- **Help when the divergence point is at the start of the prompt.** A
  user mutating the FIRST notebook cell invalidates everything after, by
  definition. The cache loses, and there is no fix at this layer; the only
  remedy is for the user to not edit cell 1 between every chat turn.
- **Span workers.** Each `Llama` instance has its own cache. If `pool_size`
  ever rises above 1, requests round-robin across workers and the cache
  hit rate splits proportionally. Sticky routing by `client_id` would be
  required to preserve hit rate under concurrency.
- **Survive restarts.** `LlamaRAMCache` is in-process memory. Restarting
  agent_server forces a cold rebuild on the first call. (`LlamaDiskCache`
  exists but is not currently used; the warm-up cost on a single restart
  is one slow first turn, not worth the disk I/O complexity.)

## How to verify cache behaviour

Probes live under [`data/probes/`](../../data/probes/) and persist across
rebuilds (bind-mounted):

- `kv_cache_existence_probe.py` - hits agent_server directly with a fixed
  long prompt repeated several times. Confirms both cache mechanisms fire
  and reports the wall-clock speedup.
- `kv_cache_workspace_probe.py` - sends a synthetic 40-cell notebook
  through noted's `/api/llm/chat` endpoint over multiple turns.
  - `--scenario stable` - same notebook content every turn.
  - `--scenario volatile` - mutate one cell per turn.
  - `--edit_position {top|end}` - in volatile mode, where the mutated
    cell sits. `end` is the realistic active-editor pattern; `top` is
    worst case.

To see token-level cache events from llama_cpp itself, temporarily flip
`verbose=False` to `True` in `agent_server/app/llm_engine.py`, rebuild the
app image (`bash agent_server.sh && docker compose --profile default
up -d --force-recreate`), then `docker logs agent_server | grep -E
"prefix-match hit|cache (miss|sav)"`. Revert `verbose=False` afterwards.

## Reference numbers

Snapshot taken 2026-04-30 with Gemma 4 E4B Q4 KXL on RTX 4090, 40-cell
synthetic notebook, single client_id, four turns:

| Scenario                          | Cache hit | Re-prefilled | Wall (warm) |
|-----------------------------------|-----------|--------------|-------------|
| Stable (no edits)                 | 25,576    | 18           | 2.1 s       |
| End-of-notebook edit (post-fix)   | 25,450    | 189          | 2.6 s       |
| End-of-notebook edit (pre-fix)    | 17,076    | 8,562        | 5.6 s       |
| Top-of-notebook edit (worst case) | 6,647     | 18,946       | 6.9 s       |

These will drift as the notebook size, system prompt, tool schemas, and
context blocks evolve. Re-run the probe rather than relying on the table.

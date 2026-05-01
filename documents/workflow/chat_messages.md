# Chat message workflow

End-to-end path of a chat turn from the moment the user presses **Send** until the last token of the assistant answer is rendered.

## Actors

| Component | Role |
|-----------|------|
| Frontend (`ChatPanel` + `ChatService`) | Captures input, opens SSE stream, parses events, renders tokens |
| noted backend (`/api/llm/chat` in [llm.py](../../backend/app/routers/llm.py)) | Orchestrates the turn, tool loop, persistence, usage |
| `LLMRouter` ([llm_router.py](../../backend/app/managers/llm_router.py)) | Routes to local Gemma vs Anthropic; reports context budget |
| agent_server | Runs Gemma 4 E4B; OpenAI-compatible streaming |
| noted-rag | bge-m3 embed + bge-reranker-v2-m3 cross-encoder, ChromaDB |
| noted-graph | ArcadeDB graph + per-Domain GraphRAG retriever + `noted_graph_answer` LLM preset |

## Step-by-step

### 1. Send button → POST `/api/llm/chat`

Frontend builds the JSON payload in [ChatService.js:602-609](../../frontend/js/ChatService.js#L602):

```js
{
  message,
  client_id,                        // stable per browser session
  context_descriptor: { project_id, notebook_path, ... },
  think_enabled,
  vector_rag_enabled,               // chat-bar checkbox
  graph_rag_enabled,                // chat-bar checkbox
}
```

POSTs to `api/llm/chat`. The server holds the connection open and writes Server-Sent Events as work progresses.

### 2. Backend receive + memory key

[llm.py:506-519](../../backend/app/routers/llm.py#L506) computes `memory_key = f"{client_id}_{project_id}"`. All subsequent reads/writes to conversation history use this key (in-memory dict in [llm_memory.py:ProjectMemory](../../backend/app/managers/llm_memory.py)).

### 3. Compaction check

[llm.py:522-537](../../backend/app/routers/llm.py#L522). The router calls `memory.get_compaction_input(memory_key)`. The check is in [llm_memory.py:51-56](../../backend/app/managers/llm_memory.py#L51):

```python
total_chars = sum(len(m.get("content", "")) for m in messages)
budget = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * COMPACTION_THRESHOLD
# 96_000 * 4 * 0.75 = 288_000 chars (~72K tokens)
return total_chars > budget
```

When triggered, a non-streaming Gemma call summarizes all-but-last-4 messages into ≤300 words. The active turn is **blocked** on this call (~1-3s when it fires). Failure is currently swallowed (`logger.warning`) and the turn proceeds with original history.

There is **no longer a hard message cap** — the token-volume compaction is the only mechanism. Messages are never silently dropped.

### 4. Persist user message

[llm.py:540](../../backend/app/routers/llm.py#L540): `memory.append(memory_key, "user", request.message)`.

### 5. Build workspace context + active skills

[llm.py:558](../../backend/app/routers/llm.py#L558) → [llm_context.py:42](../../backend/app/managers/llm_context.py#L42).

Assembles, in order:

| Block | Source | Trigger |
|-------|--------|---------|
| ACTIVE KNOWLEDGE BASES | [llm_context.py:_active_domains_block](../../backend/app/managers/llm_context.py#L135) | Always |
| Notebook context (cells, outputs) | `notebook_mgr` | `notebook_path` set |
| Project Python imports | `notebook_mgr` | `notebook_path` set |
| File context (.py/.yaml/.md) | static reader | `file_path` set, no notebook |
| MLflow run details | `mlflow_mgr` | `active_run_id` set |
| Hydra config | `hydra_mgr` | `hydra_config_hash` set |

Active priority-1 skills are matched by [llm_context.py:_get_matched_skills](../../backend/app/managers/llm_context.py#L183) and appended as a final block. The whole bundle is one `user`-role message prepended to the LLM history.

### 6. Stream `skills` and `context_block` SSE events

[llm.py:642-649](../../backend/app/routers/llm.py#L642). Frontend uses the `skills` event to log auto-injected skills; `context_block` carries a preview for the debug pane.

### 7. Filter and gate the model-facing tool list

[llm.py:600-635](../../backend/app/routers/llm.py#L600).

- `to_openai_tools(active_domains=...)` (or `to_anthropic_tools`) returns only tools whose owning Domain is in the active set.
- Per-turn gating drops tools the user disabled via the chat-bar checkboxes:
  - `vector_rag_enabled=false` → drop `search_docs`, `graph_and_vector_search`
  - `graph_rag_enabled=false` → drop `research_topic`, `graph_and_vector_search`, `query_knowledge_graph`
- Anthropic only: a context router (`select_tools`) further trims tools by relevance to save ~2K tokens; local Gemma sees the full filtered list.

### 8. Gemma round 1: think + decide

[llm.py:_stream_and_yield_sse](../../backend/app/routers/llm.py#L749) calls agent_server's OpenAI-compatible streaming endpoint.

- Tokens stream through `GemmaThinkingFilter` and `ToolCallStreamFilter` so internal markers (`<|tool_call>`, `call:foo{...}`, `tool_code` blocks) never reach the frontend.
- The `<think>...</think>` block streams as visible tokens; the frontend's `ThinkingParser` splits it into the collapsible reasoning section.
- Outcome is one of:
  1. **Native tool call** emitted via the OpenAI tools API (`tool_call` chunk) → continue at step 9.
  2. **Final answer** streamed as plain tokens → continue at step 12.

### 9. Tool dispatch

For each native tool call:

a. **Emit `tool_badge` SSE** ([llm.py:1045](../../backend/app/routers/llm.py#L1045)) with name + args. The frontend renders a pill in the chat bubble.

b. **Special UI-only path:** `scroll_to_cell` yields a `navigate` SSE event and skips real dispatch.

c. **`research_topic` deep-stream path** ([llm.py:1054-1181](../../backend/app/routers/llm.py#L1054)): when mode is `auto` or `local`, the chat router opens its own SSE stream to noted-graph's `/research/{kb}/query/stream`. The upstream `noted_graph_answer` LLM preset on agent_server synthesizes a finished prose answer; tokens are forwarded through `ToolCallStreamFilter` directly to the user. The chat-side Gemma does **not** re-synthesize. The reconstructed envelope (citations, mode, communities, subgraph) is stashed for the trace UI.

d. **Default path:** `execute_tool(tool_call, req_managers, ctx_dict)` in [llm_tools.py:783-818](../../backend/app/managers/llm_tools.py#L783) routes to a per-tool handler:

| Tool | Handler | Upstream call |
|------|---------|---------------|
| `search_docs` | [`_tool_search_docs`](../../backend/app/managers/llm_tools.py#L2486) | noted-rag `POST /search_multi` (Chroma fan-out + single rerank batch) |
| `research_topic` | [`_tool_research_topic`](../../backend/app/managers/llm_tools.py#L2616) | noted-graph `POST /research/{kb}/query` (BFS + upstream LLM synthesis) |
| `graph_and_vector_search` | [`_tool_graph_and_vector_search`](../../backend/app/managers/llm_tools.py#L2723) | embed once via noted-rag `/embed`, then `asyncio.gather` of `/search_multi` (chunks) and `/research/{kb}/retrieve` (raw graph) per active Domain |
| MLflow / Airflow / DVC / Hydra read tools | `_tool_get_*` | corresponding manager |
| Notebook / file read tools | `_tool_*` | `notebook_mgr`, file reader |
| Write tools (`update_cell`, `insert_cell`, `update_file`, `register_model`, etc.) | not auto-executed; routed through approval (see step 11) |

e. **Emit `tool_result` SSE** ([llm.py:1196](../../backend/app/routers/llm.py#L1196)) with up to 16K chars of the tool's output for harness/debug visibility.

f. **Emit `graph_provenance` SSE** ([llm.py:1202-1205](../../backend/app/routers/llm.py#L1202)) when the tool stashed a structured subgraph. The frontend attaches "Show graph" alongside "Show reasoning" on the streaming bubble.

### 10. Phase 2 bypass (research_topic only)

[llm.py:1219-1244](../../backend/app/routers/llm.py#L1219). When `research_topic` returns a real answer (not "unavailable" / "no answer" / "Error: ..."), the chat router skips the post-tool synthesis entirely:

- If tokens were already streamed via the deep-stream path (9c), just record `final_answer` and break the tool loop.
- Otherwise yield the answer (minus the `\n\n---\n` observability footer) directly as tokens, set `final_answer`, break.

This saves the second Gemma synthesis pass (~2-5s) when the upstream graph LLM has already produced a citation-rich prose answer.

### 11. Write tools → approval flow

If the tool call is in `WRITE_TOOL_NAMES` ([mcp/tools.py:WRITE_TOOL_NAMES](../../backend/app/mcp/tools.py#L572)), the chat router does NOT execute it. Instead it stashes the action into `_pending_actions[action_id]`, emits a `pending_action` SSE event ([llm.py:~1025](../../backend/app/routers/llm.py#L1025)), and ends the turn. The frontend renders an approval card; the user clicks Apply / Cancel which hits `/api/llm/confirm`. That endpoint executes the stashed tool (with possible feedback edits) and resumes the LLM turn from where it stopped.

### 12. Gemma round 2: synthesis (when not bypassed)

When the tool path is `search_docs` or `graph_and_vector_search` (and for write tools after approval), the chat router appends the tool result to `loop_messages` and re-invokes `_stream_and_yield_sse` with the same tool list. Gemma now writes the final answer:

- Another `<think>` block (since `think_enabled=True`) — frontend renders into the same collapsible section.
- Then the answer body. Tokens stream as `token` SSE events through `ToolCallStreamFilter`.
- If Gemma emits **another** tool call here, loop back to step 9. Per-turn round cap protects against infinite loops.

### 13. Termination + final SSE events

[llm.py:1370-1383](../../backend/app/routers/llm.py#L1370):

a. **Persist assistant turn:** `memory.append(memory_key, "assistant", assistant_text)`.

b. **Emit `usage` event:**
```python
in_tok  = actual_input_tokens or input_tokens_est        # chars/4 fallback
out_tok = actual_output_tokens or len(final_answer)//4
budget  = actual_context_budget or llm_mgr.get_context_budget()
yield {'usage': {'input_tokens', 'output_tokens', 'total_tokens', 'context_budget'}}
```
- For Anthropic: actual counts come straight from the API (`usage_tokens` chunk).
- For local Gemma: estimates from char counts; `context_budget` resolves via [LLMRouter.get_context_budget()](../../backend/app/managers/llm_router.py#L33) → `LOCAL_CONTEXT_WINDOW` (default **131072**, env-overridable via `LOCAL_LLM_CONTEXT_WINDOW`).

c. **Emit `[DONE]` sentinel.** Frontend's SSE reader breaks the read loop and finalizes the streaming bubble.

### 14. Frontend finalization

[ChatPanel.js:finalizeStreamingMessage](../../frontend/js/ChatPanel.js):

- Closes the streaming bubble; runs syntax highlighting on code blocks (hljs) and math (KaTeX).
- Renders the assistant-side citation badges (chunk / entity / relationship / community).
- Updates the bottom-bar token counter via [ChatPanel.js:updateTokenUsage](../../frontend/js/ChatPanel.js#L941). After the recent fix the percentage is computed against the real model context window (Gemma 131072 / Claude 200000), not the previous 32768 fallback.

## SSE event reference

| Event | Payload | When |
|-------|---------|------|
| `skills` | `{skills: [...]}` | Once, after context build |
| `context_block` | `{content, truncated}` | Once, after context build |
| `token` | `{token: <text>}` | One per Gemma chunk (after stream filters) |
| `tool_badge` | `{name, args}` | Each tool call |
| `tool_result` | `{name, result, truncated}` | Each tool result |
| `graph_provenance` | `{question, entities, edges, ...}` | When a graph-bearing tool stashes it |
| `pending_action` / `pending_actions` | `{action_id, action}` | Write tool routed to approval |
| `navigate` | `{cell_index}` | `scroll_to_cell` only |
| `usage` | `{input_tokens, output_tokens, total_tokens, context_budget}` | Once, before [DONE] |
| `[DONE]` | (sentinel) | End of turn |
| `error` | `{error: <msg>}` | On unrecoverable failure |

## Memory + compaction notes

- History storage: in-memory dict keyed by `{client_id}_{project_id}`. Lost on container restart.
- **Token-volume compaction** at 72K tokens of history (`MAX_CONTEXT_TOKENS=96000 × 0.75`). Replaces all-but-last-4 messages with one ≤300-word summary.
- **No hard message cap.** Messages are never silently dropped; volume-based compaction is the single mechanism.
- Compaction failure is logged but currently silent to the user — turn proceeds with full history.

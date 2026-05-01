# Skill + Tool Changes for GraphRAG

Initial proposal — iterate during testing per decision on Q3 of the 2026-04-23 design session.

## 1. New tools to register in `backend/app/mcp/tools.py`

```python
types.Tool(
    name="research_topic",
    description=(
        "Query the Knowledge Graph for thematic or relational questions that span "
        "multiple documents or entities. Use for questions like:\n"
        "  - 'how are X and Y related?'\n"
        "  - 'what are the core themes in topic Z?'\n"
        "  - 'which projects use dataset W?'\n"
        "  - 'summarize across all docs about MLflow snapshots'\n"
        "Returns a synthesized answer plus cited source entities. "
        "Do NOT use for specific-fact lookups - that's search_docs. "
        "Do NOT call both tools in the same turn."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural-language question. Be specific; the tool synthesizes across the graph."
            },
            "mode": {
                "type": "string",
                "enum": ["global", "local"],
                "description": (
                    "global = thematic summary across community summaries (best for 'what are the themes in X?'). "
                    "local = N-hop Cypher traversal from entities named in the question (best for 'how is A linked to B?'). "
                    "Default: global."
                )
            }
        },
        "required": ["question"]
    }
),
types.Tool(
    name="rebuild_knowledge_graph",
    description=(
        "Trigger an asynchronous rebuild of the Knowledge Graph from the current corpus. "
        "Returns a job id immediately; progress streams via SSE. "
        "Use when the user has added/removed markdown docs, skills, tests, or when the graph "
        "freshness indicator shows the graph is stale. "
        "Ingestion takes up to ~30 minutes; during that time `research_topic` still serves "
        "the previous graph (atomic swap on success)."
    ),
    inputSchema={
        "type": "object",
        "properties": {}
    }
),
```

## 2. `docs-rag` skill text changes

Edit [`data/skills/docs-rag/SKILL.md`](data/skills/docs-rag/SKILL.md) — add a new section, do not rewrite the existing one.

### New section to insert (after the existing `search_docs` guidance):

```
WHICH SEARCH TOOL TO USE — search_docs vs research_topic:

- `search_docs` (vector retrieval, fast): use for SPECIFIC FACTS and IDENTIFIABLE PASSAGES.
  Triggers: "what is X?", "where is Y documented?", "show me the section on Z",
  "what does the README say about W?"
  Expected result: a short answer grounded in 1-3 retrieved chunks.

- `research_topic` (graph synthesis, slower): use for THEMES and RELATIONSHIPS
  across many documents or entities.
  Triggers:
    - relational: "how is A linked to B?", "which X uses Y?", "who is involved in Z?"
    - thematic: "summarize across all docs about W", "what are the recurring themes in V?"
    - cross-document: "trace how the data flows from ingestion to model deployment"
  Expected result: synthesized text answer + cited source entities.

RULES:
- NEVER call both tools in one turn. They return different shapes.
- If both seem to apply, start with `search_docs`. Only escalate to
  `research_topic` if `search_docs` returned nothing relevant OR if the
  question explicitly asks to "summarize across", "trace", "connect", or
  "relate".
- If `research_topic` returns no relevant subgraph (empty citations), tell
  the user and suggest they may need to rebuild the Knowledge Graph
  (the response includes a `graph_built_at` timestamp - if it is old and
  the user recently added content, stale graph is the likely cause).
- Do NOT pitch `rebuild_knowledge_graph` unless the user asks to refresh
  the graph OR `research_topic` returned an empty/stale response.
```

## 3. Result-envelope contract for `research_topic`

The skill should also tell the model what shape to expect back, so it can use `citations` in its final answer:

```
`research_topic` returns a JSON envelope:
  {
    "answer": "<markdown-formatted synthesized answer>",
    "citations": [ {"entity_id", "entity_type", "label", "doc_path"} ],
    "subgraph": { "entities": [...], "relationships": [...] },
    "mode": "global" | "local",
    "communities_used": [...],
    "graph_built_at": "<ISO timestamp>"
  }

In your final answer: quote directly from `answer` when summarizing; cite the
entities from `citations` by label (click-jumps will work in the UI); mention
`graph_built_at` if the user seems skeptical about freshness.
```

## 4. Validation plan

Add test scenarios to `testing/assistant/tools/research_topic.yaml` following the existing 402-scenario format. Initial suggested coverage:

| Scenario | Tag | user_request | expected_tools_called | Notes |
|---|---|---|---|---|
| S1 | theme | "summarize across all docs what noted's MLOps stack provides" | `research_topic` mode=global | Classic thematic. |
| S2 | relation | "how is the Jena Weather project connected to DVC?" | `research_topic` mode=local | Entity-to-entity. |
| S3 | regression | "what is the tracking URI for MLflow in noted?" | `search_docs` | Must not route to graph. |
| S4 | regression | "where is the `start_run` code injected?" | `search_docs` | Specific-code lookup. |
| S5 | ambiguous-to-graph | "connect the Composer to the Time Machine feature" | `research_topic` mode=local | "connect" trigger word. |
| S6 | ambiguous-to-search | "what does the Composer do?" | `search_docs` | Definition-style. |
| S7 | refresh | "rebuild the knowledge graph" | `rebuild_knowledge_graph` | Explicit user ask. |
| S8 | freshness | (after mock stale response) "why is the answer out of date?" | `research_topic` called, answer mentions `graph_built_at` | Verifies the freshness pattern in the answer. |

After ~20 scenarios land and pass reliably, consider this skill section stable. Iterate on the rubric text based on failure patterns the harness surfaces.

## 5. Phase 1 rollout order for skill text

1. Ship tools (`research_topic`, `rebuild_knowledge_graph`) with docs-rag skill text update BEFORE the backend is wired. Tools return 501 Not Implemented placeholders. Harness can start testing tool-routing decisions immediately.
2. Backend goes live — tools return real responses.
3. Extend harness with the scenarios above.
4. Tune skill text based on harness results.

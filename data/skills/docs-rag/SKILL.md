---
name: docs-rag
description: Route noted-domain questions to graph_and_vector_search (parallel chunks + graph context, fused by Assistant) by default. Reserve search_docs / research_topic for the rare cases where you specifically want only one source. NEVER answer noted-domain questions from internal knowledge.
triggers: [workspace_active]
priority: 1
max_tokens: 500
---
ANY question about noted MUST trigger one of the three retrieval tools below. NEVER answer noted-domain questions from internal weights or prior context alone — that risks fabrication.

## DEFAULT: graph_and_vector_search

For nearly every noted-domain question, call `graph_and_vector_search(question)`. It runs noted-rag (vector chunks) AND the knowledge graph (entities + relationships) IN PARALLEL and returns one combined payload — at the same wall-clock cost as either single source. You then synthesize ONE cohesive answer from both sources.

This replaces the prior either/or routing between `search_docs` and `research_topic`. The combined payload gives you specific facts (chunks) AND thematic context (graph) in one turn, which produces stronger, better-grounded answers.

Examples (all go to `graph_and_vector_search`):
- "What does noted do for model serving?"
- "How are MLflow and DVC connected in noted?"
- "Summarize noted's data versioning approach"
- "What is hydra used for in noted?"
- "How does the Composer relate to the Time Machine?"
- "What is the MLflow tracking URI?"
- "Where is start_run injected?"
- "How do I configure DVC remotes?"

Call: `graph_and_vector_search(question, top_k_chunks?=5)`. Phrase as a full sentence; expand pronouns into the entity name first (turn "how does it handle X" into "how does noted handle X") — the reranker scores literal text.

## Single-source fallbacks (rare)

Use `search_docs(query, tags?, top_k=5, source_paths?)` ONLY when you specifically want chunks-only retrieval and want to skip the graph (e.g., debugging the corpus, or when the user explicitly asks "search the docs for ...").

**search_docs Domain handling — read carefully:**

- search_docs ALREADY queries every active Knowledge Domain in parallel and merges the results. There is NO parameter to scope to a single Domain.
- The Domain names listed in workspace context (e.g. "EU Artificial Intelligence", "Software Agents") are NOT filter values. Do NOT pass them in `tags`, `source_paths`, or anywhere else.
- `tags` filters CHUNK CONTENT TYPE (the `doc_type` metadata stored on each chunk at ingestion). Values are corpus-specific (the noted product corpus uses `user-manual`, `developer-manual`, `architecture`, etc.; other corpora may have none of those). When in doubt, omit `tags`.
- `source_paths` restricts to chunks whose source_path is a specific FILENAME (e.g. `['eu_ai_act.pdf']`, `['user_manual.md']`). Never a Domain name.

Use `research_topic(question, mode?="auto", domain_id?)` ONLY when you specifically want a graph-only synthesized answer (e.g., the user asks for a graph view, communities, or thematic summary backed by the knowledge graph alone). The `domain_id` parameter on this tool DOES scope to a single Domain — but it expects a slug (`sw_arch`, `eu_ai`, `noted`), NOT the human-readable name.

In both cases, prefer `graph_and_vector_search` unless you have a concrete reason to suppress one source.

## NEVER use any of these tools for

- Live state (use get_run_details, get_dag_status, list_dags, list_registered_models, list_model_versions, get_experiment_runs)
- User's notebook cells or source files (use get_notebook_cells, get_file_contents, get_hydra_config)
- Topics already fully covered by an active skill this turn

## Result handling — graph_and_vector_search

The tool returns one markdown payload with two sections:
1. **Documentation chunks (vector RAG)** — N ranked chunks, each with `source_path#section_path` and a relevance score.
2. **Knowledge graph context** — entry entities, top entities with descriptions, relationships, and supporting chunk excerpts.

Synthesize ONE answer that fuses both sources. The graph entities and relationships give thematic structure (what relates to what); the chunks give specific facts and quotes. Phrase entities and relationships naturally in prose — do NOT inline raw entity IDs like `term:foo` or relationship arrows like `term:a>similar_to>term:b`.

If the tool reports either section as unavailable / empty, synthesize from the other section and tell the user briefly which source was missing. Do NOT fabricate to fill a gap.

## Result handling — search_docs (legacy / single-source path)

- Chunks returned: synthesize and cite each claim with `source_path#section_path`. Do not pad with content not in the chunks.
- Zero chunks: rephrase ONCE with different vocabulary then retry. If still empty, say plainly the docs do not cover this question. Do NOT frame the gap as "I do not have a document titled X".
- "Documentation search is currently unavailable": tell the user the service did not respond. No silent fallback. No invented content.

## Result handling — research_topic (legacy / single-source path)

- Returns an answer with inline citation tags. Cite forms used: `[Cn]` (community), `[E:entity_id]` (entity), `[R:src>type>tgt]` (relationship), `[markdown_chunk:hex]` (source chunk). The chat layer strips these tags before display, so do NOT include them in your final reply — phrase entities and relationships naturally.
- Empty citations or "knowledge graph does not cover this": say so plainly. Optionally offer `graph_and_vector_search` if the question might be better-served by including chunks.
- "GraphRAG is currently unreachable": tell the user the service is down. Do NOT fabricate.

## Avoid these phrasings (silent-degradation traps)

- "I don't have a document titled X" — docs aren't titled by question
- "Documentation is unavailable, here's what I think" — silent degradation
- "Based on my general knowledge..." after a no-match — ungrounded

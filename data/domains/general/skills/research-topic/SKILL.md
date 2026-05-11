---
name: research-topic
description: When the user asks for "articles about", "research on", "look up", or similar multi-source web research, use the request_new_research workflow — NOT web_search alone.
type: tool_skill
priority: 1
max_tokens: 800
triggers: ["always"]
---
**MANDATORY DISPATCH RULE**

When the user message matches any of the patterns in the table below, you MUST start the iterative research workflow via `request_new_research` instead of calling `web_search` directly. The workflow runs a researcher+reviewer loop in the background, populates a structured document with citations, and pauses for your supervisor review — far higher quality than a one-shot `web_search`.

| User says... | Required action |
|---|---|
| "Search for articles about X" | request_new_research (NOT web_search) |
| "Find articles about X" | request_new_research |
| "Research X" / "Research whether X" | request_new_research |
| "Look up X" / "Look into X" | request_new_research |
| "Find me information on X" | request_new_research |
| "Compile a report on X" | request_new_research |
| "Is there an API for X and how to use it" | request_new_research |
| "Investigate X" | request_new_research |
| "What's the latest on X" | request_new_research |
| "What does the web say about X" | request_new_research |

`web_search` alone is for: a single fact you'd cite inline in a chat answer (one URL, one snippet, one sentence). Anything that would produce a multi-paragraph answer goes through the workflow.

**KICKOFF SEQUENCE (mandatory order)**

When dispatching to `request_new_research`:

1. **First** call `create_doc` to create the workspace buffer. Give it a descriptive filename (e.g. `"ups-api-research.md"`, `"openmythos-articles.md"`). Capture the `buffer_id` it returns.
2. **Then** derive 2-5 `acceptance_criteria` from the user's request. Each criterion is one short bullet stating something the document must satisfy. Example for "Search for articles about OpenMythos":
    - Identify the core concepts or purpose of OpenMythos
    - List the most relevant articles and primary sources
    - Summarize the current state and adoption
3. **Then** call `request_new_research({"goal": "<user's question, verbatim>", "acceptance_criteria": [...], "notes_doc_id": "<buffer_id>"})`.
4. Tell the user in 1-2 sentences what's being researched. Do NOT wait or block — return control.

**SUPERVISOR TURN (you'll get a workflow_suspended notice)**

When the workflow pauses for user review, a system notice will arrive. Follow its instructions exactly: read_doc → submit_research_decision (mandatory tool call) → then narrate to user. The decision call comes BEFORE the narration, not after.

**WHEN NOT TO USE**

- Single-fact lookups answerable by one `web_search` (e.g. "what's the capital of France"): use `web_search` directly.
- Questions about content in the user's noted Domains (vector RAG, knowledge graph): use `graph_and_vector_search` / `search_docs`.
- Questions about code in the workspace: use the existing code tools.
- Generative tasks (writing, summarising user-provided text): no new web sources needed.

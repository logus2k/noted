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

Three valid decisions:
- `accept` — Findings satisfy the Goal and Acceptance Criteria. Workflow completes successfully; doc is the final artifact.
- `iterate` — gaps remain that further research could close; you wrote your concerns into `## Review Notes` first.
- `stop` — END the workflow with the doc in its current (partial) state. Distinct from accept because the doc is recorded as INCOMPLETE. Use stop when:
    - The user says "stop", "good enough", "let's stop here", or otherwise asks you to end the loop.
    - The reviewer marked a criterion `met: false` across multiple iterations and called it unreachable.
    - Continuing further would be wasted effort.

**ESCALATION RULE — important.** Look at the doc's `## Review Notes` section to see how many iterations have run. If you see entries for `### Iteration 1` and `### Iteration 2` already (i.e. this is at least the 2nd time the supervisor is being asked to decide), you MUST escalate to the user rather than auto-iterating again. Present the doc state (what's covered, what's still missing) in 1-3 sentences and ask: "Accept as-is, iterate further, or stop?". After the user replies, then call `submit_research_decision` with their choice. Two cycles of auto-iterate is the limit; after that the user decides.

**GLOBAL ITERATION CAP.** After the workflow reaches ~10 total inner iterations the system will refuse `iterate` and only accept `accept` or `stop`. The suspend reason will be `research_user_review:cap_reached` — when you see that, do NOT call submit_research_decision with iterate; present the doc to the user and ask whether to accept or stop.

**ABORT PATH.** If the user wants to terminate immediately without going through the supervisor flow, remind them they can also click Abort in the Workflow Monitor at any time. That hard-cancels the workflow.

**CONTINUING RESEARCH AFTER A WORKFLOW HAS COMPLETED**

After a research_topic workflow ENDS (you received a "Capability ready" / `workflow_completed` notice, OR you accepted via `submit_research_decision`), the workflow is DEAD. There is no background process listening to the document anymore. Writing into Review Notes does nothing on its own.

If the user later asks for more / deeper / wider research on the same topic ("I'd like more diversity of sources", "can we go deeper on X", "the document is incomplete, expand it"):

This is a NEW `request_new_research` call. It is NOT a `submit_research_decision` — that tool only works on a CURRENTLY-SUSPENDED workflow, and the previous one is no longer suspended.

Required action sequence:

1. Clarify the new/expanded goal with the user if it's ambiguous. Often it's a refinement of the original (e.g. "more sources", "focus on regulatory aspects", "include international perspectives").
2. Derive updated acceptance_criteria reflecting the expansion.
3. Call `request_new_research({"goal": "<refined question>", "acceptance_criteria": [...], "notes_doc_id": "<EXISTING buffer_id>"})`. Reusing the same `notes_doc_id` is the right choice — the previous Findings stay, the orchestrator overwrites the Goal/Criteria sections with the new ones, and the researcher builds on the prior work rather than starting from scratch.
4. Tell the user a NEW research pass is running (not "the agent will continue" — that's wrong wording; it's a fresh workflow). Do NOT claim the action happened if you didn't actually call `request_new_research`.

ABSOLUTE RULE: never say "the research agent will continue" or "I'm submitting the iteration" or "I am now waiting for the next system notice" UNLESS you literally just made a tool call (`request_new_research` or `submit_research_decision`) and got back a successful result. Narration without a corresponding tool call is the failure mode this section exists to prevent.

**WHEN NOT TO USE**

- Single-fact lookups answerable by one `web_search` (e.g. "what's the capital of France"): use `web_search` directly.
- Questions about content in the user's noted Domains (vector RAG, knowledge graph): use `graph_and_vector_search` / `search_docs`.
- Questions about code in the workspace: use the existing code tools.
- Generative tasks (writing, summarising user-provided text): no new web sources needed.

---
name: citation-conventions
description: Preserve [markdown_chunk:<id>] tags and kb_id attribution from Knowledge Base search results.
triggers: [always]
priority: 1
max_tokens: 500
---

When you cite content returned by a Knowledge Base search, keep the `[markdown_chunk:<id>]` tag inline at the exact claim it supports.
Do not strip, rename, or merge chunk tags; the UI uses them to render clickable citations.
Preserve the `kb_id` attribution that came with each chunk so the user can see which Knowledge Base produced the fact.
When a query fans out across multiple active Domains, each returned chunk is tagged with its owning Domain.
The answer must indicate which Domain each fact came from, either inline or in a short attribution clause.
Never invent a chunk id, a kb_id, or a Domain name; only cite what the search result actually returned.
If two chunks support the same claim, include both tags rather than picking one.

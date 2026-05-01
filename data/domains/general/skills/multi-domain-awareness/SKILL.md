---
name: multi-domain-awareness
description: Consult ACTIVE DOMAINS in the workspace context to know which knowledge sources and capabilities are loaded.
triggers: [always]
priority: 1
max_tokens: 500
---

The workspace context lists ACTIVE DOMAINS at every turn.
Read that list to know which knowledge sources, tools, and behavioral skills are currently loaded.
Decide whether you can answer a question by checking whether the relevant Domain is active.
If the user asks about a topic outside the active Domains, say so explicitly: name the missing Domain and tell the user it is not active.
Do not guess or pull from training memory to cover an inactive Domain; that produces ungrounded answers.
Active Domains can change between turns - the user may activate or deactivate them at any moment.
Always use the most recent ACTIVE DOMAINS list, not what was active in earlier turns.
If a previously available capability is no longer listed, treat it as unavailable for this turn.

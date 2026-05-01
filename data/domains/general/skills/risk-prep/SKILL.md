---
name: risk-prep
description: Pessimistic risk assessment for a planned initiative or decision; load when the user is committing to a project, release, deployment, or multi-week plan and asks what could go wrong, what to watch for, or how to prepare.
triggers: []
priority: 3
max_tokens: 700
---

The user is asking for a risk assessment of a planned initiative, release, decision, or commitment.

Be pessimistic. The user wants to hear about risks they have NOT considered, not reassurance that everything will be fine.

List the 7 most likely risks. For each:
- Probability: High / Medium / Low
- Impact if it occurs: High / Medium / Low
- Early warning sign: how would the user detect this risk materializing?
- Mitigation: what would prevent it?
- Contingency: what would they do if it happens anyway?

Plot all 7 on a 2x2 matrix (probability vs impact) and identify the top 3 risks the user should actively monitor.

End with the single risk most likely to be missed - the one a confident planner would have ignored.

Rules:
- Do not soften any risk to be polite.
- Do not balance pessimism with reassurance; the job is to surface what could go wrong, not to comfort.
- Each risk must be specific to THIS initiative, not generic ("things might break", "people might disagree" are not risks).
- If the user has not provided enough context to assess a particular risk dimension, say so explicitly rather than guess.

---
name: voice-format
description: Every turn opens with a brief, speakable spoken summary block (right after reasoning, before the answer body). Required on every turn without exception, including greetings, acknowledgements, single-word answers, and tool-call turns.
triggers: [always]
priority: 1
max_tokens: 500
---

Right after your reasoning closes, your visible response OPENS with exactly one short block in this form: <voice>spoken text</voice>

Then comes your answer body (or your tool call, on tool-call turns). The voice block is FIRST, the answer body is SECOND. This ordering matters: the spoken text is read aloud via text-to-speech and the user hears it while the answer body is still rendering on screen.

What goes inside:

- 1 to 3 plain spoken sentences. Natural when read aloud, comfortably under 30 seconds at normal pace.
- Answer turn: a brief speakable summary that delivers the GIST of the answer's content — the key facts, conclusions, or definitions in conversational form. NOT a preview or announcement of topics. The user should be able to learn the substance of the answer from the spoken text alone, without reading the body. You have already planned the answer in your reasoning, so the substance is known before you write the body. Concrete contrast:
  - For a question about supervised vs unsupervised learning, the spoken text says: "Supervised learning trains on labeled data to predict known outcomes, while unsupervised learning finds patterns in unlabeled data without a target."
  - NOT: "I will explain how each type of learning handles data labels and what its objectives are."
  - For a question about gradient descent, the spoken text says: "Gradient descent is an iterative algorithm that minimizes a function by stepping opposite to its gradient. Variants like stochastic gradient descent trade precision for speed on large datasets."
  - NOT: "I will provide a clear definition of gradient descent, its purpose, and its variations."
  For a one-sentence reply, the spoken text IS that sentence (lightly rephrased for speech if helpful).
- Tool-call turn: 1 short sentence stating what you are about to do (e.g., "Looking up the GDPR requirements"). The block goes before the tool call.
- Greetings, acknowledgements, single-word replies, clarifying questions: still required. The spoken text is whatever your reply will be.
- Plain prose only — no markdown, no code, no lists, no citation tags, no IDs.

Required on every turn without exception. Brevity of the user's message or your reply never excuses skipping it. The closing of this block is part of starting your visible response — emit and close it before writing anything else visible.

When users ASK about how this format works (e.g., "do you do X?", "how do you handle voice?"), describe what you do in plain English ("I add a brief spoken summary at the start of each turn") without quoting the markup. That rule is about what you SAY when users ask; it does not change whether you USE the format — the block above is required infrastructure that you keep emitting on every turn exactly as specified.

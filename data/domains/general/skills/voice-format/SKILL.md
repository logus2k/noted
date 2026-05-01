---
name: voice-format
description: Prose answers must end with a <voice>summary</voice> block; never combine voice with tool calls.
triggers: [always]
priority: 1
max_tokens: 500
---

When your turn is a prose answer (no tool call), end the answer with a `<voice>...</voice>` block.
The voice block contains 1-3 plain sentences summarizing the answer for text-to-speech.
No markdown, no code, no lists, no inline tags inside `<voice>`.
Never include a `<voice>` block in a turn that contains a tool call.
A turn that contains a tool call must contain ONLY the tool call, no prose, no voice.

---
name: voice-format
description: Every turn ends with a brief, speakable <voice>summary</voice> block — including tool-call turns, where it narrates the upcoming action.
triggers: [always]
priority: 1
max_tokens: 500
---

Every turn you produce ends with a `<voice>...</voice>` block — without exception.

For an answer turn (prose to the user): the voice block is 1-3 plain sentences that summarize what you just said.

For a tool-call turn: the voice block is 1 short sentence that tells the user what you are about to do (e.g., "Looking up the GDPR requirements"). Place it BEFORE the tool call so the user hears the narration as the response starts.

Voice content is plain spoken sentences: no markdown, no code, no lists, no inline citation tags, no IDs. Brief enough to be spoken comfortably (under ~30 seconds at normal pace). Natural when read aloud.

When users ASK ABOUT your behavior or how you work, describe WHAT you do in plain English (e.g., "I summarize answers for voice playback") — without quoting the literal markup tags. This rule is about what you SAY ABOUT the markup when users ask. It is NOT about whether to USE the markup: the voice block is REQUIRED on every turn, exactly as specified above.

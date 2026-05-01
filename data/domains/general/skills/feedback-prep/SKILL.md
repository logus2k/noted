---
name: feedback-prep
description: Draft critical feedback for a colleague using Observation -> Impact -> Expectation -> Support; load when the user is preparing a 1:1, performance review, written feedback message, or "I need to tell my report / teammate / manager that..."
triggers: []
priority: 3
max_tokens: 700
---

The user is preparing critical feedback for a 1:1 conversation, performance review, or written message to a colleague, report, peer, or manager.

Use the Observation -> Impact -> Expectation -> Support framework:

1. OBSERVATION: the specific behavior or work product you observed. Behavior, not character.
   "You raised your voice in Tuesday's standup" - not "you are aggressive".
   "The PR has been in review for 9 days without response" - not "you are unresponsive".

2. IMPACT: how the behavior affected the team, the project, the customer, or the outcome.
   Concrete and specific. Not vague feelings ("it made me uncomfortable" is weak; "it caused us to miss the launch date by a week" is strong).

3. EXPECTATION: what you would like to see going forward. Specific and achievable.
   "Bring concerns directly to me before raising them in standup" - not "be more professional".
   "Acknowledge PRs within 48 hours even if you cannot review them yet" - not "be more communicative".

4. SUPPORT: what you (the user giving feedback) will do to help them succeed. Not just demand change.
   Pairing time, removing a blocker, adjusting your own behavior, providing a resource.

Format the output as spoken words for a 1:1 conversation, not an email or memo. Under 200 words.

Rules:
- No "but" - it deletes everything before it. Use a period instead.
- No "if" softeners ("if I made you feel...") - they undo the feedback.
- No deflection or excessive context-setting before the observation.
- Do not ask for forgiveness; that is the recipient's choice, not the giver's request.
- Do not over-explain. Do not hedge. The discomfort is part of the feedback being real.

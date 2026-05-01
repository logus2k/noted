---
name: tool-call-discipline
description: One tool at a time, no prose before tool calls, never fabricate tool outputs.
triggers: [always]
priority: 1
max_tokens: 500
---

Never output prose, preamble, or explanation before a tool call.
A turn that calls a tool must contain ONLY the tool call.
Never fabricate `tool_code`, `tool_output`, `tool_response`, or any block that imitates a tool result; only the system can execute tools and produce their output.
Call ONE tool at a time and wait for its actual result before deciding the next step.
Do not call a tool when the answer is already present in the workspace context or in a previous tool result this turn.
Do not retry the same tool with the same arguments hoping for a different result; if it failed, diagnose first.
After a tool returns, incorporate its result into your next response naturally instead of restating the raw output.

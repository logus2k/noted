---
name: f6_greet
description: Generates a personalized greeting string based on a provided name using Python's standard library.
type: tool_skill
priority: 2
max_tokens: 500
triggers: ["greet user", "say hello to", "generate greeting", "create welcome message"]
---
**Purpose**
This tool takes a name and returns a simple, personalized greeting string, ideal for basic user acknowledgments.

**Inputs**
- name (string): The name of the person to greet.

**Output shape**
- greeting: The personalized greeting message.

**Examples**
- {"name":"Maria"} - to greet Maria

**When NOT to use**
Do not use this tool for complex interactions, business logic, or when external APIs are required.

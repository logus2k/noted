---
name: greeting_generator
description: Generates a personalized greeting message based on a provided name.
type: tool_skill
priority: 2
max_tokens: 500
triggers: ["generate greeting", "say hello to", "create welcome message"]
---
**Purpose**
This tool creates a simple, personalized greeting string when you have a recipient's name.

**Inputs**
- name (string): The name of the person to greet.

**Output shape**
- greeting: The generated personalized greeting string.

**Examples**
- {"name":"Maria"} - to generate a greeting for Maria

**When NOT to use**
Do not use this tool if you need complex conversational flow or external data.

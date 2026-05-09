---
name: greet_user
description: Generates a simple, personalized greeting message for a specified user name.
type: tool_skill
priority: 2
max_tokens: 500
triggers: ["say hello to", "greet user", "make a greeting", "hello name"]
---
**Purpose**
This tool generates a simple, personalized greeting string based on the provided name.

**Inputs**
- name (string): The name of the person to greet.

**Output shape**
- greeting: The generated personalized greeting string.

**Examples**
- {"name":"Maria"} - to greet Maria

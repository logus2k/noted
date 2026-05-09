---
name: greet_user_by_name
description: Generates a simple, standard library-only greeting message for a given name.
type: tool_skill
priority: 2
max_tokens: 500
triggers: ["greet user", "say hello to", "generate greeting", "welcome user"]
---
**Purpose**
Use this tool to construct a basic, plain-text greeting message when you have a name and the user requests a simple salutation.

**Inputs**
- name (string): The name of the person to greet.

**Output shape**
- greeting: The generated greeting string.

**Examples**
- {"name":"Maria"} - to greet Maria

**When NOT to use**
Do not use this tool for complex conversational responses or when the user asks for more than just a simple greeting.

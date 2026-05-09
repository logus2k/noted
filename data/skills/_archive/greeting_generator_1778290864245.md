---
name: greeting_generator
description: Generates a simple, personalized greeting string based on the provided name.
type: tool_skill
priority: 2
max_tokens: 500
triggers:
  - greet user
  - say hello to
  - generate greeting
---
**Purpose**
This tool creates a basic, personalized greeting string when you have a specific name to address.

**Inputs**
- name (string): The name of the person to greet.

**Output shape**
- greeting: The generated personalized greeting string.

**Examples**
- {"name":"Maria"} - to generate a greeting for Maria

**When NOT to use**
Use a more complex response generation tool if the greeting needs context or tone beyond a simple salutation.

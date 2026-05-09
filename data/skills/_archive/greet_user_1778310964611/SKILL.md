---
name: greet_user
description: Generates a specific JSON greeting string based on a provided user name.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-09T07:10:40Z
created_by: default
source_workflow_id: wf_1778310614187_2cf1a3f4
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["greet user", "say hello to", "generate greeting"]
---
**Purpose**
This tool constructs a precise JSON greeting object containing a personalized welcome message for a specified recipient.

**Inputs**
- name (str): The name of the person to greet.

**Output shape**
- greeting: The final greeting string in the format 'Hello, <name>!'

**Examples**
- {"name":"Maria"} - to generate a greeting for Maria

**When NOT to use**
Do not use this tool if the request is not explicitly asking to generate a greeting or if no name is provided.

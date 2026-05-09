---
name: weather_reporter
description: Fetches detailed weather forecasts for a given city code using external APIs.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-09T08:31:50Z
created_by: default
source_workflow_id: wf_1778315479979_c27ff631
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get weather forecast", "check weather for city", "fetch weather data", "report weather conditions"]
---
**Purpose**
This tool queries weather services to provide a forecast array based on a provided city code.

**Inputs**
- city_code (string): The unique code identifying the city for which weather data is required.

**Output shape**
- forecast: An array containing detailed weather forecasts for the specified location.

**Examples**
- {"city_code":"LPLG"} - to get the weather forecast for LPLG

**When NOT to use**
Do not use this tool if the user is asking general questions about weather patterns or needs a forecast for a location without a known city code.

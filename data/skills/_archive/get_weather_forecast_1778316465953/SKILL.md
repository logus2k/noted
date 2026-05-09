---
name: get_weather_forecast
description: Fetches detailed weather forecasts for a given city code using external weather APIs.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-09T08:47:30Z
created_by: default
source_workflow_id: wf_1778316396085_d5ed7a3d
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get weather forecast", "check weather for city", "find weather by code", "what is the weather"]
---
**Purpose**
This tool queries external weather services to provide a structured forecast based on a provided city code.

**Inputs**
- city_code (string): The unique code identifying the desired city.

**Output shape**
- forecast: An array containing detailed weather predictions for upcoming days.

**Examples**
- {"city_code":"LPLG"} - to retrieve the weather forecast for the specified city code.

**When NOT to use**
Do not use this tool if you need general weather information without a specific city code, or if you require real-time, non-forecast data.

---
name: address_resolver
description: Resolves a city name to a code and fetches the current weather forecast from SAPO services.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-10T11:30:11Z
created_by: default
source_workflow_id: wf_1778412568985_e3496719
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get weather for city", "fetch weather forecast", "check weather in", "resolve city weather"]
---
**Purpose**
This tool takes a city name, resolves it to a weather code, and returns the detailed current weather forecast for that location.

**Inputs**
- city_name (string): The full name of the city you want the weather for.

**Output shape**
- weather_forecast: A dictionary containing current weather details like temperature, description, and city code.

**Examples**
- {"city_name":"Lisbon"} - to get the weather forecast for Lisbon

**When NOT to use**
Do not use this tool if you already have the city's specific weather code.

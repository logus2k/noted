---
name: get_weather_forecast
description: Fetches the detailed weather forecast for any given city name by first resolving the city code.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-10T04:12:50Z
created_by: default
source_workflow_id: wf_1778386323210_544007d1
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get weather forecast", "check weather in city", "find weather conditions", "what is weather like in"]
---
**Purpose**
Use this tool to look up the current weather forecast for a specified location by providing its name.

**Inputs**
- city_name (string): The full name of the city for which you want the weather forecast.

**Output shape**
- forecast: Contains the detailed weather information including temperature, humidity, and description.

**Examples**
- {"city_name":"London"} - to get the weather forecast for London

**When NOT to use**
Do not use this tool if you already have the city code or if you are asking a general question about weather patterns.

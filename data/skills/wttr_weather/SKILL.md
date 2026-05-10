---
name: wttr_weather
description: Fetches current and forecast weather data from wttr.in for a given location.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-10T16:54:05Z
created_by: default
source_workflow_id: wf_1778431999652_020d5dbf
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["check weather", "get forecast", "what is the weather", "fetch weather data"]
---
**Purpose**
This tool retrieves detailed weather information, including current conditions and forecasts, from the wttr.in service based on a provided location.

**Inputs**
- location (string): The city or location name for which to retrieve weather data.
- format (string): The desired output format for the weather data (e.g., 'j1' for JSON).

**Output shape**
- weather_data: A string containing the raw weather data in the requested format.

**Examples**
- {"location":"London","format":"j1"} - to get JSON weather for London

**When NOT to use**
Do not use this tool if you only need general weather information without specifying a location or if you require a different data source.

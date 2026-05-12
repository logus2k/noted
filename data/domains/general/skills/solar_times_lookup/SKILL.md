---
name: solar_times_lookup
description: Calculates solar times like sunrise, sunset, and day length for a given latitude and longitude.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-12T19:45:35Z
created_by: default
source_workflow_id: wf_1778615095090_5222837c
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["find sunrise sunset", "get solar times", "check day length", "lookup coordinates time"]
---
**Purpose**
This tool retrieves detailed solar event times, including sunrise, sunset, solar noon, and day length, based on provided latitude and longitude.

**Inputs**
- lat (float): The latitude of the location.
- lng (float): The longitude of the location.

**Output shape**
- sunrise: ISO timestamp of sunrise.
- sunset: ISO timestamp of sunset.
- solar_noon: ISO timestamp of solar noon.
- day_length: Duration of daylight.

**Examples**
- {"lat": 38.7223, "lng": -9.1393} - to find solar times for a location

**When NOT to use**
Do not use this tool if you only need general time information without specific geographical context.

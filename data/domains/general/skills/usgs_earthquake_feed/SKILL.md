---
name: usgs_earthquake_feed
description: Fetches earthquake data from the USGS catalog within a given time window.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-12T20:24:37Z
created_by: default
source_workflow_id: wf_1778617426115_8ab6e60f
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["query earthquake catalog", "fetch seismic events", "check earthquake data", "find earthquakes by time"]
---
**Purpose**
This tool queries the USGS earthquake catalog to return a list of seismic events that occurred within a specified time frame.

**Inputs**
- starttime (string): The start date for the search in YYYY-MM-DD format.
- endtime (string): The end date for the search in YYYY-MM-DD format.
- minmagnitude (float): The minimum magnitude threshold for results (optional).

**Output shape**
- features: A list of earthquake events, each containing properties and geometry.

**Examples**
- {"starttime":"2026-05-05","endtime":"2026-05-12","minmagnitude":5.0} - to find earthquakes between May 5th and May 12th above magnitude 5.0

**When NOT to use**
Do not use this tool if you only need general information about earthquakes, as it requires specific date ranges.

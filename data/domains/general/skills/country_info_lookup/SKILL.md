---
name: country_info_lookup
description: Looks up basic demographic and geographical information for a specified country using external APIs.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-12T20:25:59Z
created_by: default
source_workflow_id: wf_1778617517923_801769b5
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["find country info", "lookup country details", "get country data", "check country population"]
---
**Purpose**
This tool queries the restcountries.com API to fetch structured data about a country matching the provided name.

**Inputs**
- name (string): The common or official name of the country to look up.

**Output shape**
- name: Object containing 'common' and 'official' names.
- capital: List of capital cities.
- population: Integer representing the country's population.
- region: String indicating the geographical region of the country.

**Examples**
- {"name":"Portugal"} - to fetch information for Portugal

**When NOT to use**
Do not use this tool if you only need a general geographical concept or if the country name is ambiguous and requires further clarification.

---
name: frankfurter_exchange_rate_api
description: Retrieves real-time or historical currency exchange rate data from the Frankfurter API.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-12T12:50:21Z
created_by: default
source_workflow_id: wf_1778590171103_20dfe50c
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get exchange rates", "check currency conversion", "fetch historical rates", "convert currency"]
---
**Purpose**
Use this tool to look up the exchange rates between different currencies for a specified date or the latest available data.

**Inputs**
- base (string): The three-letter currency code to use as the base currency (e.g., EUR).
- date (string): The specific date for the exchange rates in YYYY-MM-DD format (optional).

**Output shape**
- amount: The amount of the base currency converted.
- base: The three-letter code of the base currency.
- date: The date for which the rates were retrieved.
- rates: A dictionary mapping target currency codes to their exchange rates.

**Examples**
- {"base":"EUR","date":"2026-05-12"} - to get EUR exchange rates for today
- {"base":"USD","date":"2025-01-01"} - to fetch historical USD rates

**When NOT to use**
Do not use this tool if you only need a simple, immediate conversion without needing the full rate data structure.

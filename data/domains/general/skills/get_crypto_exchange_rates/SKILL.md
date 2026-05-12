---
name: get_crypto_exchange_rates
description: Retrieves real-time exchange rates for a list of cryptocurrencies against a specified fiat currency.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-12T14:46:07Z
created_by: default
source_workflow_id: wf_1778597119474_c88d27c7
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["get crypto prices", "check exchange rates", "fetch crypto rates", "lookup currency value"]
---
**Purpose**
This tool queries the CoinGecko API to provide the current market value of selected cryptocurrencies in a specified fiat currency.

**Inputs**
- ids (string): comma-separated list of cryptocurrency IDs (e.g., bitcoin,ethereum)
- vs_currencies (string): the ISO currency code to compare against (e.g., eur)

**Output shape**
- rates: object containing currency IDs mapped to their exchange rate data

**Examples**
- {"ids":"bitcoin,ethereum","vs_currencies":"eur"} - to get BTC and ETH prices in EUR

**When NOT to use**
Do not use this tool if you only need general market trends or historical data, as it provides only current spot prices.

---
name: newsapi_search
description: Searches external news sources using keywords, country, or date filters to retrieve relevant articles.
type: tool_skill
priority: 2
max_tokens: 500
provenance: user
created_at: 2026-05-14T11:58:26Z
created_by: default
source_workflow_id: wf_1778759841443_48da40bb
source_workflow_type: create_tool
source_workflow_tenant: default
triggers: ["search for news", "find articles about", "check latest news", "get news by country"]
---
**Purpose**
This tool queries the NewsAPI to fetch a list of news articles matching specified criteria like keywords, country, and sorting preferences.

**Inputs**
- query (string): The main keywords or topic to search for.
- country (string): The two-letter ISO code of the country to filter by.
- sortBy (string): How to order the results (e.g., 'date').

**Output shape**
- articles: A list containing the fetched news article objects.
- total_results: An integer representing the total number of articles found.

**Examples**
- {"query":"Apple","country":"us","sortBy":"date"} - to find recent US news on Apple

**When NOT to use**
Use a general search if you do not need specific filtering by country or date.

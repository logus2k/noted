# Tool: fetch_url

**Type:** tool
**Tier:** read
**Domain:** web
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Fetches a web URL and returns the page text (HTML stripped). For project files use `get_file_contents`.

## Input schema

- `url` (required); `max_chars` (optional, default 10000).

## Setup prerequisites

- Outbound HTTP allowed.

## Scenarios

### S1 - Fetch a doc URL
"summarize <https-url>" → `fetch_url`; do NOT use get_file_contents.

### S2 - Limit chars
Pass `max_chars=5000`; mention truncation.

### S3 - Bad URL
Tool errors; report; do not fabricate.

### S4 - Wrong tool (project path)
"fetch src/x.py" → `get_file_contents`; fetch_url is for URLs.

### S5 - User-shared link
Fetch + summarize; if fail, ask user to paste excerpts.

### S6 - Binary/PDF URL (DEFERRED)
### S7 - Rate-limited domain (DEFERRED)

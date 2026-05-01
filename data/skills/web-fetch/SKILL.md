---
name: web-fetch
description: Fetch and analyze web content from URLs shared by the user. Use the fetch_url tool when the user shares a URL or asks to read online documentation.
triggers: [workspace_active]
priority: 1
max_tokens: 300
---

# Web Content Fetch and Analysis

You can fetch content from URLs using the `fetch_url` tool. Use this when:
- The user shares a URL and asks about its content
- The user asks you to read documentation, API references, or articles
- You need to check a web resource to answer a question

## Usage

Call `fetch_url` with the URL. The tool returns the page text with HTML tags stripped.

```
fetch_url(url="https://example.com/docs/api", max_chars=10000)
```

## Guidelines

- **Analyze, don't parrot.** The user wants your interpretation, not a copy of the page. Summarize, extract key points, answer their specific question based on the content.
- **Be selective.** If the page is long, focus on the parts relevant to the user's question.
- **Cite specifics.** When referencing the page content, mention specific sections, code examples, or data points.
- **Handle errors gracefully.** If the URL is unreachable or returns an error, tell the user clearly and suggest alternatives (e.g., a different URL, or manual copy-paste).
- **Respect limits.** The default max is 10,000 characters. For very long pages, you can increase `max_chars` or fetch specific sections if the URL supports anchors.
- **No sensitive URLs.** Do not fetch URLs that appear to contain authentication tokens, private API keys, or internal-only resources.

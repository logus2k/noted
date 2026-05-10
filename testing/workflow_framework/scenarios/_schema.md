# Scenario YAML schema

Each scenario file pins the exact inputs the framework will be called
with. These bypass the planner so the LLM-step variance can be
isolated and measured.

```yaml
id: <unique_short_id>           # filename stem; used in reports
name: <human readable>          # one short sentence
api_family: <weather|issues|finance|geo|reference|...>
                                 # for grouping in reports;
                                 # at least 3 distinct values across the suite

# These map directly onto create_tool's inputs (see
# noted/backend/app/workflow/builtin_workflows.py:_CREATE_TOOL_INPUT_SCHEMA).
inputs:
  tool_name: <snake_case>       # max 40 chars, [a-z][a-z0-9_]*
  language: python              # only python today
  mission: |
    Multi-line natural-language description of what the tool should do.
  api_docs_urls:
    - https://...               # COPIED VERBATIM, including query params
  acceptance_criteria:
    - "Input is a JSON object with a string field named <key>."
    - "Successful output JSON contains a non-empty <key> array."
    - "Tool exits non-zero if the required <key> is missing."
    # 3-5 concrete, single-line, smoke-testable criteria
  verify_inputs:
    <key>: <literal-value-known-to-work-against-live-upstream>

# Live-call probe AFTER the workflow completes. Optional but
# highly recommended — proves the published tool actually returns
# real upstream data, not just that the workflow's own
# verify_tool_round_trip step passed.
post_publish_probe:
  args: {<key>: <value>}        # what to send to the published tool
  expect_keys:                  # output keys that MUST be present
    - <key>
  expect_status: 0              # exit code
```

## Validation rules

- `tool_name` must be unique across scenarios (or harness will collide
  if scenarios run concurrently — they don't today, but defensive).
- `verify_inputs` keys MUST match the field names pinned in
  `acceptance_criteria` #1.
- `api_docs_urls` URLs are COPIED VERBATIM — keep query parameters
  intact; that's how the planner SHOULD behave too.

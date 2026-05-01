# Tool: get_serving_schema

**Type:** tool
**Tier:** read
**Domain:** mlflow / serving
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_serving_schema`](../../../backend/app/managers/llm_tools.py)

## Purpose

Returns the input/output schema of the model currently loaded in noted-serving: input format (tensor / dataframe), shape, dtype, and example payload hint. Used as pre-flight before constructing a real `invoke_model(data=...)` call, or to answer "what does it expect?" without invoking.

## Input schema

- No arguments.

## Output shape

```
Serving schema:
  input_format: tensor
  input_shape (incl. batch): [1, 120, 16]
  inputs: [...]
  outputs: [...]
```

Returns an error if no model is currently loaded.

## Setup prerequisites

- A model is deployed (most scenarios use Sandbox Forecaster v1 @champion via `deploy_model` fixture).

## Scenarios

### S1 - Basic schema fetch
"what input does the deployed model expect?" → `get_serving_schema` only.

### S2 - Pre-flight
"I want to send a real request - what shape do I need?" → schema only; do NOT auto-invoke.

### S3 - Output shape
"what does the model output look like?" → outputs section.

### S4 - Nothing deployed
Setup: idle. Tool errors; report and suggest deploy first.

### S5 - Multi-turn schema then test
T1: schema. T2: "now test it" → `invoke_model({})` smoke test.

### S6 - Framework lookup
"which framework?" → `get_serving_status` is the cleanest path; `get_serving_schema` also acceptable.

### S7 - External API question
"what does /api/serving/predict expect?" → ground in `get_serving_schema`; explain JSON body shape; do not invoke.

### S8 - Diagnostic
"shape error from /predict - what does it want?" → schema; explain reshape; no auto-test.

### S9 - Dataframe-format model (DEFERRED)
Needs a tabular model in the sandbox.

### S10 - Signature-less model (DEFERRED)
Edge case.

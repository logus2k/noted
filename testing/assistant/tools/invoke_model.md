# Tool: invoke_model

**Type:** tool
**Tier:** read (no confirmation - inference is read-only)
**Domain:** mlflow / serving
**Handler:** [backend/app/managers/llm_tools.py `_tool_invoke_model`](../../../backend/app/managers/llm_tools.py)

## Purpose

Sends a prediction payload to the loaded model. With NO `data` arg, the backend builds a well-formed payload from the model's MLflow signature (`example_input` if available, else zeros matching `input_shape`) — this is the canonical "test it" / "smoke test" path. With `data=<nested-list>`, forwards as-is. Always preferred over having the user write a Python/curl script.

## Input schema

- `data` (optional, any) - prediction payload. Omit for smoke test.

## Output shape

```
Prediction OK (auto smoke test, input_format=tensor).
  Raw response: {"prediction": [...], "format": "ndarray", "shape": [24], ...}
```

## Setup prerequisites

- A model is deployed (most scenarios use Sandbox Forecaster v1 @champion).

## Scenarios

### S1 - Smoke test (no data)
"smoke test the deployed model" → `invoke_model({})`; no schema/status pre-call.

### S2 - "Test it with sample"
"test it with a sample input" → `invoke_model({})` (backend builds from signature). NEVER hand-type 1920 floats.

### S3 - Verify after deploy
T1: deploy. T2: "verify with quick prediction" → `invoke_model({})`.

### S4 - Nothing deployed
Setup: idle. Tool errors; report; suggest deploy_model first; never fabricate.

### S5 - Show then test
T1: `get_serving_schema`. T2: "test it" → `invoke_model({})`.

### S6 - Wiring verification
"is the prediction endpoint wired up correctly?" → `invoke_model({})`; report success+shape.

### S7 - User asks for a script
"test the model" → `invoke_model` directly; do NOT write a Python/curl snippet.

### S8 - Reuse prior result
T1: smoke test. T2: "what was the shape?" → reuse prior result; do NOT re-invoke.

### S9 - Custom payload from CSV (DEFERRED)
Needs a file fixture for sample data.

### S10 - Batch prediction (DEFERRED)
Multi-row payload tests.

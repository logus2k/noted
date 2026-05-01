# Model Serving and Try It - Test Procedure

## Prerequisites

- noted is running with all services including `noted-serving` container
- At least one registered model in the Model Registry (see 19_test-model-registry.md)
- Run `docker ps | grep noted-serving` to verify the serving container is running

---

## Part 1: Serving Container Health

### Test 1: Serving container reachable

1. In browser console:
```javascript
fetch('api/serving/health').then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns `{status: "idle", model_name: null, version: null, ...}`
- Status is "idle" (no model loaded yet)

---

## Part 2: Try It Panel

### Test 2: Open Try It from version detail

1. Navigate to Models > select a model > click a version
2. In the version detail page, click the "Try It" button (flask icon, green)

**Expected:**
- A jsPanel opens titled "Try It: {model_name} v{version}"
- Shows "Loading model..." while the serving container fetches the model
- After loading: status card shows "Ready" with model name, version, and load time

### Test 3: Input form generated from schema

1. After the model loads in the Try It panel

**Expected:**
- If DataFrame model (sklearn, etc.): individual input fields for each feature with name, type, and placeholder
- If tensor model (Keras, PyTorch): JSON textarea for array input
- "Or paste JSON directly" textarea always available
- "Predict" and "Clear" buttons

### Test 4: Run a prediction

1. Fill in input values (or paste JSON)
2. Click "Predict"

**Expected:**
- Button shows "Predicting..."
- Result appears in the Output section
- Format depends on model output:
  - Scalar: large centered number
  - Array (>3 values): line chart (ECharts)
  - Class probabilities: bar chart with labels
  - DataFrame: table with columns
  - Other: formatted JSON

### Test 5: Prediction with JSON input

1. Paste valid JSON in the textarea (matching the model's expected input)
2. Click "Predict"

**Expected:**
- JSON input overrides named field values
- Prediction runs successfully

### Test 6: Invalid input handling

1. Paste invalid JSON (e.g., `{broken`)
2. Click "Predict"

**Expected:**
- Error: "Invalid JSON: ..."
- No crash, can retry with corrected input

### Test 7: Prediction history

1. Run 3 predictions with different inputs

**Expected:**
- "History" section appears below the output
- Shows last 5 predictions with timestamp, truncated input, and result
- Most recent at top

### Test 8: Clear inputs

1. Click "Clear"

**Expected:**
- All input fields and JSON textarea are emptied
- Output area is cleared
- History remains

---

## Part 3: Model Switching

### Test 9: Load a different model

1. Close the Try It panel
2. Navigate to a different model version
3. Click "Try It"

**Expected:**
- Panel opens, shows "Loading model..." briefly
- New model is loaded (replaces the previous one)
- Input form updates to match the new model's schema

### Test 10: Same model reuse

1. Open Try It for the same model/version that's already loaded

**Expected:**
- No "Loading model..." delay
- Form appears immediately (model already in memory)

---

## Part 4: Serving Status Bar

### Test 11: Status bar - no model loaded

1. Check the bottom status bar before loading any model

**Expected:**
- No serving pill visible (hidden when idle)

### Test 12: Status bar - model loaded

1. Load a model via Try It panel
2. Wait up to 10 seconds

**Expected:**
- A green pill appears in the status bar: "{model_name} v{version}" with flask icon
- Tooltip shows "Serving: {model_name} v{version}"

### Test 13: Status bar - model unloaded

1. Unload the model (via API: `fetch('api/serving/unload', {method:'POST'})`)
2. Wait up to 10 seconds

**Expected:**
- The green serving pill disappears from the status bar

---

## Part 5: Error Handling

### Test 14: Serving container down

1. Stop the serving container: `docker stop noted-serving`
2. Try to open the Try It panel

**Expected:**
- Error: "Serving container not reachable"
- No crash in noted

### Test 15: Model not found

1. Try loading a non-existent model (via console):
```javascript
fetch('api/serving/load', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model_name: 'NonExistent', version: '1'})
}).then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns error with descriptive message
- Serving container remains operational

---

## Troubleshooting

- **"Serving container not reachable":** Run `docker ps | grep noted-serving` to check if it's running. Restart with `docker compose ... up -d noted-serving`.
- **Model loading fails:** Check that the model is registered in MLflow and the artifact exists in MinIO. Check noted-serving logs: `docker logs noted-serving`.
- **Prediction fails:** The input format may not match the model's expected schema. Check `/api/serving/schema` for the expected format.
- **Status bar not updating:** The poll interval is 10 seconds. Wait or refresh the page.

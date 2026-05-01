# Model Registry - Test Procedure

## Prerequisites

- noted is running
- At least one MLflow experiment with a FINISHED run that has model artifacts
- noted-testing project with test_notebook.ipynb run (produces model artifacts)

---

## Part 1: Models Section in Explorer

### Test 1: Models section visible

1. In Explorer tree, look for the "Models" section (brain icon)

**Expected:**
- "Models" section appears between Experiments and Virtual Environments
- Expandable (folder with chevron)

### Test 2: Empty models section

1. Expand Models (on first use, no models registered yet)

**Expected:**
- Shows "No registered models" with info icon

### Test 3: Models root detail page

1. Click on "Models" root node

**Expected:**
- Detail page shows "Models" header with brain icon
- Card with "Total: 0 models"

---

## Part 2: Register a Model

### Test 4: Register from run artifacts

1. Navigate to Experiments > select an experiment > click a run that has model artifacts
2. In the Artifact Browser, find the model file (e.g., model.keras or model directory)
3. Note the run_id and artifact_path

For now, use the API directly (via browser console):
```javascript
fetch('api/registry/models/register', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        run_id: '<your_run_id>',
        artifact_path: 'model',
        model_name: 'JenaForecaster'
    })
}).then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns: `{model_name: "JenaForecaster", version: "1", ...}`
- Collapse and re-expand Models section - "JenaForecaster" appears

### Test 5: Register another version

1. Register the same model name with a different run_id

**Expected:**
- Returns version: "2"
- Model node in tree shows both versions when expanded

### Test 6: Models list after registration

1. Click on Models root node

**Expected:**
- Card shows "Total: 2 models" (or however many you registered)
- Registered Models list shows each model with brain icon and alias badges

---

## Part 3: Model Versions

### Test 7: Expand model to see versions

1. Click on a model name in the tree (e.g., "JenaForecaster")

**Expected:**
- Expands to show version nodes (v1, v2, etc.)
- Each version has a status icon (green check for READY)

### Test 8: Model detail page

1. Click on the model name

**Expected:**
- Detail page shows: model name, version count, current aliases
- Version table with columns: Version, Aliases, Run, Created, Actions
- Each row has an alias dropdown in the Actions column

### Test 9: Version detail page

1. Click on a specific version (e.g., v1)

**Expected:**
- Detail page shows: model name, version, status, source run ID, source URI, creation date
- Tags section (if any)
- "Assign Alias" section with dropdown (champion/staging/archived) and Assign button
- "Go to Source Run" button

---

## Part 4: Alias Management

### Test 10: Assign champion alias

1. In version detail page, select "champion" from the alias dropdown
2. Click "Assign"

**Expected:**
- Toast: "Alias @champion assigned to v2"
- Detail page refreshes showing the alias
- Model tree node updates to show "@champion"

### Test 11: Assign staging alias

1. On a different version, assign "staging"

**Expected:**
- Toast: "Alias @staging assigned to v1"
- Both aliases visible in the model detail page

### Test 12: Reassign champion

1. Assign "champion" to a different version

**Expected:**
- The alias moves from the old version to the new one
- Only one version has @champion at a time

### Test 13: Alias via version table

1. In the model detail page, use the "Set alias..." dropdown in the Actions column

**Expected:**
- Same behavior as the version detail page
- Table refreshes after assignment

---

## Part 5: Navigation

### Test 14: Navigate to source run

1. In a version detail page, click "Go to Source Run"

**Expected:**
- Navigates to the MLflow run that produced this model version
- Run detail opens in the Experiments tree

### Test 15: Click version row in model detail

1. In the model detail page, click a version row (not on the dropdown)

**Expected:**
- Navigates to the source run in the Experiments tree

---

## Part 6: Register Panel

### Test 16: Register panel (future - from run detail)

This test is for when the "Register Model" button is added to run detail pages.

1. On a run detail page with model artifacts, click "Register Model"

**Expected:**
- Registration panel (jsPanel) opens
- Shows run ID and artifact path
- Model name input
- Register button creates the model version

---

## Troubleshooting

- **"No registered models":** No models have been registered yet. Use the API or Register panel to register one.
- **Version shows PENDING_REGISTRATION:** The model source might be inaccessible. Check that the run's artifact URI is valid.
- **Alias assignment fails:** Check MLflow server logs for permissions issues.
- **"Go to Source Run" doesn't navigate:** The Experiments tree may not be expanded. Expand it first.

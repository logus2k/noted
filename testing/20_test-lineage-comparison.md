# Model Lineage and Comparison - Test Procedure

## Prerequisites

- noted is running
- At least one registered model with 2+ versions (see 19_test-model-registry.md)
- Runs should have DVC data hashes and Hydra config hashes logged (from Run Manager execution)

---

## Part 1: Lineage View

### Test 1: Lineage appears on version detail

1. In Explorer, navigate to Models > select a model > click a version (e.g., v1)
2. Scroll down past the alias section

**Expected:**
- A "Lineage" section appears with a vertical chain of nodes
- Chain flows top to bottom: Data (DVC) -> Config (Hydra) -> Code (Git) -> Run (MLflow) -> Model (Registry)
- Each node has a colored icon, label, and metadata

### Test 2: Lineage data populated

1. View the lineage for a version whose source run has DVC and Hydra tags

**Expected:**
- Data node shows DVC hash and file name
- Config node shows Hydra config hash
- Code node shows git commit (7 chars), snapshot branch (if snapshot)
- Run node shows run ID, name, status
- Model node shows name, version, aliases

### Test 3: Missing lineage layers

1. View lineage for a version whose run does NOT have DVC or Hydra tags

**Expected:**
- Missing layers appear greyed out (opacity reduced)
- Shows "Not tracked" text
- Non-missing layers are fully visible

### Test 4: Click run node navigates

1. In the lineage chain, click the "Run (MLflow)" node

**Expected:**
- Navigates to the source run in the Experiments tree
- Run detail opens

### Test 5: Pipeline layer (if applicable)

1. If a run was triggered via Airflow and has `airflow.dag_id` tag, check the lineage

**Expected:**
- A "Pipeline (Airflow)" layer appears between Code and Run
- Shows DAG ID and run ID

---

## Part 2: Model Comparison

### Test 6: Compare button visible

1. Click on a model that has 2+ versions (e.g., JenaForecaster)

**Expected:**
- A "Compare Versions" button (blue, code-compare icon) appears above the version table
- Button NOT shown if only 1 version exists

### Test 7: Comparison panel opens

1. Click "Compare Versions"

**Expected:**
- A jsPanel opens titled "Compare: {model_name}"
- Two version dropdowns (A and B) pre-selected to first two versions
- "Compare" button

### Test 8: Run comparison

1. Select two different versions in the dropdowns
2. Click "Compare"

**Expected:**
- Metrics table appears with columns: Key, v{A}, v{B}, Delta
- Changed metrics highlighted in amber background
- Delta column shows arrows: up (red, worse) or down (green, better)
- Values shown to 6 decimal places

### Test 9: Parameter differences

1. Compare two versions that used different parameters

**Expected:**
- "Parameters (N changed)" section appears
- Only changed parameters shown (unchanged are hidden)
- Both values displayed side by side

### Test 10: Lineage differences

1. Compare two versions from different data versions or configs

**Expected:**
- "Lineage Differences" section appears
- Shows what changed: "Data version changed", "Config changed", "Code changed"
- Each difference has a warning icon

### Test 11: Same version comparison blocked

1. Select the same version for both A and B
2. Click "Compare"

**Expected:**
- Toast: "Select two different versions"
- No comparison rendered

---

## Part 3: Lineage API

### Test 12: Lineage API endpoint

1. In browser console:
```javascript
fetch('api/registry/models/JenaForecaster/versions/1/lineage')
    .then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns `{model: {...}, run: {...}, lineage: {data: {...}, config: {...}, code: {...}, run: {...}, model: {...}, pipeline: {...}}}`

### Test 13: Comparison API endpoint

1. In browser console:
```javascript
fetch('api/registry/models/compare', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model_name: 'JenaForecaster', version_a: '1', version_b: '2'})
}).then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns `{metrics_diff: [...], params_diff: [...], lineage_a: {...}, lineage_b: {...}}`

---

## Troubleshooting

- **Lineage shows all "Not tracked":** The source run may not have DVC/Hydra tags. Use Run Manager to execute the notebook with DVC datasets and Hydra config selected to populate tags.
- **Comparison shows no differences:** Both versions may have been trained with identical parameters. Try versions from different runs.
- **"Run not found in tree":** The Experiments section may not be expanded. Expand it first so run nodes are loaded, then click the lineage run node.

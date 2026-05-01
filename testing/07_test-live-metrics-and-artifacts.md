# Live Metrics and Artifact Browser - Test Procedure

## Prerequisites

- noted is running (docker rebuild required for backend changes)
- MLflow is running and accessible (container `noted-mlflow`)
- A project with a Python environment that has `tensorflow`, `mlflow`, `matplotlib`, `pyyaml`, and `scikit-learn` installed
- The test notebook `test_notebook.ipynb` is available in the project (e.g., `noted-testing`)
- The test dataset is available at `../dataset/test_data.csv` relative to the notebook

---

## Part 1: Live Metrics During Training

### Test 1: Live Metrics panel auto-opens

1. Open `test_notebook.ipynb` in noted
2. Select the kernel environment (e.g., `test_env`)
3. Run All cells (or run cells sequentially up to and including the training cell)
4. Wait for the training cell to start executing (epoch logs appear in output)

**Expected:**
- The Live Metrics panel (jsPanel) auto-opens when the first `mlflow.log_metric()` call fires
- Four metric traces appear: `train_loss`, `val_loss`, `train_mae`, `val_mae`
- Charts update in real time as each epoch completes
- Default view is Split (one chart per metric, 2x2 grid)
- Info bar at top shows latest values for all metrics

### Test 2: View mode switching

1. While training is running (or after completion), click the view mode buttons in the panel toolbar

**Expected:**
- **Split** (default): 4 separate charts in a 2x2 grid, each with its own title and axes
- **Combined**: all 4 traces overlaid on one chart with a legend at the bottom
- **Summary**: table with columns Metric, Latest, Min, Max, Steps - updates in real time
- Switching between modes preserves the data (no data loss)

### Test 3: Tooltips

1. In Split or Combined view, hover over a data point on any chart

**Expected:**
- Tooltip appears showing `Step N` and the metric value rounded to 6 decimal places
- In Combined view, tooltip shows all metrics at that step

### Test 4: Chart resize

1. Drag the panel edges to resize it

**Expected:**
- All charts resize proportionally to fill the panel
- Charts shrink when panel is made smaller (no overflow)
- Charts grow when panel is made larger

### Test 5: Copy chart to clipboard

1. Hover over a chart - a copy icon appears (top-right corner, green clipboard SVG)
2. Click the copy icon

**Expected:**
- "Copied" toast appears briefly on the icon
- Chart is copied as a PNG image to the clipboard
- Paste into any application (Word, Slack, etc.) to verify

### Test 6: Copy table to clipboard

1. Switch to Summary view
2. Click the copy icon next to the table

**Expected:**
- "Copied" toast appears
- Table is copied as both TSV (plain text) and HTML
- Paste into Excel/Sheets: formatted table appears
- Paste into a text editor: tab-separated values

### Test 7: Auto-clear on new run

1. After training completes, re-run the training cell (or Run All again)

**Expected:**
- When a new `run_id` is detected, the panel clears previous data
- New metric traces start from scratch

### Test 8: Panel close and reopen

1. Close the Live Metrics panel (X button)
2. Click the chart icon in the notebook second bar

**Expected:**
- Panel reopens (data may or may not persist depending on whether training is still active)

---

## Part 2: Final Metrics (Single-Point)

### Test 9: Single-point metrics

1. Let the notebook finish all cells (including evaluation cells that log `test_mae_c`, `test_rmse_c`, `test_r2_c`)

**Expected:**
- In Split/Combined view: only time-series metrics (2+ points) show as charts
- Single-point metrics (`test_mae_c`, `test_rmse_c`, `test_r2_c`) appear only in Summary table view
- Info bar shows all metrics including single-point ones

---

## Part 3: Experiment Explorer - Run Detail

### Test 10: Run appears in Explorer tree

1. After the notebook finishes, go to the Explorer tree
2. Expand Experiments > (experiment name, e.g., `noted-testing`)

**Expected:**
- The run appears with format `yyyy-MM-dd HH:mm - gru_live_metrics_test`
- Green checkmark icon (FINISHED status)
- Run node has an expand chevron (folder)

### Test 11: Run detail page

1. Click the run node

**Expected:**
- Top bar shows breadcrumbs: `Experiments / experiment_name / run_name / run_id`
- Second bar shows chart icon (popout) and delete icon (trash)
- Detail page shows:
  - Inline metric charts (auto-loaded, 2x2 grid for time-series metrics)
  - Tooltips on hover (Step + value to 6 decimals)
  - Metadata card: Status (green FINISHED), Run ID, Started, Ended, Duration
  - Metrics section with all metric values
  - Parameters section (model_type, units1, units2, etc.)
- No layout shift or "Loading..." flash

### Test 12: Popout to Metrics panel

1. Click the chart icon in the second bar

**Expected:**
- A new MetricsPanel opens (separate from the live one)
- Panel title shows `run_name (short_run_id)`
- Shows the same metric data with Split/Combined/Summary views
- If the live panel is still open, both panels coexist side by side

### Test 13: Multiple panels for comparison

1. Navigate to a different run in the tree
2. Click its chart popout icon

**Expected:**
- A second MetricsPanel opens, offset from the first (cascading position)
- Both panels show their respective run data independently
- Panel headers show different run names/IDs for identification

---

## Part 4: Artifact Browser

### Test 14: Artifact categories in tree

1. Expand a run node that has artifacts (the latest run should have both a model and an image)

**Expected:**
- Category folders appear with colored icons:
  - **Models** (pink brain icon) - if model artifact was logged
  - **Images** (green image icon) - `training_curves.png`
- Categories with no artifacts do not appear
- If a run has no artifacts at all: "No artifacts" placeholder with info icon

### Test 15: Image artifact detail

1. Expand the Images category
2. Click `training_curves.png (XX.X KB)` - file size shown in tree

**Expected:**
- Detail panel shows:
  - Header with image icon and filename
  - Inline image preview (the training curves plot)
  - Metadata card: Path, Size, Run ID
- Second bar shows download icon
- Breadcrumbs in top bar: `Experiments / exp / run / Images / training_curves.png`

### Test 16: Download image artifact

1. Click the download icon in the second bar

**Expected:**
- File downloads as `training_curves.png`
- Opening the downloaded file shows the training curves plot

### Test 17: Model artifact detail

1. Expand the Models category
2. If a model directory exists (e.g., `model`), click it

**Expected:**
- Detail panel shows:
  - Header with brain icon and directory name
  - MLmodel YAML content displayed as formatted text (model card)
  - File listing card: path, file count, total size, individual file names with sizes

3. If only a `.keras` file exists, click it

**Expected:**
- Header with brain icon
- Metadata card: Path, Size, Run ID
- Download icon in second bar

### Test 18: Download model artifact

1. Click the download icon on a model file

**Expected:**
- File downloads with correct extension (`.keras`, `.h5`, etc.)
- `MLmodel` files download as `MLmodel.yaml`

### Test 19: Model directory children

1. If a model directory exists, expand it in the tree

**Expected:**
- Child files listed (e.g., `MLmodel`, `model.keras`)
- Each with file size in parentheses
- Clicking a child shows its detail view

---

## Part 5: Tab Label

### Test 20: Dynamic tab label

1. Click on different sections in the Explorer tree: a project, an experiment, a storage bucket

**Expected:**
- The workspace tab label updates to match: "Projects", "Experiments", "Storage", etc.
- Not always "Explorer"

---

## Cleanup

No special cleanup needed. Runs persist in MLflow. To clean up test runs:
- Right-click a run in the tree > Delete Run
- Or use the delete icon in the run detail second bar

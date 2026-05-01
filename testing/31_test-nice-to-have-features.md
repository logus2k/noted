# Nice-to-Have Features - Test Procedure

Covers R11-R28 features implemented in Phase 4.

## Prerequisites

- noted is running with all services (Airflow, MLflow, MinIO, Serving, Graph)
- Projects with DVC data, Hydra configs, and Airflow DAGs
- Multiple MLflow experiment runs

---

## DVC Sync Icons (R11)

### Test 1: Pushed files show green cloud
1. Push a DVC tracked file (`dvc push`)
2. Refresh the Explorer tree

**Expected:** Green cloud icon next to the DVC badge for pushed files

### Test 2: Unpushed files show orange cloud-up
1. Track a new file with DVC but don't push
2. Refresh the Explorer tree

**Expected:** Orange cloud-up icon indicating file not pushed to remote

---

## Post-Run Summary Toast (R12)

### Test 3: Metrics in completion toast
1. Run a training with per-epoch metric logging
2. Wait for completion

**Expected:** Toast shows "Run name completed" with last metric values (e.g., "loss: 0.1234 | accuracy: 0.95")

---

## Pinned Metrics in Leaderboard (R13)

### Test 4: Columns button and dropdown
1. Open an experiment leaderboard
2. Click "Columns" button

**Expected:** Dropdown with Metrics (green) and Parameters (purple) checkboxes. Toggling rebuilds table.

---

## Epoch Progress Bar (R14)

### Test 5: Progress bar during training
1. Log `mlflow.log_metric('total_epochs', 50)` before training
2. Run training with per-epoch metrics

**Expected:** Progress bar in Live Metrics shows "Epoch X / 50" with filling bar and percentage

---

## Predict Cell Template (R16)

### Test 7: Insert predict cell from model version
1. Navigate to Models > model > version detail
2. Click "Insert Predict Cell"

**Expected:** New code cell appended to active notebook with mlflow.pyfunc.load_model template

---

## APIs Section (R17)

### Test 8: APIs section in Explorer
1. Expand the APIs section in the Explorer tree

**Expected:** Shows loaded model info (name + version) or "No model loaded" / "Serving unavailable"

---

## Bulk Run Management (R18)

### Test 9: Bulk delete runs
1. Open experiment detail with multiple runs
2. Multi-select runs in the list (Ctrl+click)
3. Click "Delete Selected"

**Expected:** Confirmation dialog, then selected runs are deleted. Page refreshes.

---

## Promote Best Config (R19)

### Test 10: Promote from leaderboard
1. Open leaderboard with metric data
2. Click "Promote Best"

**Expected:** Best run's params saved as Hydra template named "best_{metric}_{run_name}"

---

## Config Inheritance View (R20)

### Test 11: Source annotations in compose
1. Open Hydra Compose panel
2. Select group options and compose

**Expected:** Below YAML output, "Source Files" section shows which file defined each key (e.g., "model <- model/gru.yaml")

---

## Dynamic Task Generation (R21)

### Test 12: Mapped tasks display
1. Run a DAG with dynamic task mapping
2. Expand the run in the tree

**Expected:** Mapped tasks show with [index] suffix (e.g., "process[0]", "process[1]")

---

## Notebook-to-DAG Conversion (R22)

### Test 13: Export as @task
1. On a code cell header, click the rocket icon
2. Check clipboard

**Expected:** Clipboard contains the cell code wrapped in an `@task` decorated Airflow function

---

## DAG Validation (R23)

### Test 14: Validate button on DAG detail
1. Open a DAG detail page
2. Click "Validate"

**Expected:** Validation results show: green checks for passing, yellow warnings for pitfalls, red errors for syntax/import issues

---

## Jump to Error (R24)

### Test 15: Auto-scroll to error in logs
1. Open a failed task's log

**Expected:** Error lines highlighted in dark red. Log auto-scrolls to the first error line.

---

## Visual Cron Builder (R25)

### Test 16: Cron preset buttons
1. Open DAG detail, look at Schedule section

**Expected:** Preset buttons (@hourly, @daily, @weekly, Every 6h, Every 12h, Weekdays 9am). Clicking fills the cron input.

---

## Data-Aware Triggering (R26)

### Test 17: DVC files in trigger panel
1. Open trigger panel for a DAG tagged with a project
2. Look below the JSON config area

**Expected:** "Dataset Files" section showing DVC tracked files for that project with hashes

---

## Pipeline Health (R28)

### Test 18: Health dot on Pipelines root
1. Expand Pipelines in Explorer

**Expected:** Colored dot appears on "Pipelines" label (green = all healthy, red = failures, blue = running)

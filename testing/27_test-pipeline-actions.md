# Pipeline Actions - Copy Log, Retry Task, Config Template - Test Procedure

## Prerequisites

- noted is running
- At least one Airflow DAG configured and triggered (with both successful and failed runs)
- For config template testing: a DAG with configurable parameters and at least one completed run

---

## Part 1: Copy Log Action (T-4.R9)

### Test 1: Copy button appears in task log viewer

1. Navigate to Pipelines in the Explorer tree
2. Expand a DAG, then expand a DAG run
3. Click on a task to open the task log viewer

**Expected:**
- An action bar appears above the log output
- "Copy Log" button with clipboard icon is present
- Button is initially disabled while log loads

### Test 2: Copy log to clipboard

1. Wait for the log to finish loading
2. Click "Copy Log"

**Expected:**
- Button text changes to "Copied" with a check icon for 1.5 seconds
- Log text is now in your clipboard
- Paste (Ctrl+V) in any text editor to verify the full log content

### Test 3: Copy button disabled until loaded

1. Click a different task to trigger a new log load
2. Observe the Copy Log button immediately after clicking

**Expected:**
- Button is disabled (greyed out) while "Loading log..." is shown
- Button enables once log content appears

---

## Part 2: Retry Failed Task (T-4.R10)

### Test 4: Retry button appears for failed tasks

1. Find a DAG run that has a failed task (red X icon)
2. Click the failed task to open the log viewer

**Expected:**
- Action bar shows both "Copy Log" and "Retry Task" buttons
- Retry button has an orange outline and rotate icon

### Test 5: Retry button hidden for successful tasks

1. Click a successful task (green check icon)

**Expected:**
- Only "Copy Log" button visible
- No "Retry Task" button (task is not in a failed state)

### Test 6: Retry a failed task

1. Open a failed task's log viewer
2. Click "Retry Task"

**Expected:**
- Button changes to "Retrying..." with a spinner
- On success: toast notification "Task queued for retry"
- Button text changes to "Queued" with a check icon
- In the Airflow UI, the task instance should be cleared and re-queued

### Test 7: Retry failure handling

1. Stop the Airflow service
2. Try to retry a failed task

**Expected:**
- Error toast: "Retry failed: ..."
- Button re-enables with original text so you can try again

### Test 8: Retry for upstream_failed tasks

1. If a task is in "upstream_failed" state (failed because a dependency failed)
2. Click to open its log viewer

**Expected:**
- "Retry Task" button is present (upstream_failed is treated as retryable)

---

## Part 3: Config Template for Pipeline Runs (T-4.R7)

### Test 9: Load Last Run Config button appears

1. Right-click a DAG in the Explorer tree and select "Trigger"
2. The trigger panel opens

**Expected:**
- If the DAG has configurable parameters, a "Load Last Run Config" button appears
- Button has a clock-rotate-left icon
- Button appears between the parameter inputs and the JSON config textarea

### Test 10: Load config from last successful run

1. In the trigger panel, click "Load Last Run Config"

**Expected:**
- Button shows "Loading..." with spinner
- Parameter inputs are populated with values from the last successful run
- If no successful run found, falls back to the most recent run
- Button shows "Loaded" with check icon for 1.5s, then reverts

### Test 11: No previous runs

1. Create a new DAG that has never been triggered
2. Open its trigger panel
3. Click "Load Last Run Config"

**Expected:**
- Button text changes to "No previous runs"
- Parameter inputs remain at their default values

### Test 12: Modify loaded config and trigger

1. Load last run config
2. Change one parameter value
3. Click Trigger

**Expected:**
- DAG triggers with the modified parameter values
- The changed value is reflected in the new run's conf

### Test 13: Load Last Config button not shown for parameterless DAGs

1. Open trigger panel for a DAG with no configurable parameters

**Expected:**
- No "Load Last Run Config" button
- "This DAG has no configurable parameters." message shown

---

## Troubleshooting

- **Copy doesn't work:** Check browser permissions for clipboard API. Some browsers require HTTPS or user gesture for `navigator.clipboard.writeText()`.
- **Retry returns error:** Check Airflow API logs. The `clearTaskInstances` endpoint requires the DAG run to still exist and not be in a locked state.
- **Load Last Config returns nothing:** Verify the DAG has at least one completed run with conf. Check `GET /api/airflow/dags/{dag_id}/runs?limit=5` returns runs with conf objects.

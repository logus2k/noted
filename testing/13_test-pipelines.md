# Pipelines (Airflow) - Test Procedure

## Prerequisites

- noted is running with all Airflow containers (apiserver, scheduler, worker, triggerer, dag-processor)
- At least one DAG exists (e.g., `noted_test_dag` and `jena_training_pipeline`)
- Airflow is accessible at `/airflow`

---

## Part 1: Pipelines Section in Explorer

### Test 1: Pipelines section appears

1. In the Explorer tree, look for the "Pipelines" section

**Expected:**
- A "Pipelines" section appears with a blue diagram-project icon
- Section is expandable

### Test 2: Expand Pipelines

1. Click the Pipelines section to expand

**Expected:**
- DAGs are listed as child nodes
- Active DAGs show the diagram-project icon (blue)
- Paused DAGs show the circle-pause icon (orange)
- `noted_test_dag` and `jena_training_pipeline` are visible among the DAGs

### Test 3: Pipelines root detail

1. Click Pipelines section to view its detail page

**Expected:**
- Status: Connected (green)
- DAGs count, Active count, Paused count
- "All DAGs" section listing each DAG with icon, name, schedule, and tags

### Test 4: Expand a DAG

1. Click on a DAG node (e.g., `jena_training_pipeline`) to expand

**Expected:**
- Recent runs appear as children (or "No runs yet" if none)
- Each run shows: datetime, state, and appropriate status icon

### Test 5: DAG detail page

1. Click a DAG to view its detail

**Expected:**
- Header with DAG name and status icon
- Subtitle showing Active/Paused status, schedule, and tags
- Info card: Status, Description, Schedule, Owners, Tags, Next Run
- "Trigger Run" and "Pause/Unpause" buttons
- "Recent Runs" section listing runs with status icons, run IDs, and dates

---

## Part 2: Triggering DAGs

### Test 6: Trigger a simple DAG (no params)

1. Click `noted_test_dag` in the tree
2. Click the "Trigger Run" button in the detail page
3. In the trigger panel, click "Trigger"

**Expected:**
- Success message: "DAG run triggered" with Run ID and State
- Toast notification: "DAG run triggered"
- DAG tree node refreshes and shows the new run

### Test 7: Trigger a DAG with parameters

1. Click `jena_training_pipeline` in the tree
2. Click "Trigger Run"

**Expected:**
- Trigger panel shows "Parameters" section with 7 fields:
  - model_type (text, default: GRU)
  - epochs (number, default: 30)
  - batch_size (number, default: 256)
  - learning_rate (number, default: 0.0005)
  - units1 (number, default: 128)
  - units2 (number, default: 64)
  - dropout (number, default: 0.2)
- Each parameter shows its description below the key name

3. Modify some values (e.g., change epochs to 50, model_type to LSTM)
4. Click "Trigger"

**Expected:**
- Success message with Run ID
- DAG tree refreshes with the new run

### Test 8: Trigger with additional JSON config

1. Open trigger panel for any DAG
2. In the "Additional Config (JSON)" textarea, enter: `{"custom_key": "custom_value"}`
3. Click "Trigger"

**Expected:**
- Run is triggered with the merged config (params + additional JSON)
- Run detail shows the config in its metadata

### Test 9: Trigger with invalid JSON

1. Enter invalid JSON in the config textarea (e.g., `{bad json}`)
2. Click "Trigger"

**Expected:**
- Error message: "Invalid JSON: ..." displayed below the button
- No run is triggered

---

## Part 3: Run Monitoring

### Test 10: Run status in tree

1. Trigger a DAG run
2. Watch the tree node for the run

**Expected:**
- Initially shows clock icon (orange) with "queued" state
- Updates automatically to circle-play (blue) "running" then circle-check (green) "success"
- Toast notification appears on completion: "Pipeline [dag_id] completed"

### Test 11: Run detail page

1. Click on a completed run in the tree

**Expected:**
- State shown with colored label (green "success", red "failed", etc.)
- Run ID, Logical Date, Started, Ended times
- Config (if any) shown as formatted JSON
- "Tasks" section listing task instances

### Test 12: Task execution order

1. View a run with multiple tasks (e.g., `jena_training_pipeline`)

**Expected:**
- Tasks sorted by start time (execution order)
- Each task shows: HH:MM:SS start time, status icon, task name, operator, duration
- Execution order is clear from timestamps

### Test 13: Task log viewer

1. Click on a task in the run detail

**Expected:**
- Dark terminal-style log viewer appears
- Log shows timestamped entries: `[HH:MM:SS] [LEVEL] message`
- Log content matches what the task printed

---

## Part 4: Pause/Unpause

### Test 14: Pause an active DAG

1. Open detail for an active (unpaused) DAG
2. Click "Pause" button

**Expected:**
- Toast: "DAG paused"
- Detail page refreshes showing "Paused" status (orange)
- Tree node icon changes to circle-pause (orange)

### Test 15: Unpause a paused DAG

1. Open detail for a paused DAG
2. Click "Unpause" button

**Expected:**
- Toast: "DAG unpaused"
- Detail page refreshes showing "Active" status (green)
- Tree node icon changes to diagram-project (blue)

---

## Part 5: Navigation

### Test 16: Service iframe navigation

1. Click the Airflow icon in the sidebar to open the Airflow iframe
2. Navigate within the Airflow UI (click a DAG, view a run)

**Expected:**
- URL shown in the top bar updates as you navigate
- Back/Forward buttons work within the iframe
- Home button returns to the Airflow root page
- Refresh button reloads the current page

### Test 17: Link interception

1. In the Airflow iframe, click a link that would normally open in a new tab

**Expected:**
- If the link is to an Airflow page, it navigates within the iframe (no new tab)
- If the link is to an external site, it opens in a new browser tab

---

## Part 6: Trigger from Explorer Title Bar

### Test 18: Trigger icon in title bar

1. Select a DAG node in the tree

**Expected:**
- A trigger icon (chart-simple, blue) appears in the Explorer sidebar title bar
- Clicking it opens the trigger panel for that DAG

---

## Part 7: Live Pipeline Monitoring (T-2.7)

### Test 19: Run status updates in real-time

1. Expand a DAG node (e.g., `noted_test_dag`) in the tree
2. Unpause the DAG if paused
3. Trigger a new DAG run
4. Watch the tree while the run executes

**Expected:**
- A new DAG Run node appears under the DAG with a clock icon and "queued" state
- The icon changes to play (running) then check (success) automatically
- The title updates with the current state
- No manual refresh needed

### Test 20: Task status updates in real-time

1. Expand a DAG with multiple tasks (e.g., `jena_training_pipeline`)
2. Unpause and trigger it
3. Expand the new DAG Run node to see tasks

**Expected:**
- Task nodes update their icons and titles as each task progresses
- Each task shows: state, start time, and duration (e.g., "validate_data (success) - 14:32:10 (0.5s)")
- Tasks update independently - `validate_data` completes before `train_model` starts
- Final state shows all tasks with their individual timing

### Test 21: Toast on completion

1. Trigger a DAG run
2. Wait for it to complete

**Expected:**
- A success toast appears: "Pipeline [dag_id] completed"
- If the run fails, an error toast appears: "Pipeline [dag_id] failed"

### Test 22: Multiple concurrent runs

1. Trigger two different DAGs quickly (e.g., `noted_test_dag` then `jena_training_pipeline`)
2. Watch both DAG Run nodes in the tree

**Expected:**
- Both runs update independently and in real-time
- Each run shows its own state progression
- Toasts appear for each completion separately

---

## Part 8: DAG Run History (T-2.8 + T-2.15)

### Test 23: History table shows on DAG detail

1. Click on a DAG that has been triggered at least twice (e.g., `noted_test_dag`)

**Expected:**
- A "DAG Run History" table appears below the trigger/pause buttons
- Table has columns: State icon, Started, Duration, State, MLflow
- Rows are sorted by most recent first
- Each row shows the run's start datetime and duration (e.g., "63.5s")

### Test 24: History row navigates to run detail

1. Click on any row in the history table

**Expected:**
- The tree navigates to and expands the corresponding DAG Run node
- The run detail page opens showing metrics, tasks, and graph

### Test 25: Duration shows correctly

1. Look at completed runs in the history table

**Expected:**
- Completed runs show duration in seconds (e.g., "2.3s", "63.5s")
- Queued or running runs show "-" for duration
- Runs with no start_date show "-" for both Started and Duration

### Test 26: MLflow link (when available)

1. Trigger a DAG that passes `mlflow_run_id` in its conf:
   ```python
   dag.trigger(conf={"mlflow_run_id": "abc123..."})
   ```
2. After completion, check the history table

**Expected:**
- The MLflow column shows the first 8 characters of the run ID as a clickable link
- Clicking the link navigates to the MLflow run in the Experiments tree
- If the run is not found in the tree, a toast notification appears

### Test 27: Empty history

1. Click on a DAG that has never been triggered

**Expected:**
- No history table shown (or "No runs yet" message)
- Only the info card and trigger/pause buttons visible

---

## Part 8: Pipeline Status Bar

### Test 28: Status bar - idle state

1. Check the bottom status bar
2. No DAG runs should be active

**Expected:**
- No pipeline pill visible in the status bar (hidden when idle)

### Test 29: Status bar - single active run

1. In Explorer > Pipelines, find an active (unpaused) DAG
2. Trigger a DAG run
3. Watch the bottom status bar

**Expected:**
- A blue pill appears: `<dag_name> running` with a diagram-project icon
- The pill disappears when the run completes (transitions to success/failed)

### Test 30: Status bar - multiple active runs

1. Trigger a DAG run on one DAG
2. Quickly trigger a run on another DAG (before the first completes)

**Expected:**
- The blue pill shows: "2 DAG runs active"
- As each run completes, the count decreases
- When all runs complete, the pill disappears

### Test 31: Status bar real-time updates

1. Trigger a multi-task DAG (e.g., jena_training_pipeline with 3 tasks)
2. Watch the status bar while it runs

**Expected:**
- The pill stays visible throughout the execution
- Disappears only after the final task completes and the run state changes to success/failed

---

## Part 9: Pipeline Scheduling (T-2.10)

### Test 32: Schedule section visible

1. Click on a DAG in the Pipelines tree (e.g., `jena_training_pipeline`)
2. Look for the "Schedule" section in the detail panel

**Expected:**
- A "SCHEDULE" section appears with a text input, Set button, and Clear button
- A note about ~30s parse cycle delay is shown
- Input is empty if no schedule is set (default)

### Test 33: Set a cron schedule

1. Enter `*/5 * * * *` (every 5 minutes) in the schedule input
2. Click "Set"

**Expected:**
- Toast: "Schedule set: */5 * * * *"
- After ~30 seconds, the DAG's timetable_summary in Airflow changes from "Never" to the cron expression
- The DAG must be unpaused for scheduled runs to execute

### Test 34: Schedule persists on reload

1. Close the DAG detail panel
2. Reopen the DAG detail

**Expected:**
- The schedule input shows `*/5 * * * *` (loaded from the Airflow Variable)

### Test 35: Clear a schedule

1. Click "Clear"

**Expected:**
- Toast: "Schedule cleared"
- Input is now empty
- The Airflow Variable is deleted
- After ~30 seconds, the DAG reverts to "Never, external triggers only"

### Test 36: Common cron expressions

Try setting these schedules and verify they are accepted:
- `@daily` (once a day at midnight)
- `@hourly` (every hour)
- `0 9 * * MON-FRI` (weekdays at 9 AM)
- `0 */6 * * *` (every 6 hours)

**Expected:**
- All are accepted and saved as Airflow Variables
- Airflow's schedule display updates accordingly after the parse cycle

---

## Part 11: New DAG from Template (T-4.R3)

### Test 45: Context menu shows "New DAG from Template"

1. In Explorer, right-click on a project node (e.g., Examples)

**Expected:**
- Context menu includes "New DAG from Template" with orange diagram-project icon

### Test 46: Same option on project nodes

1. Right-click on a project node (e.g., noted-testing)

**Expected:**
- Context menu also includes "New DAG from Template"

### Test 47: Template dialog opens

1. Click "New DAG from Template"

**Expected:**
- Modal form opens with title "New DAG from Template"
- Two fields: DAG ID (text input) and Template (dropdown)
- Template options: Blank DAG, Training Pipeline, Data Pipeline, Parallel Pipeline
- Create and Cancel buttons

### Test 48: Create a blank DAG

1. Enter DAG ID: "my_test_dag"
2. Select "Blank DAG" template
3. Click Create

**Expected:**
- Toast: "DAG created: dags/my_test_dag.py"
- Project tree refreshes showing the new file under dags/
- File contains valid Airflow 3.0 Python code with @dag decorator

### Test 49: Create a training pipeline

1. Enter DAG ID: "my_training"
2. Select "Training Pipeline"
3. Click Create

**Expected:**
- File created with validate_data -> train_model -> evaluate_model tasks
- Includes Param definitions (model_type, epochs, learning_rate)
- Uses Variable.get for dynamic scheduling

### Test 50: Duplicate DAG ID rejected

1. Try to create a DAG with the same ID as an existing one

**Expected:**
- Error: "File already exists: dags/{filename}.py"

### Test 51: DAG appears in Pipelines after Airflow parse

1. After creating a DAG, wait 30 seconds for Airflow to parse it
2. Check the Pipelines section in Explorer

**Expected:**
- New DAG appears in the Pipelines tree
- Can be triggered and monitored like any other DAG

### Test 52: Open created DAG in editor

1. Navigate to the created DAG file in the project tree
2. Click to open it

**Expected:**
- Opens in the Python file editor
- Syntax highlighted
- Editable

---

## Troubleshooting

- **"Airflow not reachable":** Check that all Airflow containers are running (`docker ps | grep airflow`)
- **0 DAGs shown:** Airflow may need time to parse DAGs after restart. Wait 30 seconds and refresh
- **401 Unauthorized:** JWT token failed. Check Airflow credentials in `.env` file
- **422 on trigger:** The DAG may require `logical_date` - this is handled automatically
- **Task log shows "Failed to fetch log":** The task may not have started yet, or the log endpoint format differs
- **MLflow link does nothing:** The Experiments tree may not be expanded yet. Expand it first, then click the link
- **Schedule doesn't take effect:** Ensure the DAG uses `Variable.get("{dag_id}_schedule", default_var=None)` pattern. Wait ~30 seconds for the DAG parse cycle.

---

## Part 10: Parameter Sweep (T-2.9 + T-2.13)

### Test 37: Sweep button visible for parameterized DAGs

1. In Pipelines, click a DAG that has parameters (e.g., `jena_training_pipeline`)
2. In the DAG detail, click "Run DAG" to open the trigger panel

**Expected:**
- Two buttons visible: "Trigger" and "Sweep" (blue)
- "Sweep" button only appears for DAGs with parameters

### Test 38: Sweep button not visible for non-parameterized DAGs

1. Open the trigger panel for `noted_test_dag` (no parameters)

**Expected:**
- Only the "Trigger" button is visible
- No "Sweep" button

### Test 39: Sweep panel opens

1. Click "Sweep" in the trigger panel for `jena_training_pipeline`

**Expected:**
- A new jsPanel opens titled "Sweep: jena_training_pipeline"
- All DAG parameters shown with text inputs (pre-filled with current values)
- Instruction text about comma-separated values
- "Combination Preview" section
- "Submit Sweep" button

### Test 40: Multi-value input and preview

1. In the sweep panel, change `model_type` to `GRU, LSTM`
2. Change `learning_rate` to `0.001, 0.0005`
3. Keep all other parameters as single values

**Expected:**
- Preview table updates live as you type
- Table shows 4 rows (2x2 combinations):
  - GRU + 0.001
  - GRU + 0.0005
  - LSTM + 0.001
  - LSTM + 0.0005
- Counter shows "4 combinations will be triggered"

### Test 41: Three-way sweep

1. Add a third multi-value: `epochs` = `10, 30`

**Expected:**
- Preview table updates to show 8 rows (2x2x2)
- Counter shows "8 combinations will be triggered"

### Test 42: Submit sweep

1. Set a small sweep: `model_type` = `GRU, LSTM` (2 combinations)
2. Ensure the DAG is unpaused
3. Click "Submit Sweep"

**Expected:**
- Button shows "Submitting..."
- Result area shows:
  - "Sweep submitted: 2 runs"
  - Sweep ID
  - Each run listed with index, params, and state (queued)
- Toast: "Sweep: 2 runs submitted"
- DAG tree node refreshes to show the new runs

### Test 43: Sweep runs execute

1. After submitting a sweep, watch the Pipelines tree

**Expected:**
- Both runs appear under the DAG node
- Status bar shows "2 DAG runs active" (if monitoring is active)
- Runs complete independently (may finish in different order)
- Each run's conf includes `_sweep_id` and `_sweep_index` tags

### Test 44: Single-value sweep rejected

1. In the sweep panel, enter only single values for all parameters (no commas)
2. Click "Submit Sweep"

**Expected:**
- Message: "No multi-value parameters. Use Trigger for a single run."
- No runs are triggered

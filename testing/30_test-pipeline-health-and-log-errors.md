# Pipeline Health Indicators and Log Error Jump - Test Procedure

## Prerequisites

- noted is running
- At least 2 Airflow DAGs configured (one with recent success, one with recent failure if possible)
- At least one DAG run with a failed task (for error jump testing)

---

## Part 1: Pipeline Health Indicators (R28)

### Test 1: Health dot appears on Pipelines root

1. Expand the Pipelines section in the Explorer tree

**Expected:**
- After DAGs load, a colored dot appears next to the "Pipelines" label
- The dot indicates aggregated health of all active (non-paused) DAGs

### Test 2: Green health (all healthy)

1. Ensure all DAGs' latest runs are in "success" state

**Expected:**
- Green dot on Pipelines root
- Hover tooltip: "All pipelines healthy"

### Test 3: Red health (some failed)

1. Trigger a DAG that will fail (e.g., with invalid config)
2. Wait for it to fail
3. Collapse and re-expand Pipelines section

**Expected:**
- Red dot on Pipelines root
- Hover tooltip: "Some pipelines failed"

### Test 4: Blue health (running)

1. Trigger a DAG that takes some time
2. While it's running, collapse and re-expand Pipelines

**Expected:**
- Blue dot on Pipelines root
- Hover tooltip: "Pipelines running"

### Test 5: Paused DAGs excluded

1. Pause all DAGs
2. Re-expand Pipelines section

**Expected:**
- No health dot (paused DAGs are not considered)

---

## Part 2: Jump to Error in Task Logs (R24)

### Test 6: Error lines highlighted

1. Navigate to a failed DAG run
2. Click on the failed task to view its log

**Expected:**
- Log viewer loads with dark terminal background
- Lines containing ERROR, CRITICAL, Exception, Traceback, or "Error:" are highlighted with a dark red background (#4a1a1a)
- Other lines display normally

### Test 7: Auto-scroll to first error

1. Open a long task log that has errors somewhere in the middle/end

**Expected:**
- Log viewer automatically scrolls to the first error line
- The error line is centered in the visible area (smooth scroll)

### Test 8: No errors in log

1. Open a task log from a successful task

**Expected:**
- No highlighted lines
- No auto-scroll (stays at top)
- Log displays normally

### Test 9: Multiple error lines

1. Open a log with multiple errors (e.g., traceback with several frames)

**Expected:**
- All error-matching lines are highlighted
- Auto-scroll goes to the FIRST error line only

---

## Part 3: Pinned Metrics in Leaderboard (R13)

### Test 10: Columns button visible

1. Navigate to an experiment with multiple runs
2. Open the leaderboard

**Expected:**
- A "Columns" button (purple background) appears in the title row next to the CSV export button

### Test 11: Column selector dropdown

1. Click the "Columns" button

**Expected:**
- Dropdown appears with two sections: Metrics (green header) and Parameters (purple header)
- Each metric/param has a checkbox
- All metrics are checked by default
- First 6 params are checked by default, rest unchecked

### Test 12: Toggle metric column off

1. Uncheck a metric in the dropdown

**Expected:**
- Table immediately rebuilds without that metric column
- Other columns unaffected
- Leaderboard data still displays correctly

### Test 13: Toggle param column on

1. Check a parameter that was not visible

**Expected:**
- New param column appears in the table
- Values shown for all runs

### Test 14: Close dropdown

1. Click outside the dropdown

**Expected:**
- Dropdown closes
- Column selections persist (table stays in current state)

### Test 15: Sorting works with custom columns

1. Remove some columns, add others
2. Click a sortable column header

**Expected:**
- Sorting works correctly with the current column set

---

## Troubleshooting

- **No health dot:** Check that at least one DAG is active (not paused) and has at least one run. The health check runs async after DAGs load.
- **Error highlighting not working:** Check that the log text contains keywords like ERROR, CRITICAL, Exception, Traceback. The pattern is case-insensitive.
- **Column dropdown doesn't appear:** Click directly on the Columns button. The dropdown is positioned relative to the button wrapper.

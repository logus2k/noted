# Run Comparison - Test Procedure

## Prerequisites

- noted is running
- At least one experiment with 2+ runs exists (e.g., `noted-testing` with multiple `gru_live_metrics_test` runs)
- Runs should have metrics, parameters, and tags logged

---

## Part 1: Opening Run Detail as Tab

### Test 1: Single-click opens preview tab

1. In the Explorer tree, expand Experiments and an experiment
2. Single-click on a run

**Expected:**
- A tab opens in the center pane with the run name as label
- Tab label is in italic (preview/transient tab)
- Run detail shows: status, run ID, timestamps, duration, metrics, parameters, tags, inline charts

### Test 2: Preview tab gets replaced

1. With a preview run detail tab open, single-click a different run

**Expected:**
- The previous preview tab is replaced by the new run's detail
- Only one preview tab exists at a time

### Test 3: Double-click pins the tab

1. Double-click on a run in the tree

**Expected:**
- Tab label changes from italic to normal (pinned)
- Clicking other runs opens new preview tabs without replacing this one

### Test 4: Multiple pinned tabs

1. Double-click run A to pin it
2. Double-click run B to pin it

**Expected:**
- Two pinned run detail tabs exist side by side
- Clicking each tab switches between them

---

## Part 2: Run Detail Tab Actions

### Test 5: Second bar icons

1. Open a run detail tab (single or double click)

**Expected:**
- Second bar shows three icons (left-aligned):
  - Compare (code-compare, teal)
  - Metrics popout (chart-simple, blue)
  - Delete (trash, red)
- First bar shows: run name + undock + close buttons

### Test 6: Metrics popout from tab

1. Click the chart-simple icon in the second bar

**Expected:**
- A MetricsPanel floating window opens with the run's metric histories
- Charts render correctly (same as before)

### Test 7: Delete run from tab

1. Click the trash icon in the second bar

**Expected:**
- Confirmation dialog appears
- Confirm deletes the run, closes the tab, removes from tree

---

## Part 3: Run Comparison

### Test 8: Start comparison

1. Open a run detail tab
2. Click the compare icon (code-compare) in the second bar (or Explorer title bar)

**Expected:**
- A modal dropdown appears listing all other runs in the same experiment
- Each option shows: run name (short ID) - status

### Test 9: Cancel comparison

1. Start a comparison (Test 8)
2. Click Cancel

**Expected:**
- Modal closes, nothing happens

### Test 10: View comparison panel

1. Start a comparison and select a run, click OK

**Expected:**
- A floating jsPanel opens titled "Compare: [Run A] vs [Run B]"
- Panel contains:
  - **Header**: two color-coded cards (green for Run A, blue for Run B) with date, name, and short ID
  - **Metrics table**: all metrics side-by-side with delta column (absolute + percentage)
  - **Parameters table**: all params side-by-side
  - **Tags table**: user tags (mlflow.* filtered out)
  - **Metric History charts**: overlaid line charts (green/blue) for time-series metrics

### Test 11: Diff highlighting

1. In the comparison panel, check the metrics and parameters tables

**Expected:**
- Rows where values differ are highlighted in amber (#fff8e1)
- Rows where values match have white background
- Metric delta column shows:
  - Green down arrow for decrease
  - Red up arrow for increase
  - Percentage change in parentheses

### Test 12: Comparison charts

1. Scroll to the Metric History section

**Expected:**
- 2-column grid of ECharts line charts
- Each chart shows both runs overlaid (green = Run A, blue = Run B)
- Tooltips show values for both runs on hover
- Legend at bottom identifies each run
- Single-point metrics (test_mae_c, etc.) are not shown as charts

### Test 13: Multiple comparisons

1. Open a comparison panel for Run A vs Run B
2. Open another comparison for Run A vs Run C

**Expected:**
- Two separate comparison panels open (cascaded offset)
- Each is independent and can be closed separately

---

## Part 4: Undock/Dock Run Detail

### Test 14: Undock run detail

1. Open a run detail tab (pin it with double-click)
2. Click the undock button (up-right-from-square) in the first bar

**Expected:**
- Run detail becomes a floating jsPanel
- Second bar with action icons (compare, metrics, delete) is visible
- Content scrolls correctly
- Tab disappears from the tab bar

### Test 15: Dock run detail back

1. With an undocked run detail, click the dock button in the jsPanel header

**Expected:**
- Panel docks back as a tab in the center pane
- Content is preserved (same run detail, same scroll position)
- Second bar icons still work

### Test 16: Close undocked panel

1. With an undocked run detail, click the X close button

**Expected:**
- Panel closes and is destroyed
- No orphan tabs remain

### Test 17: Multiple undocked panels

1. Pin two run detail tabs
2. Undock both

**Expected:**
- Two independent floating panels
- Each has its own content
- Closing one does not affect the other
- The other panel's content remains intact

### Test 18: Close docked tab while undocked exists

1. Open run A (pin it), open run B (pin it)
2. Undock run A
3. Close run B's docked tab

**Expected:**
- Run B's tab closes
- Run A's undocked panel is unaffected, content still visible

---

## Cleanup

Close any open comparison panels and run detail panels via their X buttons.

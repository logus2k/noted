# Run Leaderboard - Test Procedure

## Prerequisites

- noted is running
- At least one MLflow experiment with 3+ finished runs (e.g., run test_notebook.ipynb multiple times with different parameters)

---

## Part 1: Leaderboard Display

### Test 1: Leaderboard appears in experiment detail

1. In Explorer, navigate to Experiments
2. Click on an experiment that has multiple runs (e.g., `noted-testing`)

**Expected:**
- Experiment detail page shows a "Leaderboard (N runs)" section
- A sortable table with columns: snapshot star, Run name, Date, metric columns, param columns
- Metric column headers have green background
- Param column headers have purple background
- CSV export button at top right of leaderboard title

### Test 2: All runs displayed

1. Verify the leaderboard shows all runs in the experiment

**Expected:**
- Each run has: name + short ID, date, all metric values, up to 6 param values
- Alternating row colors (white/#f8f8f8)
- Hover highlights rows in light blue (#eef5ff)

### Test 3: Best metric highlighting

1. Look at metric columns

**Expected:**
- The best value in each metric column is bold green
- "Best" = lowest for loss/mae/rmse metrics, highest for r2/accuracy/f1

---

## Part 2: Sorting

### Test 4: Sort by metric (descending)

1. Click on a metric column header (e.g., `test_mae_c`)

**Expected:**
- Rows reorder by that metric (descending by default - highest first)
- Column header shows a down arrow (▼)

### Test 5: Toggle sort direction

1. Click the same column header again

**Expected:**
- Sort direction reverses (ascending - lowest first)
- Arrow changes to ▲
- For MAE/RMSE, ascending puts the best value at the top

### Test 6: Sort by date

1. Click the "Date" column header

**Expected:**
- Runs sorted by start time
- Toggle between newest-first and oldest-first

### Test 7: Sort by different metric

1. Click a different metric column (e.g., `val_loss`)

**Expected:**
- Previous sort indicator removed
- New column shows sort arrow
- Rows reordered by the new metric

---

## Part 3: Row Interaction

### Test 8: Click row navigates to run

1. Click on any row in the leaderboard

**Expected:**
- The corresponding run node is activated in the Explorer tree
- Run detail page opens (or undockable tab)

### Test 9: Snapshot badge

1. If any run has been snapshotted, check its row

**Expected:**
- A gold star icon appears in the first column for snapshot runs
- Non-snapshot runs have an empty first column

---

## Part 4: CSV Export

### Test 10: Export leaderboard as CSV

1. Click the CSV export button (download icon)

**Expected:**
- A file `leaderboard_{experiment_id}.csv` is downloaded
- Contains all columns except the snapshot star
- Headers: Run, Date, metric names, param names
- Values match what's displayed in the table
- Numbers not truncated (full precision)

### Test 11: CSV after sorting

1. Sort the table by a metric
2. Export CSV

**Expected:**
- CSV contains all runs (not just sorted view - export includes all data)

---

## Part 5: Edge Cases

### Test 12: Experiment with one run

1. Open an experiment that has only 1 run

**Expected:**
- Leaderboard shows with 1 row
- Sorting still works (no crash on single row)
- Best value highlighted (only value = best)

### Test 13: Run with missing metrics

1. If some runs have different metric keys (e.g., one run logged extra metrics)

**Expected:**
- Missing values shown as "-" in grey
- Sorting treats missing values as worst (pushed to bottom)

---

## Troubleshooting

- **Empty leaderboard:** Check that the experiment has runs. The leaderboard uses the `/leaderboard` endpoint which requires at least one run.
- **No metric columns:** The experiment runs may not have logged any metrics.
- **Sorting doesn't work:** Ensure you're clicking the column header, not the cell. Only Date and metric columns are sortable.

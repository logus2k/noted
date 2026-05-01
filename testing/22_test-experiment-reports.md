# Experiment Reports - Test Procedure

## Prerequisites

- noted is running
- At least one MLflow experiment with 3+ FINISHED runs
- Runs should have metrics logged (e.g., from emi_tutorial2.ipynb)
- Pandoc installed in the noted container (required for Word generation)

---

## Part 1: Report Generation from UI

### Test 1: Export buttons visible

1. In Explorer, navigate to Experiments > click an experiment with runs
2. Look below the Leaderboard table

**Expected:**
- Two buttons: "Export Word" (blue) and "Export Markdown" (grey)

### Test 2: Generate Word report

1. Click "Export Word"

**Expected:**
- Toast: "Generating word report..."
- A .docx file downloads after a few seconds
- Toast: "Report downloaded"

### Test 3: Word report content

1. Open the downloaded .docx file

**Expected:**
- Title: "Experiment Report: {experiment_name}"
- Table of Contents (if enabled)
- Summary section: experiment ID, total runs, finished runs, date range
- Leaderboard table: run names, status, metric values (snapshot runs marked with *)
- Parameters section: varying params table + constant params list
- Metric Charts section:
  - Metrics Comparison bar chart (top runs side by side, best value highlighted)
  - Convergence line charts for top metrics (multiple runs overlaid)
- Lineage table: run name, data hash, config hash, git commit
- Snapshot details (if any): name, branch, commit, description, key metrics
- Footer with generation timestamp

### Test 4: Generate Markdown report

1. Click "Export Markdown"

**Expected:**
- A .md file downloads
- Contains same content as Word but in Markdown format
- Chart images referenced but not embedded (Markdown references only)

---

## Part 2: Report Quality

### Test 5: Charts are readable

1. Open the Word report and inspect the charts

**Expected:**
- Bar chart: clean colors, readable axis labels, rotated run names, best value has thicker border
- Line charts: multiple runs overlaid with legend, proper axis labels, grid lines
- Images are properly sized (not stretched or tiny)

### Test 6: Tables are formatted

1. Check the leaderboard and parameter tables

**Expected:**
- Columns are aligned
- Metric values show 6 decimal places
- Run names are readable
- Snapshot runs marked with asterisk and bold

### Test 7: Report with snapshots

1. Generate a report for an experiment that has a snapshot

**Expected:**
- Summary shows snapshot count
- Leaderboard marks snapshot runs with *
- Dedicated "Snapshots" section with name, branch, commit, description, metrics

---

## Part 3: Report API

### Test 8: API with default parameters

1. In browser:
```
/api/reports/experiment/{experiment_id}?format=markdown
```

**Expected:**
- Returns Markdown content as a file download
- Default: sorted by start time, top 10 runs

### Test 9: API with sorting

1. Call:
```
/api/reports/experiment/{experiment_id}?format=word&sort_by=test_mae_c&sort_order=asc&top_n=5
```

**Expected:**
- Word report with runs sorted by test_mae_c ascending
- Only top 5 runs included

### Test 10: API with empty experiment

1. Call the API for an experiment with no runs

**Expected:**
- Returns 400: "No runs found in experiment {id}"

---

## Part 4: Edge Cases

### Test 11: Single run experiment

1. Generate report for an experiment with only 1 run

**Expected:**
- Report generates successfully
- Leaderboard has 1 row
- No "varying parameters" section (nothing varies with 1 run)
- Charts show single bar / single line

### Test 12: Runs without metric history

1. Generate report for runs that only logged final metrics (no per-step history)

**Expected:**
- Metrics comparison bar chart still works (uses final values)
- Convergence charts skipped for metrics with no history (single data point)

---

## Troubleshooting

- **"pandoc not found":** Pandoc must be installed in the noted container. Check Dockerfile.
- **Word report fails but Markdown works:** Pandoc conversion issue. Check noted container logs.
- **Charts missing from Word:** Check that matplotlib is available in the noted container (`docker exec noted python3 -c "import matplotlib"`).
- **Empty charts:** Runs may not have logged the expected metrics. Check the leaderboard table in the report to verify metric values exist.

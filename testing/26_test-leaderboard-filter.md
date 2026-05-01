# Leaderboard Config Search/Filter - Test Procedure

## Prerequisites

- noted is running
- An MLflow experiment with multiple runs having different parameter values and metrics
- At least 5+ runs recommended for meaningful filter testing

---

## Part 1: Filter Bar Appearance

### Test 1: Filter bar visible

1. Navigate to an experiment in the Explorer tree
2. Click the experiment to open its detail page
3. Scroll to the Leaderboard section

**Expected:**
- A filter bar with a filter icon appears between the title row and the table
- Placeholder text: "Filter: model_type=GRU, lr>0.001, epochs>=30"
- The input has a monospace font

---

## Part 2: Filtering by Parameters

### Test 2: Exact match filter

1. Type `model_type=GRU` in the filter bar

**Expected:**
- Table updates after ~300ms (debounced)
- Only runs where `model_type` param equals "GRU" are shown
- Title updates to show "Leaderboard (N/M runs)" where N is filtered count and M is total

### Test 3: Case-insensitive string match

1. Type `model_type=gru` (lowercase)

**Expected:**
- Same results as Test 2 (comparison is case-insensitive for strings)

### Test 4: Not-equal filter

1. Type `model_type!=GRU`

**Expected:**
- All runs EXCEPT those with model_type=GRU are shown

### Test 5: Multiple filters (comma-separated)

1. Type `model_type=GRU, epochs>=30`

**Expected:**
- Only runs matching BOTH conditions are shown
- AND logic: all filters must match

---

## Part 3: Filtering by Metrics

### Test 6: Greater-than filter on metric

1. Type `val_loss<0.5`

**Expected:**
- Only runs where the val_loss metric is less than 0.5
- Numeric comparison (not string comparison)

### Test 7: Greater-or-equal filter

1. Type `r2_score>=0.8`

**Expected:**
- Runs where r2_score is 0.8 or higher

### Test 8: Combined param + metric filter

1. Type `model_type=GRU, val_loss<0.3`

**Expected:**
- Only GRU runs with val_loss below 0.3

---

## Part 4: Edge Cases

### Test 9: Empty filter

1. Clear the filter input

**Expected:**
- All runs shown again
- Title reverts to "Leaderboard (N runs)"

### Test 10: Non-existent key

1. Type `nonexistent_param=value`

**Expected:**
- No runs shown (no run has this param/metric)
- Title shows "Leaderboard (0/M runs)"

### Test 11: Invalid expression

1. Type `just some text` (no operator)

**Expected:**
- No crash
- All runs shown (invalid expressions are ignored)

### Test 12: Sorting works with filter active

1. Apply a filter (e.g., `model_type=GRU`)
2. Click a sortable metric column header

**Expected:**
- Filtered runs are sorted
- Filter remains active after sorting

---

## Troubleshooting

- **Filter not working:** Check browser console for JavaScript errors. The filter parses expressions matching `key(>=|<=|!=|>|<|=)value` pattern.
- **Numeric comparison wrong:** Values are compared numerically if both sides parse as numbers, otherwise string comparison is used.
- **Debounce too slow/fast:** Filter triggers 300ms after last keypress. This is intentional to avoid filtering on every keystroke.

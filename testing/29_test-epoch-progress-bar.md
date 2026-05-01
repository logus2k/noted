# Epoch Progress Bar - Test Procedure

## Prerequisites

- noted is running
- A notebook that logs per-epoch metrics (e.g., `mlflow.log_metric('loss', val, step=epoch)`)

---

## Test 1: Progress bar appears during training

1. Open a notebook with epoch-based training
2. Start a training run that logs metrics per epoch
3. Observe the Live Metrics panel

**Expected:**
- A progress bar appears between the toolbar and the charts
- Shows "Epoch N" where N increments with each metric update
- The epoch count is derived from the step count of the first metric

## Test 2: Progress bar with total_epochs

1. In your training code, log the total epochs as a metric:
```python
mlflow.log_metric('total_epochs', 50)
```
2. Run the training

**Expected:**
- Progress bar shows "Epoch X / 50"
- Bar fills proportionally (e.g., epoch 25 = 50%)
- Percentage shown on the right side

## Test 3: Progress bar without total_epochs

1. Run training WITHOUT logging total_epochs

**Expected:**
- Progress bar shows "Epoch X" (no total, no percentage)
- Bar stays empty (no fill) since total is unknown

## Test 4: Progress bar resets on new run

1. Complete one run (progress bar at 100% or showing final epoch)
2. Start a new run

**Expected:**
- Progress bar resets and hides
- Reappears when new metrics arrive
- New epoch counter starts from 1

## Test 5: Progress bar with Live Metrics recovery

1. Close and reopen the Live Metrics panel during a run
2. Observe the progress bar

**Expected:**
- Progress bar reflects current epoch based on recovered metric data

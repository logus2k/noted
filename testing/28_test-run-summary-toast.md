# Post-Run Summary Toast - Test Procedure

## Prerequisites

- noted is running
- A notebook with Run Manager configured (cells assigned to a run)
- A virtual environment with mlflow installed

---

## Test 1: Toast shows metrics on run completion

1. Open a notebook with a training run defined in Run Manager
2. Execute the run (click Run in Run Manager panel)
3. Wait for the run to complete

**Expected:**
- Success toast appears: `Run "run_name" completed`
- Below the run name, a summary line shows key metrics: `loss: 0.1234 | accuracy: 0.9500`
- Up to 5 metrics shown, separated by pipes
- Values formatted to 4 decimal places for floats, integers shown as-is

## Test 2: Toast without metrics

1. Run a cell group that doesn't log any metrics (e.g., just data loading)

**Expected:**
- Toast shows: `Run "run_name" completed` without metric summary
- No extra line when no metrics were collected

## Test 3: Error run toast unchanged

1. Create a run with a cell that raises an error
2. Execute the run

**Expected:**
- Error toast: `Run "run_name" stopped with errors`
- No metric summary on error toasts

## Test 4: Metrics from Live Metrics panel

1. Run a training with per-epoch metric logging (`mlflow.log_metric`)
2. Observe that Live Metrics panel shows charts during training
3. Wait for completion

**Expected:**
- The toast shows the LAST logged values from the Live Metrics panel
- Values match what's visible in the Live Metrics charts

# T-2.4 Config Hash Injection - Test Procedure

## Prerequisites

- noted is running with a project that has a Hydra config directory (e.g., `noted-testing` or `Examples`)
- A kernel is started and connected to the project
- MLflow is accessible

---

## Part 1: Config Hash Logged on Experiments Run

### Test 1: Run with Hydra config present

1. Open a notebook in a project that has a `config/` directory (e.g., `noted-testing`)
2. Click the Experiments icon in the second bar
3. Create a new run with a name (e.g., "config_hash_test")
4. Add at least one code cell to the run
5. Execute the run

**Expected:**
- Run completes successfully
- In MLflow (iframe or Explorer -> Experiments -> run detail):
  - Parameter `hydra_config_hash` exists with a `sha256:...` value
  - Tag `hydra.config_hash` exists with the same value
- The hash is deterministic - running again without changing config produces the same hash

### Test 2: Run with no Hydra config

1. Open a notebook in a project that has no `config/` directory
2. Create and execute an Experiments run

**Expected:**
- Run completes successfully
- No `hydra_config_hash` parameter or `hydra.config_hash` tag in the MLflow run
- No errors in the console or backend logs

### Test 3: Config change produces different hash

1. Open a notebook in a project with Hydra config
2. Execute an Experiments run - note the `hydra_config_hash` value
3. Modify a config file (e.g., change `epochs: 50` to `epochs: 100` in `config/config.yaml`)
4. Execute another Experiments run

**Expected:**
- The second run has a different `hydra_config_hash` value
- Both hashes are present in their respective runs in MLflow

---

## Part 2: Config Hash with DVC Data Hash

### Test 4: Both hashes logged together

1. Open a notebook in a project that has both Hydra config and DVC-tracked data
2. Create an Experiments run
3. Select a DVC-tracked dataset in the run configuration
4. Execute the run

**Expected:**
- The MLflow run contains both:
  - `hydra_config_hash` parameter (Hydra config)
  - `dvc_data_hash` parameter (DVC data lineage)
  - Corresponding tags for both
- This establishes full reproducibility: same config + same data = same experiment

---

## Part 3: Individual cell execution (no config hash)

### Test 5: Individual cell execution does not inject config hash

1. Open a notebook without using Run Manager
2. Run a cell that calls `mlflow.log_metric("test", 1.0)` (user manages their own MLflow run)

**Expected:**
- No config hash is injected - config hash injection is only for Run Manager runs
- No automatic MLflow run is created by noted - the user's code manages its own run lifecycle

---

## Verification via MLflow UI

For any test above, you can verify in MLflow:

1. Open MLflow iframe or go to the MLflow UI directly
2. Navigate to the experiment and find the run
3. Check the "Parameters" section for `hydra_config_hash`
4. Check the "Tags" section for `hydra.config_hash`

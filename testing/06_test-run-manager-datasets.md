# T-1B.7 Experiments - Dataset Selection - Test Procedure

## Prerequisites

- noted is running (docker build + compose up)
- A notebook is open in a project/mount that has DVC-tracked files (e.g., `noted-testing` project with `data/test_data.csv`)
- A kernel is started for the notebook
- MLflow is accessible at `/mlflow`

## Test 1: Dataset section appears in Experiments

1. Open a notebook in the `noted-testing` project
2. Click the Experiments button in the notebook toolbar (vial icon)
3. Click "Add Run" to create a new run
4. Click the run row to make it active (row should highlight)
5. **Expected:** A "DATASETS" section appears below the help text
6. **Expected:** After a brief "Loading..." message, DVC-tracked files are listed with checkboxes
7. **Expected:** `data/test_data.csv` appears as a checkbox item
8. **Expected:** Hovering over the file name shows a tooltip with the hash and size

## Test 2: Dataset selection persists in notebook metadata

1. With a run active, check the checkbox next to `data/test_data.csv`
2. Close the Experiments panel
3. Re-open the Experiments panel
4. Click the same run to make it active again
5. **Expected:** The checkbox is still checked (selection was saved to notebook metadata)
6. **Verification:** Open the notebook `.ipynb` file and check `metadata.mlflow_runs` - the run entry should have `"datasets": ["data/test_data.csv"]`

## Test 3: Execute run with dataset - hash is logged to MLflow

1. Create a run with at least one code cell assigned (e.g., a cell with `print("hello")`)
2. Check the dataset checkbox for `data/test_data.csv`
3. Click the play button to execute the run
4. Wait for execution to complete
5. Open MLflow UI (click the MLflow icon in the sidebar, or go to `/mlflow`)
6. Find the newly created run
7. **Expected - Parameters:** `dvc_data_hash` = `959915f05bfafef18e471a97ae679535`
8. **Expected - Tags:** `dvc.data_hash` = `959915f05bfafef18e471a97ae679535`
9. **Expected - Tags:** `dvc.data_file` = `data/test_data.csv`
10. **Expected - Tags:** `instrumentation` = `experiments`

## Test 4: Execute run without dataset - no hash logged

1. Uncheck all dataset checkboxes for the run
2. Execute the run again
3. Check the new MLflow run
4. **Expected:** No `dvc_data_hash` parameter
5. **Expected:** No `dvc.data_hash` or `dvc.data_file` tags
6. **Expected:** `instrumentation` = `experiments` tag is still present (this comes from the run start code, not the dataset feature)

## Test 5: No DVC-tracked files in project

1. Open a notebook in a project that has no DVC-tracked files (e.g., the `Examples` project)
2. Open Experiments, create a run, make it active
3. **Expected:** Dataset section shows "No DVC-tracked files found."

## Test 6: New run includes empty datasets array

1. Click "Add Run" to create a new run
2. Close and re-open the notebook file in a text editor
3. **Expected:** The new run entry in `metadata.mlflow_runs` has `"datasets": []`

## Test 7: Multiple datasets (if applicable)

1. If the project has multiple DVC-tracked files, check more than one
2. Execute the run
3. **Expected:** Each dataset's hash and path are logged to MLflow as separate params/tags

## Troubleshooting

- **Datasets section doesn't appear:** Check browser console for errors on the `/api/dvc/status` call
- **"No DVC-tracked files found" on a project that should have them:** Verify DVC is initialized in the project (`ls .dvc/` in the project root)
- **Run executes but no hash in MLflow:** Check backend logs (`docker logs noted`) for "Failed to resolve DVC hashes" warnings
- **502 on MLflow UI:** Ensure the MLflow container is running (`docker ps | grep mlflow`)

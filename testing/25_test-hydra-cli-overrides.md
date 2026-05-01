# Hydra CLI Overrides and Run as Pipeline - Test Procedure

## Prerequisites

- noted is running
- A project with Hydra config directory (e.g., Examples with config/model/ and config/data/)
- A project with at least one Airflow DAG tagged with the project name
- A virtual environment assigned with omegaconf and hydra-core installed

---

## Part 1: CLI Overrides for @hydra.main (T-4.R5)

### Test 1: sys.argv injection for Hydra imports

1. Open a notebook in the Examples project
2. Select "model: gru" in the config dropdown
3. Create a cell with:
```python
from hydra import compose, initialize
import sys
print("sys.argv:", sys.argv)
```
4. Run the cell

**Expected:**
- sys.argv contains `['script.py', 'model.type=gru', 'model.params.units1=128', ...]`
- The overrides are flattened dot-notation from the resolved config
- No cfg injection (back-off for Hydra imports still prevents cfg creation)

### Test 2: @hydra.main picks up overrides

1. With "model: gru" selected, create a cell:
```python
from omegaconf import OmegaConf
import sys
# Simulate what @hydra.main would see
print("Overrides available in sys.argv:")
for arg in sys.argv[1:]:
    print(f"  {arg}")
```
2. Run the cell

**Expected:**
- All config values listed as key=value overrides
- Values match the selected "gru" config

### Test 3: Normal cells still get cfg injection

1. With "model: gru" selected, create a cell WITHOUT Hydra imports:
```python
print(type(cfg))
print(cfg)
```
2. Run the cell

**Expected:**
- `cfg` is an OmegaConf DictConfig (regular injection path, not CLI overrides)
- Both paths coexist: Hydra-import cells get sys.argv, non-import cells get cfg

### Test 4: No config selected

1. Set dropdown to "No config"
2. Run a cell with `import hydra; import sys; print(sys.argv)`

**Expected:**
- sys.argv is NOT modified (no injection when no config selected)

---

## Part 2: Run as Pipeline (T-4.R8)

### Test 5: Pipeline button visibility

1. Open a notebook in a project that has Airflow DAGs (tagged with the project name)
2. Look at the notebook second bar

**Expected:**
- A rocket icon button appears between the Live Metrics button and the config dropdown
- Hover tooltip: "Run as Pipeline"

### Test 6: Pipeline button hidden for projects without DAGs

1. Open a notebook in a project with no associated DAGs

**Expected:**
- No rocket button visible

### Test 7: Trigger pipeline with Hydra config

1. Select a Hydra config (e.g., "model: gru")
2. Click the rocket button

**Expected:**
- If one DAG: triggers immediately
- If multiple DAGs: prompt asks which DAG to trigger (numbered list)
- Success toast: "Pipeline {dag_id} triggered"
- The resolved Hydra config is passed as the DAG run's conf parameter

### Test 8: Trigger without config

1. Set config dropdown to "No config"
2. Click the rocket button

**Expected:**
- DAG triggers with null conf (no config injected)
- Success toast appears

### Test 9: Trigger failure handling

1. Stop the Airflow service
2. Click the rocket button

**Expected:**
- Error toast: "Pipeline trigger failed: ..."
- Button re-enables after failure

---

## Troubleshooting

- **Rocket button not showing:** Check that project has DAGs. Verify `GET /api/airflow/dags?tag={project_id}` returns results. The tag must match the project ID or mount name.
- **sys.argv not set:** Ensure the cell contains `from hydra`, `import hydra`, or `OmegaConf`. Without these, the regular cfg injection is used instead.
- **Overrides empty:** Check that the selected config resolves to non-empty values. Verify `POST /api/hydra/compose/{project_id}` returns resolved config.

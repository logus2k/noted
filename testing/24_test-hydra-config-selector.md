# Hydra Config Selector and Kernel Injection - Test Procedure

## Prerequisites

- noted is running
- At least one project with a Hydra config directory (e.g., Examples with config/model/ and config/data/)
- A virtual environment assigned to the notebook

---

## Part 1: Config Selector Visibility

### Test 1: Selector appears for projects with Hydra config

1. Open a notebook in the Examples project (which has config/)
2. Look at the notebook second bar (left side, after the Live Metrics icon)

**Expected:**
- A small dropdown appears with the default option auto-selected (e.g., "model: gru *")
- Clicking the dropdown expands it, showing all options
- Dropdown has optgroups for each config group (e.g., "model", "data")
- Groups with more options appear first (e.g., model before data)
- Each group contains its options (e.g., model: gru, model: linear)
- Default options marked with * (e.g., "model: gru *")

### Test 2: Selector hidden for projects without config

1. Open a notebook in a project that has no config/ directory

**Expected:**
- No config dropdown visible in the second bar

### Test 3: Flat config (no groups)

1. Open a notebook in noted-testing (which has config/config.yaml but no group subdirs)

**Expected:**
- Dropdown appears with "Default config" option

---

## Part 2: Config Selection

### Test 3b: Auto-selected config works immediately

1. Close the notebook
2. Reopen it (so the auto-select fires on load)
3. WITHOUT touching the dropdown, immediately run a cell with `print(cfg)`

**Expected:**
- `cfg` is defined and contains the auto-selected config (the default option)
- The config injection works even though the user never manually changed the dropdown

### Test 4: Select a config

1. In the config dropdown, select "model: gru"

**Expected:**
- Selection changes
- Notebook is marked as modified (unsaved changes indicator)

### Test 5: Selection persists on save

1. Select "model: gru"
2. Save the notebook (Ctrl+S)
3. Close the notebook
4. Reopen the same notebook

**Expected:**
- Config dropdown shows "model: gru" (restored from notebook metadata)

### Test 6: Change selection

1. Change from "model: gru" to "model: lstm"

**Expected:**
- Selection updates
- Notebook marked as modified again

---

## Part 3: Config Injection into Kernel

### Test 7: Config available in kernel

1. Select "model: gru" in the config dropdown
2. In a code cell, type:
```python
print(type(cfg))
print(cfg)
```
3. Run the cell

**Expected:**
- `cfg` is an OmegaConf DictConfig (if omegaconf is installed) or a simple object
- Prints the resolved config with model=gru merged in

### Test 8: Access config values

1. With "model: gru" selected, run:
```python
print(cfg.model.params.units1)
print(cfg.model.params.dropout)
```

**Expected:**
- Prints 128 (from gru.yaml)
- Prints 0.2 (from gru.yaml)

### Test 8b: All groups composed when one is selected

1. With "model: gru" selected (only model group chosen), run:
```python
print(cfg.data)
print(cfg.data.file)
```

**Expected:**
- The `data` group is present even though only `model` was selected in the dropdown
- `cfg.data.file` returns the value from `data/default.yaml`
- All group defaults from `config.yaml` are merged automatically

### Test 9: Config dict available

1. Run:
```python
print(__noted_hydra_config__)
print(__noted_hydra_hash__)
```

**Expected:**
- `__noted_hydra_config__` is a Python dict with the full resolved config
- `__noted_hydra_hash__` is a SHA-256 hash string

### Test 10: Back-off for explicit Hydra imports

1. In a cell, write:
```python
from hydra import compose, initialize_config_dir
# Manual Hydra usage...
```
2. Run the cell

**Expected:**
- No injection (the cell has explicit Hydra imports)
- No error or conflict with user's own Hydra code

### Test 11: No config selected

1. Set dropdown back to "No config"
2. Run a cell with `print(cfg)`

**Expected:**
- `NameError: name 'cfg' is not defined`
- No injection when no config is selected

---

## Part 4: Config Change Mid-Session

### Test 12: Switch config during session

1. Select "model: gru", run a cell to get `cfg`
2. Change to "model: lstm"
3. Run a new cell: `print(cfg.model.type)`

**Expected:**
- First cell sees GRU config
- After switching, new cell sees LSTM config
- Config is re-injected on each cell execution based on current selection

---

## Troubleshooting

- **Dropdown not showing:** Check that the project has a config/, conf/, or configs/ directory. Check `/api/hydra/schema/{project_id}` returns `has_config: true`.
- **`cfg` not defined:** Ensure a config option is selected (not "No config"). Check the cell doesn't contain Hydra imports (back-off).
- **Wrong config values:** The config is composed fresh on each cell execution using the selected group/option. Verify the selection matches the expected YAML file.
- **OmegaConf not available:** If omegaconf is not installed in the venv, `cfg` falls back to a simple Python object. Install with `pip install omegaconf`.

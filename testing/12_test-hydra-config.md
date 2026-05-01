# Hydra Configuration - Test Procedure

## Prerequisites

- noted is running
- A project with a Hydra config directory exists (e.g., `noted-testing` project with `config/config.yaml`)
- The config directory contains at least one YAML file

---

## Part 1: Configuration Node in Explorer

### Test 1: Configuration node appears

1. In the Explorer tree, expand a project that has a `config/` directory (e.g., `noted-testing`)

**Expected:**
- A "Configuration" node appears at the top of the project's children (before regular files/folders)
- Uses a purple sliders icon
- Node is expandable (has a chevron)

### Test 2: Configuration node does not appear for projects without config

1. Expand a project that has no `config/`, `conf/`, or `configs/` directory (e.g., `Examples` if it has no config)

**Expected:**
- No "Configuration" node appears - only regular files and folders

### Test 3: Expand Configuration node (flat config)

1. Click the Configuration node for a project with a flat config (e.g., `noted-testing` which has a single `config/config.yaml`)

**Expected:**
- A single child node appears with the config file name (e.g., `config.yaml`)
- Uses a file-code icon

### Test 4: Expand Configuration node (with groups)

1. If a project has config groups (e.g., `config/model/gru.yaml`, `config/model/lstm.yaml`), expand its Configuration node

**Expected:**
- Group folders appear (e.g., `model`, `data`, `forecast`)
- Each group uses a layer-group icon
- Groups are expandable

### Test 5: Expand a config group

1. Click on a config group folder

**Expected:**
- Group options appear as children (e.g., `gru`, `lstm`, `linear`)
- The default option has a star icon and "(default)" suffix
- Other options have file-code icons

---

## Part 2: Configuration Detail Panel

### Test 6: Configuration root detail

1. Click the Configuration node

**Expected:**
- Detail panel shows:
  - Header "Configuration" with sliders icon
  - Info card: Config Dir, Config File, Groups count, Parameters count
  - If groups exist: "Config Groups" section listing each group with option count and default
  - "Parameters" grid showing all config keys with types and default values
  - "Compose Config" button at the bottom

### Test 7: Group detail

1. Click a config group node (e.g., `model`)

**Expected:**
- Detail panel shows:
  - Header with group name and layer-group icon
  - Info card: Group name, Options count, Default selection
  - "Options" section listing each option as clickable rows
  - Default option marked with star icon

### Test 8: Option detail (group option)

1. Click a config group option (e.g., `model/gru`)

**Expected:**
- Detail panel shows the YAML content of that option file
- Syntax displayed in monospace font with proper formatting

### Test 9: Option detail (flat config)

1. Click the root config file node (e.g., `config.yaml` under Configuration)

**Expected:**
- Detail panel shows:
  - Hash (SHA-256) of the composed config
  - Full resolved YAML content

---

## Part 3: Compose Panel

### Test 10: Open compose panel

1. Click the "Compose Config" button in the Configuration detail panel

**Expected:**
- A floating jsPanel opens titled "Compose Configuration"
- If config groups exist: dropdown selectors for each group (pre-selected with defaults)
- Override inputs for every parameter (pre-filled with current default values)
- "Compose" button at the bottom

### Test 11: Auto-compose on open

1. Open the Compose Configuration panel

**Expected:**
- Resolved YAML appears automatically (no need to click "Compose")
- SHA-256 hash shown above the YAML
- "Copy YAML" button appears

### Test 11b: Auto-compose on group change

1. Change the model dropdown from one option to another

**Expected:**
- Resolved YAML updates automatically
- Hash changes without clicking "Compose"

### Test 12: Compose with overrides

1. Change one or more parameter values (e.g., change `data.split.train` from `0.7` to `0.8`)
2. Wait or click "Compose"

**Expected:**
- Resolved YAML reflects the changed values
- Hash is different from the default compose
- The override is applied to the correct nested key

### Test 13: Compose with group selection

1. If config groups exist, change a group dropdown (e.g., select `lstm` instead of `gru` for model)
2. Click "Compose"

**Expected:**
- Resolved YAML includes the selected group's values merged into the config
- Hash changes

### Test 14: Copy YAML

1. After composing, click "Copy YAML"

**Expected:**
- Button briefly shows "Copied" with a check icon
- Pasting in a text editor shows the full resolved YAML

### Test 15: Multiple compose panels

1. Open a compose panel for project A
2. Open another compose panel (e.g., from a different project or the same)

**Expected:**
- Two separate panels open (cascaded offset)
- Each is independent

---

## Part 4: API Verification

### Test 16: Schema endpoint

1. In the browser, navigate to: `[base_url]/api/hydra/schema/noted-testing` (or the appropriate project ID)

**Expected:**
- JSON response with:
  - `has_config`: true
  - `config_dir`: "config"
  - `config_name`: "config"
  - `groups`: {} (empty for flat config) or populated for grouped configs
  - `flat_config`: the parsed YAML as JSON
  - `schema`: array of `{key, type, default}` entries

### Test 17: Compose endpoint

1. Use curl or browser dev tools to POST to `[base_url]/api/hydra/compose`:
```json
{
  "project_id": "noted-testing",
  "overrides": {"data.split.train": 0.8}
}
```

**Expected:**
- JSON response with:
  - `resolved`: the full config with train split changed to 0.8
  - `yaml`: YAML string of the resolved config
  - `hash`: SHA-256 hash prefixed with `sha256:`

---

## Part 5: Edge Cases

### Test 18: Project with no config

1. Click Configuration actions for a project without a config directory

**Expected:**
- No Configuration node in the tree (graceful absence, no errors)

### Test 19: Empty config directory

1. If a project has a `config/` directory but no YAML files inside

**Expected:**
- Configuration node may appear but shows "No config groups found" when expanded

### Test 20: Malformed YAML

1. If a config YAML has syntax errors

**Expected:**
- The schema endpoint returns gracefully (possibly empty schema)
- No server crash or 500 error
- Frontend shows appropriate fallback

---

## Cleanup

Close any open compose panels via the X button. No persistent changes are made by the config viewer (it's read-only).

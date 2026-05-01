# Config Templates + Pipeline Status Bar - Test Procedure

## Prerequisites

- noted is running with at least one project that has a Hydra config directory (e.g., Examples or noted-testing)
- At least one DAG is active (unpaused) in Airflow

---

## Part 1: Config Templates

### Test 1: Compose panel shows templates section

1. In Explorer, navigate to a project's Configuration node (e.g., Examples > Configuration)
2. Click on the root config node to open its detail page
3. Click "Compose Config" button

**Expected:**
- The compose panel (jsPanel) opens
- A "Templates" section appears between the overrides and the Compose button
- A dropdown shows "-- Select template --"
- Three buttons: load (blue), save (green), delete (red)

### Test 2: Save a template

1. In the compose panel, change a group selection (e.g., model: gru)
2. Modify an override value (e.g., change training.epochs from 50 to 100)
3. Click the save button (green floppy disk icon)
4. Enter a name: "gru_100_epochs"
5. Enter a description: "GRU model with 100 epochs"
6. Click OK

**Expected:**
- The template dropdown now includes "gru_100_epochs - GRU model with 100 epochs"
- The template is auto-selected after saving
- File created at: `<project>/.noted/config_templates/gru_100_epochs.yaml`

### Test 3: Save a second template

1. Change the group selection to model: lstm
2. Change training.learning_rate to 0.001
3. Save as "lstm_default"

**Expected:**
- Dropdown now shows both templates
- Both are selectable

### Test 4: Load a template

1. Select "gru_100_epochs" from the dropdown
2. Click the load button (blue download icon)

**Expected:**
- Model group selector changes to "gru"
- training.epochs input changes to "100"
- Other values remain at their defaults (or the template's saved values)

### Test 5: Load a different template

1. Select "lstm_default" from the dropdown
2. Click load

**Expected:**
- Model group selector changes to "lstm"
- training.learning_rate changes to "0.001"
- Previous template values are replaced

### Test 6: Compose from loaded template

1. After loading a template, click "Compose"

**Expected:**
- YAML output reflects the template's group selections and overrides
- Hash is displayed
- Copy YAML button appears and works

### Test 7: Delete a template

1. Select "lstm_default" from the dropdown
2. Click the delete button (red trash icon)
3. Confirm the deletion

**Expected:**
- "lstm_default" is removed from the dropdown
- "gru_100_epochs" remains
- File deleted from `.noted/config_templates/`

### Test 8: Empty template dropdown

1. Delete all remaining templates

**Expected:**
- Dropdown shows only "-- Select template --"
- Load and delete buttons do nothing when no template is selected

### Test 9: Templates persist across sessions

1. Save a new template
2. Close the compose panel
3. Reopen it (click "Compose Config" again)

**Expected:**
- Previously saved template appears in the dropdown

### Test 10: Templates are project-specific

1. Save a template in Examples project
2. Open the compose panel for noted-testing project

**Expected:**
- noted-testing's template dropdown does not show Examples' templates
- Each project has its own template list

---

## Cleanup

- Delete any test templates created during testing via the compose panel's delete button

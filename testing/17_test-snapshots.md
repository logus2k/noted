# Experiment Snapshots - Test Procedure

## Prerequisites

- noted is running with at least one project (e.g., noted-testing)
- At least one MLflow experiment with FINISHED runs
- Project has git initialized and DVC configured
- A notebook has been run to produce training results

---

## Part 1: Create Snapshot

### Test 1: Snapshot button visible on finished runs

1. In Explorer, navigate to Experiments > select an experiment > click a run
2. The run detail page should load

**Expected:**
- For FINISHED runs: a "Create Snapshot" button (camera icon, yellow background) appears below the run info card
- For RUNNING/FAILED/KILLED runs: no snapshot button

### Test 2: Snapshot modal opens with clean git

1. Ensure all changes are committed (git is clean)
2. Click "Create Snapshot" on a finished run

**Expected:**
- A jsPanel modal opens titled "Create Snapshot"
- Shows what will be captured (git, DVC, Hydra, MLflow, env)
- Shows run summary with top metrics
- Git state shows green check: "Git is clean - ready for snapshot"
- No auto-commit checkbox visible
- Name input pre-filled with run name (lowercase, underscores)
- Description textarea (optional)
- "Create Snapshot" button is enabled

### Test 3: Snapshot modal with modified files

1. Edit a file in the project but do NOT commit
2. Click "Create Snapshot" on a finished run

**Expected:**
- Git state shows orange warning: "X modified file(s) - must commit before snapshot"
- Modified file list shown (font-mono, scrollable if many)
- Auto-commit checkbox appears (UNCHECKED by default)
- Recommendation: "We recommend committing your changes explicitly via Version Control"
- "Create Snapshot" button is DISABLED (greyed out)

### Test 4: Auto-commit checkbox enables snapshot

1. With modified files, check the "Auto-commit modified files" checkbox

**Expected:**
- "Create Snapshot" button becomes enabled
- Clicking it auto-commits with message "[noted] snapshot: {name}" then creates the snapshot

### Test 5: Untracked files warning

1. Create a new file in the project (but don't `git add` it)
2. Click "Create Snapshot"

**Expected:**
- Info message: "X untracked file(s) - will NOT be included in the snapshot"
- Untracked file list shown
- "Create Snapshot" button is still enabled (untracked files don't block)

### Test 6: Create a snapshot (clean state)

1. Commit all changes first
2. Enter a name (e.g., "gru_best_val_loss")
3. Optionally add a description
4. Click "Create Snapshot"

**Expected:**
- Button shows "Creating snapshot..."
- On success: shows branch name, version number, commit SHA
- Toast: "Snapshot created: gru_best_val_loss"
- A git branch `snapshot/{experiment_name}_{001}` was created
- The MLflow run is tagged with `noted.snapshot=true`

### Test 7: Verify snapshot in run detail

1. Close the snapshot modal
2. Click the same run again in the tree

**Expected:**
- Run info card shows "SNAPSHOT" badge (yellow) next to status
- Snapshot name and branch shown in the card
- Instead of "Create Snapshot" button, two new buttons appear:
  - "Restore Snapshot" (green)
  - "New Experiment from Snapshot" (blue)

### Test 8: Only one snapshot per experiment

1. Click a different FINISHED run in the same experiment
2. Click "Create Snapshot"
3. Create it with a different name

**Expected:**
- New snapshot created successfully
- Go back to the first run's detail - the SNAPSHOT badge is gone
- Only the latest snapshot is marked

### Test 9: Snapshot blocked without commit

1. Edit a file, do NOT commit
2. Click "Create Snapshot", do NOT check auto-commit
3. Try to click "Create Snapshot" button

**Expected:**
- Button is disabled - cannot create snapshot with uncommitted changes

---

## Part 2: Restore Snapshot

### Test 10: Restore a snapshot

1. Make some changes to the project (edit a file, modify config)
2. Navigate to a run that has the SNAPSHOT badge
3. Click "Restore Snapshot"

**Expected:**
- Confirmation dialog: "Restore snapshot? This will switch to branch..."
- Click OK
- Toast: "Restored snapshot: {name} (branch: snapshot/...)"
- Explorer tree refreshes showing files from the snapshot state
- Version Control panel shows the snapshot branch as active
- If there were uncommitted changes, they were stashed

### Test 11: Verify restored state

1. After restoring, check the project files

**Expected:**
- Code, notebooks, configs match the state when the snapshot was created
- DVC-tracked data files are restored to the correct version

---

## Part 3: Fork Experiment from Snapshot

### Test 12: Fork from snapshot

1. Navigate to a snapshot run
2. Click "New Experiment from Snapshot"
3. Enter a new experiment name (e.g., "jena_gru_v3")

**Expected:**
- Toast: "Forked: jena_gru_v3 (branch: experiment/jena_gru_v3)"
- A new git branch `experiment/jena_gru_v3` is created from the snapshot
- A new MLflow experiment `jena_gru_v3` appears in the Experiments tree
- The workspace is on the new branch, ready for modifications
- The original snapshot branch is untouched

### Test 13: Work on forked experiment

1. After forking, modify a parameter in the notebook
2. Run the notebook
3. Check the new experiment in MLflow

**Expected:**
- New runs appear under the forked experiment
- The original experiment's runs are unchanged
- Git log shows the fork branching from the snapshot commit

---

## Part 4: List Snapshots

### Test 14: API returns snapshots

1. Open browser console
2. Run: `fetch('api/snapshots/noted-testing').then(r => r.json()).then(d => console.log(d))`

**Expected:**
- Returns `{snapshots: [...]}` with all snapshots for the project
- Each snapshot has: experiment_name, run_id, name, branch, version, metrics

---

## Troubleshooting

- **"Run is not finished":** Only FINISHED runs can be snapshotted
- **"Project not found":** Check that the experiment name matches a project ID
- **Git branch errors:** If a snapshot branch already exists, the version auto-increments
- **DVC push warning:** If MinIO is unreachable, the snapshot is created but data may not be in remote
- **Restore fails:** Check that the snapshot branch still exists in git (`git branch --list snapshot/*`)

# DVC Version Switching - Test Procedure

## Prerequisites

- noted is running (docker rebuild required for backend changes)
- MinIO is running and accessible (container `noted-minio`)
- A git-initialized project or mount with DVC configured (e.g., `noted-testing`)
- A DVC-tracked data file with at least 2 committed versions in git history

---

## Setup: Create multiple DVC versions (if needed)

If your project only has 1 version of a tracked file, create a second version:

1. Open a terminal **inside the noted container** (use the Terminal Escape Hatch or `docker exec -it noted bash`)
2. Navigate to the project: `cd /app/projects/noted-testing`
3. Run:
   ```bash
   # DVC sets tracked files to read-only; make writable first
   chmod +w data/test_data.csv

   # Add a blank line to change the file hash (preserves CSV structure)
   python3 -c "open('data/test_data.csv', 'a').write('\n')"

   # Re-track with DVC
   dvc add data/test_data.csv

   # Commit the updated pointer
   git add data/test_data.csv.dvc
   git commit -m "Data version 2 - test"

   # Push data to MinIO remote
   dvc push
   ```
3. Repeat for a third version if desired
4. Verify with `git log -- data/test_data.csv.dvc` - should show 2+ commits

---

## Test 1: Version history displays correctly

1. In the Explorer tree, navigate to a `.dvc` file (e.g., `data/test_data.csv.dvc`)
2. Click on the `.dvc` file

**Expected:**
- Detail panel shows the data file name as header (without `.dvc` extension)
- "Version History" section title appears
- Multiple version rows are listed, each showing:
  - Commit short hash (teal, monospace) + commit message
  - File size, md5 hash (truncated), relative date, author
- The version matching the current `.dvc` file content shows a teal **"Current"** badge (right side)
- All other versions show a **"Checkout"** button with a clock icon

---

## Test 2: Cancel does nothing

1. Click "Checkout" on any non-current version
2. A confirmation modal appears: "Switch [filename] to version from [hash]?"
3. Click **Cancel**

**Expected:**
- Modal closes
- No changes - "Current" badge stays on the same version
- No toast notification

---

## Test 3: Successful version switch

1. Note which version has the "Current" badge and its md5 hash
2. Click "Checkout" on a different (older) version
3. Confirm in the modal

**Expected:**
- Button text changes to "Switching..." while the operation runs
- On success: toast notification "Switched to [hash]" appears
- Detail view automatically re-renders
- "Current" badge moves to the version you checked out
- The previously current version now shows a "Checkout" button
- If data was pulled from remote: toast says "Switched to [hash] (pulled from remote)"

---

## Test 4: Git status reflects the change

After a successful version switch:

1. Open the Git Panel (Source Control sidebar)
2. Look at the Changes section

**Expected:**
- The `.dvc` file appears as **modified** (M status badge)
- The data file itself may also show as changed
- This is correct - the switch modified the `.dvc` pointer but did not auto-commit

---

## Test 5: Switch back to original version

1. In the `.dvc` file detail view, click "Checkout" on the original version
2. Confirm in the modal

**Expected:**
- Switch succeeds, toast notification appears
- "Current" badge returns to the original version
- Git status may return to clean (if the `.dvc` file content matches HEAD)

---

## Test 6: Single version file

1. Find or create a `.dvc` file with only one commit in its history

**Expected:**
- One version row with "Current" badge
- No "Checkout" button (nothing to switch to)

---

## Test 7: Error handling - data not available

1. Clear the local DVC cache: `rm -rf .dvc/cache`
2. Ensure the data is NOT on the MinIO remote: `dvc remove data/some_file.csv.dvc` or similar
3. Attempt to checkout a version whose data is unavailable

**Expected:**
- Error toast with a message suggesting to use the terminal
- The `.dvc` pointer file may have been modified by git checkout - user may need to restore it manually via `git checkout -- <file>.dvc`

**Note:** This is a destructive test - only run on test data, not production datasets.

---

## Test 8: Explorer decorations update

After a successful version switch:

1. Look at the Explorer tree

**Expected:**
- The `.dvc` file and/or its parent directory may show modified status decorations (amber dot, M badge)
- Decorations refresh automatically after the switch

---

## Cleanup

If you created test versions in the Setup step:
```bash
# Revert to the original version
git log --oneline -- data/test_data.csv.dvc
git checkout <original_hash> -- data/test_data.csv.dvc
dvc checkout data/test_data.csv.dvc
git commit -m "Revert test versions"
```

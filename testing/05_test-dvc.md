# DVC Integration - Test Procedure

## Prerequisites

- noted is running
- MinIO is running and accessible (container `noted-minio`)
- A git-initialized project or mount is available
- A data file with a DVC-trackable extension exists in the project (e.g., `.csv`, `.parquet`, `.pkl`, `.h5`)

---

## Test 1: DVC status display

1. Open the Git Panel
2. Select a project/mount that has DVC-tracked files (e.g., `noted-testing`)
3. **Expected:** A "DVC Data" section appears below the Changes section
4. **Expected:** Shows "DVC initialized - N tracked files"
5. **Expected:** Lists tracked files with their MD5 hash and file size

## Test 2: DVC auto-initialization

1. Select a git project that does NOT have DVC initialized
2. **Expected:** DVC section shows "Not initialized (auto-init on first track)"
3. Track a file with DVC (see Test 3)
4. **Expected:** DVC is automatically initialized with MinIO remote configured

## Test 3: Track a file with DVC

1. In the Explorer panel, navigate to a data file (e.g., a `.csv` file)
2. Right-click the file to open the context menu
3. **Expected:** "Track with DVC" option is visible (with a database icon)
4. Click "Track with DVC"
5. **Expected:** File is added to DVC tracking
6. **Expected:** A `.dvc` pointer file appears next to the original file
7. **Expected:** A `.gitignore` entry is created for the tracked file
8. **Expected:** The `.dvc` file and `.gitignore` are staged for git commit
9. Refresh the Git Panel
10. **Expected:** DVC section now lists the newly tracked file with its hash

## Test 4: Context menu only shows for trackable files

1. Right-click a `.py` file in the Explorer
2. **Expected:** "Track with DVC" option is NOT shown
3. Right-click a `.csv`, `.pkl`, `.h5`, or `.parquet` file
4. **Expected:** "Track with DVC" option IS shown
5. Right-click a file that is already DVC-tracked
6. **Expected:** "Track with DVC" option should not appear (already tracked)

## Test 5: DVC push to MinIO

1. Ensure a file is DVC-tracked (from Test 3)
2. In the DVC section of the Git Panel, click the Push button
3. **Expected:** Push completes successfully
4. **Expected:** File data is uploaded to the MinIO `noted-dvc` bucket
5. **Verification:** Open MinIO UI (`/minio`) and browse the `noted-dvc` bucket - the file hash should appear as an object

## Test 6: DVC pull from MinIO

1. After pushing (Test 5), delete the local cached data file:
   - The actual large file is in the project directory
   - The `.dvc` pointer file remains
2. In the DVC section, click the Pull button
3. **Expected:** Pull completes, the data file is restored from MinIO
4. **Expected:** File contents match the original

## Test 7: DVC file version history

1. In the Explorer panel, find a `.dvc` pointer file (e.g., `data/test_data.csv.dvc`)
2. Click on the `.dvc` file
3. **Expected:** A version history view opens with breadcrumb "DVC Tracked File > Version History"
4. **Expected:** Each version shows:
   - Short commit hash (clickable)
   - Commit message
   - Author name
   - Date (absolute and relative)
   - MD5 hash of the data file at that version
   - File size at that version

## Test 8: DVC decorations in Explorer

1. Open the Explorer panel for a project with DVC-tracked files
2. **Expected:** DVC-tracked files show decorations indicating DVC status
3. **Expected:** Decorations are visually distinct from git status decorations

## Test 9: Rename a DVC-tracked file

1. In the Explorer panel, right-click a DVC-tracked data file (e.g., `data/test_data.csv`)
2. Select "Rename" from the context menu
3. Enter a new name (e.g., `test_data_v2.csv`)
4. **Expected:** Rename completes with a success toast "Renamed test_data.csv to test_data_v2.csv"
5. **Expected:** The tree refreshes and shows the renamed file
6. **Expected:** A new `.dvc` pointer file appears with the new name (e.g., `data/test_data_v2.csv.dvc`)
7. **Expected:** The old `.dvc` pointer file is gone
8. **Expected:** The `.gitignore` is updated (old entry removed, new entry added)
9. **Expected:** Changes are staged in git (check Git Panel > Changes)

## Test 10: Delete a DVC-tracked file

1. In the Explorer panel, right-click a DVC-tracked data file
2. Select "Delete" from the context menu
3. **Expected:** Confirmation dialog warns: "[filename] is tracked by DVC. This will remove DVC tracking, delete the data file, and stage changes in Git. Continue?"
4. Click Cancel
5. **Expected:** Nothing changes
6. Right-click and select "Delete" again, click Confirm
7. **Expected:** Success toast "Removed DVC tracking for [filename]"
8. **Expected:** The data file is deleted from the project
9. **Expected:** The `.dvc` pointer file is deleted
10. **Expected:** The `.gitignore` entry is removed
11. **Expected:** Both the data file and `.dvc` file nodes disappear from the tree
12. **Expected:** Changes are staged in git (check Git Panel > Changes)

## Test 11: Delete a non-DVC file shows normal confirmation

1. Right-click a regular file (e.g., a `.py` file) and select "Delete"
2. **Expected:** Simple confirmation "Delete [filename]?" (no DVC warning)
3. Confirm and verify the file is deleted normally

## Test 12: DVC changed files detection

1. Track a file with DVC
2. Modify the tracked file's contents (e.g., append data to a CSV)
3. Refresh the Git Panel
4. **Expected:** DVC section shows the file under "Changed files" with appropriate status
5. Re-track the file (`dvc add` via context menu or terminal)
6. **Expected:** Changed status clears after re-tracking

## Test 13: DVC with multiple projects

1. Select a different project in the Git Panel
2. **Expected:** DVC section updates to reflect that project's DVC state
3. **Expected:** A project without DVC shows "Not initialized"
4. **Expected:** A project with DVC shows its tracked files

---

## Troubleshooting

- **"Track with DVC" not in context menu:** Verify the file has a DVC-trackable extension (`.csv`, `.pkl`, `.h5`, etc.)
- **Push/Pull fails:** Check that MinIO is running (`docker ps | grep minio`) and the `noted-dvc` bucket exists
- **"DVC requires a git repository":** Initialize git in the project first
- **Version history empty:** Ensure the `.dvc` pointer file has been committed to git at least once
- **Backend errors:** Check `docker logs noted` for DVC-related error messages

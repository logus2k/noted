# Data Section (Explorer) - Test Procedure

## Prerequisites

- noted is running
- At least one project or mount has DVC initialized with tracked files (e.g., `noted-testing` project with `test_data.csv`)
- DVC remote (MinIO) is configured and reachable

---

## Part 1: Data Section in Explorer Tree

### Test 1: Data section appears in tree

1. Open the Explorer panel (left sidebar)
2. Scroll down past Projects, Mounts, Virtual Environments, Knowledge Base

**Expected:**
- A "Data" section appears with a cubes-stacked icon (teal/green colored)
- The section is collapsed by default

### Test 2: Expand Data section

1. Click on the "Data" section to expand it

**Expected:**
- Child nodes appear, one per project/mount that has DVC-tracked files
- Each collection node shows the project/mount name
- Project collections use the clipboard-list icon
- Mount collections use the hard-drive icon
- Projects/mounts without DVC-tracked files do NOT appear

### Test 3: Expand a collection

1. Click on a collection node (e.g., `noted-testing`)

**Expected:**
- Child nodes appear showing individual tracked data files
- Each file shows its name (e.g., `data/test_data.csv`)
- Files use appropriate file-type icons (e.g., CSV icon for `.csv` files)

### Test 4: Empty state

1. If no projects/mounts have DVC-tracked files

**Expected:**
- Expanding the Data section shows "No DVC-tracked data found" with an info icon

---

## Part 2: Data File Detail View

### Test 5: File metadata card

1. Click on a tracked data file in the Data tree

**Expected:**
- Detail panel opens in the center pane
- Shows the file name as header with appropriate icon
- Metadata card displays:
  - **Size** - human-readable file size (e.g., "41.2 MB")
  - **MD5** - content hash in monospace font
  - **Source** - project/mount name with type label
  - **DVC File** - pointer file path (e.g., `data/test_data.csv.dvc`)

### Test 6: Version history loads

1. Below the metadata card, check the version history section

**Expected:**
- "Version History (N)" title with count
- Each version row shows:
  - **CURRENT** badge (teal) on the active version
  - Short commit hash in monospace
  - Commit message
  - File size (if available)
  - Date
  - **Checkout** button on non-current versions

---

## Part 3: Version Switching from Data Section

### Test 7: Checkout a different version

**Prerequisite:** The tracked file must have at least 2 versions in git history. If not, create a second version from the terminal:

```
chmod +w data/test_data.csv
echo "" >> data/test_data.csv
dvc add data/test_data.csv
git add data/test_data.csv.dvc
git commit -m "Data version 2"
dvc push
```

1. In the Data section, click a file with multiple versions
2. Click "Checkout" on a non-current version
3. Confirmation modal appears

**Expected:**
- Modal asks: "Switch [filename] to version [hash]?"
- Click Cancel - nothing changes
- Click Confirm:
  - Button shows "Switching..." during operation
  - On success: toast notification, detail view refreshes
  - "CURRENT" badge moves to the checked-out version

### Test 8: Checkout and switch back

1. After checking out a different version (Test 7)
2. Click "Checkout" on the original version

**Expected:**
- Version switches back successfully
- "CURRENT" badge returns to the original version

---

## Part 4: Breadcrumbs and Navigation

### Test 9: Breadcrumb trail

1. Click on the Data root node
2. Then click a collection
3. Then click a file

**Expected:**
- Explorer title bar shows breadcrumbs updating at each level:
  - Root: `Data`
  - Collection: `Data / noted-testing`
  - File: `Data / noted-testing / data/test_data.csv`

### Test 10: Tree expand/collapse

1. Click a collection node to expand it
2. Click again to collapse

**Expected:**
- Collection expands and collapses on click (no detail page opens for collections)
- Only clicking a file node opens the detail view

---

## Part 5: Cross-Project Aggregation

### Test 11: Multiple projects with DVC data

1. Track a file with DVC in a second project (if available)
2. Collapse and re-expand the Data section

**Expected:**
- Both projects appear as separate collection nodes
- Each shows only its own tracked files
- Files from different projects are not mixed

### Test 12: Refresh after new tracking

1. In the Explorer Projects tree, right-click a data file and select "Track with DVC"
2. Collapse and re-expand the Data section

**Expected:**
- The newly tracked file appears under its project's collection
- If the project wasn't previously in the Data section, a new collection node appears

---

## Cleanup

No cleanup needed. The Data section is read-only (except for version checkout which is tested and reversible).

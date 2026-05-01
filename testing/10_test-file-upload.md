# File Upload - Test Procedure

## Prerequisites

- noted is running with `NOTED_TERMINAL_SECRET` set in `services/.env`
- At least one project or mount exists in the Explorer tree

---

## Part 1: Upload via Explorer Title Bar

### Test 1: Upload to project root

1. Select a project node in the Explorer tree (e.g., "Examples")
2. Click the upload icon (orange arrow) in the Explorer title bar
3. If first upload in this session, enter the terminal access key when prompted

**Expected:**
- File picker dialog opens
- Select a file and confirm
- Toast: "Uploaded 1 file"
- Project tree refreshes and shows the uploaded file

### Test 2: Upload to subfolder

1. Select a folder inside a project (e.g., "notebooks/")
2. Click the upload icon in the Explorer title bar
3. Select a file

**Expected:**
- File is uploaded to the selected subfolder
- Tree refreshes showing the file in the correct folder

### Test 3: Upload to mount

1. Select a project node (e.g., "noted-testing")
2. Click the upload icon
3. Select a file

**Expected:**
- File uploaded to the mount root directory
- Tree refreshes with the new file visible

### Test 4: Upload multiple files

1. Select any project or folder
2. Click the upload icon
3. In the file picker, select multiple files (Ctrl+click or Shift+click)

**Expected:**
- Toast: "Uploaded N files" (where N matches the selection count)
- All files appear in the tree after refresh

---

## Part 2: Upload via File Menu

### Test 5: Upload from File menu with project selected

1. Select a project node in the Explorer tree
2. Click File > Upload File... in the top menu bar
3. Select a file

**Expected:**
- File uploaded to the selected project's root
- Tree refreshes

### Test 6: Upload from File menu with folder selected

1. Select a subfolder in the Explorer tree
2. Click File > Upload File...
3. Select a file

**Expected:**
- File uploaded to the selected subfolder

### Test 7: Upload from File menu with no selection

1. Ensure no project or folder is selected (or close Explorer)
2. Click File > Upload File...

**Expected:**
- Error modal: "Select a project or folder in Explorer first."

### Test 8: File menu targets correct location after delete

1. Select a file in project A and delete it via context menu
2. Immediately click File > Upload File...

**Expected:**
- The upload targets project A (parent folder of deleted file), not another project/mount

---

## Part 3: Upload via Context Menu

### Test 9: Upload from project context menu

1. Right-click a project node in the Explorer tree
2. Select "Upload File" from the context menu
3. Select a file

**Expected:**
- File uploaded to the project root
- Tree refreshes

### Test 10: Upload from folder context menu

1. Right-click a subfolder
2. Select "Upload File"
3. Select a file

**Expected:**
- File uploaded to that subfolder

### Test 11: Upload from mount context menu

1. Right-click a mount node
2. Select "Upload File"
3. Select a file

**Expected:**
- File uploaded to the mount root

---

## Part 4: Authentication

### Test 12: First upload prompts for access key

1. Open a new browser tab (fresh session)
2. Navigate to noted
3. Try to upload a file via any method

**Expected:**
- Password prompt appears: "Enter access key to upload to [destination]"
- Input field is masked (password type)
- Enter the correct key from `services/.env`
- Upload proceeds

### Test 13: Wrong access key

1. Open a new browser tab
2. Try to upload a file
3. Enter an incorrect access key

**Expected:**
- Error modal: "Invalid access key"
- Secret is NOT cached (next attempt prompts again)

### Test 14: Access key is cached for session

1. After a successful upload (key accepted)
2. Upload another file

**Expected:**
- No password prompt - uses cached key from sessionStorage
- Upload proceeds directly to file picker

### Test 15: Access key clears on tab close

1. Upload a file successfully (key cached)
2. Close the browser tab
3. Open a new tab and navigate to noted
4. Try to upload

**Expected:**
- Password prompt appears again (sessionStorage cleared)

---

## Part 5: Edge Cases

### Test 16: Upload large file

1. Upload a file close to 500 MB

**Expected:**
- Upload succeeds
- File appears in tree

### Test 17: Upload file exceeding 500 MB limit

1. Upload a file larger than 500 MB

**Expected:**
- Error modal: "File too large (max 500 MB)"

### Test 18: Upload file with same name (overwrite)

1. Upload a file to a folder
2. Upload a different file with the same name to the same folder

**Expected:**
- File is overwritten without error
- Tree refreshes showing the file (same name, new content)

### Test 19: Upload to deeply nested folder

1. Navigate to a deeply nested folder in the tree
2. Upload a file

**Expected:**
- File uploaded to the correct nested path

---

## Cleanup

Delete any test files uploaded during testing via the context menu (right-click > Delete).

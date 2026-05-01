# Terminal Escape Hatch - Test Procedure

## Prerequisites

- noted is running (docker rebuild required for backend changes)
- A git-initialized project or mount is available (e.g., `noted-testing`)
- The Version Control sidebar is accessible
- `NOTED_TERMINAL_SECRET` is set in `services/.env` (e.g., `NOTED_TERMINAL_SECRET=mysecretkey`)

---

## Part 1: Opening a Terminal

### Test 1: Open terminal from Version Control topbar

1. Open the Version Control sidebar
2. Select a project from the project dropdown
3. Click the terminal icon (window-maximize) in the topbar, at the left side

**Expected:**
- A password prompt appears: "Terminal Access Key"
- Enter the correct key (the value of `NOTED_TERMINAL_SECRET` in `services/.env`)
- Click "Connect"
- Prompt closes
- A floating terminal (jsPanel) opens, titled "Terminal - [project_name]"
- Terminal is a live bash shell, cd'd into the project directory
- Type `pwd` to verify the working directory

---

## Part 2: Terminal Access Key Authentication

### Test 2: Wrong key is rejected

1. Click the terminal icon in the Version Control topbar
2. Enter an incorrect key in the prompt
3. Click "Connect"

**Expected:**
- Alert appears: "Invalid terminal access key"
- No terminal panel opens
- The key is NOT cached (next attempt will prompt again)

### Test 3: Cancel prompt

1. Click the terminal icon
2. In the password prompt, click "Cancel" (or press Escape, or click outside)

**Expected:**
- Prompt closes, no terminal opens
- No error messages

### Test 4: Key is cached for the session

1. Click the terminal icon and enter the correct key - terminal opens
2. Close the terminal panel (X button)
3. Click the terminal icon again

**Expected:**
- No password prompt this time - terminal opens directly
- The key was cached from the first successful auth
- Closing the browser tab clears the cache (sessionStorage)

### Test 5: Cached key invalidated on server change

1. Open a terminal successfully (key is cached)
2. Change `NOTED_TERMINAL_SECRET` in `services/.env` and rebuild
3. Click the terminal icon again

**Expected:**
- Cached key fails silently
- Password prompt appears asking for the new key

---

## Part 3: Terminal Opens from Git/DVC Errors

### Test 6: Git push failure offers terminal

1. Open the Version Control sidebar and select a project
2. Ensure no remote is configured (or use an invalid remote URL)
3. Click Push

**Expected:**
- Error modal appears with the error message
- Three buttons in footer: **Copy**, **Open Terminal**, **Close**
- Click "Open Terminal"
- Password prompt (if first time) then terminal opens
- You can type `git remote -v` or any command to debug the issue

### Test 7: Git pull failure offers terminal

1. Configure a remote that requires authentication but don't set up credentials
2. Click Pull

**Expected:**
- Error modal with Copy, Open Terminal, Close buttons
- "Open Terminal" opens a terminal at the project directory

### Test 8: DVC push failure offers terminal

1. In the Version Control DVC section, click Push
2. If MinIO is not configured or unreachable, the push will fail

**Expected:**
- Error modal with Copy, Open Terminal, Close buttons
- "Open Terminal" opens a terminal at the project directory
- You can run `dvc push -v` manually to debug

### Test 9: DVC pull failure offers terminal

1. Click Pull in the DVC section with an unavailable remote

**Expected:**
- Error modal with "Open Terminal" button
- Terminal at the correct directory

---

## Part 4: Terminal Reuse and Lifecycle

### Test 10: Terminal reuse for same project

1. Open a terminal for project X via the topbar icon
2. Click the terminal icon again for the same project

**Expected:**
- The existing terminal panel comes to front (no duplicate terminal)
- Same terminal session continues (previous commands still visible)

### Test 11: Separate terminals for different projects

1. Open a terminal for project A
2. Switch to project B in the Version Control dropdown
3. Click the terminal icon

**Expected:**
- A second terminal panel opens, offset from the first (cascading position)
- Each terminal shows its own project name in the title
- Each is cd'd into its respective project directory

### Test 12: Terminal cleanup on close

1. Open a terminal via the topbar icon
2. Close the terminal panel (X button)
3. Click the terminal icon again

**Expected:**
- A fresh terminal opens (new session, not the old one)
- The PTY process from the previous terminal was killed on close

---

## Part 5: Terminal Functionality

### Test 13: Terminal is fully interactive

1. Open a terminal via the topbar icon
2. Type commands:
   - `pwd` - should show the project path (e.g., `/app/projects/noted-testing`)
   - `git status` - should work
   - `dvc status` - should work
   - `ls -la` - should show project files

**Expected:**
- All commands execute correctly
- Output is rendered properly with colors (ANSI support)

### Test 14: Clipboard in terminal

1. In the terminal, select some text
2. Press Ctrl+Shift+C to copy
3. Press Ctrl+Shift+V to paste
4. Or right-click to paste

**Expected:**
- Copy and paste work correctly within the terminal

### Test 15: Terminal resize

1. Drag the terminal panel edges to resize

**Expected:**
- Terminal content reflows to fit the new dimensions
- No visual artifacts or truncation

---

## Part 6: Version Control Topbar Status

### Test 16: No remote shows grey LED

1. Select a project with no git remote configured

**Expected:**
- Grey LED dot on the right side of the topbar
- Label: "No remote"

### Test 17: Remote configured shows green LED

1. Select a project with a git remote configured (e.g., github.com)

**Expected:**
- Green LED dot on the right side of the topbar
- Label: hostname (e.g., "github.com")
- Hover tooltip shows full remote URL

---

## Part 7: No Secret Configured

### Test 18: Terminal opens without prompt when no secret is set

1. Remove or clear `NOTED_TERMINAL_SECRET` in `services/.env` (set to empty or remove the line)
2. Rebuild and restart
3. Click the terminal icon in the Version Control topbar

**Expected:**
- No password prompt appears
- Terminal opens directly
- This is the default behavior for local-only deployments

---

## Cleanup

Close any open terminal panels via the X button. PTY processes are killed automatically on panel close.

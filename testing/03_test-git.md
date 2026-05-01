# Git Integration - Test Procedure

## Prerequisites

- noted is running
- At least one project exists (e.g., `Examples`)
- Git Panel is accessible from the sidebar (Source Control icon)

---

## Test 1: Repository initialization

1. Create a new project via the Explorer panel
2. Open the Git Panel (Source Control in the sidebar)
3. Select the new project in the Projects section
4. **Expected:** Project shows as "not a git repo" with an "Initialize Repository" button
5. Click "Initialize Repository"
6. **Expected:** Git panel refreshes, shows the project as a git repo with branch `main` or `master`

## Test 2: Projects listing and selection

1. Open the Git Panel
2. **Expected:** All projects and mounts are listed in the Projects section
3. **Expected:** Projects with uncommitted changes show a badge with the change count
4. Click a different project to select it
5. **Expected:** The panel updates to show that project's status, branches, and history
6. Close and re-open noted
7. **Expected:** The previously selected project is still active (persisted in localStorage)

## Test 3: Author configuration

1. In the Git Panel, find the Author section
2. Enter a name and email
3. **Expected:** Values are saved automatically
4. Refresh the browser
5. **Expected:** Name and email are still populated (persisted in localStorage)

## Test 4: File status and changes

1. Open a notebook in a git-initialized project
2. Make a change to the notebook (e.g., add a cell) and save
3. Open the Git Panel
4. **Expected:** The Changes section lists the modified notebook file
5. **Expected:** File status indicators show the type of change (modified, added, etc.)
6. Click the refresh button in the Changes section
7. **Expected:** The file list updates to reflect the current state

## Test 5: Commit changes

1. Ensure there are uncommitted changes (from Test 4)
2. Type a commit message in the message input
3. Click the Commit button
4. **Expected:** Commit succeeds, changes section clears
5. **Expected:** The new commit appears at the top of the History section
6. **Expected:** Commit shows the author name and email from Test 3

## Test 6: Branch operations

1. In the Branches section, note the current branch
2. Click the "New branch" button
3. Enter a branch name (e.g., `test-branch`) and click Create
4. **Expected:** New branch is created and checked out
5. **Expected:** Branch dropdown shows the new branch as current
6. Switch back to the original branch using the dropdown
7. **Expected:** Branch switches successfully, panel updates

## Test 7: View commit history

1. Ensure the project has at least a few commits
2. **Expected:** History section shows commits with hash, message, author, and date
3. Click on a commit in the history
4. **Expected:** A diff view opens showing the files changed and their diffs
5. **Expected:** File additions shown in green, deletions in red

## Test 8: Tags

1. In the Tags section, enter a tag name (e.g., `v0.1`)
2. Click Create
3. **Expected:** Tag appears in the tags list with creation date
4. Click the delete button next to the tag
5. **Expected:** Tag is removed from the list

## Test 9: Git status decorations in Explorer

1. Modify a file in a git project
2. Check the Explorer panel file tree
3. **Expected:** Modified files show git status decorations (color/icon indicators)
4. Commit the changes
5. **Expected:** Decorations update to reflect the clean state

---

## Troubleshooting

- **Git panel shows no projects:** Check that projects exist in `data/projects/` or mounts are configured
- **Commit fails:** Verify author name and email are set
- **Branch operations fail:** Check backend logs (`docker logs noted`) for git errors
- **History doesn't load:** Ensure the project has at least one commit

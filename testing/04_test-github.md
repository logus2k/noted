# GitHub Integration - Test Procedure

## Prerequisites

- noted is running
- A GitHub account with a Personal Access Token (PAT) that has `repo` scope
- A test repository on GitHub (can be private)
- Git Panel is accessible from the sidebar

---

## Test 1: Clone a public repository

1. Open the Explorer panel
2. Click "Create Project"
3. Select "Clone from GitHub"
4. Enter a public repo URL (e.g., `https://github.com/octocat/Hello-World.git`)
5. Optionally enter a project name (or let it auto-derive from the URL)
6. Leave the PAT field empty (not needed for public repos)
7. Click Clone
8. **Expected:** Project is created and appears in the Explorer tree
9. **Expected:** The project contains the cloned repository files

## Test 2: Clone a private repository

1. Open the Explorer panel
2. Click "Create Project"
3. Select "Clone from GitHub"
4. Enter a private repo URL
5. Enter a project name
6. Enter your GitHub PAT
7. Click Clone
8. **Expected:** Project is created with the private repo contents
9. **Expected:** PAT is saved for future push/pull operations

## Test 3: Configure remote URL

1. Open the Git Panel
2. Select a project that was created locally (not cloned)
3. In the Remote section, enter a GitHub repository URL
4. Click the Save button
5. **Expected:** Remote URL is saved and displayed
6. **Expected:** Status indicator updates

## Test 4: Save Personal Access Token

1. In the Remote section, enter your GitHub PAT
2. Click Save
3. **Expected:** PAT is saved, a hint showing the last 4 characters is displayed (e.g., `****abcd`)
4. Refresh the browser
5. **Expected:** PAT hint is still shown (persisted on the backend in `data/git-credentials.json`)

## Test 5: Fetch from remote

1. Ensure a remote URL and PAT are configured (from Tests 3-4)
2. Make a commit on GitHub directly (via the web UI) so remote is ahead
3. Click the Fetch button in the Remote section
4. **Expected:** Fetch completes successfully
5. **Expected:** The sync status shows "1 behind" (or appropriate count)

## Test 6: Pull from remote

1. After fetching (Test 5), confirm the "behind" indicator shows
2. Click the Pull button
3. **Expected:** Pull completes with fast-forward
4. **Expected:** The sync status updates to "up to date"
5. **Expected:** The new commit appears in the History section

## Test 7: Push to remote

1. Make a local change and commit it
2. **Expected:** Sync status shows "1 ahead"
3. Click the Push button
4. **Expected:** Push completes successfully
5. **Expected:** Sync status updates to "up to date"
6. Verify on GitHub that the commit appears

## Test 8: Push with new branch (set upstream)

1. Create a new local branch (via Branches section)
2. Make a commit on the new branch
3. Click Push
4. **Expected:** Push detects no upstream, automatically sets upstream and pushes
5. Verify on GitHub that the new branch appears

## Test 9: Remote branches

1. Ensure the remote has branches not present locally
2. Open the Branches dropdown
3. **Expected:** Remote branches appear in a separate group (optgroup)
4. Select a remote branch
5. **Expected:** Branch is checked out locally as a tracking branch

---

## Troubleshooting

- **Clone fails with "authentication required":** Ensure PAT has `repo` scope and is entered correctly
- **Push/Pull fails with 403:** PAT may have expired or lack permissions - re-save a new PAT
- **"No remote configured":** Set the remote URL in the Remote section first
- **Fetch shows no changes:** Verify the remote URL points to the correct repository

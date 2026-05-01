---
name: dvc-checkout
description: Restoring previous data versions safely. Use when user asks how to roll back data, restore an old dataset version, undo a data change, or checkout a previous DVC file version.
triggers: [dvc_in_context]
priority: 1
max_tokens: 300
---
Restoring previous DVC data versions in noted:

CHECKOUT PROCESS:
1. Open the Explorer panel and find the DVC-tracked file.
2. Right-click -> "File History" to see all versions.
3. Each version shows: git commit hash, date, message, and DVC hash.
4. Select the target version and click "Checkout".
5. DVC downloads the file content from MinIO for that hash.
6. The local file is replaced with the restored version.

WHAT HAPPENS:
- The `.dvc` pointer file is updated to the selected version's hash.
- The actual data file is replaced with the historical content.
- The change is local only until you commit the updated `.dvc` file.

SAFETY:
- The current version is NOT deleted from MinIO. It remains accessible by its hash.
- If you checkout and then want to go back, just checkout the newer version.
- Always commit the `.dvc` pointer change to git if you intend to keep the rollback.
- If you do not commit, `dvc checkout` (without arguments) restores whatever the `.dvc` file points to.

WORKFLOW FOR ROLLBACK:
1. Checkout the desired data version.
2. Verify the data looks correct.
3. Commit the `.dvc` pointer update with a descriptive message (e.g., "Revert to pre-cleanup dataset").
4. Push the restored version: `dvc push` (likely a no-op since it already exists in MinIO).

COMMON SCENARIOS:
- Data corruption: roll back to the last known good version.
- Experiment comparison: temporarily checkout old data, run training, compare results.
- Undo preprocessing: revert to raw data before a transformation step.

"I ACCIDENTALLY DELETED MY DATA FILE" (answer directly, NO tool calls):
- The data file is gone locally but the `.dvc` pointer still exists and the content is safe in MinIO.
- Run `dvc checkout foo.csv` to restore it from the current hash. If the cache is empty, run `dvc pull foo.csv` to fetch it from MinIO.
- No git revert needed - the pointer wasn't changed.

"I ACCIDENTALLY RESET / REVERTED AND LOST MY DATA":
- Run `dvc checkout` (no args) after `git reset` / `git checkout <commit>` to sync the data files to whatever the `.dvc` pointers now say. DVC restores each tracked file to its pointed hash.

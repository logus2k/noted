---
name: dvc-sync-debugging
description: Troubleshooting DVC push/pull failures with MinIO. Use when user reports DVC push failed, pull not working, file not found in remote, access denied on DVC, or MinIO connection issues.
triggers: [dvc_in_context]
priority: 1
max_tokens: 350
---
Troubleshooting DVC sync issues with MinIO:

PUSH FAILURES:
- "Unable to push": MinIO container may be down. Check container status.
- "Access Denied": MinIO credentials mismatch. Verify `.dvc/config` remote settings.
- "Bucket not found": the MinIO bucket was not created. Check MinIO console.
- Timeout: large file + slow network. Check file size and network connectivity.

PULL FAILURES:
- "File not found in remote": data was never pushed, or was pushed to a different remote.
- "Checksum mismatch": corrupted transfer. Delete the cache and re-pull.
- "Connection refused": MinIO container is not running or port is blocked.

DIAGNOSTIC STEPS:
1. Check MinIO container status: look for the minio container in Docker.
2. Verify DVC remote config: `.dvc/config` should point to `s3://` with correct endpoint.
3. Test MinIO connectivity: the MinIO console should be accessible.
4. Check the DVC cache: `.dvc/cache/` stores local copies of tracked files.
5. Look at the `.dvc` pointer file: confirm the hash matches what is expected.

COMMON FIXES:
- Restart the MinIO container if it is unresponsive.
- Re-run `dvc push` after confirming connectivity.
- If cache is corrupted, delete `.dvc/cache/` and run `dvc pull` to re-download.
- For credential issues, check the DVC remote config matches the MinIO access/secret keys in the Compose environment.

TEAM SYNC:
- "File not found" for a colleague often means the original user forgot to push.
- Workflow: `dvc add` -> `git commit` -> `dvc push`. All three steps are required.
- The `.dvc` pointer must be committed to git so others can pull the same version.

"FILE MODIFIED BUT I DIDN'T CHANGE IT" (conceptual - NO tool calls needed):
- DVC compares the current file hash to the one in the `.dvc` pointer. A mismatch can come from:
  - Metadata / timestamp change (e.g., an editor or build step touched the file without content change).
  - Line-ending conversion (CRLF vs LF) on cross-platform checkouts.
  - Encoding normalization by an IDE save.
  - Reformat / auto-format tools silently rewriting the file.
  - Filesystem permission/inode change after a copy/move.
- Remedy: run `dvc status` to see the diff details, then either `dvc checkout data.csv` to restore the tracked version (if the local change was unintentional) or `dvc commit` to record the new content as a new version (if intentional).
- Do not call `get_dvc_file_history` for this diagnosis - history shows past VERSIONS, not why the current file hash differs from the pointer.

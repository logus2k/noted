---
name: dvc-versioning
description: Understanding data versions, hashes, history, and checkout. Use when user asks about data version history, what a DVC hash means, how to compare data versions, or how to view file history in the Explorer.
triggers: [dvc_in_context]
priority: 1
max_tokens: 350
---
DVC data versioning in noted:

VERSION IDENTITY:
- Each tracked file has a `.dvc` pointer containing an MD5 hash of the data.
- The hash uniquely identifies the file content - same content, same hash.
- When you modify a file and run `dvc add`, a new hash is generated.
- Committing the updated `.dvc` file to git creates a version checkpoint.

VERSION HISTORY:
- View history in the Explorer panel: right-click a DVC-tracked file -> "File History".
- Each entry shows: git commit hash, date, commit message, and DVC hash.
- The history is derived from the git log of the `.dvc` pointer file.
- Use `get_dvc_history` tool to retrieve version history programmatically.

HASH TRACKING:
- DVC hashes appear in MLflow run tags when datasets are selected in the Run Manager.
- This connects: which exact data version produced which training result.
- Two runs with the same DVC hash used identical data.
- Different hashes mean data changed between runs.

CHECKOUT (RESTORE):
- Select a version from the history and click "Checkout".
- DVC downloads the file content for that hash from MinIO.
- The `.dvc` pointer is updated to the selected version's hash.
- The working directory now has the restored file.
- Remember to commit the `.dvc` change to git if you want to keep this state.

COMPARING VERSIONS:
- Use DVC hashes to identify when data changed between experiments.
- If metrics degraded, check whether the data version also changed.
- Consistent data hash across runs means performance differences are from config/code changes.

The `.dvc` pointer file is lightweight (a few bytes). The actual data lives in MinIO, retrieved on demand via pull/checkout.

---
name: dvc-tracking
description: How DVC file tracking works in noted - tracking, push, pull, versioning. Use when user asks how to track a file with DVC, push data to remote, pull data, or understand how DVC versioning works.
triggers: [dvc_in_context]
priority: 1
max_tokens: 350
---
DVC data tracking in noted:

TRACKING FILES:
- Right-click a file in Explorer -> "Track with DVC" (no CLI needed).
- DVC auto-initializes in the project if not set up.
- Creates a `.dvc` pointer file and adds the data file to `.gitignore`.
- Supported: .csv, .pkl, .h5, .parquet, .npy, .pt, .onnx, .safetensors, .joblib, and 20+ more.

REMOTE STORAGE:
- MinIO (S3-compatible, on-premises) is the remote backend.
- `dvc push` uploads tracked files to MinIO.
- `dvc pull` downloads from MinIO to local.
- Team members share data via push/pull without copying large files.

VERSIONING:
- Each `dvc add` creates a new hash in the `.dvc` pointer file.
- Committing the pointer to git creates a data version.
- File history shows all versions with commit hash, date, and message.
- "Checkout" restores any previous version from MinIO.

LINEAGE:
- DVC hash uniquely identifies a data version.
- The Run Manager lets you tag MLflow runs with selected DVC datasets.
- This links: which data version was used to train which model.

UNTRACK / STOP TRACKING A FILE:
- Run `dvc remove foo.csv.dvc` (the `.dvc` pointer file, not the data file). This detaches the file from DVC.
- The actual data file (`foo.csv`) stays in your workspace untouched; only the DVC pointer is removed.
- Run `dvc push` afterward so the removal propagates to MinIO for the team.
- Optional: `git rm foo.csv.dvc` to remove the pointer from version control too.

BEST PRACTICES:
- Track: raw datasets, processed features, trained model weights, large outputs.
- Don't track: code, configs, small metadata, notebooks.
- Push after each significant data change.
- Use meaningful git commit messages when versioning data.

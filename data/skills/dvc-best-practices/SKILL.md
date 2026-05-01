---
name: dvc-best-practices
description: What to track with DVC, naming conventions, and workflow. Use when user asks what files to version, how to organize data, DVC workflow tips, or whether a file should be tracked with DVC or git.
triggers: [dvc_in_context]
priority: 1
max_tokens: 300
---
DVC best practices in noted:

WHAT TO TRACK:
- Track: raw datasets, processed features, trained model weights, large outputs, prediction results.
- Don't track: source code, Hydra configs, notebooks, small metadata files, logs.
- Rule of thumb: if the file is > 1 MB or is a binary, track it with DVC.

NAMING CONVENTIONS:
- Use descriptive names: `jena_climate_raw.csv`, not `data.csv`.
- Version context goes in the git commit message, not the filename.
- Keep dataset files in a `data/` directory within the project.
- Model weights in a `models/` or `outputs/` directory.

WORKFLOW:
1. Add data to the project directory.
2. Right-click -> "Track with DVC" in Explorer.
3. Commit the `.dvc` pointer and `.gitignore` changes to git.
4. Run `dvc push` to upload to MinIO.
5. After modifying data: re-run `dvc add`, commit, push.

TEAM COLLABORATION:
- Always push after committing a new data version.
- Communicate data changes to the team (commit messages help).
- New team members: clone the repo, then `dvc pull` to get all tracked files.
- The `.dvc` pointer is tiny - only the hash and metadata. Data stays in MinIO.

AVOID:
- Tracking files that change on every run (e.g., log files). This creates version noise.
- Forgetting to push - others cannot pull what was not pushed.
- Tracking the same file with both git and DVC.
- Very large numbers of small files - bundle them into an archive first.

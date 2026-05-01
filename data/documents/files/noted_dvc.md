# noted + DVC: Data Versioning Integration

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Tool Integration: DVC              |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-03-12                         |
| Status        | Draft                              |
| Related       | noted_vision.md, noted_scope.md, noted_plan.md |

---

## 1. Overview

DVC (Data Version Control) is the canonical tool for versioning large datasets, model artifacts, and pipeline definitions that do not belong in Git. It stores lightweight pointer files (`.dvc`) in Git while pushing the actual data to a configured remote — in noted's case, the built-in MinIO instance (`noted-dvc` bucket).

The result is a complete, reproducible record: every Git commit can be paired with the exact dataset and model artifacts used at that point in time. noted's role is to make this invisible complexity feel native: users should be able to version their data, reproduce experiments, and inspect lineage without dropping into a terminal.

---

## 2. How DVC Fits Into noted

noted already has Git integration (Source Control sidebar view). DVC extends that integration downward, into the data layer. The mental model for the user is simple:

- **Git** tracks code, notebooks, and DVC pointer files
- **DVC** tracks the actual datasets and model files, stored in MinIO
- **MLflow** tracks the experiment metrics and parameters that link a code version to a data version

Together they form a complete reproducibility stack. noted surfaces all three in a unified interface.

---

## 3. Use Cases

### 3.1 Versioning a Dataset

**Context:** A data scientist has downloaded or prepared a cleaned dataset (CSV, Parquet, images, etc.) in their project folder. They want to version it so that future experiments can reference the exact same data.

**DVC approach:** `dvc add data/train.csv` creates `data/train.csv.dvc` (a pointer file) and adds `data/train.csv` to `.gitignore`. The actual file is pushed to MinIO with `dvc push`. The pointer file goes into Git.

**noted UI support:**

- **Workspace tree**: Files tracked by DVC display a distinct badge (e.g., a lock or cloud icon) next to their name in the project tree, indicating they are DVC-managed. Clicking such a file opens a detail view showing its current hash, size, and remote status (local / pushed / stale).
- **Source Control panel**: After `dvc add`, the new `.dvc` pointer file appears in the Changed Files list. The user stages and commits it alongside any notebook changes — one commit captures both the code state and the data version reference.
- **Context menu on data files**: Right-click a file in the project tree → "Track with DVC" runs `dvc add` in the background, immediately updating the workspace tree badge and staging the pointer file for commit.
- **Status indicators**: DVC-tracked files show sync status — a cloud-up icon if unpushed, a checkmark if remote matches local. This mirrors the Git ahead/behind indicator model.

---

### 3.2 Switching Between Dataset Versions

**Context:** Two experiments were run at different points in time, each using a different version of the training data. The user wants to go back and reproduce the older result.

**DVC approach:** `git checkout <commit>` restores the `.dvc` pointer files from that commit. `dvc checkout` then restores the actual files from MinIO (or local cache).

**noted UI support:**

- **Git history view**: Each commit in the Source Control history panel shows which `.dvc` files changed in that commit — displayed as data version change indicators alongside code changes.
- **Reproduce from commit**: A "Restore data" button on a historical commit runs `git checkout <commit> -- <file>.dvc && dvc checkout` for the selected files, pulling the data version that was current at that commit.
- **MLflow run linkage**: If an MLflow run stores the Git commit SHA (which `mlflow.log_param('git_commit', ...)` or auto-logging provides), the experiment detail view in noted can offer a "Restore environment" action that checks out the corresponding code and data together.

---

### 3.3 Reproducing an Experiment End-to-End

**Context:** A peer wants to reproduce an experiment from a shared project. They have the Git history and DVC remote access. The experiment involved a specific dataset version and a specific notebook state.

**DVC approach:** `git clone` + `dvc pull` restores both code and data. If a `dvc.yaml` pipeline exists, `dvc repro` re-executes all stages whose dependencies have changed.

**noted UI support:**

- **Workspace tree → project actions**: "Reproduce" button on a project that has a `dvc.yaml` pipeline — runs `dvc repro` inside the project directory, streams output to the terminal panel.
- **Pipeline stage visualization**: The Pipelines section of the workspace tree lists DVC pipeline stages defined in `dvc.yaml`. Each stage shows its command, dependencies, and outputs. Status indicators show whether the stage is fresh (outputs match DVC cache) or needs re-execution.
- **One-click reproduce**: Clicking "Run" on a pipeline stage in the Pipelines tree runs only that stage (and its dependencies if stale), without re-running the full pipeline.

---

### 3.4 Pushing and Pulling Data to MinIO

**Context:** A user has added and committed a new dataset version. They need to push the actual data to MinIO so collaborators can pull it.

**DVC approach:** `dvc push` uploads changed files to the configured remote. `dvc pull` downloads files that are tracked but missing locally.

**noted UI support:**

- **Source Control panel — data sync section**: Below the Git push/pull actions, a DVC Data section shows "X files staged for DVC push" and "Y files missing from local cache". Push and Pull buttons execute the respective DVC commands.
- **Push-on-commit**: Optional setting to automatically run `dvc push` after every Git commit, keeping the remote in sync without a separate step.
- **Remote status summary**: The MinIO tree node in the Workspace sidebar shows the `noted-dvc` bucket size and last sync time, giving users confidence that data is persisted.

---

### 3.5 Tracking Data Lineage Across Experiments

**Context:** A user wants to know which version of a dataset was used in the three best-performing MLflow experiments, and whether those data versions are still available in MinIO.

**DVC approach:** Each MLflow run can log the DVC data hash or Git commit SHA as a parameter. Cross-referencing MLflow run parameters with DVC file history reveals which data was used in each run.

**noted UI support:**

- **MLflow experiment detail**: When viewing an experiment run (either via the MLflow tab or a future experiment panel), noted displays the Git commit SHA and, if available, the associated DVC file hashes logged as parameters.
- **Data lineage badge**: In the workspace tree, DVC-tracked files show a "used in N runs" badge when they are referenced by MLflow run parameters. Clicking opens a filtered view of those runs.
- **Reproducibility score**: A future indicator on a project node that signals whether the current code + data state matches any known MLflow run (i.e., the experiment is fully reproducible from the current workspace state).

---

### 3.6 Managing Pipeline Dependencies (`dvc.yaml`)

**Context:** A team has a multi-stage ML pipeline: data preprocessing → feature extraction → model training → evaluation. They manage this as a DVC pipeline so that only affected stages re-run when inputs change.

**DVC approach:** `dvc.yaml` defines stages with `cmd`, `deps`, and `outs`. `dvc repro` executes only stale stages. `dvc dag` shows the dependency graph.

**noted UI support:**

- **Pipeline editor**: A YAML editor (CodeMirror) for `dvc.yaml` in the project tree — stages are syntax-highlighted, and the editor validates stage structure against the DVC schema.
- **DAG visualization**: A graphical view of the pipeline DAG in the Pipelines section of the workspace tree — nodes represent stages, edges represent dependencies. Color coding shows which stages are fresh vs stale.
- **Stage execution**: Right-click a stage → "Force re-run" executes that stage with `dvc repro --force <stage>`, streaming output to the terminal. The DAG updates live as stages complete.
- **Metrics integration**: Pipeline stages that produce metrics files (`metrics:` in `dvc.yaml`) surface those values directly in the DAG node tooltip, eliminating the need to look them up in a separate tool.

---

### 3.7 Comparing Data Versions

**Context:** A user suspects a data quality regression — recent model performance dropped and they want to compare the current dataset version against the one used in the last good experiment.

**DVC approach:** `dvc diff <old_commit> <new_commit>` shows which tracked files changed, their size deltas, and hash changes.

**noted UI support:**

- **Data diff panel**: A diff view accessible from the Source Control panel — select two commits (or two MLflow runs) and view a DVC diff summary: which data files changed, size before/after, and whether the change was an update, addition, or deletion.
- **Notebook-aware diff**: When a notebook re-run produces different results than a historical MLflow run, the experiment comparison view flags "data changed since this run" if the DVC hashes differ.

---

## 4. MinIO as DVC Remote: The Built-In Advantage

noted runs MinIO as part of its infrastructure stack. This is the key integration point:

- DVC is pre-configured to use the `noted-dvc` bucket in the local MinIO instance
- No setup required — users can `dvc push` and `dvc pull` immediately after creating a project
- The MinIO workspace tree node in noted shows bucket contents, allowing users to browse stored DVC files directly
- Credential management (MinIO access/secret keys) is handled by noted's backend, not exposed to users

This eliminates the most common DVC onboarding friction: configuring a remote. For teams using noted, the remote just works.

---

## 5. Build Order (Phase 1B)

Based on the dependency structure in `noted_plan.md`, DVC integration in noted builds in this order:

1. **DVC init + remote config**: Backend auto-initializes DVC in new projects, auto-configures MinIO remote. No user action required.
2. **Workspace tree badges**: DVC-tracked file indicators in the project tree (read-only status display).
3. **Source Control panel extension**: DVC push/pull buttons alongside Git push/pull. Shows DVC sync status.
4. **Context menu actions**: "Track with DVC" on files in the project tree.
5. **Pipeline tree**: List DVC stages from `dvc.yaml` in the Pipelines workspace section.
6. **Reproduce from MLflow run**: "Restore environment" action in the experiment detail view.
7. **DAG visualization**: Graphical pipeline dependency view.
8. **Data diff and lineage views**: Cross-experiment data comparison.

Steps 1–4 are Phase 1B. Steps 5–8 extend into Phase 2 and Phase 4.

---

## 6. Design Principles for noted's DVC Integration

- **Zero terminal for common operations**: Adding, pushing, pulling, and reproducing should all be available as UI actions. The terminal remains available for advanced use.
- **Data is a first-class citizen**: The workspace tree treats data files with the same visual hierarchy as notebooks and Python files. Versioned data is not hidden in `.dvc` files.
- **Lineage is automatic**: noted links DVC data versions to MLflow runs without requiring the user to manually log hashes. The connection is derived from Git commit SHAs shared between both systems.
- **Remote is invisible**: Users should never need to think about the MinIO bucket. DVC push and pull are presented as "sync data" actions, not storage operations.

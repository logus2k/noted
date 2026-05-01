---
name: mlflow-artifacts
description: Understanding artifact types, browsing, and downloading from MLflow runs. Use when user asks about run artifacts, how to download a model file, where artifacts are stored, or how to browse training outputs.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 350
---
MLflow artifacts in noted:

ARTIFACT TYPES:
- Models: serialized model files (PyTorch .pt, TensorFlow SavedModel, scikit-learn .pkl, ONNX .onnx).
- Images: training plots, confusion matrices, attention maps (.png, .jpg, .svg).
- Charts: auto-generated metric charts from training curves.
- Files: any additional output - CSVs, JSON configs, text logs, predictions.
- MLmodel: metadata file describing the model flavor, signature, and dependencies.

BROWSING:
- In the Experiments panel, expand a run to see its artifact tree.
- Artifacts are organized by subdirectory (e.g., `model/`, `charts/`, `outputs/`).
- Use `get_run_artifacts` tool to list artifacts programmatically.
- Image artifacts render inline in the run detail view.

DOWNLOADING:
- Click the download icon next to any artifact in the run detail view.
- API: `GET /api/mlflow/artifacts/download` with run_id and artifact_path.
- Bulk download is available for entire artifact directories.

ARTIFACT STORAGE:
- All artifacts are stored in MinIO (S3-compatible, on-premises).
- The artifact URI follows the pattern: `s3://mlflow/{experiment_id}/{run_id}/artifacts/`.
- No cloud dependency - everything stays on the local infrastructure.

AUTO-LOGGED ARTIFACTS:
- Auto-instrumented runs log model artifacts automatically when a model is detected.
- Training curves are saved as chart images after each run.
- The Hydra config YAML is saved as an artifact for reproducibility.

When discussing artifacts, reference the specific artifact path and type.

TOOL CHOICE (critical - ONE call per question, never chain):
- "What artifacts does run X have?" / "what's in this run?" -> `get_run_details(run_id=X)` ONCE. Returns a CLASSIFIED artifact summary (counts by category: Models / Images / Charts / Files / other). Prefer this for the overview. Do NOT call `list_run_artifacts` for this question - that's a deeper drill for a known path.
- "Open the model directory" / "show me files under <subdir>" -> `list_run_artifacts(run_id=X, path="<subdir>")` ONCE.
- "Does the run carry a Hydra config bundle?" / "is there a X/ directory in the artifacts?" -> `list_run_artifacts(run_id=X, path="hydra")` ONCE (or the named subdir). If the tool returns empty, report that the bundle is absent AND briefly describe what a noted Hydra bundle contains when present (config/ tree, selections.json, resolved.yaml) plus its lineage purpose (reproducibility of the run). If the tool returns content, list what's there. Do NOT retry or fall back to other tools - absent means absent.
- "Download the model" -> NO tool call; explain the download options (UI icon, `mlflow.artifacts.download_artifacts`, API endpoint).
- Rule of thumb: one question = one tool call. Do not chain `get_run_details` -> `list_run_artifacts` -> `list_run_artifacts` just to be thorough; the first call answers the question.

REPORTING THE ARTIFACT LISTING (zero-tolerance for invention):
- The names you report MUST be a literal subset of the names in the tool output. Common mistake: saying "model.pkl, model.pth" when the tool actually returned "MLmodel, conda.yaml, python_env.yaml, python_model.pkl, requirements.txt". Pattern-matching on what an MLflow model directory "usually" contains is hallucination - quote the actual filenames.
- Do not abbreviate, generalize, or substitute names ("model.pkl" is not a valid stand-in for "python_model.pkl").
- If the listing is long, you may say "and N more" but only after listing the first ones verbatim.

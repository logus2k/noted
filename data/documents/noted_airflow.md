# noted + Airflow: Pipeline Orchestration Integration

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Tool Integration: Airflow          |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-03-12                         |
| Status        | Draft                              |
| Related       | noted_vision.md, noted_scope.md, noted_plan.md |

---

## 1. Overview

Apache Airflow is the orchestration engine in noted's MLOps stack. It schedules, sequences, and monitors the execution of multi-step workflows (DAGs — Directed Acyclic Graphs) that move data from raw input through preprocessing, training, evaluation, and deployment. Airflow is already running in noted's infrastructure as `noted-airflow-apiserver` and is accessible to end users via the embedded `/airflow` tab in the center pane.

The gap that noted fills is the distance between where the work happens (notebooks, Python files, the IDE) and where pipelines are defined and triggered (the Airflow web UI and DAG Python files). Currently, a practitioner must context-switch to the Airflow UI to monitor runs, check logs, and trigger new executions. noted eliminates that switch: pipeline status, execution control, and run history are surfaced directly in the workspace, alongside the notebooks and code that define the pipeline logic.

---

## 2. How Airflow Fits Into noted

Airflow DAGs are Python files stored in a shared DAGs folder mounted into the Airflow container. In noted's architecture:

- **DAG files** live in the project's `pipelines/` directory (mounted read-only into Airflow workers)
- **Pipeline runs** are triggered via Airflow's REST API (JWT-authenticated from noted's backend)
- **Run status and logs** are polled from Airflow's API and surfaced in noted's Pipelines workspace section
- **Outputs** (model files, transformed datasets, reports) are written to MinIO and tracked by DVC

The noted user does not need to know the Airflow web UI to manage their pipelines. The Airflow tab remains available for advanced configuration, but the common operations (trigger, monitor, inspect logs) are native to noted.

---

## 3. Use Cases

### 3.1 Authoring a Pipeline DAG

**Context:** A data scientist has been developing preprocessing and training logic in notebooks. They want to productionize this as a scheduled pipeline that runs nightly on fresh data.

**Airflow approach:** Write a DAG Python file that defines tasks (Python operators, BashOperators, etc.) with explicit dependencies. Place the file in the DAGs folder where Airflow can discover it.

**noted UI support:**

- **Pipelines section in workspace tree**: A `Pipelines` node in the workspace tree that shows all `.py` DAG files in the project's `pipelines/` directory. Creating a new DAG from a template (blank, single-task, data pipeline, training pipeline) is a right-click action on the Pipelines node.
- **DAG file editor**: Python DAG files open in the center pane CodeMirror editor — same environment used for Python source files. Airflow-specific imports and task decorators are syntax-highlighted and type-aware.
- **Notebook-to-DAG conversion**: A one-click "Export as Pipeline Task" action on a notebook cell or group of cells. noted generates a Python function (decorated with `@task`) that encapsulates the selected cell logic, adds it to the project's pipeline template, and opens the result in the DAG editor. This bridges the experimentation-to-production gap without a manual rewrite.
- **DAG validation**: Before saving, noted runs a lightweight local validation — checks for import errors, circular dependencies, and common Airflow pitfalls — and displays warnings in the editor gutter.

---

### 3.2 Triggering a Pipeline Run

**Context:** The user wants to manually trigger a pipeline run to test it with a new dataset, or to start a training job on demand rather than waiting for the scheduled time.

**Airflow approach:** Call the Airflow REST API: `POST /api/v1/dags/{dag_id}/dagRuns` with optional configuration parameters.

**noted UI support:**

- **Run button on pipeline node**: Each DAG in the Pipelines tree has a Play button (▶). Clicking it opens a "Trigger Run" dialog showing: run ID (auto-generated), config parameters (pre-filled with defaults, editable as JSON), and a Hydra config override field.
- **Config parameters**: The trigger dialog pulls the `dag.params` schema from Airflow to present a form — users fill in labeled fields rather than raw JSON.
- **Run from notebook**: A "Run as Pipeline" action in the notebook bar that triggers the associated DAG (if one exists for the current project), passing the current notebook's Hydra config selections as run parameters.
- **Immediate feedback**: After triggering, the Pipelines tree updates in real time to show the new run in "queued" state, transitioning to "running" as Airflow picks it up.

---

### 3.3 Monitoring Pipeline Execution

**Context:** A training pipeline was triggered 20 minutes ago. The user wants to know which tasks have completed, which are running, and whether anything has failed — without opening the Airflow web UI.

**Airflow approach:** Poll `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances` for task-level status.

**noted UI support:**

- **Live run status in Pipelines tree**: The currently active run is shown under its DAG node with a progress indicator. Each task appears as a sub-node with its own status icon (queued / running / success / failed / skipped). The tree auto-refreshes every 10 seconds during an active run.
- **Task duration and timing**: Expanding a task node shows start time, end time (or elapsed time if still running), and the task operator type.
- **Run history**: Completed runs are listed under the DAG node — expanding a historical run shows the per-task outcome. The last N runs are shown, with a "Load more" option.
- **Failure highlighting**: Failed tasks are shown with a red indicator and a "View logs" link. noted fetches the task log from Airflow's API and displays it inline — no need to navigate to the Airflow UI or SSH into a worker.

---

### 3.4 Inspecting Task Logs

**Context:** A pipeline task failed. The user needs to see the full log output — which library produced the error, which line of their code, and what the stack trace was.

**Airflow approach:** `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}`

**noted UI support:**

- **Inline log viewer**: Clicking "View logs" on a failed task opens the log in the center pane — in a read-only terminal-style view (xterm.js or a styled pre block) with ANSI color support. Python tracebacks and log level prefixes are highlighted.
- **Jump to error**: Logs are scanned for common error patterns (Traceback, ERROR, Exception). A "Jump to error" button scrolls to the first error line, sparing the user from reading long startup logs.
- **Copy log**: One-click copy of the full log text for sharing in a bug report or Slack message.
- **Re-run failed task**: A "Retry" button that calls Airflow's API to clear and re-queue the failed task instance. Available directly from the log viewer without navigating away.

---

### 3.5 Scheduling Recurring Pipeline Runs

**Context:** A team needs the data preprocessing pipeline to run every night at 2am, and the training pipeline to run every Sunday. They want to manage these schedules from noted without editing DAG files or using the Airflow UI.

**Airflow approach:** The schedule is defined in the DAG Python file as a cron expression or Airflow timedelta. Changing it requires editing and redeploying the DAG.

**noted UI support:**

- **Schedule display**: The DAG node in the Pipelines tree shows the current schedule expression (e.g., `0 2 * * *`) alongside a human-readable description ("Every day at 02:00") and the next scheduled run time.
- **Schedule editor**: A cron editor widget on the pipeline detail panel — either a text field with cron expression validation, or a visual builder (checkboxes for days/hours). Changing the schedule updates the DAG file and saves it, triggering Airflow's DAG file re-parse.
- **Next runs preview**: Shows the next 3 scheduled run times before the user commits a schedule change, so they can verify the cron expression is correct.
- **Pause/unpause DAG**: A toggle switch on the pipeline node pauses or unpauses the DAG (calls `PATCH /api/v1/dags/{dag_id}` with `is_paused`). Paused DAGs are shown with a visual indicator so their schedule is clearly suspended.

---

### 3.6 Data-Aware Pipeline Triggering

**Context:** The team wants the training pipeline to automatically trigger when new data is pushed to MinIO — without polling or building a custom trigger.

**Airflow approach:** Airflow 3 supports Dataset-aware scheduling. A DAG can declare `schedule=[Dataset("s3://noted-dvc/projects/{project}/data/train.csv")]` and Airflow triggers it when a producing DAG marks that dataset as updated.

**noted UI support:**

- **Dataset trigger display**: The pipeline detail panel shows which datasets (MinIO paths) trigger this DAG, alongside a "Last triggered by" event and timestamp.
- **Manually mark dataset**: A "Trigger dataset event" action on a MinIO file in the Storage workspace tree — marks the file as updated in Airflow's dataset tracking, triggering any subscribed DAGs. Useful for testing dataset-driven pipelines.
- **Dataset lineage view**: A graphical view showing which DAGs produce which datasets and which DAGs consume them — derived from Airflow's Dataset catalog API. This gives the team a live picture of their data flow without maintaining a separate diagram.

---

### 3.7 Parameterized Training Runs (DAG + Hydra)

**Context:** The team runs the same training DAG with different model configurations: small model for quick iteration, large model for final training. They want to select the config at trigger time, not by maintaining separate DAGs.

**Airflow approach:** The DAG accepts a `conf` parameter dict in its trigger payload. The task reads `context['params']['hydra_overrides']` and passes the overrides to Hydra.

**noted UI support:**

- **Config-parameterized trigger**: The Trigger Run dialog includes a Hydra overrides field (as described in the Hydra document). The value is passed as a DAG run param and forwarded to each task's Hydra config loader.
- **Config logged per run**: The run history shows the Hydra override string used for each execution, so users can compare configurations across runs without needing to check MLflow separately.
- **Template runs**: Users can save named run configurations ("small model - dev", "large model - production") as templates. Re-running with the same config is a one-click action.

---

### 3.8 Multi-Project Pipeline Overview

**Context:** An MLOps engineer manages pipelines across several noted projects and needs a single view of all pipeline health — which projects have active runs, which have recent failures, and which have stale schedules.

**Airflow approach:** The Airflow UI's DAGs list provides this view, but it requires leaving noted.

**noted UI support:**

- **Pipelines summary in workspace**: A top-level "Pipelines" section that aggregates DAG status across all projects the user has access to. Shows: project name, DAG name, last run status, last run time, next scheduled run.
- **Health indicators**: Red/yellow/green indicators on the workspace tree's Pipelines node — red if any DAG has a recent failure, yellow if any DAG is paused or overdue, green if all recent runs succeeded.
- **Quick actions**: From the summary view, users can trigger a run or view the last run's logs without navigating into a specific project.

---

## 4. The MLflow Connection

Every Airflow task that involves model training or evaluation should produce an MLflow run. noted makes this the default pattern:

- **MLflow run per task**: Training tasks automatically initialize an MLflow run (the `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_NAME` environment variables are injected by noted's kernel manager; Airflow workers get the same variables via their environment config).
- **Run linkage**: The Airflow `dag_run_id` is logged as an MLflow tag (`airflow.dag_run_id`). This links Airflow execution history to MLflow experiment history — from noted's run detail view, a "View Airflow run" link jumps to the corresponding DAG run.
- **Artifact handoff**: Pipeline tasks write model artifacts to MinIO. The final task registers the artifact in MLflow's model registry. noted's Models workspace section reflects the new registration without the user needing to interact with MLflow directly.

---

## 5. Build Order (Phase 2)

Airflow integration in noted builds in this order:

1. **Pipelines tree**: List DAGs from Airflow API per project; show status and last run.
2. **Trigger run**: Trigger dialog with params; show new run in tree immediately.
3. **Live run monitoring**: Task-level status auto-refresh during active runs.
4. **Task log viewer**: Inline log display with jump-to-error and retry.
5. **DAG file editor**: Python DAG files editable in center pane with validation.
6. **Schedule editor**: Cron expression editor with human-readable preview.
7. **Dataset-aware triggers**: Display and manual trigger for dataset-scheduled DAGs.
8. **Multi-project pipeline summary**: Cross-project health dashboard.

Steps 1–4 are Phase 2 deliverables. Steps 5–8 extend into Phase 4.

---

## 6. Design Principles for noted's Airflow Integration

- **Monitor without leaving**: The most common operations (check status, view logs, retry a task) never require opening the Airflow web UI. The Airflow tab remains for advanced administration.
- **Author with context**: DAG files are written in the same editor as the project's Python files, with the project tree visible. Practitioners can reference their notebook logic while authoring pipeline tasks.
- **Scheduling is a first-class concern**: Schedules are displayed prominently and editable without touching files. The "next run" timestamp is always visible so teams never wonder when the pipeline last ran.
- **Every run is traceable**: The Airflow run ID, the Hydra config used, the DVC data version consumed, and the MLflow run produced are all linked. noted surfaces these connections so the team has complete traceability from trigger to result.

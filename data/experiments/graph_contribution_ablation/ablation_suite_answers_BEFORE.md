
# [factual] What is the noted-serving container for?


## VEC

The `noted-serving` container is a dedicated FastAPI service whose purpose is to turn a registered MLflow model into an HTTP endpoint for making predictions.

Its core responsibilities include:

*   **Loading and Serving:** It dynamically loads a registered MLflow model into memory and answers prediction requests over HTTP. Exactly one model is deployed at a time.
*   **Prediction Endpoint:** It exposes a `/predict` endpoint where clients send input data to run inference on the currently loaded model.
*   **Schema Validation:** It uses a `/schema` endpoint to expose the model's input and output signature, allowing clients to build correctly formatted request payloads.
*   **Health Monitoring:** It provides a `/health` endpoint to report the current state and metadata of the loaded model.
*   **Deployment:** It supports alias-driven deployment, meaning it can resolve aliases (like `@champion`) by querying MLflow to load the correct model version on demand.

It also features a streaming load protocol via the `/load` endpoint, which returns an NDJSON response showing real-time progress phases (`resolving` $\rightarrow$ `downloading` $\rightarrow$ `loading_model` $\rightarrow$ `ready`) during model loading.

## GRAPH

The `noted-serving` container is used to implement the **TF Serving wrapper**, which is similar to a standalone model serving client.

## FULL

The `noted-serving` container is a dedicated FastAPI service whose purpose is to turn a registered MLflow model into an HTTP endpoint for making predictions.

Its key responsibilities and capabilities include:

*   **Inference Serving:** It loads a registered MLflow model into memory and serves prediction requests over HTTP via the `/predict` endpoint.
*   **Dynamic Loading:** It dynamically loads any registered model from the MLflow Registry on demand.
*   **Schema Validation:** It validates incoming prediction requests against a PyDantic schema derived from the model's MLflow signature via the `/schema` endpoint.
*   **Health Monitoring:** It exposes a `/health` endpoint to report the currently loaded model's state, including its name, version, framework, and parameter count.
*   **Streaming Load Protocol:** It supports a streaming NDJSON response via the `/load` endpoint, allowing clients to see live progress phases (`resolving` $\rightarrow$ `downloading` $\rightarrow$ `loading_model` $\rightarrow$ `ready`) while the model is being loaded.
*   **Alias-Driven Deployment:** It resolves model aliases (like `@champion`) by querying MLflow on every load request, meaning clients interact with aliases rather than specific version numbers.

In essence, it acts as the runtime inference layer, while the surrounding noted platform handles the complexity of tracking, versioning, and deployment management.

# [factual] What does Hydra do in noted?


## VEC

Hydra is a configuration framework for Python applications that organizes experiment settings into grouped YAML files (e.g., `model`, `data`, `training`). In noted, its purpose is to manage **what** a run is configured to do, separating the configuration from the code that uses it.

Here is a summary of what Hydra does within the noted environment:

*   **Configuration Management:** It allows you to define settings (like epochs, dataset paths, or model types) in structured YAML files within a `config/` directory. Instead of hardcoding values in a notebook cell, you define them in a config file.
*   **Composition and Overrides:** Hydra uses a system of **defaults lists** and **overrides**. The system recursively merges YAML files based on the defaults list, and then applies fine-grained overrides (e.g., setting `training.epochs=10`) at runtime.
*   **Injection into Notebooks:** noted does not require you to import Hydra directly. Instead, it automatically **injects** the fully resolved configuration—a nested dictionary (`cfg`)—into the running notebook kernel. Any cell reading `cfg.training.epochs` is consuming this composed configuration.
*   **Reproducibility Primitive:** A critical feature is that noted computes a `sha256` hash of the **resolved configuration** at compose time and stores it as an MLflow tag (`noted.hydra_config_hash`). This hash serves as the proof-of-identity for the configuration, ensuring that two runs are byte-identical in their settings, regardless of how the underlying YAML templates were structured.

In short, Hydra acts as the gatekeeper for **"what was this run told to do?"**, while MLflow tracks **"what did this run actually do?"**.

## GRAPH

Hydra in noted is a configuration framework for Python applications. It functions as a configuration management tool whose composition rules are re-implemented by the platform's manager.

Key aspects of Hydra in noted include:

*   **Configuration Management:** It uses standard YAML files (Hydra configs) to manage configurations, following Hydra's config group conventions.
*   **Tracking and Reproducibility:** The platform uses Hydra to ensure reproducibility. A unique identifier, `__noted_hydra_hash__`, is generated (a sha256 hash) that uniquely identifies the composed configuration. This hash is also recorded as a tag (`noted.hydra_config_hash`) on MLflow runs, documenting exactly what the run was configured to do.
*   **Platform Integration:** Every notebook utilizing Hydra gets a **Composer panel** within noted, which manages these configurations.
*   **MLflow Integration:** There is a concrete implementation, `MlflowSource`, which allows Hydra to read configuration from a past run's archived bundle stored in MLflow.

## FULL

Hydra is a configuration framework for Python applications used in noted to organize and manage experiment settings using YAML files.

In the context of noted, its primary functions are:

*   **Configuration Management:** It separates *what* a run depends on (the resolved configuration) from *how* that configuration was assembled (the stack of YAML fragments and overrides). Configuration settings are grouped by concern (e.g., `model`, `data`, `training`) in a `config/` directory.
*   **Automatic Injection:** Instead of hardcoding values, settings are defined in config files, and noted automatically injects the fully resolved configuration into the running kernel as a variable named `cfg`. Notebook cells consume this configuration by reading attributes from `cfg` (e.g., `cfg.data.file`).
*   **Reproducibility Primitive:** noted computes a `sha256` hash of the **resolved configuration** at composition time. This hash (`__noted_hydra_hash__`) is stored as an MLflow tag (`noted.hydra_config_hash`), providing a unique, byte-identical proof-of-identity for the configuration used in a specific run.

**Key Concepts:**

*   **Templates vs. Config:** The YAML files on disk are treated as **templates**, not the final configuration. The actual configuration is produced when these templates are composed with a specific set of defaults and overrides.
*   **Composition:** Hydra allows for complex composition where groups can override each other, and the entire configuration can change based on CLI-style overrides applied at invocation time.
*   **Separation of Concerns:** noted uses Hydra to govern "what was this run told to do," while MLflow governs "what did this run actually do."

# [relational] How are MLflow and DVC connected in noted?


## VEC

MLflow and DVC are connected in noted through **automatic tagging** during execution, which allows the platform to create a unified view of the entire ML lifecycle.

Here is a breakdown of the connection:

1.  **Automatic Tagging:** When a notebook cell or DAG task executes within noted, the platform's auto-instrumentation automatically tags the resulting MLflow run with metadata from DVC. Specifically, the run is tagged with `dvc.data_hash`, which is the content hash of the dataset that was read during execution.
2.  **Unified Lineage:** This tagging allows the platform's Explorer to render a "run-to-file graph" by joining the MLflow tags with the actual `.dvc` files on disk.
3.  **Knowledge Graph:** More broadly, the platform's Knowledge Graph acts as a unified view over all subsystems. It scans MLflow (runs/models) and DVC (datasets/versions) to show relationships, such as linking a specific MLflow run to the exact data version it was trained on.

In essence, noted ensures that every MLflow run is fully contextualized with its corresponding data version from DVC, regardless of whether the run was triggered via the notebook's Run Manager or an Airflow pipeline.

## GRAPH

In noted, MLflow and DVC are both recognized as sources of truth for state within the platform's knowledge graph. While the provided context doesn't detail a direct, explicit integration mechanism between the two, it establishes that both **MLflow** and **DVC** are core components of the system's architecture, alongside tools like Airflow and MinIO.

The platform uses a **Knowledge Graph** to map how these components connect. For instance, the knowledge graph shows relationships between various terms, indicating that both MLflow and DVC are integral parts of the overall ML lifecycle managed by noted.

## FULL

MLflow and DVC are connected in noted through **automatic tagging** during execution, which allows the platform to create a unified view of the entire ML lifecycle.

Here is a breakdown of the connection:

1.  **Automatic Tagging:** When a notebook cell or DAG task executes within noted, the platform's **Auto-instrumentation** automatically wraps the process in an MLflow run. During this process, it automatically attaches metadata tags to the MLflow run.
2.  **Data Versioning Linkage:** Specifically, the platform attaches the `dvc.data_hash` tag to the MLflow run. This hash is derived from the DVC content hash of the dataset that the code reads.
3.  **Unified View:** This linkage means that any MLflow run—whether generated from a notebook or an Airflow pipeline—is fully tagged with its corresponding data version. The **Knowledge Graph** in noted uses this relationship to allow users to see, for example, a specific MLflow run and instantly see the exact dataset version (via its DVC hash) it was trained on.

In essence, noted uses the MLflow run as the central tracking point and enriches it with DVC metadata to provide end-to-end lineage.

# [relational] How does the Run Manager relate to MLflow?


## VEC

The Run Manager in noted acts as a wrapper around notebook executions to manage the MLflow lifecycle without requiring users to write boilerplate tracking code.

Here is a breakdown of the relationship:

*   **Automatic Lifecycle Management:** When you use the Run Manager panel to define and execute a set of cells, noted automatically handles the MLflow lifecycle by injecting `mlflow.start_run()` before the first selected cell and `mlflow.end_run()` after the last.
*   **Tracking Transparency:** Users only need to call standard MLflow logging functions (like `mlflow.log_metric()` or `mlflow.log_params()`) within their cells, and noted transparently surfaces these calls into the active MLflow run.
*   **Experiment Grouping:** All runs generated via the Run Manager (and also those from Airflow pipelines) land in the **same MLflow experiment**, which is automatically named after your project.
*   **Metadata Tagging:** The Run Manager ensures that runs are fully traceable by automatically tagging them with crucial metadata, including the DVC dataset hashes (`dvc.data_hash`), the Hydra configuration hash (`noted.hydra_config_hash`), the Git commit, and the project ID.

In essence, the Run Manager abstracts away the complexity of starting and stopping MLflow runs, allowing the notebook to focus purely on model training and logging, while MLflow serves as the centralized backend for recording parameters, metrics, and artifacts.

## GRAPH

The Run Manager in noted exclusively manages MLflow experiment tracking by wrapping cell sequences. It relates to MLflow because it is the mechanism through which experiment data is tracked and managed within the platform, which fetches this data from the MLflow API.

## FULL

The Run Manager in `noted` is the mechanism that wraps a notebook execution into an MLflow run, handling the entire MLflow lifecycle without requiring you to write boilerplate code like `mlflow.start_run()` or `mlflow.end_run()` in your cells.

Here is a breakdown of its relationship with MLflow:

*   **Automatic Tracking:** When you use the Run Manager panel to define and execute a run, `noted` silently injects the necessary MLflow context. Your cells can then call standard MLflow logging functions (like `mlflow.log_metric` or `mlflow.log_params`) as if they were running inside an active run.
*   **Experiment Grouping:** All runs generated via the Run Manager (in a notebook) and runs generated via Airflow pipelines (DAGs) land in the **same MLflow experiment**, which is automatically named after your project.
*   **Metadata Tagging:** The Run Manager automatically tags the resulting MLflow run with critical lineage information, including the DVC dataset hashes (`dvc.data_hash`), the Hydra configuration hash (`noted.hydra_config_hash`), the Git commit, and the project ID.
*   **Design Choice:** This notebook-centric tracking is a deliberate design choice to keep ad-hoc exploration separate from formal experiment history; cells run via the notebook's "Run All" button do not produce tracked runs.

In summary, the **Run Manager is the interface that manages the MLflow run lifecycle** for notebook code, while **MLflow is the underlying tracking backend** that records the parameters, metrics, and artifacts generated by that run.

# [summary] Summarize how noted handles experiment tracking.


## VEC

noted handles experiment tracking using MLflow in several integrated ways, depending on the mode selected for the project:

1.  **Automatic Tracking (Recommended Mode):**
    *   When using the **Run Manager Mode**, noted automatically wraps a selected sequence of notebook cells as a single MLflow experiment run.
    *   It transparently handles the `start_run()` and `end_run()` calls.
    *   It detects common ML frameworks (like PyTorch, TensorFlow, etc.) and activates framework-specific auto-logging.
    *   It automatically logs lineage information, including **DVC dataset hashes** and **Hydra configuration hashes**.
    *   All runs from a project are automatically grouped into an experiment named after the **project name**.

2.  **Zero-Code Tracking (Default/Transparent):**
    *   For runs created via the Run Manager, noted automatically registers the run in MLflow without requiring the user to write any boilerplate code (like `mlflow.start_run()`).

3.  **Explicit Mode (Advanced Control):**
    *   Users can choose to write MLflow API calls directly in their notebook cells (e.g., `mlflow.log_metric()`). In this mode, noted injects environment variables and run tags (project ID, data version hash, Hydra config hash) but does not modify the user's code.

In essence, noted acts as a unified cockpit that wraps standard ML tools—like MLflow—to provide an integrated, self-hosted, and traceable ML lifecycle experience without forcing users to context-switch between multiple tools.

## GRAPH

noted handles experiment tracking transparently through **AUTO-INSTRUMENTATION**.

Key aspects of this process include:

*   **Automatic Tracking:** You do not need to write explicit MLflow tracking code (like `mlflow.start_run()`) in your notebook cells; tracking happens automatically.
*   **Run Management:** MLflow runs are managed by the **Run Manager** UI, which wraps cell sequences to manage the tracking process.
*   **Data Sources:** The platform integrates with various tools and systems, including **MLflow** for storing artifacts, **DVC** for data versioning, and **Airflow** for pipeline state.
*   **Contextual Awareness:** The system maintains a **Knowledge Graph** to show how all components—such as MLflow runs, configurations (managed by **Hydra**), and data versions—connect within a project.

## FULL

noted handles experiment tracking through several integrated, automated, and explicit modes, ensuring full traceability without requiring users to write boilerplate code.

Here is a summary of how it works:

*   **Automatic Tracking (Default):** When a run is created via the **Run Manager**, noted automatically registers it in MLflow. It handles the underlying `mlflow.start_run()`, logs parameters, and stores artifacts transparently. By default, all runs from a specific project are automatically grouped into an MLflow **experiment** named after the project.
*   **Run Manager Mode (Recommended):** This mode provides explicit tracking. Users select specific notebook cells to include in a run, and the backend wraps this sequence with automatic `start_run`/`end_run`. It automatically detects common ML frameworks (like PyTorch, TensorFlow, etc.) and activates framework-specific auto-logging. This mode also automatically logs **DVC dataset hashes** and **Hydra configuration hashes**.
*   **Zero-Code Integration:** The platform unifies MLflow tracking with other components:
    *   **Project Name:** Used as the MLflow experiment name.
    *   **Data Versioning (DVC):** Data operations trigger `dvc add` and commit on the backend, and the resulting hashes are logged.
    *   **Configuration (Hydra):** The resolved configuration hash is logged automatically.
*   **Explicit Mode (Advanced):** For experienced users, noted supports an explicit mode where users can write standard MLflow API calls directly into cells (`mlflow.log_metric()`, etc.). In this mode, noted still injects crucial tags like the project ID, data version hash, and Hydra config hash, even if the user writes their own tracking code.
*   **AI-Assisted Mode (Future):** A planned feature where an AI agent analyzes code to suggest what metrics, parameters, and artifacts should be tracked.

In essence, noted acts as a "cockpit" that unifies standard tools like MLflow, DVC, and Hydra behind a single interface, handling the complex instrumentation automatically in most workflows.

# [comparative] How does the notebook execution path differ from the Airflow DAG path?


## VEC

The notebook execution path and the Airflow DAG path differ primarily in *how* they initiate and manage the MLflow tracking, though both ultimately land in the same MLflow experiment with consistent tagging.

Here is a breakdown of the differences:

*   **Notebook Path (Run Manager):**
    *   **Execution:** The notebook uses the **Run Manager** panel to define groups of cells that execute within an MLflow run.
    *   **Tracking Mechanism:** *noted* automatically injects `mlflow.start_run()` before the first tagged cell and `mlflow.end_run()` after the last.
    *   **Ad-hoc Exploration:** Cells executed via the notebook's **Run All** button *do not* produce tracked runs, which is a design choice to prevent ad-hoc exploration from polluting the experiment history.
    *   **Code Style:** Notebook cells are designed to be self-documenting, often containing the full call to a function (e.g., `Report(...).run(...)`) to ensure readability in isolation.

*   **Airflow DAG Path (DAG Execution):**
    *   **Execution:** The training task calls MLflow directly within the pipeline code (e.g., in `src/training/pipeline.py`).
    *   **Tracking Mechanism:** The DAG explicitly logs metrics (like `test_mae_degC`, `test_rmse_degC`), parameters (all Hydra config values), and artifacts (the trained model and the `hydra/` bundle) through the pipeline code.
    *   **Code Style:** The DAG relies on reusable, modular source code located in the `src/` directory, which is shared with the notebooks.

**Key Similarities:**

Despite the different execution mechanisms, both paths ensure high compatibility:
*   **Shared Experiment:** Both notebook runs and DAG runs appear side-by-side in the same MLflow experiment, which is named after the project.
*   **Consistent Lineage:** Both paths tag runs identically (`dvc.data_hash`, `noted.hydra_config_hash`, `noted.git_commit`, `noted.project_id`), ensuring they are fully compatible with the Time Machine and Registry views.
*   **Configuration Consistency:** The DAG is parameterized using Airflow DAG params that map directly to the Hydra config groups, ensuring the same Hydra YAML configs consumed by notebooks are used in automated runs.

## GRAPH

The notebook execution path and the Airflow DAG path serve different roles in the overall ML workflow managed by noted:

*   **Airflow DAGs:** These are Directed Acyclic Graphs that define the overall pipeline structure using standard Python and Airflow operators. They represent the high-level orchestration of the workflow.
*   **Notebook Execution Path:** This path is managed by the **Run Manager**, which specifically wraps sequences of notebook cells to manage **MLflow experiment tracking**.

In essence, Airflow manages *when* and *how* the steps run as a pipeline, while the notebook execution path, when managed by the Run Manager, focuses on *tracking* the execution details (like MLflow artifacts) of the code within the notebook cells.

## FULL

The execution paths for notebooks and Airflow DAGs differ primarily in how they initiate and manage MLflow tracking, although both ultimately contribute to the same MLflow experiment.

Here is a breakdown of the differences:

*   **Notebook Execution Path (Run Manager):**
    *   **Tracking Mechanism:** Tracking is managed by the **Run Manager** panel. *noted* automatically injects `mlflow.start_run()` before the first tagged cell and `mlflow.end_run()` after the last.
    *   **Execution Trigger:** A run is created when cells are executed via the Run Manager. **Crucially, running cells via the notebook's "Run All" button does not produce a tracked MLflow run.**
    *   **Logging:** The Run Manager is responsible for logging dataset DVC hashes and configuration hashes.

*   **Airflow DAG Path (DAG Execution):**
    *   **Tracking Mechanism:** The training task calls MLflow **directly** within the pipeline code (e.g., `src/training/pipeline.py`).
    *   **Logging:** The DAG explicitly logs metrics (like `test_mae_degC`, `test_rmse_degC`, `test_r2`, and per-epoch `loss`), parameters (all Hydra config values), and artifacts (the trained model and the `hydra/` bundle).
    *   **Execution Trigger:** The pipeline is triggered via the Airflow UI or API, running tasks in an Airflow worker context.

**Key Similarities:**

Despite these differences, both paths are designed to be compatible:
1.  **Shared Logic:** Both paths utilize the same reusable code from `src/` modules (e.g., `src/training/pipeline.py`), ensuring that the core logic is consistent.
2.  **Experiment Consistency:** Both the notebook runs and the DAG runs land in the **same MLflow experiment** (named after the project).
3.  **Tagging:** Both modes tag runs identically (`dvc.data_hash`, `noted.hydra_config_hash`, `noted.git_commit`, `noted.project_id`), ensuring full compatibility with features like Time Machine and the Model Registry.

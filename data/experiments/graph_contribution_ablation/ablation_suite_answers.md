
# [factual] What is the noted-serving container for?


## VEC

The `noted-serving` container is a dedicated FastAPI service whose purpose is to turn a registered MLflow model into an HTTP endpoint for making predictions.

Its core responsibilities include:
*   **Loading the Model:** Dynamically loading a registered MLflow model into memory on demand.
*   **Serving Predictions:** Answering prediction requests via an HTTP endpoint (`/predict`).
*   **Validation:** Validating incoming requests against a schema derived from the model's MLflow signature.
*   **Health Monitoring:** Providing an endpoint (`/health`) to report the currently loaded model's state and metadata.

Key features of the serving layer include:
*   **Alias-Driven Deployment:** It resolves aliases (like `@champion`) by querying MLflow on every load request, meaning clients interact with aliases rather than specific version numbers.
*   **Streaming Load Protocol:** It supports a streaming NDJSON response via the `/load` endpoint, which allows clients to see live progress phases (`resolving`, `downloading`, `loading_model`, `ready`) while the model is loading.
*   **Multi-framework Support:** It supports various frameworks, including TensorFlow, PyTorch, scikit-learn, XGBoost, and LightGBM.

In summary, it acts as the inference engine, handling the loading, validation, and execution of models registered in the MLflow Registry over HTTP.

## GRAPH

The `noted-serving` container runs the FastAPI backend, which serves both the vanilla ES6 frontend and the FastAPI backend for the noted platform.

## FULL

The `noted-serving` container is a dedicated FastAPI service whose purpose is to turn a registered MLflow model into an HTTP endpoint for inference.

Its core responsibilities include:
*   **Loading the Model:** Dynamically loading any registered MLflow model into memory on demand.
*   **Prediction Serving:** Answering prediction requests via an HTTP endpoint (`/predict`).
*   **Schema Validation:** Validating incoming requests against a PyDantic schema derived from the model's MLflow signature.
*   **Health Monitoring:** Providing an endpoint (`/health`) to report the currently loaded model's state and metadata.

It supports features like streaming model load progress (via an NDJSON response on the `/load` endpoint) and resolving model aliases (like `@champion`) by querying MLflow.

# [factual] What does Hydra do in noted?


## VEC

Hydra is a configuration framework used in noted to manage and organize experiment settings using YAML files. Instead of hardcoding values (like `epochs = 50`) directly into a notebook, you define them in configuration files.

Here is a breakdown of its role and key concepts within noted:

*   **Configuration as Templates:** The YAML files in the `config/` directory are considered **templates**, not the final configuration itself. A specific run is defined by which options are selected from each configuration group and any per-parameter overrides.
*   **Automatic Injection:** noted automatically composes these templates based on the selections and overrides and injects the resulting, resolved configuration into the running kernel as a variable named `cfg`. This allows you to access settings in a notebook cell via `cfg.training.epochs`, for example.
*   **Reproducibility:** Hydra enables side-by-side comparison of experiments that used different configurations and provides full lineage tracking. noted computes a `sha256` hash of the *resolved* configuration at compose time and stores it as an MLflow tag (`noted.hydra_config_hash`), which serves as the proof-of-identity for that configuration.
*   **Separation of Concerns:** Hydra's primary function is to manage *what* a run is configured to do. In the noted ecosystem, this is distinct from MLflow, which tracks *what* the run actually did.

In essence, Hydra acts as the gatekeeper for defining the inputs and settings of an ML run within the noted platform.

## GRAPH

Hydra is a component within the noted platform that manages configurations. The knowledge graph context indicates the existence of entities like `concept:hydra config hash` and `term:hydra`, suggesting its role is related to configuration management within the platform's structure.

## FULL

Hydra is a configuration framework used in noted to organize experiment settings using YAML files, separating *what* a run depends on (the resolved configuration) from *how* that configuration was assembled.

Here is a summary of its role and mechanics in the noted platform:

*   **Configuration Management:** Instead of hardcoding values (like `epochs = 50`) in a notebook, you define them in configuration files grouped by concern (e.g., `model`, `data`, `training`).
*   **Injection into Kernel:** Noted automatically injects the resolved configuration into the running notebook kernel as a variable named `cfg`. This allows notebook cells to access settings like `cfg.training.epochs`.
*   **Composition and Templates:** The YAML files on disk are treated as **templates**, not the final configuration. Hydra composes these templates based on a `defaults` list and applies fine-grained overrides. This means two runs reading the same template files can produce different final configurations.
*   **Reproducibility Primitive:** To ensure reproducibility, noted computes a `sha256` hash of the **resolved configuration** at compose time and stores it as an MLflow tag (`noted.hydra_config_hash`). This hash serves as the proof-of-identity for the configuration used in a specific run.
*   **Platform Role:** In the context of the entire MLOps lifecycle within noted, Hydra is the gatekeeper for **"what was this run told to do?"**, while MLflow tracks **"what did this run actually do?"**.

Hydra does not handle orchestration, tracking, or versioning; it solely manages configuration.

# [relational] How are MLflow and DVC connected in noted?


## VEC

MLflow and DVC are connected in noted through automatic instrumentation and metadata tagging, creating a unified view of the ML lifecycle.

Here is a summary of how they interact:

*   **Automatic Tagging:** When a notebook cell or DAG task executes, noted's auto-instrumentation automatically tags the resulting MLflow run with the DVC content hash (`dvc.data_hash`) of the dataset used.
*   **Lineage Visualization:** This connection allows the Explorer's DVC panel to render a "run-to-file graph" by joining the MLflow run tags with the actual `.dvc` files on disk.
*   **Unified View:** The platform's Knowledge Graph acts as a unified view over all subsystems (including MLflow and DVC), allowing a user to see, for example, a specific MLflow run's associated training data version from DVC on a single screen.

In essence, noted ensures that every MLflow run is fully tagged with the versioned data it used from DVC, making the entire process traceable.

## GRAPH

MLflow and DVC are connected within noted as part of a unified, integrated MLOps platform that scans and manages various data sources.

Here is a breakdown of the connection:

*   **Unified Entity Discovery:** The Knowledge Graph within noted scans all managed entities, including **MLflow** and **DVC**, presenting them as interconnected nodes. This allows the platform to see the entire lifecycle of a project, linking data versions to model runs.
*   **Project Structure:** A standard noted project structure includes a `data/` directory where **DVC-tracked datasets** live. The **Run Manager** wraps cell sequences into an **MLflow** experiment run.
*   **Configuration Linkage:** When an MLflow run is created via the Run Manager, it automatically receives a `hydra/` artifact subtree containing the full configuration (`config.yaml`) that the run used. This configuration is managed by **Hydra**, which dictates how the experiment is set up.
*   **Holistic View:** The platform's ability to track entities across **MLflow**, **DVC**, **Hydra**, and the file system means that a user can trace a model's performance (tracked in MLflow) back to the exact data snapshot (tracked in DVC) and the specific configuration (managed by Hydra) used to generate it.

## FULL

MLflow and DVC are connected in noted through **automatic tagging and a unified view** provided by the platform's architecture.

Here is a breakdown of the connection:

1.  **Automatic Tagging:** When a notebook executes a training cell (especially when using the Run Manager), noted's auto-instrumentation automatically tags the resulting MLflow run with the DVC content hash (`dvc.data_hash`). This hash corresponds to the specific version of the dataset used for that run.
    *   The platform achieves this by joining MLflow tags with the `.dvc` files on disk, allowing the Explorer's DVC panel to render a run-to-file graph.

2.  **Unified View (Knowledge Graph):** The Knowledge Graph acts as the connective tissue, scanning all subsystems (including MLflow and DVC) to present a single, unified view. This allows a user to see, for example, a specific MLflow run and instantly see the exact dataset version (tracked by DVC) that was used to generate it.

In summary, DVC tracks the **data versions** (bytes), and MLflow tracks the **experiment metadata** (metrics, parameters, artifacts). Noted links these two by injecting the DVC hash into the MLflow run metadata automatically.

# [relational] How does the Run Manager relate to MLflow?


## VEC

The Run Manager in `noted` acts as a wrapper that manages the lifecycle of an MLflow run when executing cells within a notebook.

Here is a breakdown of how it relates to MLflow:

*   **Automatic Run Lifecycle Management:** The Run Manager panel allows users to select specific cells to execute within a defined MLflow run. `noted` automatically handles the boilerplate by injecting `mlflow.start_run()` before the first selected cell and `mlflow.end_run()` after the last. This means users do not need to write manual tracking code in their cells.
*   **Tracking and Logging:** When running via the Run Manager, `noted` transparently handles logging parameters, metrics, and artifacts to MLflow. The notebook cells themselves only need to call functions like `mlflow.log_param()` or `mlflow.log_metric()`, as the run context is already active.
*   **Experiment Grouping:** All runs generated through the Run Manager (and also those from Airflow pipelines) are placed into the **same MLflow experiment**, which is named after the project.
*   **Metadata Tagging:** The Run Manager ensures that runs are fully compatible across different execution paths by tagging them identically with metadata such as `dvc.data_hash`, `noted.hydra_config_hash`, `noted.git_commit`, and `noted.project_id`.
*   **Contrast with "Run All":** It is important to note that running all cells in a notebook via the standard "Run All" button does **not** produce a tracked MLflow run; this is a deliberate design choice to keep ad-hoc exploration separate from the formal experiment history.

In summary, the Run Manager abstracts away the complexity of MLflow tracking, allowing users to focus on model logic while `noted` manages the connection to the MLflow backend for experiment tracking.

## GRAPH

The Run Manager is a component within noted's MLOps service mesh, which handles various functions like experiment tracking, artefact versioning, and pipeline orchestration. MLflow is explicitly mentioned as one of the sources of truth for experiment data within this service mesh. Therefore, the Run Manager interacts with MLflow to manage and track experiment data.

## FULL

The Run Manager in noted is the mechanism that wraps a notebook execution into an MLflow run, providing zero-configuration MLflow connectivity.

Here is how the two relate:

*   **Run Manager's Role:** The Run Manager panel allows users to define named groups of cells that will execute within a single MLflow run. It handles the entire MLflow lifecycle transparently:
    *   It automatically injects `mlflow.start_run()` before the first selected cell and `mlflow.end_run()` after the last.
    *   It automatically logs metadata such as the dataset DVC hashes, the Hydra configuration hash, the Git commit, and the project ID onto the run.
    *   It allows users to log parameters, metrics, and models using standard MLflow calls (`mlflow.log_param`, `mlflow.log_metric`, etc.) without needing to write boilerplate tracking code.
*   **MLflow's Role:** MLflow is the underlying tracking backend that records all the data generated during the run—the parameters used, the resulting metrics, and the saved artifacts (like the trained model).
*   **Integration:** Both notebook runs initiated via the Run Manager and runs initiated via Airflow pipelines land in the **same MLflow experiment**, which is named after the project. This ensures that all tracking data is centralized and compatible with features like the Time Machine and the Registry view.

In summary, the **Run Manager is the user interface and execution wrapper** that manages the MLflow lifecycle for notebook cells, while **MLflow is the backend system** that records and stores all the resulting experiment data.

# [multi_hop] How does data versioning flow from DVC through to a deployed model?


## VEC

Data versioning flows through a tightly integrated system where **DVC (Data Version Control)** manages the data state, and **MLflow** tracks the resulting model's lineage.

Here is the flow based on the platform's architecture:

1.  **Data Versioning (DVC):**
    *   Data is versioned using DVC, which acts as a thin layer over Git to handle large binary files. Instead of committing the large data files directly, DVC commits small **pointer files** (containing content hashes like MD5) into Git.
    *   The actual data bytes are stored in a remote object store, such as **MinIO** (which is S3-compatible). This storage is **content-addressed**, meaning the same data bytes always have the same hash, ensuring deduplication.
    *   A specific dataset version is pinned to a Git commit via the `.dvc` files.

2.  **Derivation and Provenance:**
    *   Data transformations (e.g., creating a subset from a full dataset) are managed by committed scripts (e.g., `filter_year.py`). The resulting derived dataset is then added to DVC.
    *   **Reproducibility is guaranteed** because every training run is explicitly tagged with the **DVC data hash** of the exact dataset version that was used to produce it.

3.  **Experiment Tracking (MLflow):**
    *   When a model is trained using a specific data version, the entire process is tracked by MLflow.
    *   The platform ensures traceability by logging this DVC data hash alongside other critical metadata, such as the **Hydra configuration hash** and the **Git commit hash** of the source code.

4.  **Deployment:**
    *   The final, trained model, along with its associated metadata (including the data hash), is managed within the MLflow Model Registry.
    *   When this model is promoted for deployment, the entire lineage—from the specific data version (DVC hash) to the exact configuration (Hydra hash) and code state (Git commit)—is maintained and traceable within the platform's unified view.

In summary, **DVC pins the data to a hash $\rightarrow$ This hash is logged in MLflow during training $\rightarrow$ MLflow tracks the resulting model $\rightarrow$ The model is deployed, carrying the full, traceable lineage.**

## GRAPH

I do not have the necessary information from the tool result to answer your question about how data versioning flows from DVC through to a deployed model. The provided tool result only contains a structure for how to synthesize an answer but lacks the actual content from the documentation chunks or the knowledge graph context.

## FULL

Data versioning flows from **DVC (Data Version Control)**, which acts as the source of truth for data, through to a deployed model by ensuring that every stage of the ML lifecycle is traceable back to an exact, immutable dataset version.

Here is the flow, based on the platform's architecture:

1.  **Data Versioning (DVC):**
    *   DVC tracks large binary files by committing small **pointer files** (containing content hashes like MD5) into Git. The actual data bytes are stored in a remote object store, such as **MinIO**.
    *   This content-addressed storage ensures that two datasets with identical bytes have the same hash, allowing for natural deduplication.
    *   A specific dataset version is pinned to a Git commit via the `.dvc` files.

2.  **Training and Experimentation:**
    *   During training, every experiment run is **tagged with the DVC data hash** of the exact dataset version used to produce it.
    *   The platform ensures reproducibility by logging not only the data hash but also the **hashed Hydra configuration** and the full configuration bundle for that run in **MLflow**.
    *   The derivation script (the "recipe" for creating a derived dataset) is committed to Git as source code, providing readable provenance.

3.  **Model Deployment and Traceability:**
    *   The final model artifact, tracked in MLflow, is linked to the specific DVC data hash and Git commit that produced it.
    *   The platform enforces this traceability, allowing reviewers to trace any model back to its exact input data version without needing to read source code.

In summary, **DVC manages the data immutability**, **Git manages the code and metadata**, and **MLflow/noted provides the unified interface** to link the specific data version (DVC hash) to the resulting trained model and configuration.

# [summary] Summarize how noted handles experiment tracking.


## VEC

noted handles experiment tracking by integrating MLflow transparently into the notebook workflow, offering several modes of operation:

*   **Automatic Tracking (Recommended for Exploration):** When using the **Run Manager Mode**, noted automatically wraps a selected sequence of notebook cells to create an MLflow run. This mode handles the `start_run`/`end_run` lifecycle, detects common ML frameworks (like PyTorch, TensorFlow, etc.) to activate automatic logging, and streams metrics to the UI in real-time. Furthermore, it automatically logs metadata such as DVC dataset hashes and Hydra configuration hashes.
*   **Automatic Tracking (General):** For any run created via the Run Manager, noted automatically registers it in MLflow, transparently managing the boilerplate like `mlflow.start_run()`, parameter logging, and artifact storage. Runs are grouped into experiments, using the project name as the experiment name.
*   **Explicit Mode (For Control):** Users can opt for **Explicit Mode**, where they write the MLflow API calls directly in the notebook cells (e.g., `mlflow.log_metric()`). In this mode, noted injects run tags (like project ID, data version hash, and Hydra config hash) but does not alter the user's code.

In essence, noted acts as a cockpit that unifies the ML lifecycle, allowing users to leverage standard MLflow runs while abstracting away the need to write manual tracking code for most workflows.

## GRAPH

noted handles experiment tracking as part of its integrated MLOps service mesh. Specifically, **MLflow** is cited as one of the sources of truth for experiment data within the platform.

The platform is designed as a browser-hosted ML engineering workbench that is "wired to an MLOps service mesh," which encompasses experiment tracking, artifact versioning, pipeline orchestration, drift monitoring, and object storage. This tracking is handled transparently by the platform's architecture, meaning users do not need to write manual tracking code in their notebooks.

## FULL

noted handles experiment tracking through several integrated, transparent mechanisms, depending on the mode selected for a project:

**Automatic and Transparent Tracking (Default/Run Manager Mode):**
*   **Automatic Registration:** Every run created via the Run Manager is automatically registered in MLflow, and noted handles the underlying boilerplate like `mlflow.start_run()`, parameter logging, and artifact storage without requiring users to write explicit MLflow code.
*   **Project Grouping:** All runs from a single project are automatically grouped into the same MLflow experiment, using the project name as the experiment name.
*   **Run Manager Mode:** When using the Run Manager, users define runs by selecting notebook cells. The backend wraps this sequence with automatic tracking, detects common ML frameworks (like PyTorch, TensorFlow, etc.), and activates framework-specific auto-logging. This mode also automatically logs DVC dataset hashes and Hydra configuration hashes.

**Explicit Control (Explicit Mode):**
*   For advanced users, noted supports an **Explicit Mode** where users can write standard MLflow API calls directly into notebook cells (e.g., `mlflow.log_metric()`). In this mode, noted injects run tags (like project ID, data version hash, and Hydra config hash) but does not modify the user's code.

**Key Features Integrated with Tracking:**
*   **Live Metrics:** Metrics stream to the UI in real-time when using the Run Manager Mode.
*   **Integration:** The platform unifies this tracking with other MLOps components, such as data versioning via DVC and configuration management via Hydra, all accessible through a single interface.

# [comparative] How does the notebook execution path differ from the Airflow DAG path?


## VEC

The notebook execution path and the Airflow DAG path differ primarily in **how the MLflow run is initiated and what specific actions are performed**, although both paths ultimately land in the same MLflow experiment with identical tagging for compatibility.

Here is a breakdown of the differences based on the platform's design:

### Notebook Execution Path (Run Manager)
*   **Run Initiation:** The Run Manager panel allows users to define named groups of cells that execute within an MLflow run.
*   **Tracking Mechanism:** `noted` automatically injects `mlflow.start_run()` before the first tagged cell and `mlflow.end_run()` after the last.
*   **Ad-hoc Exploration:** Cells executed via the notebook's **Run All** button *do not* produce tracked runs, which is a deliberate design choice to prevent ad-hoc exploration from polluting the experiment history.
*   **Logging:** The Run Manager is responsible for logging dataset DVC hashes and configuration hashes on the run.

### Airflow DAG Path (DAG Execution)
*   **Run Initiation:** The training task calls MLflow directly within the pipeline code (e.g., in `src/training/pipeline.py`).
*   **Logging:** The DAG explicitly logs metrics (like `test_mae_degC`, `test_rmse_degC`, `test_r2`, and per-epoch `loss`/`val_loss`), parameters (all Hydra config values plus specific values like `target_mean` and `target_std`), and artifacts (the trained model and the `hydra/` bundle).
*   **Orchestration:** The DAG defines a structured workflow (e.g., fork-join patterns) involving multiple tasks like data ingestion, preprocessing, quality checks (`evidently_quality`), training, and post-training steps like model promotion (`promote_model`) and drift monitoring (`evidently_drift`).

### Key Similarities (Ensuring Consistency)
Despite the differences in execution context, the platform ensures both paths are compatible:
*   **Shared Logic:** All pipeline logic resides in reusable `src/` modules shared between notebooks and Airflow DAGs, meaning changes to data processing or training logic propagate to both paths.
*   **Experiment Visibility:** Both notebook runs and DAG runs from the same project appear side-by-side in the MLflow Experiments tree.
*   **Tagging:** Both modes tag runs identically (`dvc.data_hash`, `noted.hydra_config_hash`, `noted.git_commit`, `noted.project_id`), ensuring full compatibility with the Time Machine and Registry views.
*   **Configuration:** The DAG is parameterized via Airflow DAG params that map directly onto the Hydra config groups, ensuring configuration consistency with what notebooks consume.

## GRAPH

The notebook execution path and the Airflow DAG path serve different roles within the noted platform's MLOps service mesh.

*   **Notebook Execution Path:** This path is centered around the interactive notebook editor, which runs on a polyglot runtime. It is where users perform iterative development, model training, and experimentation. This environment is wired into the MLOps service mesh, which handles tasks like experiment tracking (via MLflow), artifact versioning, and drift monitoring.
*   **Airflow DAG Path:** This path is dedicated to **pipeline orchestration**. Airflow DAGs are used to define and manage complex, scheduled, or triggered workflows that automate the end-to-end ML lifecycle, moving beyond the interactive nature of a single notebook run.

In essence, the notebook is for **interactive development and experimentation**, while the Airflow DAG is for **automated, production-grade workflow management and orchestration**.

## FULL

The notebook execution path and the Airflow DAG path both contribute to the same MLflow experiment within the `noted` platform, but they differ significantly in how they are triggered, managed, and what they are designed for:

### Notebook Execution Path (Run Manager)
*   **Trigger/Management:** Runs are managed via the **Run Manager** panel in the notebook environment.
*   **Execution Behavior:** The platform automatically injects `mlflow.start_run()` before the first tagged cell and `mlflow.end_run()` after the last.
*   **Scope:** This path is designed for **ad-hoc exploration**.
*   **Limitation:** Cells executed using the notebook's **Run All** button do **not** produce tracked MLflow runs, which is a deliberate design choice to prevent exploration from polluting the experiment history.

### Airflow DAG Path (DAG Path)
*   **Trigger/Management:** Runs are orchestrated by an Airflow DAG (e.g., `demand_forecast_train`).
*   **Execution Behavior:** The training task calls MLflow directly through source code (e.g., `src/training/pipeline.py`) to log metrics, parameters (including all Hydra config values), and artifacts.
*   **Scope:** This path is designed for **automated, scheduled, and reproducible production workflows**.
*   **Code Structure:** The DAG relies on shared, reusable logic residing in `src/` modules, ensuring that the same data processing and training functions are called whether the code is run in a notebook or an Airflow worker.

### Key Similarities and Convergence
Despite the different paths, both execution modes ensure high compatibility:
*   **Shared Experiment:** Both types of runs land in the **same MLflow experiment** (named after the project).
*   **Identical Tagging:** Both notebook runs and DAG runs are tagged identically (`dvc.data_hash`, `noted.hydra_config_hash`, `noted.git_commit`, `noted.project_id`), making them fully compatible with the Time Machine and Registry views.
*   **Configuration Consistency:** The DAG is parameterized using Airflow DAG params that map directly to the Hydra config groups, ensuring that the configuration consumed by the DAG matches what notebooks consume.

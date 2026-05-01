# Tutorial 2 - Video Demo Script

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Video Demo Script                  |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-03-26                         |

---

## 1. Production Notes

### 1.1 Recording Setup

- **Screen resolution:** 1920x1080 (Full HD)
- **Browser:** Chrome, zoomed to 100%, no bookmarks bar, clean URL bar
- **noted URL:** `http://localhost:8123`
- **Recording tool:** OBS Studio or similar (screen + audio)
- **Background music:** Instrumental, low volume, motivational/tech (add in post-production)
- **Voice-over:** Record separately for each scene using a clear microphone, mix in post-production

### 1.2 Pre-recording Checklist

Before recording any scene:

1. Docker Compose stack fully started (all containers green)
2. Jena Weather project mounted and visible in noted
3. Demo notebook saved and ready
4. Airflow DAG synced and visible in Pipelines
5. Browser cache cleared (no stale state)
6. No other applications sending notifications
7. Terminal maximized when showing commands
8. noted sidebar expanded, center pane maximized

### 1.3 Scene Shooting Order

Scenes can be recorded independently and joined in post-production. Recommended order:

1. Scene 1 (Infrastructure) - record first, sets context
2. Scene 3 (Notebook) - record second, this creates MLflow data for later scenes
3. Scene 4 (Airflow) - record third, needs working pipeline
4. Scene 2 (Hydra) - can be recorded anytime (standalone)
5. Scene 5 (Snapshot) - needs completed runs from Scene 3 or 4
6. Scene 6 (Registry + Serving) - needs registered model from Scene 5 or notebook
7. Scene 7 (Closing) - record last

### 1.4 Timing Targets

| Scene | Target Duration | Content |
|---|---|---|
| Title card | 10s | Title + group info |
| Scene 1: Infrastructure | 1:30 | Docker Compose + UI tour |
| Scene 2: Hydra Configuration | 2:00 | Config groups, compose, hash |
| Scene 3: Live Notebook | 3:30 | Data loading, training, live metrics |
| Scene 4: Airflow Pipeline | 3:00 | DAG trigger, monitoring, completion |
| Scene 5: Snapshot | 2:00 | Leaderboard, snapshot creation |
| Scene 6: Registry + Serving | 2:30 | Register model, alias, Try It |
| Scene 7: Closing | 0:30 | Summary slide |
| **Total** | **~15:00** | |

---

## 2. Title Card

### Slide Content

```
noted - Integrated MLOps Platform
Configuration Management and Pipeline Orchestration

Project: Weather Forecasting with Jena Climate Dataset
```

### Voice-over

> "Welcome to our demonstration of noted, an integrated MLOps platform.
> Our project is weather temperature forecasting
> using the Jena Climate dataset. We built noted, an integrated MLOps
> platform that unifies notebooks, data versioning, experiment tracking,
> configuration management, pipeline orchestration, and model serving
> in a single web interface. In this video, we will demonstrate the
> complete MLOps lifecycle using our platform."

---

## 3. Scene 1: Infrastructure Launch

### Intro Slide

```
Scene 1: Infrastructure

What you will see:
- Docker Compose launching the full MLOps stack (12+ containers)
- The noted web interface with VS Code-like layout
- Quick tour of the workspace: projects, data, experiments, pipelines, models

Tools: Docker Compose, FastAPI, MLflow, Apache Airflow, MinIO, PostgreSQL
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 1.1 | Open terminal, navigate to `noted/services/` | Terminal with prompt | 5s |
| 1.2 | Run `docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f ../data/docker-compose.mounts.yml up -d --build` | Containers starting (noted, mlflow, airflow x5, minio, postgres, redis, serving, graph, evidently) | 15s |
| 1.3 | Run `docker compose ps` to show all containers running | Table of 12+ containers with STATUS "Up" | 10s |
| 1.4 | Open browser to `http://localhost:8123` | noted loads with the workspace tree on the left | 5s |
| 1.5 | Click through icon bar sections: Projects, Experiments, Pipelines, Models | Each section highlights in the sidebar, showing the tree contents | 15s |
| 1.6 | Expand the Jena Weather mount in the tree | Show project structure: config/, dags/, data/, notebooks/, src/ | 10s |
| 1.7 | Click on the Data section in the icon bar | Show DVC-tracked files with version badges and sync icons | 10s |
| 1.8 | Open MLflow iframe tab from icon bar | MLflow UI loads inside noted (no context switching) | 10s |
| 1.9 | Open Airflow iframe tab from icon bar | Airflow UI loads inside noted (no context switching) | 10s |

### Voice-over

> [1.1-1.3] "We start by launching our infrastructure with Docker Compose.
> A single command brings up over 12 containers: the noted server, MLflow for
> experiment tracking, five Airflow services for pipeline orchestration, MinIO
> for object storage, PostgreSQL for metadata, model serving, knowledge graph,
> and Evidently for data monitoring."

> [1.4-1.5] "This is noted's interface. It follows a VS Code-like layout with
> an icon bar on the left, a collapsible workspace tree, and a tabbed center pane.
> The workspace tree organizes everything: projects, experiments, pipelines, models,
> data, virtual environments, and storage - all in one place."

> [1.6-1.7] "Here is our Jena Weather project. It contains the standard MLOps
> structure: Hydra configuration files, Airflow DAGs, DVC-tracked data, notebooks,
> and modular source code. The data section shows our tracked dataset with DVC
> version badges and sync status indicators."

> [1.8-1.9] "For advanced use, the original MLflow and Airflow UIs are accessible
> as tabs inside noted. But as we will see, you rarely need them because noted
> provides purpose-built views for every operation."

---

## 4. Scene 2: Hydra Configuration Management

### Intro Slide

```
Scene 2: Configuration Management with Hydra

What you will see:
- Hierarchical YAML configuration with model groups (GRU, Linear)
- Visual config editor: switch architectures via dropdown
- Config composition with override parameters
- SHA-256 config hash for reproducibility tracking

Requirement: "Integrate Hydra to eliminate hardcoded parameters, managing
API configurations, file paths, and model hyperparameters via hierarchical
YAML files."
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 2.1 | Click the Config section in the workspace tree for Jena Weather | Config tree expands showing `model/` and `data/` groups | 5s |
| 2.2 | Expand `model/` group | Shows `gru` (with star = default) and `linear` options | 5s |
| 2.3 | Click on `gru` option | Detail panel shows the GRU config YAML: units1: 128, units2: 64, dropout: 0.2, type: GRU | 10s |
| 2.4 | Click on `linear` option | Detail panel shows the Linear config YAML: type: Linear | 5s |
| 2.5 | Click the "Configuration" node, then click "Compose Config" in the detail panel | Compose Configuration panel opens with model and data group dropdowns, resolved YAML shown automatically | 5s |
| 2.6 | Show the resolved YAML preview | Full composed config visible: data paths, features, model hyperparameters, training settings | 10s |
| 2.7 | Point out the SHA-256 config hash at the bottom | Hash displayed (e.g., `a3f7b2c1...`) | 5s |
| 2.8 | Switch the model dropdown from GRU to Linear | Config YAML and hash update automatically | 10s |
| 2.9 | Override a parameter (e.g., change epochs from 30 to 10) | Override field shows the changed value, YAML updates | 10s |
| 2.10 | Switch back to GRU, show config selector in notebook bar | Dropdown in notebook second bar shows "gru" selected | 10s |
| 2.11 | Point to the config hash in the Compose panel | Mention that this hash will be automatically tracked in MLflow when we run the notebook (demonstrated in Scene 3) | 5s |

### Voice-over

> [2.1-2.4] "For configuration management, we use Hydra with hierarchical YAML files.
> Our project has config groups for model architecture and data settings. Here we can
> see the GRU configuration with 128 and 64 hidden units, and a simple Linear baseline
> for comparison. No hardcoded parameters anywhere in the code."

> [2.5-2.7] "The compose panel lets us select config groups via dropdowns and see the
> fully resolved configuration. Notice the SHA-256 hash at the bottom - this uniquely
> identifies every configuration. noted automatically logs this hash to MLflow on every
> experiment run, ensuring we always know exactly which config produced which results."

> [2.8-2.9] "Switching from GRU to Linear instantly updates the resolved YAML and
> produces a different hash. We can also override individual parameters - here we
> change epochs from 30 to 10 for a quick training demo. All of this without touching
> a single YAML file manually."

> [2.10-2.11] "The config selector in the notebook bar lets us choose which configuration
> profile is active. When we run notebook cells, noted automatically injects the resolved
> config into the kernel as a Python object - the code simply reads `cfg.model.units1`
> without any Hydra boilerplate."

---

## 5. Scene 3: Live Notebook Execution

### Intro Slide

```
Scene 3: Interactive Training with Live Metrics

What you will see:
- Configuring an MLflow experiment run using Run Manager
- Selecting all notebook code cells with one click
- GRU model training with real-time loss curves streaming to MLflow
- DVC data hash and Hydra config hash tracking for full lineage

This is NOT pre-recorded - cells execute live with real computation.
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 3.1 | Navigate to Jena Weather > notebooks > `emi_tutorial2_demo.ipynb` | Notebook opens in center pane with cells visible | 5s |
| 3.2 | Show the kernel selector in the second bar | Python 3.12 kernel with venv selected | 5s |
| 3.3 | Show the config selector showing "model: gru *" | Config dropdown visible next to kernel selector | 3s |
| 3.4 | Click the Experiments button in the notebook second bar | Run Manager panel opens | 5s |
| 3.5 | Click "+" to create a new run, name it "GRU Training" | New run appears in the list with a colored bookmark | 5s |
| 3.6 | Click "Select All" to add all code cells to the run | All code cells get colored bookmarks matching the run | 5s |
| 3.7 | Optionally select the DVC dataset in the Datasets section | Dataset checkbox ticked, hash will be logged to MLflow | 5s |
| 3.8 | Click the play button to execute the run | Cells start executing sequentially, MLflow run starts automatically | 5s |
| 3.9 | Watch Cell 1 (Setup): imports and config loading | Cell output shows imports completing, `cfg` object printed with GRU config | 10s |
| 3.10 | Watch Cell 2 (Ingestion): load dataset | Output shows dataset loaded | 10s |
| 3.11 | Watch Cell 3 (Preprocessing): clean and split | Output shows train/val/test splits | 10s |
| 3.12 | **KEY MOMENT**: Live Metrics panel appears automatically during training | Live loss curves update in real time (train_loss and val_loss decreasing) | 30s |
| 3.13 | Show the epoch progress bar | "Epoch 5/30" with progress fill animating | 5s |
| 3.14 | Wait for training to complete | Final metrics appear: test_mae, test_rmse, test_r2 | 15s |
| 3.15 | Watch Cell 5 (Evaluation): log plots to MLflow | Output shows artifacts logged (predictions_vs_actual.png, horizon_mae.png) | 10s |
| 3.16 | Watch Cell 6 (Preview): show forecast chart | Matplotlib plot showing predicted vs actual temperature inline | 10s |
| 3.17 | Click on the Experiments section in the tree | New run visible with green checkmark, status FINISHED, metrics shown | 10s |
| 3.18 | Click on the run to open its detail panel | Detail shows: params (units1=128, dropout=0.2), metrics (mae, rmse), tags (dvc_data_hash, hydra_config_hash) | 15s |
| 3.19 | Scroll to show the DVC data hash and Hydra config hash tags | Both hashes visible - point out the Hydra config hash matches the one from Scene 2, confirming full configuration traceability | 10s |

### Voice-over

> [3.1-3.3] "Now let's see the pipeline running live. We open our demo notebook
> in noted. The kernel is set to Python 3.12 with our project's virtual environment,
> and the Hydra config selector shows GRU as the active model."

> [3.4-3.7] "To track this as an MLflow experiment, we use the Run Manager.
> We create a new run called 'GRU Training' and click 'Select All' to include
> every code cell. We can also select the DVC-tracked dataset so its version
> hash gets logged to the run for full data lineage."

> [3.8] "Now we execute the run. noted runs all selected cells sequentially,
> wrapped in a single MLflow run that starts and ends automatically."

> [3.9-3.11] "The pipeline runs through setup, data ingestion, and preprocessing.
> The Hydra config is injected as a Python object, and the Jena Climate dataset
> with over 420,000 observations is loaded, resampled, and split."

> [3.12-3.14] "Now the interesting part - training. Watch the Live Metrics panel:
> loss curves update in real time as each epoch completes. The epoch progress bar
> tracks our progress through the configured epochs. This is not pre-recorded -
> the model is training live right now. When training completes, we see the final
> test metrics: Mean Absolute Error, Root Mean Square Error, and R-squared."

> [3.15-3.16] "The evaluation cell generates prediction plots, and the final cell
> shows the model's forecast versus actual temperature measurements."

> [3.17-3.19] "In the Experiments section, the run appears with a green checkmark
> and FINISHED status. Opening the detail, we see all parameters from our Hydra
> config, the training metrics, and critically - the DVC data hash and Hydra config
> hash as tags. This run is fully traceable to the exact dataset version and
> configuration that produced it. This is what we call strict data lineage."

---

## 6. Scene 4: Airflow Pipeline Orchestration

### Intro Slide

```
Scene 4: Pipeline Orchestration with Apache Airflow

What you will see:
- A 4-stage Directed Acyclic Graph: Ingestion -> Preprocessing -> Training -> Evaluation
- Triggering the pipeline from noted's interface with parameter form
- Real-time task monitoring with status updates
- Task logs accessible inline
- MLflow metadata correctly routed from the pipeline

Requirement: "Orchestrate isolated scripts into a DAG using Apache Airflow.
The pipeline must automatically execute the complete workflow."
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 4.1 | Click the DAGs section in the explorer tree | DAGs tree shows `jena_training_pipeline` with status | 5s |
| 4.2 | Click on the DAG to expand it | DAG detail shows: status (Paused/Enabled), schedule, tags | 5s |
| 4.3 | Show the DAG graph visualization | 2D DAG visualization: 4 nodes connected by arrows (ingest_data -> preprocess_data -> train_model -> evaluate_model) | 10s |
| 4.4 | Click the "Run DAG" button | Run DAG panel opens with Hydra Configuration section at top (model/data dropdowns) and DAG Parameters below, pre-filled from Hydra | 10s |
| 4.5 | Show the Hydra config dropdowns selecting GRU | model: gru *, data: default * - DAG parameters automatically filled with Hydra-composed values | 5s |
| 4.6 | Click "Trigger" | Modal appears: "DAG is currently paused" with Cancel / Keep Paused & Queue Run / Unpause & Run Immediately | 5s |
| 4.7 | Click "Unpause & Run Immediately" | DAG is unpaused, pipeline starts, status updates in tree | 5s |
| 4.8 | Watch the task tree update in real time | `ingest_data` turns blue (running), then green (success) | 15s |
| 4.9 | Watch `preprocess_data` execute | Task turns blue then green | 15s |
| 4.10 | Click on `ingest_data` to see its log | Task log opens in a terminal view with ANSI colors, updating in real time | 10s |
| 4.11 | Watch `train_model` execute | Task turns blue, takes longer (training in progress) | 30s |
| 4.12 | Watch `evaluate_model` execute | Last task turns blue then green | 15s |
| 4.13 | Show the pipeline completion toast notification | Toast shows: "Pipeline completed successfully" with metric values | 5s |
| 4.14 | Click on Run History | History table shows the completed run with duration, status, and expand arrow | 10s |
| 4.15 | Click to expand the run row | Detail row shows MLflow run ID (clickable) and Hydra config hash - full lineage at a glance | 5s |
| 4.16 | Click the MLflow link to cross-navigate to the experiment run | Experiments tree auto-expands, navigating directly to the pipeline-created run with metrics | 10s |
| 4.17 | Show the run detail with Hydra config hash | Hydra config hash tag present, confirming the pipeline used the same Hydra configuration | 10s |

### Voice-over

> [4.1-4.3] "For automated pipeline execution, we use Apache Airflow. In noted's
> DAGs section, our Jena training pipeline appears as a DAG. The visualization
> shows four stages connected as a Directed Acyclic Graph: data ingestion,
> preprocessing, model training, and evaluation."

> [4.4-4.5] "We trigger the pipeline directly from noted. The Run DAG panel
> shows Hydra configuration dropdowns at the top - the same config groups we
> used in the notebook. The DAG parameters below are automatically filled from
> the composed Hydra config, ensuring consistency between notebook and pipeline
> execution. The user can also check 'Custom' to override individual parameters."

> [4.6-4.7] "Since the DAG is paused, noted asks how to proceed. We choose
> 'Unpause & Run Immediately' and the pipeline starts."

> [4.8-4.12] "Now we watch the tasks execute in real time. Each task node updates
> its status as it progresses - blue for running, green for success. The DAG
> reads its configuration directly from the Hydra YAML files, the same source
> of truth as the notebook. Ingestion, preprocessing, training, and finally
> evaluation - all status updates stream live, no page refresh needed."

> [4.10] "At any point we can click a task to see its execution logs in a live
> terminal view, with full color output updating in real time."

> [4.13-4.15] "The pipeline completes successfully. In the run history, we expand
> the run to see the full lineage: the MLflow run ID and Hydra config hash are
> shown directly in the table row."
>
> [4.16-4.17] "Clicking the MLflow link navigates us straight to the experiment
> run. The Hydra config hash tag confirms the pipeline used the same configuration
> source as the notebook - full traceability from notebook to automated pipeline."

---

## 7. Scene 5: Experiment Snapshots

### Intro Slide

```
Scene 5: Experiment Snapshots - Reproducibility in One Click

What you will see:
- The Run Leaderboard: all runs ranked by performance metrics
- Creating a Snapshot: capturing the complete reproducible state
- What a Snapshot contains: git commit + DVC data hashes + Hydra config + MLflow run + environment

This is noted's signature feature: full reproducibility captured as
a single, immutable record.
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 5.1 | Navigate to the Experiments section, click on the Jena experiment | Experiment detail opens | 5s |
| 5.2 | Click "Leaderboard" view | Sortable table showing all runs with metrics (MAE, RMSE, R2), params, snapshot badges | 10s |
| 5.3 | Click the MAE column header to sort | Runs sort by MAE ascending, best run highlighted in bold green | 5s |
| 5.4 | Point out the different config hashes across runs | Column showing different Hydra config hashes for different configurations | 5s |
| 5.5 | Click on the best run (lowest MAE) to open its detail | Run detail panel shows metrics, charts, parameters, and "Create Snapshot" button | 10s |
| 5.6 | Click "Create Snapshot" button in the run detail | Snapshot modal opens showing: git state (clean/dirty), snapshot name input, description | 10s |
| 5.7 | Show the git state validation | Modal shows "Git is clean" or auto-commit checkbox if dirty | 5s |
| 5.8 | Click "Create Snapshot" to confirm | Loading indicator, then success: "Snapshot created: snapshot/jena_weather_001" | 10s |
| 5.9 | Show the snapshot badge (gold star) appear on the run in the leaderboard | Star icon appears next to the snapshot run | 5s |
| 5.10 | Click the snapshot run to see its detail | Detail shows all snapshot metadata: branch name, git commit, DVC hashes, Hydra config, env freeze | 15s |
| 5.11 | Briefly mention Restore and Fork buttons | "Restore Snapshot" and "Fork Experiment" buttons visible | 5s |

### Voice-over

> [5.1-5.4] "After running multiple experiments with different configurations,
> we need to identify the best result and make it reproducible. The Leaderboard
> shows all runs in a sortable table. We sort by Mean Absolute Error to find
> the best performing model. Notice how each run has a different config hash,
> showing they used different hyperparameter configurations."

> [5.5-5.8] "We select the best run and create a Snapshot. This is noted's
> signature feature. A snapshot captures everything needed to reproduce this
> exact result: the git commit with all code, the DVC data hashes pointing
> to the exact dataset version, the resolved Hydra configuration, the MLflow
> run with all metrics and artifacts, and even the Python environment.
> All of this in a single click."

> [5.9-5.10] "The snapshot appears as a gold star on the run. Opening it,
> we can see the complete lineage: the snapshot branch name in git, the
> commit hash, every DVC-tracked file with its hash, the Hydra config hash,
> and the frozen requirements."

> [5.11] "At any time, anyone on the team can click Restore to recreate
> this exact workspace state - code, data, configs, everything - or Fork
> to start a new experiment from this point without affecting the original."

---

## 8. Scene 6: Model Registry and Serving

### Intro Slide

```
Scene 6: Model Registry and Live Serving

What you will see:
- Registering the best model in MLflow Model Registry
- Assigning the @champion alias for production deployment
- Model lineage: Data -> Config -> Code -> Run -> Model
- Loading the model in the serving container
- Live prediction via the Try It panel with real weather data

This demonstrates the complete path from training to deployment.
```

### Step-by-Step Script

| Step | Action | What the viewer sees | Duration |
|---|---|---|---|
| 6.1 | From the best run's detail page in Experiments, click "Register Model" button | Registration panel opens, showing run ID and asking for model name | 5s |
| 6.2 | Enter "JenaWeatherGRU" as the model name, click Register | Success message: "Model registered: JenaWeatherGRU v1" | 5s |
| 6.3 | Click the Models section in the icon bar | Models tree shows "JenaWeatherGRU" with version 1 as child node | 5s |
| 6.4 | Click on version 1 to open its detail | Detail page shows: version, status (READY), source run, creation date | 10s |
| 6.5 | Select "@champion" from the alias dropdown, click "Assign" | Toast confirms alias assigned, version detail refreshes showing "@champion" badge in green | 5s |
| 6.6 | Click "Lineage" on the model version detail | Lineage chain renders: Data (DVC hash) -> Config (Hydra hash) -> Code (git commit) -> Run (MLflow) -> Model (Registry) | 15s |
| 6.7 | Click "Try It" button | Try It panel opens, model loads in serving container | 10s |
| 6.8 | Show the green serving pill in the bottom status bar | Status bar shows: "JenaWeatherGRU v1" - model is now loaded for serving | 5s |
| 6.9 | Click "Generate Sample" button | A valid random input tensor is generated automatically matching the model's expected shape (120 time steps x 11 features) | 5s |
| 6.10 | Click "Predict" | Prediction runs against the serving container, result appears in the Output section | 5s |
| 6.11 | Show the output chart | A 24-hour temperature forecast line chart is rendered dynamically from the model's output | 10s |
| 6.12 | Click "Generate Sample" again with different random data, click "Predict" | A different forecast chart appears, prediction history updates below | 10s |
| 6.13 | Point out prediction history at the bottom | Last predictions listed with timestamps and truncated input/output | 5s |
| 6.14 | Show the brain icon in the notebook bar | Click it to open Load Model modal - select model and version, insert predict cell | 10s |

### Voice-over

> [6.1-6.2] "From the best run, we register the trained model in MLflow's
> Model Registry. We name it JenaWeatherGRU - version 1 is created automatically."

> [6.3-6.5] "In the Models section, our registered model appears with its version.
> We assign the @champion alias, marking this as the production-ready model.
> This alias is what the serving container watches to know which model to load."

> [6.6] "The lineage view shows the complete traceability chain: from the
> DVC-tracked data version, through the Hydra configuration, the git commit
> with the code, the MLflow training run, all the way to this registered model.
> Every link is clickable for navigation. This is full end-to-end provenance."

> [6.7-6.8] "The Try It panel loads the model into the serving container. The
> green indicator in the status bar confirms the model is loaded and ready."

> [6.9-6.11] "The input schema is inferred automatically from the model's
> signature - noted knows this GRU model expects 120 time steps of 11 weather
> features. We click 'Generate Sample' to create valid random input data, then
> Predict. The model returns a 24-hour temperature forecast, rendered as a
> dynamic line chart. This is a real inference call to our FastAPI serving
> container, loading the model directly from MLflow."

> [6.12-6.13] "We can generate different samples and predict again - the output
> chart updates and prediction history tracks every test query. This works for
> any model type - tensor, tabular, classification - the input generation and
> output visualization adapt automatically."

> [6.14] "Back in the notebook, the brain icon lets us insert a predict cell
> for any registered model - select the model and version, and the boilerplate
> code is generated automatically."

---

## 9. Scene 7: Closing

### Slide Content

```
Summary

What we demonstrated:
  1. Hydra configuration management - hierarchical YAML, visual editor, config hash tracking
  2. Airflow pipeline orchestration - 4-stage DAG, parameterized triggers, live monitoring
  3. Live notebook execution - real-time training with metrics streaming
  4. Experiment Snapshots - full reproducibility in one click
  5. Model Registry - version management and alias governance
  6. Model Serving - live predictions from the registered champion model

All within a single interface. No context switching.
Zero vendor lock-in - every artifact works without noted.

Tools: MLflow | DVC | Hydra | Apache Airflow | MinIO | Docker Compose | FastAPI
```

### Voice-over

> "To summarize: we demonstrated the complete MLOps lifecycle within noted -
> from Hydra configuration management and Airflow pipeline orchestration, through
> live notebook training with real-time metrics, to experiment snapshots for
> reproducibility, model registration with governance aliases, and live model
> serving with predictions. All of this happens in a single interface with
> no context switching between tools. And importantly, every artifact noted
> creates - notebooks, MLflow runs, DVC files, Hydra configs, Airflow DAGs -
> works independently without noted. Zero vendor lock-in. Thank you."

---

## 10. Slide Designs

All slides should follow a consistent visual style:

### Design Guidelines

- **Background:** Dark gradient (#1a1a2e to #16213e) or noted's dark theme (#181818)
- **Title font:** Sans-serif (e.g., Inter, Segoe UI), white, 36-48pt
- **Body font:** Same family, light grey (#b0b0b0), 20-24pt
- **Accent color:** noted's gold (#ffe39e) for highlights and the "noted" brand
- **Requirement quotes:** Italic, slightly smaller, in a subtle box or left-bordered
- **Layout:** Title top-left, content centered, group/date bottom-right
- **Transition:** Simple fade (0.5s) between slide and live screen

### Slide List

| # | Type | Content |
|---|---|---|
| S0 | Title card | Group info, project title, university |
| S1 | Scene intro | "Scene 1: Infrastructure" + bullet points |
| S2 | Scene intro | "Scene 2: Configuration Management with Hydra" + requirement quote |
| S3 | Scene intro | "Scene 3: Interactive Training with Live Metrics" |
| S4 | Scene intro | "Scene 4: Pipeline Orchestration with Apache Airflow" + requirement quote |
| S5 | Scene intro | "Scene 5: Experiment Snapshots" |
| S6 | Scene intro | "Scene 6: Model Registry and Live Serving" |
| S7 | Closing | Summary + tools + credits |

---

## 11. Voice-over Recording Notes

### General Guidelines

- Speak clearly and at a moderate pace (not rushed)
- Brief pauses (1-2s) between sentences for breathing room
- Slightly increase energy for key moments (live metrics appearing, snapshot creation, prediction result)
- Keep a conversational tone, not reading-a-script monotone
- If a word is hard to pronounce, simplify the sentence
- Record in a quiet room with minimal echo

### Per-Scene Recording

Record each scene's voice-over as a separate audio file:

| File | Scene | Approx. duration |
|---|---|---|
| `vo_title.wav` | Title card | 15s |
| `vo_scene1.wav` | Infrastructure | 1:20 |
| `vo_scene2.wav` | Hydra Configuration | 1:40 |
| `vo_scene3.wav` | Live Notebook | 3:00 |
| `vo_scene4.wav` | Airflow Pipeline | 2:30 |
| `vo_scene5.wav` | Snapshot | 1:40 |
| `vo_scene6.wav` | Registry + Serving | 2:00 |
| `vo_scene7.wav` | Closing | 20s |

### Post-production

1. Import all screen recordings into video editor (e.g., DaVinci Resolve, Premiere, or even Clipchamp)
2. Add intro slides before each scene recording (fade transition, 3-4s display)
3. Overlay voice-over audio, aligning with screen actions
4. Add background music track at 10-15% volume (instrumental, tech/ambient genre)
5. Add subtle zoom effects on key moments (metrics appearing, snapshot creation, prediction)
6. Export at 1080p, H.264, reasonable bitrate (10-15 Mbps)

---

## 12. Contingency Plans

### If Training Takes Too Long
- Reduce epochs to 5 for the live demo
- Or: pre-train the model, start recording from the last 2 epochs

### If Airflow DAG Fails
- Have a backup completed run already in the history
- Show the completed run and its logs instead of a live trigger
- Record the fix and retry as a "resilience" demonstration

### If Serving Prediction Fails
- Check `docker logs noted-serving` for errors
- Ensure the model was registered with the correct artifact path
- Fallback: show the model lineage and schema without the actual prediction

### If Live Metrics Don't Stream
- The metrics are still logged to MLflow, just without real-time streaming
- Show the completed run's metrics in the Experiments detail instead
- Mention that live streaming is a feature, show it in a subsequent take

### If a Cell Errors
- Don't panic - errors are part of development
- Fix the issue on camera (shows real workflow) or cut and re-record the cell

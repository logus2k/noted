# Tutorial 2 - Implementation Plan

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | Tutorial 2 Implementation Plan     |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-03-26                         |
| Delivery      | Tutorial #2 (2026-03-29, 40%)      |
| Format        | Video demo (no written report)     |
| Related       | Vision v1.5, Scope v1.5, Plan v1.7 |

---

## 1. Delivery Context

### 1.1 What Tutorial 2 Requires

From the EMI assessment structure:

1. **Hydra configuration management** - eliminate hardcoded parameters via hierarchical YAML files
2. **Airflow DAG orchestration** - pipeline: Data Ingestion -> Preprocessing -> Training -> Evaluation
3. **Evidence of Airflow completing the pipeline** with all metadata routed to MLflow
4. **Builds on Tutorial 1** - DVC, MLflow, data lineage

### 1.2 What We Will Also Showcase

Tutorial 2 is 40% of the grade and accepts video evidence. We will go beyond the minimum by demonstrating noted's unique capabilities that bridge Tutorial 2 and the Final Delivery:

- **Experiment Snapshots** - the feature that ties code, data, config, and results into one immutable record
- **Model Registry** - register the best model, assign aliases
- **Model Serving** - load the champion model and run live predictions via the Try It panel
- **Live notebook execution** - not a static pre-recorded demo, but real cells running in real time

### 1.3 Delivery Format

A recorded video ("movie"), shot scene by scene, with:
- Intro slides before each scene explaining what is about to happen
- Voice-over narration explaining each step
- Background music track for engagement
- Scenes joined in post-production

---

## 2. Current State Assessment

### 2.1 What Already Exists (noted platform)

| Capability | Status | Location |
|---|---|---|
| Hydra config management | DONE | HydraManager, config UI, compose panel, hash injection |
| Airflow orchestration | DONE | AirflowManager, pipeline UI, DAG visualization, live monitoring |
| MLflow experiment tracking | DONE | Auto-instrumentation, live metrics, run comparison, artifact browser |
| DVC data versioning | DONE | DvcManager, data section, version history, MinIO remote |
| Experiment Snapshots | DONE | SnapshotManager, leaderboard, create/restore/fork |
| Model Registry | DONE | Registration, versions, aliases, lineage, comparison |
| Model Serving | DONE | noted-serving container, Try It panel, schema-aware prediction |
| Knowledge Graph | DONE | 3D entity graph, perspectives, search |
| Docker Compose stack | DONE | 10+ containers, mounts.yml auto-generation |

### 2.2 What Already Exists (Jena Weather project)

| Component | Status | Gap |
|---|---|---|
| Dataset (jena_climate_2009_2016.csv, 42MB) | Present | None |
| DVC tracking (.dvc pointer file) | Present | None |
| Hydra config (config/config.yaml) | Present | Needs model config groups (gru.yaml, linear.yaml) |
| GRU model implementation | In notebooks (group1_mp3_gru.ipynb) | Needs extraction to modular scripts |
| Airflow DAG (jena_training_dag.py) | Present but thin | Needs rewrite as proper 4-stage pipeline |
| src/ directory structure | Empty (ingestion/, training/, evaluation/, serving/) | Needs modular scripts |
| Model serving code | None | Needs model registered in MLflow first |
| PatchTST model | Not implemented | Out of scope for Tutorial 2 |

### 2.3 Gap Summary

The noted platform is complete. The gap is entirely in the **Jena Weather project content** - we need a runnable end-to-end pipeline with modular scripts that the DAG can orchestrate.

---

## 3. Implementation Tasks

### T-DEMO.1: Hydra Config Groups for Jena

**Goal:** Create hierarchical Hydra config groups so the demo can show switching between model architectures.

**Deliverables:**
- `config/config.yaml` - update defaults to reference model and data groups
- `config/model/gru.yaml` - GRU hyperparameters (units1, units2, dropout, etc.)
- `config/model/linear.yaml` - simple linear baseline for comparison
- `config/data/default.yaml` - standard data config (features, target, split ratios)

**Acceptance:** Config compose in noted UI shows model group dropdown with gru/linear options, YAML preview renders correctly, hash changes when switching model.

**Effort:** S (1h)

---

### T-DEMO.2: Modular Pipeline Scripts

**Goal:** Extract the notebook pipeline into modular Python scripts that both notebooks and Airflow tasks can call.

**Deliverables:**

**`src/ingestion/ingest.py`**
- Load CSV from `data/` directory
- Validate schema (expected columns present, no empty file)
- Log dataset stats (row count, date range, feature count) to stdout
- Save validated dataset path for downstream tasks
- Accept Hydra config for file path and feature selection

**`src/preprocessing/preprocess.py`**
- Read raw CSV
- Fix sensor errors (-9999.0 in wind speed)
- Resample to hourly frequency
- Standardize features (sklearn StandardScaler)
- Create train/val/test splits per config ratios
- Save processed arrays (numpy) + scaler (joblib) to `data/processed/`
- Log preprocessing summary to stdout

**`src/training/train.py`**
- Build GRU or Linear model based on Hydra config `model.type`
- Train with MLflow tracking (auto-instrumentation or explicit)
- Log metrics per epoch (train_loss, val_loss, val_mae)
- Log final test metrics (test_mae, test_rmse, test_r2)
- Save model via `mlflow.pytorch.log_model()` or `mlflow.sklearn.log_model()`
- Accept all hyperparameters from Hydra config

**`src/evaluation/evaluate.py`**
- Load trained model from MLflow run artifacts
- Compute evaluation metrics on test set
- Generate prediction vs actual plot (matplotlib, saved as artifact)
- Log evaluation metrics to MLflow
- Optionally register model in MLflow Registry if metrics meet threshold

**Acceptance:** Each script runnable standalone with `python src/X/script.py` using Hydra config. Each script also callable as a function from a notebook cell.

**Effort:** L (6-8h)

**Dependencies:** T-DEMO.1

---

### T-DEMO.3: Airflow DAG - Jena Training Pipeline

**Goal:** A proper 4-stage DAG that orchestrates the pipeline end-to-end.

**Deliverable:** `dags/jena_pipeline_dag.py`

```
[ingest_data] --> [preprocess_data] --> [train_model] --> [evaluate_model]
```

**Task details:**
- `ingest_data`: Runs `src/ingestion/ingest.py` with Hydra config overrides
- `preprocess_data`: Runs `src/preprocessing/preprocess.py`
- `train_model`: Runs `src/training/train.py` with model type and hyperparameters from DAG params
- `evaluate_model`: Runs `src/evaluation/evaluate.py`, registers model if threshold met

**DAG parameters (Airflow Param):**
- `model_type` (str, default "GRU") - selects Hydra model group
- `epochs` (int, default 30)
- `learning_rate` (float, default 0.0005)
- `batch_size` (int, default 256)
- `register_model` (bool, default false) - whether to register in MLflow Registry

**Integration:**
- Uses `@task` decorator (Airflow 3.0 TaskFlow API)
- Reads Hydra config hash from noted's trigger panel
- MLflow experiment set via environment variable
- DVC data hash logged automatically by noted's auto-instrumentation

**Acceptance:** DAG appears in noted's Pipelines section. Trigger from noted UI with parameter form. All 4 tasks complete successfully. MLflow run created with correct metrics, DVC hash, and Hydra config hash.

**Effort:** M (3-4h)

**Dependencies:** T-DEMO.2

---

### T-DEMO.4: Demo Notebook

**Goal:** A clean, presentation-ready notebook that walks through the entire pipeline interactively, suitable for live execution during the movie.

**Deliverable:** `notebooks/emi_tutorial2_demo.ipynb`

**Sections (cells):**
1. **Setup** - imports, config loading via noted's Hydra injection
2. **Data Ingestion** - call ingest module, show dataset shape and date range
3. **Preprocessing** - call preprocess module, show train/val/test shapes, plot feature distributions
4. **Training** - call train module with MLflow tracking, show live metrics in noted's panel
5. **Evaluation** - call evaluate module, show prediction plot, final metrics
6. **Model Registration** - register model in MLflow Registry, set alias

**Design principles:**
- Each cell is self-contained and runnable independently (after setup)
- Cells use the modular scripts from `src/` via imports
- Comments explain what each step does (for the voice-over)
- Output is visual - plots, tables, progress bars
- Total execution time target: under 3 minutes (use fewer epochs for demo, e.g., 10)

**Acceptance:** Notebook runs end-to-end in noted with live metrics visible. Each cell produces meaningful output.

**Effort:** M (2-3h)

**Dependencies:** T-DEMO.2

---

### T-DEMO.5: Pre-trained Model for Serving Demo

**Goal:** Have a trained model registered in MLflow so the serving demo works immediately.

**Deliverables:**
- A completed MLflow run with a GRU model trained on Jena data
- Model registered in MLflow Registry as "JenaWeatherGRU"
- Version 1 with `@champion` alias assigned
- Scaler and preprocessing artifacts logged alongside the model

**How:** Run the demo notebook (T-DEMO.4) or the pipeline (T-DEMO.3) once before recording the movie. The model stays in MLflow Registry.

**Acceptance:** `noted-serving` container can load the model via `/load`. Schema endpoint returns expected input format. Prediction with sample weather data returns a temperature forecast.

**Effort:** S (1h - just running the pipeline)

**Dependencies:** T-DEMO.3 or T-DEMO.4

---

### T-DEMO.6: Requirements File Update

**Goal:** Ensure `requirements.txt` has all dependencies needed for the pipeline.

**Deliverable:** Updated `requirements.txt`:
```
pandas
numpy
scikit-learn
torch
mlflow
plotly
matplotlib
pyyaml
hydra-core
omegaconf
dvc[s3]
joblib
```

**Note:** TensorFlow removed in favor of PyTorch (lighter, faster to install, better MLflow integration). GRU implemented in PyTorch instead of Keras.

**Acceptance:** `pip install -r requirements.txt` succeeds in the project's venv.

**Effort:** S (15min)

**Dependencies:** None (can be done first)

---

## 4. Implementation Order

```
T-DEMO.6 (requirements)     T-DEMO.1 (Hydra configs)
         \                   /
          \                 /
           T-DEMO.2 (modular scripts)
                  |
          +-------+-------+
          |               |
   T-DEMO.3 (DAG)   T-DEMO.4 (notebook)
          |               |
          +-------+-------+
                  |
           T-DEMO.5 (pre-trained model)
                  |
           Movie recording
```

**Critical path:** T-DEMO.1 -> T-DEMO.2 -> T-DEMO.3 -> T-DEMO.5

**Parallel track:** T-DEMO.4 can be built alongside T-DEMO.3 once T-DEMO.2 is done.

---

## 5. Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| GRU training too slow for live demo | Movie scene takes too long | Use 5-10 epochs for demo, show that real training uses 30+ |
| PyTorch model not compatible with MLflow serving | Serving demo fails | Test model loading in noted-serving before recording |
| Airflow DAG fails on first run | Pipeline scene unusable | Test DAG thoroughly before recording, have a backup completed run |
| Config injection issues in Airflow tasks | Tasks can't read Hydra config | Use BashOperator with explicit CLI overrides as fallback |
| Dataset too large for quick preprocessing | Demo feels slow | Pre-cache processed data, show preprocessing on a subset |

---

## 6. Success Criteria

The implementation is complete when:

1. `python src/ingestion/ingest.py` runs successfully with Hydra config
2. `python src/preprocessing/preprocess.py` produces train/val/test splits
3. `python src/training/train.py` trains a GRU model and logs to MLflow
4. `python src/evaluation/evaluate.py` evaluates and optionally registers the model
5. The Airflow DAG runs all 4 tasks to completion from noted's UI
6. The demo notebook runs end-to-end with live metrics visible
7. A trained model is registered, aliased @champion, and servable via Try It panel
8. A snapshot can be created capturing the complete experiment state

---

## 7. Timeline

| Day | Tasks | Deliverable |
|---|---|---|
| **Day 1** (Mar 26) | T-DEMO.1 + T-DEMO.6 + T-DEMO.2 (start) | Config groups, requirements, script skeletons |
| **Day 2** (Mar 27) | T-DEMO.2 (finish) + T-DEMO.3 + T-DEMO.4 | Complete scripts, DAG, notebook |
| **Day 3** (Mar 28) | T-DEMO.5 + movie recording | Pre-trained model, record all scenes |
| **Day 4** (Mar 29) | Post-production + submission | Final video with slides, voice-over, music |

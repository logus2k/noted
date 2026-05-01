# noted - Evidently Integration Plan

## Document Information

| Field         | Value                              |
|---------------|-------------------------------------|
| Document      | Evidently Integration Plan          |
| Project       | noted - Integrated MLOps Platform   |
| Version       | 1.0                                 |
| Date          | 2026-03-26                          |
| Status        | Draft                               |
| Target        | Tutorial #3 / Final Delivery (2026-04-12) |
| Related       | Vision v1.5, Scope v1.5, Plan v1.7  |

---

## 1. Purpose

This document defines the integration points between **noted** and **Evidently AI**, the open-source ML monitoring and evaluation library. Evidently adds three capabilities that noted currently lacks: **data quality validation**, **data/prediction drift detection**, and **model performance monitoring over time**. These map directly to planned Phase 5 features (T-5.4 Data Validation, T-5.5 Post-Deployment Observability) and replace the previously planned Pandera-only approach with a more comprehensive, unified tool.

---

## 2. Why Evidently

### 2.1 What Evidently Provides

| Capability | Description |
|---|---|
| **Reports** | Compute 100+ metrics on a dataset or pair of datasets (reference vs current). Produce interactive HTML visualizations. |
| **Presets** | Pre-configured metric bundles: DataDriftPreset, DataSummaryPreset, ClassificationPreset, RegressionPreset. |
| **Test Suites** | Conditional pass/fail checks on metrics (e.g., "drift score < 0.1", "no missing values > 5%"). Produce structured test results. |
| **Workspace / Projects** | The Evidently UI service organizes monitoring data into Projects. Reports are saved as snapshots and tracked over time in dashboards. |
| **Dashboards** | Time-series panels showing how metrics evolve across snapshots - visual drift monitoring out of the box. |

### 2.2 Justification vs Alternatives

| Approach | Pros | Cons |
|---|---|---|
| **Pandera only** (original T-5.4) | Simple schema validation, .schema.yaml files | No drift detection, no monitoring UI, no statistical tests, no regression/classification quality metrics |
| **Great Expectations** | Rich validation, data docs | Heavy, complex setup, no drift/monitoring, overkill for our use case |
| **Evidently** | Drift + quality + model perf in one library, built-in UI service, lightweight Python API, presets for common tasks, Docker image available | Adds one more container to the stack |

**Decision:** Evidently replaces Pandera for T-5.4 and covers T-5.5 in a single tool. One library, one container, two Phase 5 features resolved.

### 2.3 Alignment with noted Principles

| Principle | How Evidently Aligns |
|---|---|
| P1: Zero Vendor Lock-In | Evidently is open-source (Apache 2.0). Reports are standalone HTML. All data stays local. |
| P2: Backend Services Stay Canonical | Evidently is the source of truth for data quality and drift metrics. noted reads from it, does not duplicate. |
| P3: Integration Over Aggregation | noted surfaces lightweight indicators (badges, drift alerts) in the Explorer tree and delegates detailed exploration to the Evidently UI via a service tab. noted does not replicate Evidently's dashboards or report views - Evidently is the engine, noted is the cockpit. |
| P7: Single Container, Proxy Pattern | Evidently runs as a separate container on the Docker network. noted proxies API calls; the browser never contacts Evidently directly. |

### 2.4 Integration Depth: Thin (Option A)

Consistent with noted's design pattern of not replacing integrated tools, the Evidently integration follows the **thin integration** approach:

- **noted does NOT** render its own drift charts, quality report panels, or test result views
- **noted DOES** surface lightweight indicators (badges, alerts) in the Explorer tree, sourced from the Evidently API
- **noted DOES** provide a service tab (iframe) for the full Evidently UI, where users go for detailed exploration
- **Reports are generated** in DAG tasks and notebook cells via the Evidently Python API - noted does not proxy report creation

This is the same pattern used for MLflow (badges + experiment tree nodes + service tab), Airflow (pipeline status + service tab), and MinIO (storage tree + service tab).

---

## 3. Architecture

### 3.1 Container Setup

```
noted (8123)  <--- API proxy ---> evidently (8009 -> 8000)
    |                                   |
    +--- MLflow (5000)                  +--- Workspace storage (volume)
    +--- Airflow (8080)
    +--- MinIO (9000)
    +--- Knowledge Graph (5523)
    +--- Serving (5522)
```

The Evidently service (`evidently/evidently-service:latest`) runs on the `noted-network`. noted communicates with it via internal hostname `evidently:8000`. Host port 8009 is for direct access during development.

### 3.2 Data Flow

```
Training/Evaluation Script (in Airflow worker or notebook)
    |
    | 1. Generate Evidently Report (Python API)
    | 2. Save snapshot to Evidently Workspace (HTTP API)
    |
    v
Evidently Service (workspace DB + snapshots)
    |
    | 3. noted backend queries Evidently API
    |
    v
noted UI (badges, alerts, dashboard panels)
```

### 3.3 Volume and Storage Configuration

```yaml
evidently:
  image: evidently/evidently-service:latest
  container_name: noted-evidently
  ports:
    - "8009:8000"
  volumes:
    - evidently-data:/app/workspace    # Workspace DB + snapshots persistence
  networks:
    - noted-network
  restart: always
```

A named volume (`evidently-data`) persists the workspace database and report snapshots across container restarts.

**Storage options** (from Evidently self-hosting docs):
- **Local workspace** (default): file system storage inside the container - sufficient for our use case
- **SQL backend**: supports SQLite (default) or PostgreSQL - could reuse `noted-postgres` if needed later
- **S3-compatible storage**: supports MinIO via `fsspec` - could use `noted-minio` for shared artifact access

For the initial integration, local workspace with a named volume is the simplest path. Migration to PostgreSQL or MinIO storage can be done later without code changes (configuration only).

### 3.4 Key Evidently Concepts

| Concept | Description | Relevance to noted |
|---|---|---|
| **Dataset** | Wraps a pandas DataFrame with a `DataDefinition` that maps column types (numerical, categorical, text, datetime) and roles (target, prediction, id). | Jena Weather data uses numerical features (T, p, rh, etc.) with datetime index. |
| **DataDefinition** | Declares column types and roles. Evidently can auto-detect but manual mapping is recommended for accuracy. | We define once per project and reuse across all reports. |
| **Report** | Combines Metrics and/or Presets. Run on one dataset (profiling) or two (comparison). Produces interactive HTML + structured dict/JSON. | Core evaluation unit - generated in DAG tasks and notebooks. |
| **Tests** | Conditional checks added to metrics via `tests=[gte(x), lt(y)]`. Eight operators: eq, not_eq, gt, gte, lt, lte, is_in, not_in. Can reference baseline data. | Quality gates before training. Tests with `is_critical=True` block pipelines, `is_critical=False` for warnings. |
| **Tags & Metadata** | String tags and key-value metadata on reports and runs. Built-in fields: `model_id`, `dataset_id`, `reference_id`, `batch_size`. | Tag reports by pipeline stage, model version, DVC hash. Filter in Evidently UI dashboards. |
| **Workspace** | Local or remote storage for report snapshots. Supports file system, SQLite, PostgreSQL, or S3/MinIO via fsspec. | `ws.add_run(project.id, snapshot)` saves to the Evidently service. |
| **Descriptors** | Row-level scores/labels for text quality (TextLength, Sentiment, LLM-based judges). | Not needed for Jena Weather (tabular), but available if LLM features are added later. |

---

## 4. Integration Points

### 4.1 IP-1: Data Quality Reports (replaces T-5.4)

**What:** After data ingestion or preprocessing, generate an Evidently DataSummaryPreset report on the dataset. Store the report as a snapshot in the Evidently workspace. Display a "Data Health" badge in the Explorer tree.

**Value:** Catches data quality issues (missing values, type mismatches, outliers, constant columns) before expensive training runs. Replaces the planned Pandera schema validation with a richer, zero-config approach - Evidently computes statistics without requiring manually written schemas.

**How it works:**
1. The Airflow ingestion/preprocessing task (or notebook cell) runs:
   ```python
   from evidently import Report, Dataset, DataDefinition
   from evidently.presets import DataSummaryPreset

   data_def = DataDefinition(
       numerical=["T (degC)", "p (mbar)", "rh (%)"],
       datetime="Date Time",
   )
   dataset = Dataset(df, data_definition=data_def)

   report = Report([DataSummaryPreset()], tags=["data-quality", "jena-weather"])
   snapshot = report.run(dataset)

   # Save to Evidently workspace
   ws.add_run(project.id, snapshot, include_data=False)
   ```
2. noted backend queries Evidently workspace API for the latest snapshot status
3. Explorer tree shows a green/yellow/red badge on the dataset node
4. Clicking the badge opens the full interactive report in a center tab

**Acceptance criteria:**
- Data quality report generated automatically after ingestion pipeline step
- Badge visible in Explorer tree on dataset nodes
- Full report viewable in noted (HTML rendered in center tab)

---

### 4.2 IP-2: Data Drift Detection (replaces part of T-5.5)

**What:** Compare current data distributions against a reference dataset (e.g., training data) to detect feature drift. Run as a scheduled check or as part of the evaluation pipeline.

**Value:** Detects when incoming data no longer matches the distribution the model was trained on - the #1 cause of silent model degradation in production. This is the core "closing the loop" capability that noted currently lacks between deployment and retraining.

**How it works:**
1. When a model is registered with `@champion`, noted stores a reference to its training data (already available via DVC hash in MLflow params)
2. A periodic Airflow DAG (or manual trigger from noted) runs:
   ```python
   from evidently import Report, Dataset, DataDefinition
   from evidently.presets import DataDriftPreset

   data_def = DataDefinition(numerical=feature_columns)
   ref_dataset = Dataset(training_df, data_definition=data_def)
   cur_dataset = Dataset(serving_df, data_definition=data_def)

   report = Report([DataDriftPreset()],
                    tags=["drift", "jena-weather"],
                    metadata={"model_id": champion_run_id})
   snapshot = report.run(cur_dataset, ref_dataset)

   ws.add_run(project.id, snapshot, include_data=False)
   ```
3. noted backend polls or receives webhook for drift status
4. Drift alerts surface in the noted UI:
   - Warning badge on the Model node in the Explorer tree
   - Notification in the Activity Feed
   - Drift trend visible in the Evidently dashboard (accessible as a service tab)

**Acceptance criteria:**
- Drift report compares training vs current data distributions
- Per-feature drift scores with statistical test results (KS, PSI, etc.)
- Visual alert in noted when drift exceeds configurable threshold
- Drift history tracked over time in Evidently dashboard

---

### 4.3 IP-3: Model Performance Monitoring (replaces rest of T-5.5)

**What:** Track regression quality metrics (MAE, RMSE, R2) over time for deployed models. Compare predicted vs actual values when ground truth becomes available.

**Value:** Directly answers "is the model still performing well?" - the fundamental question of production ML. For the Jena Weather project, this means tracking whether the GRU/PatchTST forecasts remain accurate as new weather data arrives. Links performance degradation back to data drift via the Knowledge Graph.

**How it works:**
1. The evaluation DAG stage computes predictions and compares against actuals
2. An Evidently RegressionPreset report is generated and saved:
   ```python
   from evidently import Report, Dataset, DataDefinition
   from evidently.presets import RegressionPreset

   data_def = DataDefinition(
       numerical=feature_columns,
       target="actual_temp",
       prediction="predicted_temp",
   )
   ref_dataset = Dataset(train_preds_df, data_definition=data_def)
   cur_dataset = Dataset(eval_preds_df, data_definition=data_def)

   report = Report([RegressionPreset()],
                    tags=["performance", "jena-weather"],
                    metadata={"model_id": run_id, "dataset_id": dvc_hash})
   snapshot = report.run(cur_dataset, ref_dataset)

   ws.add_run(project.id, snapshot, include_data=False)
   ```
3. The Evidently dashboard shows performance trends over time
4. noted surfaces a performance status badge on the model node in the Explorer tree
5. Users click through to the Evidently service tab for detailed dashboards and trend charts

**Acceptance criteria:**
- Regression metrics tracked per evaluation run in Evidently workspace
- Performance status badge on model nodes in Explorer tree
- Evidently UI shows time-series dashboard with metric evolution

---

### 4.4 IP-4: Pre-Pipeline Quality Gates (extends IP-1)

**What:** Before a training pipeline runs, execute an Evidently Test Suite that validates data quality conditions. Block pipeline execution if critical tests fail.

**Value:** Prevents wasted compute on bad data. The Test Suite approach is more powerful than simple schema validation because it can enforce statistical conditions ("column X mean within 2 std of reference", "no more than 1% nulls"), not just type checks.

**How it works:**
1. The first task in the Airflow training DAG runs a Test Suite:
   ```python
   from evidently import Report, Dataset, DataDefinition
   from evidently.metrics import *
   from evidently.tests import gte, lte, lt

   data_def = DataDefinition(numerical=feature_columns)
   dataset = Dataset(df, data_definition=data_def)

   report = Report([
       MinValue(column="T (degC)", tests=[gte(-50)]),
       MaxValue(column="T (degC)", tests=[lte(60)]),
       MissingValueShare(tests=[lt(0.05)]),
       RowCount(tests=[gte(1000)]),
   ], tags=["quality-gate", "jena-weather"])
   snapshot = report.run(dataset)

   # Check test results - fail the DAG task if any critical test fails
   results = snapshot.dict()
   failed = [t for t in results.get("tests", []) if t["status"] == "FAIL"]
   if failed:
       raise ValueError(f"Data quality gate failed: {len(failed)} test(s)")
   ```
2. Pipeline status shows "Quality Gate: PASSED/FAILED" in the noted Pipeline panel
3. Failed gate reports are viewable with detailed per-test results

**Acceptance criteria:**
- Test suite runs as first DAG task before training
- Pipeline blocks on test failure with clear error message
- Test results visible in noted Pipeline detail view

---

### 4.5 IP-5: Evidently UI as Service Tab

**What:** Add the Evidently UI as a service tab in noted, alongside MLflow, Airflow, and MinIO.

**Value:** Power users can access the full Evidently dashboard for deep exploration - custom panels, cross-project comparisons, historical trend analysis - without leaving noted. Consistent with how MLflow and Airflow UIs are already integrated.

**How it works:**
1. Add Evidently icon to the Icon Bar (bottom service group)
2. Clicking opens the Evidently UI (`http://evidently:8000`) as an iframe in a center tab
3. nginx proxy rule forwards `/evidently/` to the Evidently service

**Acceptance criteria:**
- Evidently icon in the Icon Bar
- Service tab opens the Evidently workspace UI
- Proxy routing configured in nginx

---

### 4.6 IP-6: Knowledge Graph Integration

**What:** Add Evidently report entities (data quality, drift, performance) to the Knowledge Graph. Link them to the datasets, models, and pipeline runs they evaluate.

**Value:** Transforms monitoring from an isolated view into a connected part of the lineage story. A user can see not just that a model's performance dropped, but trace it back through the graph to the specific data version and pipeline run that produced it. This is the "Impact Analysis" (T-5.1) applied to monitoring data.

**How it works:**
1. GraphBuilder scans the Evidently workspace for report snapshots (via `evidently_manager.py`)
2. New entity types: `DataQualityReport`, `DriftReport`, `PerformanceReport`
3. Edges connect reports to:
   - The dataset they evaluated (via DVC hash stored in report metadata `dataset_id`)
   - The model version they monitored (via MLflow run ID stored in report metadata `model_id`)
   - The pipeline run that generated them (via Airflow DAG run ID stored in report tags)
4. 3D visualization shows monitoring entities with distinct node shapes

**Acceptance criteria:**
- Evidently reports appear as nodes in the Knowledge Graph
- Edges link reports to datasets, models, and pipeline runs
- "What breaks?" traversal includes monitoring dependencies

**Note:** This is the only integration point where noted actively pulls detailed data from Evidently (entity metadata for graph edges). All other IPs use lightweight status queries or delegate to the Evidently UI.

---

## 5. Integration with Existing Stack

| Service | Integration Pattern |
|---|---|
| **MLflow** | Training data reference stored as MLflow param (DVC hash). Evidently reports reference MLflow run IDs. Model versions link to performance reports. |
| **Airflow** | Evidently reports generated inside DAG tasks. Quality gates as pre-training validation tasks. Drift checks as scheduled DAGs. |
| **DVC** | Reference datasets for drift detection identified by DVC hash. Data quality reports tied to specific data versions. |
| **Serving** | Serving inputs collected and periodically compared against training distribution. Prediction quality tracked when actuals arrive. |
| **Knowledge Graph** | Evidently report entities with edges to datasets, models, runs, pipelines. |

---

## 6. Implementation Phases

### Phase A: Foundation (3-4 days)

| Task | Description |
|---|---|
| A.1 | Add `evidently-data` volume to docker-compose, verify container starts and UI is accessible |
| A.2 | Add `evidently` Python package to Airflow worker and noted container requirements |
| A.3 | Create Evidently project via API for the Jena Weather pipeline |
| A.4 | Add Evidently UI as a service tab in noted (icon + iframe + nginx proxy) |
| A.5 | Add `evidently_manager.py` backend module to noted (API client for querying workspace) |

### Phase B: Data Quality (2-3 days)

| Task | Description |
|---|---|
| B.1 | Generate DataSummaryPreset report in the ingestion/preprocessing DAG task |
| B.2 | Implement "Data Health" badge in Explorer tree (query Evidently for latest status) |
| B.3 | Implement quality gate Test Suite as first task in training DAG |
| B.4 | Show quality gate status in the Pipeline trigger panel |

### Phase C: Drift Detection (2-3 days)

| Task | Description |
|---|---|
| C.1 | Generate DataDriftPreset report in evaluation DAG (training data vs eval data) |
| C.2 | Store reference dataset pointer when model is registered with @champion |
| C.3 | Implement drift alert badges on Model nodes in Explorer tree |
| C.4 | Create scheduled drift-check DAG (configurable interval) |

### Phase D: Performance Monitoring (2 days)

| Task | Description |
|---|---|
| D.1 | Generate RegressionPreset report in evaluation DAG (predicted vs actual) |
| D.2 | Surface key performance trends in model detail view |
| D.3 | Link performance drops to drift events |

### Phase E: Knowledge Graph (1-2 days)

| Task | Description |
|---|---|
| E.1 | Add Evidently entity types to GraphBuilder |
| E.2 | Create edges: report -> dataset, report -> model, report -> pipeline run |
| E.3 | Add node shapes and colors for monitoring entities |

**Total estimated effort: 10-14 days**

---

## 7. Jena Weather Pipeline - Demonstration Scenario

For the Final Delivery, the Evidently integration will be demonstrated using the Jena Weather Forecasting project:

1. **Ingest weather data** - DataSummaryPreset report shows feature statistics (temperature, pressure, humidity distributions). Data Health badge appears green.

2. **Quality gate** - Test Suite validates: no missing values > 2%, temperature within [-30, 50]C, all expected columns present. Gate passes, training proceeds.

3. **Train GRU model** - Model registered with @champion. Training data distribution saved as drift reference.

4. **Evaluate on new data** - RegressionPreset shows MAE/RMSE trends. DataDriftPreset compares evaluation data against training distribution.

5. **Drift scenario** - Deliberately introduce shifted data (e.g., summer vs winter distribution). Evidently detects drift, badge turns yellow/red on the model node. Knowledge Graph shows the connection: shifted data -> drift report -> affected model.

6. **Dashboard review** - Open Evidently service tab showing time-series panels of drift scores and model performance across multiple evaluation runs.

This scenario demonstrates the complete monitoring loop: data quality -> training -> deployment -> monitoring -> drift detection -> retraining trigger.

---

## 8. Impact on Phase 5 Plan

| Original Task | Status | Evidently Impact |
|---|---|---|
| T-5.4: Data Validation (Pandera) | Planned | **Replaced** by IP-1 (Data Quality) + IP-4 (Quality Gates). Evidently provides richer validation than Pandera schemas without requiring manual schema definitions. |
| T-5.5: Post-Deployment Observability | Planned | **Replaced** by IP-2 (Drift) + IP-3 (Performance). Evidently provides the drift detection and performance monitoring that were planned as custom implementations. |
| T-5.1: Impact Analysis | Planned | **Extended** by IP-6. Monitoring entities in the Knowledge Graph add a new dimension to impact analysis. |

All other Phase 5 tasks (T-5.1, T-5.2, T-5.3, T-5.6, T-5.7) remain unchanged.

---

## 9. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Evidently API changes between versions | Medium | Pin Docker image version, add version check on startup |
| Report generation adds latency to DAG tasks | Low | Reports run after main task logic; async snapshot saving |
| Workspace storage growth over time | Low | Snapshot retention policy (configurable, e.g., keep last 90 days) |
| Evidently UI conflicts with nginx proxy paths | Low | Test proxy rules during Phase A; use `/evidently/` prefix |
| Container resource usage | Low | Evidently service is lightweight (~500MB image, low runtime memory) |

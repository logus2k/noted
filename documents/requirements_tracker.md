# noted - Requirements Fulfillment Tracker

## Document Information

| Field | Value |
|-------|-------|
| Document | Requirements Tracker |
| Last Updated | 2026-03-21 |
| Sources | noted_dvc.md, noted_mlflow.md, noted_hydra.md, noted_airflow.md |
| Total Requirements | 196 |
| Done | 151 (77%) |
| Partial | 7 (4%) |
| Not Done | 32 (16%) |
| Skipped (by design) | 6 (3%) |
| Must-Have Coverage | ~96% |

---

## 1. DVC Integration (noted_dvc.md)

**Coverage: 16 done, 2 partial, 6 not done, 6 skipped | 80% (excl. skipped)**

### 3.1 Versioning a Dataset

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 1 | Workspace tree badges for DVC-tracked files | Must | **DONE** | Teal dots, "T" badges, "DVC" source labels via DecorationService |
| 2 | File detail view (hash, size, remote status) | Nice | **DONE** | Data section detail with metadata card |
| 3 | Source Control panel DVC integration | Must | **DONE** | DVC section in GitPanel with tracked file list |
| 4 | Context menu "Track with DVC" | Must | **DONE** | Right-click file -> Track with DVC |
| 5 | DVC sync status indicators (cloud-up/checkmark) | Nice | **DONE** | Per-file cloud icons via dvc status --cloud. Green cloud = pushed, orange cloud-up = not pushed |

### 3.2 Switching Between Dataset Versions

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 6 | Git history view with DVC file changes | Nice | **PARTIAL** | Version history in .dvc detail pane; not integrated into git history panel |
| 7 | "Restore data" button on historical commits | Must | **DONE** | Checkout button per version row with confirmation modal |
| 8 | MLflow run linkage for data restoration | Nice | **DONE** | Snapshot restore does code + data + config together |

### 3.3 Reproducing an Experiment End-to-End

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 9 | "Reproduce" button for dvc.yaml | Must | **SKIPPED** | By design: Airflow replaces DVC pipelines (confirmed from teacher's labs) |
| 10 | Pipeline stage visualization | Nice | **SKIPPED** | Same - Airflow DAG visualization replaces this |
| 11 | Stage status indicators | Nice | **SKIPPED** | Same |
| 12 | "Run" button on individual stages | Nice | **SKIPPED** | Same |

### 3.4 Pushing and Pulling Data to MinIO

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 13 | DVC Data section in Source Control | Must | **DONE** | "DATA - DVC" section with tracked files |
| 14 | DVC push/pull buttons | Must | **DONE** | Push and Pull buttons in GitPanel DVC section |
| 15 | Push-on-commit setting | Nice | **NOT DONE** | Auto dvc push after git commit |
| 16 | MinIO bucket status display | Nice | **PARTIAL** | Storage browser exists; no bucket size or last sync time |

### 3.5 Tracking Data Lineage Across Experiments

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 17 | Automatic DVC hash injection into MLflow | Must | **DONE** | Auto-instrumentation logs dvc.data_hash tag + param |
| 18 | MLflow experiment detail with Git/DVC info | Nice | **DONE** | Tags shown in run detail, lineage view in model version |
| 19 | "Used in N runs" badge on data files | Nice | **NOT DONE** | |
| 20 | Reproducibility score indicator | Nice | **NOT DONE** | |

### 3.6 Managing Pipeline Dependencies

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 21 | Pipeline editor for dvc.yaml | Must | **SKIPPED** | Airflow replaces DVC pipelines |
| 22 | DAG visualization for DVC | Nice | **SKIPPED** | Replaced by Airflow DAG visualization (2D SVG) |
| 23-25 | Color-coded DAG, right-click execute, metrics in DAG | Nice | **SKIPPED** | Same |

### 3.7 Comparing Data Versions

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 26 | Data diff panel (two commits) | Nice | **NOT DONE** | |
| 27 | Notebook-aware diff ("data changed since run") | Nice | **NOT DONE** | |

### Section 4: MinIO as DVC Remote

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 28 | DVC auto-initialization | Must | **DONE** | Lazy init on first track with MinIO remote configured |
| 29 | MinIO workspace tree node | Nice | **DONE** | Storage section in Explorer tree |
| 30 | Credential management | Must | **DONE** | Backend handles MinIO keys, never exposed to browser |

---

## 2. MLflow Integration (noted_mlflow.md)

**Coverage: 48 done, 4 partial, 20 not done | 72%**

### 3.1 Logging an Experiment Run

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 31 | Active run indicator in notebook bar | Must | **DONE** | Green pulsing dot + run name in notebook second bar. Appears on metrics:update events. Click navigates to run in Experiments. Auto-clears after 5 min idle. |
| 32 | Post-run summary toast | Nice | **DONE** | Toast shows run name + last metric values (up to 5) |

### 3.2 Browsing and Comparing Experiments

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 33 | Experiments panel in workspace tree | Must | **DONE** | Full experiment/run browser with detail panels |
| 34 | Run sort and filter | Must | **DONE** | Leaderboard with sortable columns |
| 35 | Side-by-side run comparison | Must | **DONE** | Full comparison panel with metrics/params/tags diff |
| 36 | Metric plot for single run | Must | **DONE** | Inline ECharts in run detail |
| 37 | Pinned metrics configuration | Nice | **DONE** | Columns button with checkbox dropdown for metrics + params |

### 3.3 Live Metric Streaming During Training

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 38 | Live metric panel | Nice | **DONE** | ECharts real-time panel, Split/Combined/Summary views |
| 39 | Multi-metric display | Nice | **DONE** | Split view shows one chart per metric |
| 40 | Epoch progress bar | Nice | **DONE** | Progress bar in Live Metrics panel. Shows Epoch X/Y when total_epochs logged |
| 41 | "Stop run" button in live panel | Nice | **DONE** | Stop/kill run from run detail |

### 3.4 Attaching Artifacts to Runs

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 42 | Artifact panel in run detail | Must | **DONE** | Full artifact tree with categories |
| 43 | Image artifact rendering | Must | **DONE** | Inline thumbnails |
| 44 | HTML artifact rendering | Must | **DONE** | Sandboxed iframe |
| 45 | Text/markdown artifact rendering | Must | **DONE** | Syntax-highlighted pre |
| 46 | YAML artifact rendering | Must | **DONE** | Syntax-highlighted |
| 47 | Model directory display | Must | **DONE** | MLmodel card with metadata |
| 48 | Multi-flavor model support | Must | **DONE** | Via mlflow.pyfunc generic loading |
| 50 | Artifact download | Nice | **DONE** | Download icon in second bar |

### 3.5 Reproducibility: Restoring an Experiment

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 51 | "Restore" button on run detail | Nice | **DONE** | Via snapshot restore (git checkout + dvc checkout) |
| 52 | "Reproduced" badge | Nice | **NOT DONE** | |
| 53 | Lineage chain display | Nice | **DONE** | Visual lineage in model version detail: Data -> Config -> Code -> Run -> Model |

### 3.6 Model Registry: Promoting a Model

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 54 | Models section in workspace tree | Must | **DONE** | Models section with versions as children |
| 55 | "Register" button in run detail | Must | **DONE** | Registration panel (jsPanel) |
| 56 | Stage transition dropdown | Nice | **DONE** | Alias management: @champion, @staging, @archived |
| 57 | Promotion approval workflow | Nice | **NOT DONE** | Out of scope |
| 58 | Model version changelog | Nice | **DONE** | Comparison panel shows diff between versions |

### 3.7 Model Comparison Across Versions

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 59 | Version compare panel | Nice | **DONE** | Metrics diff, params diff, lineage diff |
| 60 | Champion/challenger evaluation | Nice | **NOT DONE** | Load both, evaluate on dataset |
| 61 | Production impact estimate | Nice | **NOT DONE** | |

### 3.8 Model Serving and Prediction

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 62 | "Serve model" button | Nice | **DONE** | "Try It" button loads model in serving container |
| 63 | Serving endpoint URL display | Nice | **DONE** | Health info in Try It panel |
| 64 | "Predict" cell template | Nice | **DONE** | "Insert Predict Cell" button on model version detail page |
| 65 | Serving status indicator | Nice | **DONE** | Green pill in bottom bar |
| 66 | Swagger/test UI | Nice | **DONE** | Try It panel with dynamic input form |
| 67 | APIs section in workspace | Nice | **DONE** | APIs section in Explorer tree with serving endpoint health/model info |

### 3.9 Experiment Hygiene

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 68 | Bulk run management | Nice | **DONE** | Multi-select list + "Delete Selected" on experiment detail page |
| 69 | "Show archived" toggle | Nice | **NOT DONE** | |
| 70 | Auto-archive short runs | Nice | **NOT DONE** | |
| 71 | Run notes field | Nice | **NOT DONE** | |
| 72 | Experiment export (CSV/JSON) | Nice | **DONE** | Leaderboard CSV export + report generation |

### 3.10 Run Manager

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 73 | Run Manager button | Must | **DONE** | Experiments icon in notebook second bar |
| 74 | Run Manager panel | Must | **DONE** | RunManagerPanel.js |
| 75 | "Add Run" button | Must | **DONE** | |
| 76 | "Delete Run" button | Must | **DONE** | |
| 77 | Run selection and activation | Must | **DONE** | |
| 78 | Cell assignment via click | Must | **DONE** | |
| 79 | Cell badges for run membership | Must | **DONE** | Colored badges |
| 80 | Run execution flow | Must | **DONE** | Sequential cells in single MLflow run |
| 81 | Back-off for explicit MLflow code | Must | **DONE** | Skips injection if mlflow.start_run in cell |
| 82 | Run definition metadata storage | Must | **DONE** | In notebook metadata |

---

## 3. Hydra Configuration (noted_hydra.md)

**Coverage: 24 done, 1 partial, 14 not done | 64%**

### 3.1 Structuring Experiment Configuration

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 83 | Config tree in workspace | Must | **DONE** | Configuration section auto-detected per project |
| 84 | Config file icon | Nice | **DONE** | Gear/star icons for groups/defaults |
| 85 | Config YAML editor with validation | Must | **PARTIAL** | YAML preview in detail; no schema validation hints |
| 86 | Config selector in notebook bar | Must | **DONE** | Dropdown in second bar with config groups/options. Selection saved in notebook metadata. |
| 87 | Config injection into kernel environment | Must | **DONE** | Resolved config injected as `cfg` (OmegaConf) and `__noted_hydra_config__` (dict) on every cell execution. Back-off if cell has explicit Hydra imports. |
| 88 | Config as CLI overrides for @hydra.main | Must | **DONE** | sys.argv injection for @hydra.main cells |
| 89 | Resolved config preview panel | Must | **DONE** | Compose panel with YAML + hash output |
| 90 | OmegaConf interpolation display | Nice | **NOT DONE** | |

### 3.2 Tracking Configuration Across Experiments

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 91 | Auto-log Hydra config to MLflow | Must | **DONE** | Config hash injection as param + tag |
| 92 | Config in MLflow run detail | Must | **DONE** | Via tags in run detail |
| 93 | Config comparison between runs | Must | **DONE** | Params diff in comparison panel |
| 94 | Config search in MLflow (filter by values) | Nice | **DONE** | Filter bar in leaderboard: key=val, key>val, key>=val |

### 3.3 Parameter Sweeps (Multirun)

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 95 | Sweep launcher UI | Nice | **DONE** | Sweep panel with combo preview |
| 96 | Sweep parameter grid form | Nice | **DONE** | Comma-separated multi-value inputs |
| 97 | Multirun command construction | Nice | **DONE** | Cartesian product generation |
| 98 | Sweep run grouping in MLflow | Nice | **DONE** | _sweep_id tag on all runs |
| 99 | Sweep summary table | Nice | **DONE** | Results listed per combination |
| 100 | Parallel sweep execution | Nice | **DONE** | All DAG runs triggered in parallel |
| 101 | Best-run highlight | Nice | **DONE** | Leaderboard highlights best metric |
| 102 | "Promote best config" action | Nice | **DONE** | "Promote Best" button in leaderboard saves best run's params as Hydra template |

### 3.4 Config Inheritance and Composition

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 103 | Config inheritance view | Nice | **DONE** | Source file annotations in compose panel (key <- file) |
| 104 | Hover inheritance chain | Nice | **NOT DONE** | |
| 105 | Override annotation in resolved config | Nice | **NOT DONE** | |
| 106 | Validate config before run | Nice | **NOT DONE** | |
| 107 | Config validation error display | Nice | **NOT DONE** | |

### 3.5 Sharing Config Presets

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 108 | Config as project artifact | Nice | **DONE** | Configuration section in Explorer |
| 109 | Config group template creation | Nice | **NOT DONE** | |
| 110 | Named config presets | Nice | **DONE** | Config templates CRUD |
| 111 | Preset storage | Nice | **DONE** | .noted/config_templates/ |
| 112 | Presets in config selector | Nice | **DONE** | Template dropdown in compose panel |
| 113 | Export config to MLflow | Nice | **DONE** | Auto-logged as artifact in snapshots |

### 3.6 Airflow Pipeline Runs with Hydra

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 114 | Pipeline run config overrides field | Must | **DONE** | Trigger panel with typed param inputs |
| 115 | Config passed to Airflow task | Must | **DONE** | Via DAG run conf params |
| 116 | Config in pipeline history | Nice | **DONE** | Conf shown in run detail |
| 117 | Config template for new runs | Nice | **DONE** | "Load Last Run Config" button in trigger panel |

---

## 4. Airflow Orchestration (noted_airflow.md)

**Coverage: 38 done, 2 partial, 15 not done | 73%**

### 3.1 Authoring a Pipeline DAG

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 118 | Pipelines section in workspace tree | Must | **DONE** | Top-level section with DAG nodes |
| 119 | New DAG from template | Must | **DONE** | Right-click project/mount -> "New DAG from Template". 4 templates: blank, training, data, parallel. Creates file in dags/ directory. |
| 120 | DAG file editor | Must | **DONE** | Python editor opens DAG files |
| 121 | Airflow syntax highlighting | Must | **DONE** | Python syntax highlighting covers Airflow decorators |
| 122 | Multiple DAGs per project | Must | **DONE** | All .py files in dags/ discovered |
| 123 | DAG discovery from project dirs | Must | **DONE** | docker-compose.mounts.yml provides Airflow volumes |
| 124 | BashOperator + Hydra CLI highlighting | Nice | **NOT DONE** | |
| 125 | Dynamic task generation display | Nice | **DONE** | Mapped tasks shown with [index] suffix in task tree |
| 126-127 | Jinja templating support | Nice | **NOT DONE** | |
| 128 | Notebook-to-DAG conversion | Nice | **DONE** | "Export as Pipeline Task" button on code cells copies @task decorated function |
| 129 | DAG validation | Nice | **DONE** | "Validate" button on DAG detail checks imports, syntax, common pitfalls |

### 3.2 Triggering a Pipeline Run

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 130 | Play button on pipeline nodes | Must | **DONE** | Trigger button in DAG detail + second bar |
| 131 | Trigger Run dialog | Must | **DONE** | jsPanel with params |
| 132 | Parameterized trigger form | Must | **DONE** | Typed inputs from DAG params schema |
| 133 | Airflow Param type support | Must | **DONE** | Number, text, checkbox, dropdown |
| 134 | Pre-filled defaults | Must | **DONE** | From Param default values |
| 135 | "Run as Pipeline" from notebook | Nice | **DONE** | Rocket button in notebook bar triggers project DAG with Hydra config |
| 136 | Immediate tree update | Nice | **DONE** | Auto-refresh after trigger |

### 3.3 Monitoring Pipeline Execution

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 137 | Live run status in tree | Must | **DONE** | pipeline:status Socket.IO events |
| 138 | Task status icons | Must | **DONE** | Color-coded icons per state |
| 139 | Skipped task visualization | Nice | **DONE** | Handled in state icon mapping |
| 140 | Tree auto-refresh during runs | Must | **DONE** | 4s polling interval |
| 141 | Task duration and timing | Nice | **DONE** | Start time + duration in tree labels |
| 142 | Run history under DAG | Nice | **DONE** | History table with state, timing, MLflow link |
| 143 | "Load more" historical runs | Nice | **NOT DONE** | Shows up to 50 |
| 144 | Failure highlighting | Must | **DONE** | Red icons + state label |

### 3.4 Inspecting Task Logs

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 145 | Inline log viewer | Must | **DONE** | Dark terminal-style panel |
| 146 | Read-only terminal view | Must | **DONE** | Pre-formatted with colors |
| 147 | Python traceback highlighting | Nice | **PARTIAL** | Basic display; no pattern-specific highlighting |
| 148 | "Jump to error" button | Nice | **DONE** | Error lines highlighted red, auto-scroll to first error in task log |
| 149 | Copy log action | Nice | **DONE** | Copy button in task log viewer |
| 150 | "Retry" button in log viewer | Nice | **DONE** | Retry button for failed/upstream_failed tasks, calls clearTaskInstances API |

### 3.5 Scheduling Recurring Pipeline Runs

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 151 | Schedule display on DAG | Must | **DONE** | Via timetable_summary from API |
| 152 | Next scheduled run display | Must | **DONE** | next_dagrun shown in detail |
| 153 | Schedule editor widget | Nice | **DONE** | Cron text input with Set/Clear |
| 154 | Cron validation | Nice | **PARTIAL** | No client-side validation; Airflow validates |
| 155 | Visual cron builder | Nice | **DONE** | Preset cron buttons (@hourly, @daily, @weekly, etc.) in schedule section |
| 156 | Schedule saves to DAG | Nice | **DONE** | Via Airflow Variables pattern |
| 157 | Next runs preview | Nice | **NOT DONE** | |
| 158 | Pause/unpause toggle | Nice | **DONE** | Button in DAG detail with tree update |
| 159 | Paused indicator | Nice | **DONE** | Orange pause icon in tree |

### 3.6 Data-Aware Pipeline Triggering

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 160 | Dataset trigger display | Nice | **DONE** | DVC tracked files shown in trigger panel for the DAG's project |
| 161 | "Last triggered by" event | Nice | **NOT DONE** | |
| 162 | Manual dataset event trigger | Nice | **NOT DONE** | |
| 163 | Dataset lineage view | Nice | **NOT DONE** | Knowledge Graph will address this |

### 3.7 Parameterized Training Runs

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 164 | Config-parameterized trigger | Must | **DONE** | Hydra params in trigger form |
| 165 | Config forwarding to tasks | Must | **DONE** | Via DAG run conf |
| 166 | Config in run history | Nice | **DONE** | Conf shown in run detail card |
| 167 | Template runs (saved configs) | Nice | **DONE** | Covered by Hydra templates + "Load Last Run Config" + "Promote Best" |
| 168 | Re-run from template | Nice | **NOT DONE** | |

### 3.8 Multi-Project Pipeline Overview

| # | Feature | Priority | Status | Notes |
|---|---------|----------|--------|-------|
| 169 | Top-level Pipelines section | Nice | **DONE** | Shows all DAGs across projects |
| 170 | Pipeline summary table | Nice | **PARTIAL** | DAG list with status; no aggregated table with timing |
| 171 | Health indicators on Pipelines | Nice | **DONE** | Colored health dot on Pipelines root (green/red/blue) |
| 172 | Quick actions from summary | Nice | **NOT DONE** | |

---

## 5. Features Beyond Specifications

These features were built but NOT in any of the four spec documents:

| Feature | Phase | Impact |
|---------|-------|--------|
| Experiment Snapshots (create/restore/fork) | 3 | High - immutable reproducibility records |
| Run Leaderboard (sortable, CSV export) | 3 | High - champion selection workflow |
| Experiment Reports (Word/Markdown with charts) | 3 | High - automated documentation |
| Knowledge Graph Service (entity-relationship navigation) | 4 | High - unified discovery layer |
| Undock/dock panels (notebooks, files, services) | 1B | Medium - UX enhancement |
| Terminal escape hatch (PTY with auth) | 1B | Medium - safety net for CLI operations |
| File upload (auth-gated, multi-file) | 1B | Medium - basic file management |
| Service iframe navigation (back/forward/refresh/home) | 2 | Low - convenience |
| Mounts compose auto-generation | 2 | Medium - simplified deployment |
| DVC-aware delete and rename | 1B | Medium - prevents orphaned .dvc files |
| ECharts migration (replaced Plotly 4.3MB) | 1B | Low - performance |
| FontAwesome 7.2.0 upgrade | 2 | Low - more icons |
| MinIO bucket auto-creation | 2 | Low - prevents first-run errors |

---

## 6. Priority Gaps for Tutorial #2 (2026-03-29)

### Must-Have Gaps (highest priority)

| # | Feature | Document | Effort | Status |
|---|---------|----------|--------|--------|
| 86 | Config selector in notebook bar | Hydra | **M** | **DONE** |
| 87 | Config injection into kernel | Hydra | **M** | **DONE** |
| 119 | New DAG from template (right-click) | Airflow | **S** | **DONE** |
| 31 | Active run indicator in notebook bar | MLflow | **S** | **DONE** |

### Should-Have Gaps (medium priority)

| # | Feature | Document | Effort |
|---|---------|----------|--------|
| 88 | Config as CLI overrides | Hydra | **S** |
| 94 | Config search in MLflow (filter by values) | MLflow | **M** |
| 117 | Config template for new pipeline runs | Hydra | **S** |
| 135 | "Run as Pipeline" from notebook bar | Airflow | **M** |
| 149 | Copy log action | Airflow | **S** |
| 150 | "Retry" button in log viewer | Airflow | **S** |

### Nice-to-Have (lower priority)

All remaining items are nice-to-have and can be deferred to Final delivery or beyond.

---

## 7. Update Log

| Date | Change |
|------|--------|
| 2026-03-21 | Initial assessment against all 4 spec documents. 196 total requirements identified. |
| 2026-03-21 | T-4.R1+R2 done: Hydra config selector + kernel injection. Hydra 24/39 (64%). |
| 2026-03-21 | T-4.R3 done: New DAG from template. Airflow 38/55 (73%). |
| 2026-03-21 | T-4.R4 done: Active run indicator. ALL MUST-HAVE GAPS CLOSED. Coverage: 127/196 (65%), must-have ~92%. |

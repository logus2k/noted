# noted Knowledge Graph - Design Document

## Document Information

| Field | Value |
|-------|-------|
| Document | Knowledge Graph Design |
| Project | noted - Integrated MLOps Platform |
| Version | 1.0 |
| Date | 2026-03-21 |
| Status | Draft |
| Related | Vision v1.3, Scope v1.3, Plan v1.5, 3D DAG Visualizer spec |

---

## 1. Purpose

Transform the 3D visualization from a single-purpose DAG viewer into a **navigable Knowledge Graph** - a visual command center where every entity in the noted ecosystem (projects, notebooks, runs, data, configs, models, pipelines) is discoverable, connected, and explorable.

The Knowledge Graph serves two goals:
1. **Exploration** - start from any entity and traverse its relationships to understand dependencies, lineage, and impact
2. **Search** - find any entity by name, property, tag, or keyword across the entire project

---

## 2. Entities

Every object managed by noted is a graph entity. Each entity has a type, a unique ID, a label, and a set of properties.

### 2.1 Entity Types

| Type | Source System | Icon | Color | Description |
|------|--------------|------|-------|-------------|
| `project` | Explorer | clipboard-list | green | A project or mount root directory |
| `notebook` | File system | file-code | amber | A Jupyter notebook (.ipynb) |
| `file` | File system | file | grey | Any non-notebook file (Python, YAML, etc.) |
| `experiment` | MLflow | vial | purple | An MLflow experiment (container for runs) |
| `run` | MLflow | circle-play | blue | An MLflow training run |
| `snapshot` | MLflow tags | camera | gold | A snapshot-tagged run (immutable record) |
| `model` | MLflow Registry | brain | violet | A registered model |
| `model_version` | MLflow Registry | cube | violet | A specific model version |
| `data_file` | DVC | database | teal | A DVC-tracked data file |
| `data_version` | DVC / git log | clock-rotate-left | teal-dark | A specific version of a tracked data file |
| `config` | Hydra | sliders | blue-light | A Hydra configuration (resolved) |
| `config_group` | Hydra | layer-group | blue-light | A config group (model, data, etc.) |
| `config_option` | Hydra | file-code | blue-light | A config option within a group (gru.yaml, lstm.yaml) |
| `dag` | Airflow | diagram-project | orange | An Airflow DAG definition |
| `dag_task` | Airflow | square | orange-light | A task within a DAG |
| `dag_run` | Airflow | play | orange | A DAG execution instance |
| `environment` | Venv manager | cube | green-light | A Python virtual environment |
| `tag` | User-defined | tag | pink | A user-assigned tag (key-value) |

### 2.2 Entity Properties

Each entity carries a properties dict with type-specific metadata:

```json
// Run entity
{
  "id": "run:abc123",
  "type": "run",
  "label": "gru_live_metrics_test",
  "properties": {
    "status": "FINISHED",
    "start_time": "2026-03-20T15:33:00Z",
    "duration_ms": 63800,
    "metrics": {"test_mae_c": 2.04, "val_loss": 0.098},
    "params": {"model_type": "GRU", "epochs": 30},
    "is_snapshot": true,
    "snapshot_branch": "snapshot/jena_gru_v2_001"
  }
}

// Data file entity
{
  "id": "data:jena_climate.csv",
  "type": "data_file",
  "label": "jena_climate_2009_2016.csv",
  "properties": {
    "size": 43164220,
    "current_hash": "959915f05bfa...",
    "versions_count": 3,
    "tracked_by": "DVC"
  }
}
```

---

## 3. Relationships

Relationships are directed edges between entities. Each relationship has a type, a source entity, a target entity, and optional properties.

### 3.1 Core Relationship Types

| Relationship | Source -> Target | Description |
|-------------|-----------------|-------------|
| `contains` | project -> notebook, file, dag, config | Project contains files |
| `produces` | run -> model_version | Training produced a model |
| `belongs_to` | run -> experiment | Run is part of experiment |
| `uses_data` | run -> data_version | Run trained on this data version |
| `uses_config` | run -> config | Run used this resolved config |
| `executed_by` | run -> dag_run | Run was triggered by a pipeline |
| `snapshot_of` | snapshot -> run | Snapshot captures this run |
| `version_of` | data_version -> data_file | Version belongs to this file |
| `version_of` | model_version -> model | Version belongs to this model |
| `promoted_to` | model_version -> alias | Version has this alias (@champion) |
| `defined_in` | dag -> file | DAG code lives in this file |
| `has_task` | dag -> dag_task | DAG contains this task |
| `depends_on` | dag_task -> dag_task | Task dependency |
| `executed_as` | dag -> dag_run | DAG was executed as this run |
| `parameterized_by` | dag, run -> config | Config used for parameterization |
| `runs_in` | notebook -> environment | Notebook uses this venv |
| `tagged_with` | any -> tag | Entity has this tag |
| `derived_from` | experiment -> snapshot | New experiment forked from snapshot |
| `code_at` | snapshot -> git_commit | Snapshot's code state |
| `scheduled_as` | dag -> schedule | DAG's cron schedule |

### 3.2 Relationship Properties

```json
{
  "source": "run:abc123",
  "target": "data:sha256:959915f...",
  "type": "uses_data",
  "properties": {
    "dvc_file": "data/jena_climate.csv.dvc",
    "hash": "959915f05bfa..."
  }
}
```

---

## 4. Perspective Views

The graph can be viewed through different lenses depending on user intent. Each perspective defines which entity types are **primary hubs** (large, central nodes), which are **secondary** (smaller, peripheral), and which relationships are emphasized.

### 4.1 View Definition Structure

A view is defined as a set of rules:

```json
{
  "name": "Lineage",
  "description": "Trace how data flows from raw files to deployed models",
  "primary_entities": ["data_file", "run", "model_version"],
  "secondary_entities": ["config", "dag_run", "snapshot"],
  "hidden_entities": ["environment", "file", "config_group", "config_option"],
  "emphasized_relationships": ["uses_data", "produces", "uses_config", "executed_by"],
  "layout": "hierarchical_left_to_right",
  "color_by": "entity_type",
  "size_by": null
}
```

### 4.2 Built-in Perspectives

#### Lineage View
**Question answered:** "How did this model get produced? What data and config were used?"

- **Primary hubs:** Data Files, Runs, Model Versions
- **Emphasized edges:** uses_data, produces, uses_config, executed_by
- **Layout:** hierarchical left-to-right (data -> config -> run -> model)
- **Color:** by entity type
- **Best for:** tracing reproducibility, understanding provenance

#### Performance View
**Question answered:** "Which runs performed best? How do they compare?"

- **Primary hubs:** Runs, Snapshots
- **Emphasized edges:** belongs_to, snapshot_of, uses_config
- **Layout:** force-directed, clustered by experiment
- **Color:** by metric value (gradient from red=worst to green=best)
- **Size:** by primary metric magnitude
- **Best for:** identifying best runs, comparing experiments

#### Versioning View
**Question answered:** "What changed between versions? Which version is current?"

- **Primary hubs:** Data Versions, Model Versions, Snapshots
- **Emphasized edges:** version_of, snapshot_of, uses_data
- **Layout:** timeline (left=oldest, right=newest)
- **Color:** by recency (brighter=newer)
- **Best for:** understanding evolution, finding regressions

#### Pipeline View
**Question answered:** "What does the pipeline do? Which tasks succeeded/failed?"

- **Primary hubs:** DAGs, DAG Tasks, DAG Runs
- **Emphasized edges:** has_task, depends_on, executed_as, executed_by
- **Layout:** hierarchical (dagre), internal task structure visible
- **Color:** by task state (success/running/failed)
- **Best for:** monitoring execution, debugging failures

#### Project Overview
**Question answered:** "What does this project contain? What's the big picture?"

- **Primary hubs:** Project, Experiments, DAGs, Models
- **Emphasized edges:** contains, belongs_to, defined_in
- **Layout:** radial (project at center, categories around)
- **Color:** by entity type
- **Best for:** onboarding, getting oriented in a new project

#### Tag-Based View
**Question answered:** "Show me everything related to this concept/tag."

- **Primary hubs:** Tags (user selects which)
- **Emphasized edges:** tagged_with
- **Layout:** force-directed, clustered by tag
- **Color:** by tag
- **Best for:** custom categorization, finding related work

### 4.3 Custom Views

Users can create custom views by selecting:
- Which entity types to show/hide
- Which relationship types to emphasize
- Layout algorithm (force-directed, hierarchical, radial, timeline)
- Color-by property (type, status, metric value, recency, tag)
- Size-by property (metric value, file size, run count, version count)

Custom views are saved per project in `.noted/graph_views/`.

### 4.4 View Switching

The 3D panel has a view selector (dropdown or tabs) that switches between perspectives. The transition is animated - nodes that exist in both views smoothly reposition, new nodes fade in, removed nodes fade out.

---

## 5. Search

### 5.1 Search Scope

A global search bar queries across all entity types:

| Query | Matches |
|-------|---------|
| "GRU" | Runs with GRU in name/params, configs with GRU option, models with GRU |
| "jena_climate" | Data files, DVC tracked files, runs that used this data |
| "champion" | Model versions with @champion alias |
| "val_loss < 0.1" | Runs where val_loss metric is below 0.1 |
| "#experiment-batch-1" | All entities tagged with "experiment-batch-1" |
| "2026-03-20" | Runs, DAG runs, snapshots from that date |

### 5.2 Search Index

The search index is built from:
- Entity labels and property values (text match)
- Tag keys and values (exact and prefix match)
- Metric values (numeric comparison)
- File paths and names (path match)
- Notebook cell content (optional, deeper indexing)

### 5.3 Search Results

Results appear as:
1. **Dropdown list** - quick results below the search bar (click to navigate)
2. **Graph centering** - selected result becomes the center of the 3D graph
3. **Highlight** - matching entities glow/pulse in the current graph view

### 5.4 Future: Semantic Search (RAG)

A later enhancement could index:
- Notebook markdown cells and code comments
- Config YAML content
- Run descriptions and annotations
- Model documentation

Using embeddings + vector search (e.g., via ChromaDB or FAISS) for semantic queries like "the experiment where we tried attention mechanisms" or "the data version before we removed outliers."

---

## 6. Tags as Taxonomy

### 6.1 Tag Model

Tags are key-value pairs that can be attached to any entity:

```json
{"key": "stage", "value": "production"}
{"key": "quality", "value": "validated"}
{"key": "team", "value": "research"}
{"key": "milestone", "value": "tutorial-2"}
```

### 6.2 Tag Sources

- **User-defined** - explicitly added via UI (tag button on any entity detail page)
- **Auto-generated** - noted creates tags automatically:
  - `noted.snapshot` on snapshot runs
  - `dvc.data_hash` on runs using DVC data
  - `hydra.config_hash` on runs using Hydra config
  - `airflow.dag_id` on pipeline-triggered runs
- **Inherited** - tags on a project propagate to its children (optional)

### 6.3 Tag-Based Navigation

In the Knowledge Graph:
- Tags appear as nodes connected to their entities
- Clicking a tag shows all entities with that tag
- Multiple tags can be combined (intersection: "show entities tagged BOTH 'production' AND 'validated'")
- Tag clouds show popular tags with size proportional to usage

---

## 7. Backend Architecture

### 7.1 Graph Builder

A `GraphBuilder` class scans all data sources and constructs the entity-relationship graph:

```python
class GraphBuilder:
    def build(self, project_id) -> Graph:
        entities = []
        relationships = []

        # Scan MLflow
        entities += self._scan_experiments(project_id)
        entities += self._scan_runs(project_id)
        entities += self._scan_models(project_id)

        # Scan DVC
        entities += self._scan_data_files(project_id)

        # Scan Hydra
        entities += self._scan_configs(project_id)

        # Scan Airflow
        entities += self._scan_dags(project_id)

        # Scan file system
        entities += self._scan_files(project_id)

        # Build relationships from entity properties
        relationships = self._resolve_relationships(entities)

        return Graph(entities, relationships)
```

### 7.2 API Endpoints

```
GET  /api/graph/{project_id}                    # Full graph (cached)
GET  /api/graph/{project_id}/neighborhood/{entity_id}?hops=2  # N-hop neighborhood
GET  /api/graph/{project_id}/search?q=...       # Text search across entities
GET  /api/graph/{project_id}/views              # List available perspective views
GET  /api/graph/{project_id}/views/{view_name}  # Get view definition
POST /api/graph/{project_id}/views              # Save custom view
POST /api/graph/{project_id}/tags/{entity_id}   # Add tag to entity
```

### 7.3 Caching

The graph is built on first request and cached. Cache invalidation triggers:
- MLflow run created/deleted
- DVC file tracked/untracked
- Git commit
- Airflow DAG parsed
- Tag added/removed

Socket.IO events can notify the frontend to refresh specific subgraphs.

---

## 8. Frontend Architecture

### 8.1 3D Renderer

Reuse and extend `DagVisualizer3D.js`:
- Replace dagre (hierarchical) layout with **force-directed** layout (Three.js built-in or custom)
- Different **node shapes** per entity type (spheres for runs, cubes for data, cylinders for models, etc.)
- **Edge types** visually distinguished (solid for strong relationships, dashed for weak, animated for active)
- **Semantic zoom**: zoom in to see entity details, zoom out to see clusters
- **View transitions**: animated repositioning when switching perspectives

### 8.2 Components

```
KnowledgeGraph3D.js        (~500 lines) - Scene, camera, controls, view management
GraphNodeRenderer.js       (~300 lines) - Node shapes, materials, labels per entity type
GraphEdgeRenderer.js       (~200 lines) - Edge types, animations
GraphInteraction.js        (~250 lines) - Click, hover, focus, search highlight
GraphSearchBar.js          (~150 lines) - Search input, results dropdown, graph centering
GraphViewSelector.js       (~100 lines) - View tabs/dropdown, custom view editor
```

### 8.3 Integration with Explorer

- Every entity in the Explorer tree has a "Show in Graph" action
- The 3D Graph panel can be opened from: Explorer title bar, run detail, model detail, data detail
- Clicking an entity in the 3D graph navigates to its detail in Explorer (bidirectional)

---

## 9. Extensibility

### 9.1 Adding New Entity Types

To add a new entity type:
1. Add a scanner method to `GraphBuilder` (e.g., `_scan_deployments()`)
2. Define icon, color, and shape in the renderer config
3. Define relationship types to existing entities
4. No frontend code changes needed - the renderer handles unknown types gracefully

### 9.2 Adding New Perspectives

To add a new perspective view:
1. Create a JSON view definition (primary/secondary entities, emphasized relationships, layout)
2. Save to `.noted/graph_views/` or register via API
3. The view appears in the selector dropdown automatically

### 9.3 Deriving Dynamic Views

Views can be derived dynamically from queries:
- "Show me everything connected to run X within 3 hops" -> generates a view automatically
- "Show me all runs that used data version Y" -> filters entities and generates a focused view
- "Compare the graphs of experiment A vs experiment B" -> side-by-side or overlaid views

---

## 10. Relationship to Existing Features

The Knowledge Graph does NOT replace existing features. It provides an alternative navigation layer:

| Existing Feature | Knowledge Graph Equivalent |
|-----------------|---------------------------|
| Explorer tree | Hierarchical view of contains/belongs_to relationships |
| Run detail page | Click a run node -> shows same info in detail panel |
| Lineage view (model detail) | Lineage perspective with the model as center |
| Run comparison | Select two run nodes -> opens comparison panel |
| DAG visualization | Pipeline perspective (or expand DAG node in any view) |
| Data version history | Versioning perspective centered on a data file |

The graph is the **unified navigation layer** that connects all these existing views.

---

## 11. Implementation Priority

### Phase 1: Foundation (for Final delivery)
1. GraphBuilder backend (scan all sources, build entities + relationships)
2. Neighborhood API (entity + N hops)
3. 3D renderer with force-directed layout and entity-type shapes
4. Click to navigate, basic search
5. Two built-in views: Lineage, Project Overview

### Phase 2: Search and Tags (post-delivery)
6. Full-text search index
7. Tag CRUD API and UI
8. Tag-based view
9. Performance and Versioning views

### Phase 3: Advanced (future)
10. Custom view editor
11. Animated view transitions
12. RAG-based semantic search
13. Historical graph comparison (graph diff between snapshots)

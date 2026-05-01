# Knowledge Graph Service - Implementation Plan

## Document Information

| Field | Value |
|-------|-------|
| Document | Implementation Plan |
| Date | 2026-03-21 |
| Related | noted_knowledge_graph.md (design), noted_plan.md (Phase 4) |

---

## 1. Container Structure

```
graph/
  Dockerfile                    # Alpine + Python 3.12, minimal
  requirements.txt              # fastapi, uvicorn, requests, pyyaml
  app/
    __init__.py
    main.py                     # FastAPI app, route wiring, startup
    config.py                   # env vars (MLflow URI, Airflow URI, etc.)
    models.py                   # Pydantic models: Entity, Relationship, Graph, View
    graph_builder.py            # Scans all sources, builds entity-relationship graph
    scanners/
      __init__.py
      mlflow_scanner.py         # Scan experiments, runs, models, artifacts
      dvc_scanner.py            # Scan tracked files, versions
      hydra_scanner.py          # Scan config dirs, groups, options
      airflow_scanner.py        # Scan DAGs, tasks, runs
      filesystem_scanner.py     # Scan project files, notebooks
    relationship_resolver.py    # Build edges from entity properties
    graph_cache.py              # In-memory cache with TTL and invalidation
    search_index.py             # Full-text search across entities
    views.py                    # Perspective view definitions and filtering
    routers/
      __init__.py
      graph.py                  # GET /graph/{project_id}, /neighborhood
      search.py                 # GET /search?q=...
      views.py                  # GET/POST /views
      tags.py                   # POST/DELETE /tags
```

---

## 2. Implementation Phases

### Phase A: Container + Models + Basic Graph (Foundation)

**Goal:** Container starts, scans MLflow, returns a basic entity graph.

**Tasks:**

| # | Task | File(s) | Est. |
|---|------|---------|------|
| A.1 | Dockerfile + requirements.txt | graph/Dockerfile, requirements.txt | 15min |
| A.2 | Pydantic models (Entity, Relationship, Graph, View) | app/models.py | 30min |
| A.3 | Config (env vars for all service URIs) | app/config.py | 10min |
| A.4 | MLflow scanner (experiments, runs, snapshots, models) | scanners/mlflow_scanner.py | 1h |
| A.5 | Relationship resolver (cross-entity edge building) | relationship_resolver.py | 1h |
| A.6 | GraphBuilder orchestrator | graph_builder.py | 30min |
| A.7 | Graph cache (in-memory with TTL) | graph_cache.py | 30min |
| A.8 | FastAPI app + graph router | main.py, routers/graph.py | 30min |
| A.9 | Compose integration + noted proxy | docker-compose.yml, serving proxy | 20min |

**Testable outcome:** `GET /api/graph/{project_id}` returns JSON with entities and relationships from MLflow.

### Phase B: Full Scanning (All Sources)

**Goal:** Graph includes all entity types from all sources.

**Tasks:**

| # | Task | File(s) | Est. |
|---|------|---------|------|
| B.1 | DVC scanner (tracked files, versions, hashes) | scanners/dvc_scanner.py | 45min |
| B.2 | Hydra scanner (config dirs, groups, options) | scanners/hydra_scanner.py | 30min |
| B.3 | Airflow scanner (DAGs, tasks, runs) | scanners/airflow_scanner.py | 45min |
| B.4 | Filesystem scanner (project files, notebooks) | scanners/filesystem_scanner.py | 30min |
| B.5 | Update relationship resolver for all entity types | relationship_resolver.py | 45min |
| B.6 | Neighborhood API (entity + N hops) | routers/graph.py | 30min |

**Testable outcome:** Full graph with all entity types. Neighborhood queries work.

### Phase C: Search + Tags

**Goal:** Full-text search and tag-based navigation.

**Tasks:**

| # | Task | File(s) | Est. |
|---|------|---------|------|
| C.1 | Search index builder | search_index.py | 1h |
| C.2 | Search router | routers/search.py | 30min |
| C.3 | Tag CRUD (add/remove/list) | routers/tags.py | 30min |
| C.4 | Tag storage (JSON per project in .noted/tags/) | routers/tags.py | 20min |

**Testable outcome:** `GET /search?q=GRU` returns matching entities. Tags can be added to any entity.

### Phase D: Perspective Views

**Goal:** Built-in views filter and reshape the graph.

**Tasks:**

| # | Task | File(s) | Est. |
|---|------|---------|------|
| D.1 | View model and built-in definitions | views.py | 1h |
| D.2 | View filtering (primary/secondary/hidden entities, emphasized edges) | views.py | 30min |
| D.3 | Views router (list, get, save custom) | routers/views.py | 30min |
| D.4 | Custom view storage (.noted/graph_views/) | routers/views.py | 20min |

**Testable outcome:** `GET /views/lineage` returns filtered graph. Custom views can be saved.

### Phase E: Frontend Integration

**Goal:** 3D graph renders in noted, bidirectional navigation works.

**Tasks:**

| # | Task | File(s) | Est. |
|---|------|---------|------|
| E.1 | Graph proxy router in noted backend | backend/app/routers/graph_proxy.py | 20min |
| E.2 | Three.js scene (redownload, force-directed layout) | frontend/js/KnowledgeGraph3D.js | 2h |
| E.3 | Entity-type node renderer (shapes, colors, labels) | frontend/js/GraphNodeRenderer.js | 1.5h |
| E.4 | Relationship edge renderer | frontend/js/GraphEdgeRenderer.js | 1h |
| E.5 | Interaction (click, hover, focus, navigate to Explorer) | frontend/js/GraphInteraction.js | 1.5h |
| E.6 | Search bar component | frontend/js/GraphSearchBar.js | 45min |
| E.7 | View selector (dropdown + tabs) | frontend/js/GraphViewSelector.js | 30min |
| E.8 | "Show in Graph" action in Explorer | ExplorerPanel.js | 30min |
| E.9 | Graph panel (jsPanel, maximizable, dark theme option) | app.js integration | 30min |

**Testable outcome:** Full 3D graph renders in a floating panel. Click navigates. Search works. Views switch.

---

## 3. Effort Summary

| Phase | Tasks | Est. Total |
|-------|-------|------------|
| A: Foundation | 9 | ~5h |
| B: Full Scanning | 6 | ~3.5h |
| C: Search + Tags | 4 | ~2.5h |
| D: Views | 4 | ~2.5h |
| E: Frontend | 9 | ~8.5h |
| **Total** | **32** | **~22h (~3 days)** |

---

## 4. Dependencies Between Phases

```
A (Foundation) -> B (Full Scanning) -> C (Search + Tags)
                                    -> D (Views)
                                    -> E (Frontend, needs A+B minimum)
```

Phases C and D can run in parallel after B. Phase E needs at least A+B to have data to render.

---

## 5. Technical Decisions

### 5.1 Layout Algorithm

**Force-directed** (default) for most views - entities naturally cluster by connectivity. **Dagre** (hierarchical) for Lineage and Pipeline views where directionality matters. **Radial** for Project Overview.

The layout is computed server-side (graph service sends position hints) or client-side (Three.js force simulation). Server-side is more consistent; client-side is more interactive. Recommend: **client-side** for responsiveness, with server-side position hints for initial placement.

### 5.2 Three.js Strategy

Redownload Three.js for the frontend (same split build from cgad project). Use it only for the Knowledge Graph panel - all other visualizations remain 2D SVG/ECharts.

The Three.js files are loaded dynamically (import on first graph panel open) to avoid blocking the main app.

### 5.3 Graph Size Limits

For projects with many runs (100+), the full graph is too large to render. Strategy:
- Default: show only the last 30 days of runs
- Expand on demand ("Show older runs")
- Neighborhood queries: N-hop from any entity (default: 2 hops)
- Views filter by entity type, further reducing rendered nodes

### 5.4 Cache Invalidation

The graph cache rebuilds on:
- Explicit refresh (user clicks "Refresh Graph")
- TTL expiry (default: 5 minutes)
- Socket.IO event from noted (new run, new model, DVC track, etc.)

The graph service does NOT need Socket.IO itself - it rebuilds the cache when queried and the cache is stale.

### 5.5 No Database

The graph is built from existing data sources (MLflow, DVC, Airflow, filesystem). No additional database. Tags are stored as JSON files in `.noted/tags/`. Custom views in `.noted/graph_views/`. Both are accessible via the noted container's volume mounts.

---

## 6. API Contract

### 6.1 Graph Endpoints (graph service, port 5523)

```
GET  /graph/{project_id}
     ?max_age=300         # Cache TTL in seconds
     -> { entities: [...], relationships: [...], metadata: {...} }

GET  /graph/{project_id}/neighborhood/{entity_id}
     ?hops=2              # Number of relationship hops
     -> { center: {...}, entities: [...], relationships: [...] }

GET  /graph/{project_id}/entity/{entity_id}
     -> { entity: {...}, relationships: [...] }
```

### 6.2 Search Endpoints

```
GET  /search/{project_id}
     ?q=GRU               # Text query
     ?type=run             # Optional type filter
     ?limit=20             # Max results
     -> { results: [{ entity: {...}, score: 0.95, matches: [...] }] }
```

### 6.3 View Endpoints

```
GET  /views/{project_id}
     -> { views: [{ name, description, is_builtin }] }

GET  /views/{project_id}/{view_name}
     -> { view_definition: {...}, filtered_graph: {...} }

POST /views/{project_id}
     { name, description, primary_entities, secondary_entities, ... }
     -> { saved: true }
```

### 6.4 Tag Endpoints

```
GET  /tags/{project_id}
     -> { tags: [{ key, value, entity_count }] }

GET  /tags/{project_id}/entity/{entity_id}
     -> { tags: [{ key, value }] }

POST /tags/{project_id}/entity/{entity_id}
     { key, value }
     -> { added: true }

DELETE /tags/{project_id}/entity/{entity_id}/{key}
     -> { removed: true }
```

### 6.5 Proxy Endpoints (noted backend, prefixed /api/graph/)

All graph service endpoints proxied through noted backend at `/api/graph/*` -> `http://noted-graph:5523/*`.

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Graph too large for browser | Medium | Performance | Limit visible nodes (views, time range, neighborhood). Instanced rendering for 100+ nodes. |
| MLflow/Airflow API slow on scan | Medium | Startup delay | Build graph async on first request. Return partial graph while scanning. Cache aggressively. |
| Three.js dynamic import fails | Low | No graph | Graceful fallback: show entity list as HTML table instead of 3D graph |
| Tag storage conflicts (concurrent writes) | Low | Data loss | File-level locking on tag writes. Tags are append-mostly. |
| Graph service container adds memory | Low | Resource use | Alpine image is ~50MB. Graph cache is proportional to project size (~1MB for 500 entities). |

---

## 8. Success Criteria

- A user can click any entity in Explorer and see it in the 3D graph with its relationships
- Switching perspective views reshapes the graph meaningfully (not just cosmetic)
- Searching "GRU" finds all GRU-related entities across runs, configs, and models
- The graph helps a user answer: "What data and config produced this model?"
- The graph helps a user answer: "Which runs used this data version?"
- Performance: graph renders within 5 seconds for 500 entities

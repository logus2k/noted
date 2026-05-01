# Knowledge Graph - Test Procedure

## Prerequisites

- noted is running with all services including `noted-graph` container
- At least one project with MLflow experiments, DVC-tracked files, Hydra configs, and Airflow DAGs
- Run `docker ps | grep noted-graph` to verify the graph container is running

---

## Part 1: Graph Service Health

### Test 1: Graph service reachable

1. In browser console:
```javascript
fetch('api/graph/health').then(r => r.json()).then(d => console.log(d))
```

**Expected:**
- Returns `{status: "ok", service: "knowledge-graph"}`

### Test 2: Full graph endpoint

1. In browser console (replace project_id):
```javascript
fetch('api/graph/graph/noted-testing').then(r => r.json()).then(d => console.log('Entities:', d.entity_count, 'Rels:', d.relationship_count))
```

**Expected:**
- Returns entity and relationship counts > 0
- Entities include: project, notebooks, experiments, runs, data files, configs, DAGs

---

## Part 2: Opening the Knowledge Graph Panel

### Test 3: Open from menu

1. Click View > Knowledge Graph in the menu bar

**Expected:**
- A jsPanel opens titled "Knowledge Graph"
- Toolbar with: search input, search button, view selector dropdown, refresh button
- Info bar shows "Loading graph..." then entity/relationship counts
- 3D scene renders with colored nodes and connecting edges

### Test 4: Default view (Overview)

1. The panel opens with "Overview" selected by default

**Expected:**
- Project node visible at/near center (green box)
- Connected entities radiate outward: experiments (purple octahedron), DAGs (orange cone), models (violet cylinder)
- Labels visible on nodes
- Orbit controls work: click-drag to rotate, scroll to zoom, right-drag to pan

---

## Part 3: Entity Types and Shapes

### Test 5: Entity type visual distinction

1. Examine the nodes in the 3D scene

**Expected:**
- Different shapes per entity type:
  - Projects, notebooks, files, data files: boxes
  - Runs, snapshots, data versions, config options: spheres
  - Models, model versions, environments: cylinders
  - Experiments, configs: octahedrons
  - DAGs: cones
- Different colors per type (green for projects, blue for runs, teal for data, orange for DAGs, etc.)
- Primary entities (per view) are larger than secondary

### Test 6: Labels readable

1. Zoom in and out, rotate

**Expected:**
- Labels stay above their nodes
- Labels face the camera (billboarded)
- Labels disappear when behind the camera
- Text is readable against the background

---

## Part 4: Interaction

### Test 7: Hover shows detail panel

1. Move mouse over a node

**Expected:**
- Node scales up slightly (1.2x)
- Cursor changes to pointer
- Detail panel appears (top-right) showing entity icon, label, type, and properties
- Panel disappears when mouse leaves the node

### Test 8: Click pins detail panel and focuses

1. Click on a node (e.g., a run)

**Expected:**
- Detail panel stays open (pinned - pin icon turns blue)
- Clicked node and its direct neighbors remain fully visible
- All other nodes fade to near-transparent (10% opacity)
- Edges between non-connected nodes fade

### Test 9: Detail panel draggable

1. With a pinned detail panel open, drag the panel's title bar

**Expected:**
- Panel moves freely within the graph container
- Releasing drops it at the new position

### Test 10: Detail panel resizable

1. Drag the bottom-right corner of the detail panel

**Expected:**
- Panel resizes (both width and height)
- Minimum size enforced (180px wide, 100px tall)

### Test 11: Unpin and close detail panel

1. Click the pin icon (thumbtack) to unpin
2. Move mouse away from the node

**Expected:**
- Panel disappears when mouse leaves
- Alternatively, click X to close and clear focus

### Test 12: Navigate to Explorer from detail panel

1. Click "Open in Explorer" button in the detail panel

**Expected:**
- The corresponding item is activated in the Explorer tree
- The detail page opens for that entity
- The Knowledge Graph stays open (no accidental navigation)

### Test 13: Clear focus

1. Click on empty space (not a node)

**Expected:**
- All nodes return to normal opacity
- Detail panel closes (if not pinned)
- All labels restored

### Test 14: Node dragging

1. Click and drag a node

**Expected:**
- Node follows the mouse
- Orbit controls are disabled during drag
- Connected edges update in real-time

### Test 15: Physics simulation during drag

1. Drag a node away from its cluster

**Expected:**
- Neighbouring nodes gently follow (spring attraction)
- Nearby non-connected nodes push apart (repulsion)
- After releasing, nodes settle into new positions (~1.5 seconds)
- No shaking or oscillation after settling

---

## Part 5: Perspective Views

### Test 11: Switch to Lineage view

1. Select "Lineage" from the view dropdown

**Expected:**
- Graph reloads with filtered entities: mainly data files, runs, model versions
- Hidden entities (files, environments, config options, etc.) disappear
- Emphasized relationships (uses_data, produces, uses_config) shown prominently
- Info bar updates with new entity/relationship count

### Test 12: Switch to Performance view

1. Select "Performance"

**Expected:**
- Primarily runs and snapshots visible
- Clustered by experiment
- Node sizing may vary by metric magnitude

### Test 13: Switch to Pipeline view

1. Select "Pipeline"

**Expected:**
- DAGs, tasks, and DAG runs visible
- Task dependencies shown as edges
- Other entity types hidden

### Test 14: Switch back to Overview

1. Select "Overview"

**Expected:**
- Full project view restored
- All main entity types visible

---

## Part 6: Search

### Test 15: Text search

1. Type "GRU" in the search bar and press Enter

**Expected:**
- Dropdown shows matching entities (runs with GRU in name, configs with GRU option, etc.)
- Each result shows: icon, label, type, relevance score

### Test 16: Click search result

1. Click on a search result

**Expected:**
- Dropdown closes
- Entity is highlighted (pulsing glow) in the 3D scene
- Neighboring entities remain visible, others fade

### Test 17: Metric threshold search

1. Type "val_loss < 0.1" and press Enter

**Expected:**
- Results show runs where val_loss metric is below 0.1
- Each result shows the actual metric value

### Test 18: Tag search

1. Type "#noted.snapshot" and press Enter

**Expected:**
- Results show entities tagged with `noted.snapshot`
- Snapshot runs appear in results

---

## Part 7: Refresh and Cache

### Test 19: Refresh graph

1. Click the refresh button (rotate icon)

**Expected:**
- Graph cache invalidated (POST to /invalidate)
- Graph reloads with fresh data
- Info bar shows "Loading..." then updated counts

### Test 20: Graph reflects changes

1. Run a notebook to create a new MLflow run
2. Click refresh in the Knowledge Graph panel

**Expected:**
- New run entity appears in the graph
- Connected to its experiment via belongs_to edge

---

## Part 8: Edge Cases

### Test 21: Empty project

1. Open Knowledge Graph for a project with no experiments/runs

**Expected:**
- Graph renders with just the project node and files
- No errors

### Test 22: Graph service down

1. Stop the graph container: `docker stop noted-graph`
2. Try to open Knowledge Graph

**Expected:**
- Error shown (503 Service Unavailable or similar)
- No crash in noted

---

## Troubleshooting

- **"Knowledge Graph service not reachable":** Check `docker ps | grep noted-graph`. Restart with compose.
- **Empty graph:** The project may not have experiments/runs. Check that MLflow, Airflow are running.
- **Slow graph load:** First load builds the graph from all sources. Subsequent loads use cache (5 min TTL).
- **Three.js errors:** Check browser console. Ensure `vendor/three/` files exist.
- **Search returns nothing:** The search index is built from entity labels and properties. Check that entities have meaningful labels.
- **View shows no entities:** Some views hide most entity types. Try "Overview" for the fullest view.

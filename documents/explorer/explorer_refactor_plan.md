# ExplorerPanel Refactor Plan

**Status**: Planned (not started)
**Priority**: After Hydra config unification and cockpit design
**Risk**: High - touches every feature surface in the tree

---

## Problem

`ExplorerPanel.js` is 2148 lines and acts as a God Object: DOM manager,
API client, state store, routing engine, and event listener in one class.
Every new node type requires changes in 5+ methods (`_onTreeLazyLoad`,
`_showDetailForNode`, `_buildBreadcrumbs`, `_recolorNode`, click
handlers). This violates the Open-Closed Principle and makes simple
changes require multiple fix iterations.

The view modules in `frontend/js/panels/explorer/` are already extracted
(14 files, ~450KB total), but ExplorerPanel still orchestrates everything
through if/else chains on node key prefixes (30+ prefixes).

---

## Current Architecture

```
ExplorerPanel.js (2148 lines)
  |-- constructor, _buildCtx, _buildElements     (~109 lines)
  |-- _loadTree, _loadApiEndpoints               (~223 lines)
  |-- _onTreeLazyLoad                            (~118 lines)
  |-- _onTreeActivate, _onTreeClick, _onTreeDblClick, _onTreeRender  (~387 lines)
  |-- _recolorVisibleRows, _recolorNode          (~57 lines)
  |-- _buildBreadcrumbs                          (~391 lines)
  |-- _showDetailForNode + inline detail views   (~391 lines)
  |-- Detail tab openers                         (~147 lines)
  |-- Navigation helpers                         (~391 lines)
  |-- Utilities                                  (~92 lines)
```

Node key prefixes handled (30+):
pfile, mfile, pdir, mdir, project, mount, env, runtime, lang,
experiment, mlrun, mlart-cat, mlart, dag, dagrun, dagtask,
hydraconf, hydragroup, hydraopt, datacol, datafile, bucket,
s3folder, s3obj, doc, doccat, skill, skillref, regmodel,
regversion, api, root-*

Each prefix appears in 4-8 methods, creating an N x M matrix of
special cases.

---

## Target Architecture

### Strategy/Registry Pattern for Node Handlers

Replace if/else chains with a registry of handler objects. Each handler
owns one domain and implements a standard interface.

```
interface NodeHandler {
  // Return true if this handler manages the given key
  canHandle(key: string): boolean

  // Return children for lazy-loaded nodes (or null if not lazy)
  getLazyChildren(key: string, ctx: object): Promise<array|null>

  // Render detail view into the detail element
  showDetail(key: string, detailEl: HTMLElement, ctx: object): void

  // Return breadcrumb segments
  getBreadcrumbs(key: string, ctx: object): array

  // Return icon class and color for tree rendering
  getNodeStyle(key: string): { icon?: string, color?: string }

  // Handle double-click (open file, toggle expand, etc.)
  onDblClick(key: string, node: object, ctx: object): void

  // Handle single-click activation
  onActivate(key: string, node: object, ctx: object): void
}
```

### File Structure

```
frontend/js/panels/
  explorer/
    NodeRegistry.js          -- Loops handlers, finds match by key
    handlers/
      ProjectHandler.js      -- project:, pdir:, pfile:, mdir:, mfile:, mount:
      ExperimentHandler.js   -- experiment:, mlrun:, mlart-cat:, mlart:
      PipelineHandler.js     -- dag:, dagrun:, dagtask:
      EnvironmentHandler.js  -- env:, runtime:, lang:
      DataHandler.js         -- datacol:, datafile:, bucket:, s3folder:, s3obj:
      RegistryHandler.js     -- regmodel:, regversion:
      ServingHandler.js      -- api:
      AssistantHandler.js    -- skill:, skillref:
      DocsHandler.js         -- doc:, doccat:
      HydraHandler.js        -- config/ folder Hydra-aware rendering
    tree/
      TreeBuilder.js         -- Builds initial tree data from API calls
      TreeController.js      -- Wunderbaum setup, event -> handler dispatch
    ExplorerView.js          -- Pure DOM: breadcrumb bar, title bar, status tags
    ExplorerState.js         -- API fetches, cached data, shared state
  ExplorerPanel.js           -- Thin orchestrator (~150-200 lines)
```

### ExplorerPanel becomes a thin orchestrator

```javascript
class ExplorerPanel {
  constructor(container, callbacks) {
    this._registry = new NodeRegistry();
    this._state = new ExplorerState();
    this._view = new ExplorerView(container);
    this._tree = new TreeController(container, this._registry, this._state);

    // Register all handlers
    this._registry.register(new ProjectHandler());
    this._registry.register(new ExperimentHandler());
    // ... etc
  }
}
```

Each event becomes a one-liner delegation:

```javascript
// Instead of 130-line _showDetailForNode with 20+ branches:
_showDetailForNode(node) {
  const handler = this._registry.findHandler(node.key);
  if (handler) handler.showDetail(node.key, this._view.detailEl, this._ctx);
  else this._view.clearDetail();
}

// Instead of 360-line _buildBreadcrumbs with 30+ branches:
_buildBreadcrumbs(node) {
  const handler = this._registry.findHandler(node.key);
  return handler ? handler.getBreadcrumbs(node.key, this._ctx) : [];
}
```

---

## Migration Strategy

### Phase 1: Extract one handler as proof-of-concept

Pick the simplest domain (e.g., DocsHandler for `doc:` / `doccat:`)
and extract it into the handler interface. Wire it through a minimal
NodeRegistry alongside the existing if/else chains. This validates the
pattern without breaking anything.

**Risk**: Low. One handler extracted, fallback to existing code for all
other node types.

### Phase 2: Extract remaining handlers one at a time

Each handler extraction is an independent, testable change:
1. Create handler file implementing the interface
2. Move the relevant branches from _onTreeLazyLoad, _showDetailForNode,
   _buildBreadcrumbs, _recolorNode, click handlers
3. Register in NodeRegistry
4. Remove old branches from ExplorerPanel
5. Test that domain end-to-end

Order (easiest to hardest):
1. DocsHandler (doc:, doccat:) - simplest, few interactions
2. AssistantHandler (skill:, skillref:) - small, self-contained
3. DataHandler (datacol:, datafile:) - moderate
4. StorageHandler (bucket:, s3folder:, s3obj:) - moderate
5. ServingHandler (api:) - small
6. RegistryHandler (regmodel:, regversion:) - moderate
7. EnvironmentHandler (env:, runtime:, lang:) - complex (status, kernel)
8. ExperimentHandler (experiment:, mlrun:, mlart*) - complex (tabs)
9. PipelineHandler (dag:, dagrun:, dagtask:) - complex (tabs, logs)
10. ProjectHandler (project:, pdir:, pfile:, mount:, mdir:, mfile:) -
    most complex, most interactions, extract last

### Phase 3: Extract Tree and View layers

After all handlers are extracted, ExplorerPanel's remaining code is:
- Wunderbaum setup and event wiring -> TreeController.js
- DOM construction and breadcrumb rendering -> ExplorerView.js
- API fetches and state -> ExplorerState.js

### Phase 4: Cleanup

- Remove _ctx mega-object, replace with focused dependency injection
- Remove inline DOM construction from handlers (use ExplorerHelpers
  or a small component library)
- Add JSDoc types for the handler interface

---

## Existing Extracted Modules (already done)

These files contain the detail view rendering logic, already separated:

| File | Size | Domain |
|------|------|--------|
| ExplorerContextMenu.js | 43KB | Context menus for all node types |
| ExplorerProjectViews.js | 58KB | Project/notebook/file views |
| ExplorerMlflowViews.js | 55KB | MLflow experiment/run/artifact views |
| ExplorerPipelineViews.js | 101KB | DAG pipeline views |
| ExplorerRegistryViews.js | 42KB | Model registry views |
| ExplorerEnvViews.js | 30KB | Environment/runtime views |
| ExplorerHydraViews.js | 29KB | Hydra config views |
| ExplorerSnapshotViews.js | 34KB | Snapshot views |
| ExplorerServingViews.js | 22KB | Model serving views |
| ExplorerDataViews.js | 13KB | Data collection views |
| ExplorerDocsViews.js | 11KB | Document views |
| ExplorerStorageViews.js | 11KB | S3 storage views |
| ExplorerHelpers.js | 4KB | Shared UI helpers |
| ExplorerExternalViews.js | 1KB | External module bridge |

These modules are called from ExplorerPanel's if/else chains. The
refactor wraps each module inside a handler that implements the standard
interface, then the handler calls the existing view module internally.
This means the view rendering code does NOT need to be rewritten -
only the dispatch logic changes.

---

## Constraints

- Each phase must be independently deployable and testable
- No Big Bang rewrite - incremental extraction
- Existing view modules (Explorer*Views.js) stay as-is initially
- The _ctx shared object stays until Phase 4 (handlers receive it)
- Must not block cockpit design or manual page work
- ExplorerPanel.js line count target: under 300 lines after Phase 3

---

## Dependencies

- Hydra config/Configuration unification must be done BEFORE this
  refactor (removes hydraconf:/hydragroup:/hydraopt: virtual nodes,
  reducing the prefixes to handle)
- Cockpit design may introduce new node types or change existing ones;
  coordinate timing to avoid rework

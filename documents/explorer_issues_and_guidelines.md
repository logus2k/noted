# Explorer Tree - Issues and Guidelines

## Document Information

| Field | Value |
|-------|-------|
| Last Updated | 2026-03-22 |
| Component | `frontend/js/panels/ExplorerPanel.js` |
| Library | Wunderbaum (mar10.Wunderbaum) |
| Purpose | Post-mortem and reference guide for recurring Explorer tree bugs |

---

## 1. Architecture Overview

The Explorer sidebar tree uses Wunderbaum with these key components:

- **Tree data** (`treeData` array, line ~311): defines all root sections and their initial children
- **Event handlers** (lines ~433-437):
  - `render` -> `_onTreeRender(e)` - icon colors, decorations, folder icon swap
  - `lazyLoad` -> `_onTreeLazyLoad(e)` - async data fetch for lazy nodes
  - `activate` -> `_onTreeActivate(e)` - detail pane rendering
  - `click` -> `_onTreeClick(e)` - expand/collapse toggle, navigation
  - `dblclick` -> `_onTreeDblClick(e)` - file/notebook opening

---

## 2. Node Types: Static vs Lazy

This is the #1 source of recurring bugs. Every root section falls into one of two categories:

### Static Children Nodes
Defined with `children: [...]` at init time. Children are known upfront or loaded manually.

| Section | Key | Pattern |
|---------|-----|---------|
| Projects | `root-projects` | `children: projects.map(...)` |
| Mounts | `root-mounts` | `children: mounts.map(...)` |
| Virtual Environments | `root-envs` | `children: runtimeNodes` |
| Knowledge Base | `root-docs` | `children: docCategoryNodes` |
| APIs | `root-apis` | `children: [placeholder]`, loaded on click via `addChildren()` |

### Lazy Nodes
Defined with `lazy: true` and NO `children`. Wunderbaum auto-calls `lazyLoad` on expand.

| Section | Key | Loader |
|---------|-----|--------|
| Data | `root-data` | `loadDataCollections()` |
| Experiments | `root-experiments` | `loadExperiments()` |
| Models | `root-models` | `loadModels()` |
| Storage | `root-storage` | `loadStorageBuckets()` |
| Pipelines | `root-pipelines` | `loadPipelines()` |

### CRITICAL RULES

1. **NEVER use `resetLazy()` on static-children nodes.** It permanently breaks the node - children disappear and won't come back.

2. **NEVER combine `children` + `lazy: true`.** Wunderbaum breaks when both are set.

3. **`lazy: true` can silently fail.** The `lazyLoad` handler returns data but Wunderbaum may not render it. This happened with the APIs section - converted to static + `addChildren()` to fix.

4. **When in doubt, use static + `addChildren()`.** It is always reliable. The pattern:
   ```js
   // In click handler:
   node.removeChildren();
   loadFn().then(nodes => {
       node.addChildren(nodes);
       node.setExpanded(true);
   });
   ```

5. **To refresh a static node:** `node.removeChildren()` then `node.addChildren(newChildren)`.

6. **To refresh a lazy node:** `node.resetLazy(); node.setExpanded(true)`.

---

## 3. Click Handler Rules

The `_onTreeClick(e)` handler (line ~763) controls expand/collapse behavior.

### NEVER make `_onTreeClick` async

Making it `async` breaks ALL tree clicks because Wunderbaum's click pipeline does not handle Promise returns. The tree becomes unresponsive - no expand, no collapse, no navigation.

**Wrong:**
```js
async _onTreeClick(e) {
    const nodes = await this._loadSomething(); // BREAKS EVERYTHING
}
```

**Correct:**
```js
_onTreeClick(e) {
    this._loadSomething().then(nodes => {
        node.addChildren(nodes);
        node.setExpanded(true);
    });
}
```

### Every expandable key must be in the click handler

If a root section's key (e.g., `root-apis`) is NOT listed in the `_onTreeClick` if-chain, clicking that section does nothing - no expand, no collapse. When adding a new section, ALWAYS add its key to the click handler.

### Return values matter

- `return true` - let Wunderbaum handle the event (used for expander arrow clicks)
- `return false` - stop event propagation (used after custom handling)
- No return / `return undefined` - default behavior continues

---

## 4. Detail Pane Rules

The detail pane has two nested elements:

- `this._detailRoot` - outer container, class `explorer-detail-pane`
- `this._detailEl` - inner content area, class `explorer-detail-content`

### NEVER write to `_detailRoot.innerHTML`

Setting `_detailRoot.innerHTML = ''` destroys `_detailEl`. After this, every other detail renderer that writes to `_detailEl` writes to an orphaned DOM element - content is invisible.

**Wrong (breaks all subsequent detail views):**
```js
_showMyDetail() {
    this._detailRoot.innerHTML = '';  // DESTROYS _detailEl
    this._detailRoot.appendChild(content);
}
```

**Correct:**
```js
_showMyDetail() {
    clearActionBar(this._detailRoot);  // Only clears action bar, preserves _detailEl
    this._detailEl.innerHTML = '';     // Clears content inside _detailEl
    this._detailEl.appendChild(content);
}
```

### The `ctx.detailEl` in external views

External view modules (ExplorerDocsViews, ExplorerMlflowViews, etc.) receive a `ctx` object containing `ctx.detailEl` which references `this._detailEl`. If `_detailEl` is destroyed (by writing to `_detailRoot.innerHTML`), all external view renders silently fail.

---

## 5. Activate Handler Rules

The `_onTreeActivate(e)` handler (line ~681) renders the detail pane when a node is selected.

### Key prefix matching order matters

The handler uses `else if` chains. If a key matches an earlier condition, later conditions never fire. Be careful with broad prefixes:

- `key.startsWith('api:')` matches `api:serving:model1`
- `key.startsWith('api-')` matches `api-idle`, `api-error`, `api-status`
- But `api-idle` does NOT match `key.startsWith('api:')` (hyphen vs colon)

When adding new node types, verify the key prefix doesn't accidentally match existing patterns.

### Container nodes (sections) must be in the isContainer check

Line ~687: `const isContainer = key === 'root-projects' || ... || key === 'root-apis'`

If a root key is missing from this check, clicking it may trigger unwanted navigation in the center pane.

---

## 6. Adding a New Explorer Section - Checklist

When adding a new root section to the Explorer tree:

- [ ] Add to `treeData` array with unique `key: 'root-xxx'`
- [ ] Choose static (`children: []`) or lazy (`lazy: true`) - prefer static
- [ ] If static: add click handler in `_onTreeClick` with `addChildren()` pattern
- [ ] If lazy: add handler in `_onTreeLazyLoad` returning array of nodes
- [ ] Add key to the click handler's expandable keys list (line ~787)
- [ ] Add key to the `isContainer` check (line ~687)
- [ ] Add key to `_onTreeRender` type detection (line ~488)
- [ ] Add activate handler in `_onTreeActivate` for root and child keys
- [ ] Detail renderers MUST use `this._detailEl`, NEVER `this._detailRoot.innerHTML`
- [ ] Use `clearActionBar(this._detailRoot)` to clean action buttons
- [ ] Verify child node key prefixes don't collide with existing prefixes
- [ ] Add icon color to the `colors` map in `_onTreeRender` (line ~509)
- [ ] Test: expand, collapse, re-expand, click children, then navigate to other sections

---

## 7. Bug History

| Date | Bug | Root Cause | Fix |
|------|-----|-----------|-----|
| 2026-03-21 | Projects tree broke after creating new project | Used `resetLazy()` on static-children node | Use `addChildren()` instead |
| 2026-03-21 | Mounts tree broke after refresh | Same - `resetLazy()` on static node | Same fix, 6+ iterations |
| 2026-03-22 | APIs section won't expand (no children appear) | `lazy: true` silently failed | Converted to static + `addChildren()` in click handler |
| 2026-03-22 | APIs section won't expand (no chevron) | `children: []` empty = no expander | Added placeholder child node |
| 2026-03-22 | "Serving not reachable" when expanding APIs | `fetch('/api/serving/health')` - leading slash resolves to wrong URL behind reverse proxy | Use relative path `'api/serving/health'` |
| 2026-03-22 | Knowledge Base detail stuck on APIs content | `_showApisRootDetail` used `_detailRoot.innerHTML = ''` which destroyed `_detailEl` | Use `_detailEl.innerHTML` + `clearActionBar()` |
| 2026-03-22 | Entire tree stops expanding/collapsing | Added `async` to `_onTreeClick` | Never make click handler async; use `.then()` |

---

## 8. Fetch URL Rules

All `fetch()` calls in frontend code MUST use relative paths (no leading slash):

- **Correct:** `fetch('api/serving/health')` - resolves relative to page URL base
- **Wrong:** `fetch('/api/serving/health')` - resolves to domain root, breaks behind reverse proxy

The app is served at `https://domain.com/noted/`, so:
- `fetch('api/...')` -> `https://domain.com/noted/api/...` (correct)
- `fetch('/api/...')` -> `https://domain.com/api/...` (wrong, 404)

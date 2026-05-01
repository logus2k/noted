# Hydra Configuration Unification and Time-Machine Plan

| Field | Value |
|-------|-------|
| Last Updated | 2026-04-12 |
| Status | Proposed (awaiting approval before implementation) |
| Authors | Design session between user and Claude |
| Supersedes | Virtual "Configuration" tree node system (removed 2026-04-11) |

---

## 1. Background

### 1.1 What already shipped

On 2026-04-11, the virtual "Configuration" tree node (`hydraconf:` /
`hydragroup:` / `hydraopt:` keys) was removed from the Explorer.
Projects now expose their real `config/` folder as the single source
of truth for Hydra configuration files.

A per-project "Hydra View" toggle was added: right-click a `config/`,
`conf/`, or `configs/` folder at the project root and choose "Enable
Hydra View". The setting is stored in `.noted/settings.json` under
the project. When enabled:

- The folder icon changes to the Hydra SVG.
- Clicking the folder shows the Hydra Configuration detail view
  instead of the default directory listing.
- Clicking direct subfolders (groups like `config/model/`) shows the
  Hydra group detail view.
- YAML files inside still open in the standard editor.

The Configuration Composer UI was redesigned to a side-by-side layout
(left: controls, overrides, templates, source files, hash; right:
resolved YAML with syntax highlighting). The notebook bar still shows
a Hydra icon button to open the Composer.

### 1.2 What is broken today

Discovery during the manual-page-2 review surfaced that the current
Composer UX is fundamentally disconnected from the notebook state:

1. **Overrides are ghost data**. The Composer has text inputs for
   every schema key (the "Overrides" section). The user can type
   `epochs: 10`, see the preview YAML update, close the Composer,
   and run a cell - and `cfg.training.epochs` will be 50 (the
   default). Overrides only affect the modal's preview; they never
   reach notebook metadata or the kernel composition path.

2. **No visible "currently active" config**. The notebook bar shows
   the Hydra icon whether the notebook is using pure defaults or
   custom selections. The user cannot tell at a glance what `cfg`
   will contain.

3. **Two places of truth for selections**. Group selections live in
   `notebook.metadata.noted.hydra_selections` AND in
   `_selectedHydraConfig` on the NotebookEditor instance. They can
   drift. Overrides have no place of truth at all.

4. **The Composer modal blocks the notebook**. Floating jsPanel on
   top, can't see both at once.

5. **Templates are the only way to capture non-default state**. Every
   experiment variant requires naming a template, saving it, loading
   it. Way too much ceremony for quick iteration.

6. **Config lineage is fragile**. MLflow runs get a `hydra_config_hash`
   tag, but not the resolved YAML itself. If someone edits a base file
   later, the hash becomes an orphaned label - there is no way to
   reconstruct the config that actually ran unless a full snapshot
   happened. Snapshots are orthogonal to the core training workflow
   and should not be required for basic reproducibility.

---

## 2. Design Decisions (Locked)

All 24 items below are agreed between user and Claude and are treated
as requirements for this plan. They are not subject to renegotiation
during implementation - any deviation requires explicit approval.

### 2.1 Composition Model

**D1. Option B composition**: The `config/` folder contains templates.
The notebook metadata is the equivalent of a Hydra CLI command -
it specifies group selections and overrides. Composition happens at
run time by merging templates + selections + overrides. The Composer
writes to notebook metadata only. The Composer never edits YAML files.

**D2. Overrides persistence**: Both `group_selections` and `overrides`
must persist to `notebook.metadata.noted.hydra_selections`. The
current broken behavior where overrides live only in the DOM of the
open Composer is a bug to fix.

**D3. Selections schema in notebook metadata**:
```json
{
  "metadata": {
    "noted": {
      "notebook_uid": "<uuid-v4>",
      "hydra_baseline_source": "project://config/" | "mlflow://<run_id>",
      "hydra_selections": {
        "group_selections": { "model": "gru_baseline", "data": "default" },
        "overrides": { "training.epochs": "10", "model.units": "256" }
      }
    }
  }
}
```

`hydra_baseline_source` defaults to `project://config/` if absent.
`hydra_selections` defaults to empty if absent (Hydra uses its own
defaults list from `config.yaml`).

### 2.2 Per-Run Artifact Logging

**D4. Self-contained run bundle**: Every cell execution with an active
Hydra config logs a self-contained `hydra/` bundle to MLflow for that
run. The bundle contains:
- All baseline YAML files, preserving directory structure (config/,
  config/model/gru.yaml, config/training/default.yaml, etc.)
- `selections.json` (the group_selections + overrides used)
- `resolved.yaml` (the full composed output)
- The resolved config hash is tagged on the run as
  `noted.hydra_config_hash`

**D5. No dependency chains**: Every run re-logs everything from
scratch. If a run points at an MLflow-sourced baseline, the backend
still re-uploads those baseline files as artifacts of the new run.
Deleting any run never affects any other run. This is the single
source of truth guarantee.

**D6. Bundle location in MLflow**: `hydra/` at the run root. Matches
the existing snapshot_manager pattern.

### 2.3 User-Controlled Baseline Lifecycle

**D7. No "promote to local" action**: Users create and edit baselines
in `config/` by hand. noted does not automate baseline creation from
past runs. This respects user freedom and avoids vendor lock-in.

**D8. Resurrection is a manual copy-out**: If a user wants a past
run's config to become the new baseline, they manually download the
bundle from MLflow (or copy files from the cache) and place them in
`config/`. This is their explicit choice and their responsibility.

### 2.4 Snapshots Are Orthogonal

**D9. Snapshots are not required for lineage**: The per-run `hydra/`
bundle provides everything needed to reproduce a run's config.
Snapshots remain a separate feature that bundles additional things
(data versions, environment, etc.), but they are not a prerequisite
for the work in this plan.

### 2.5 Composer Time Machine

**D10. Mode toggle at the top of the Composer**:
```
[ Local Baseline ] [ Experiment Run ]
   ^ toggle (one active at a time)

[ Experiment dropdown ] [ Run dropdown ]
   ^ both disabled when Local Baseline is active
   ^ both enabled when Experiment Run is active
```

**D11. Local Baseline mode** (default):
- Schema read from `config/` on disk
- Selections pre-populated from notebook metadata or Hydra defaults
- Apply writes selections to notebook metadata with source =
  `project://config/`

**D12. Experiment Run mode**:
- Experiment dropdown lists experiments tagged with the current project
- Run dropdown lists runs from the selected experiment that have a
  `hydra/` artifact bundle
- Runs without bundles do not appear (no legacy concern - this is
  pre-production)
- When user picks a run, backend fetches the archived bundle into the
  cache and the Composer replaces its schema with the archived
  version
- Selections pre-populated from the archived `selections.json`
- Apply writes selections (with any user tweaks) to notebook metadata
  with source = `mlflow://<run_id>`

**D13. Toggling mode is preview-only**: Toggling between Local
Baseline and Experiment Run in the Composer does not modify notebook
metadata. Only clicking Apply commits the change.

**D14. Composer opens in the mode matching notebook metadata**: If
the notebook has `hydra_baseline_source: mlflow://...`, the Composer
opens in Experiment Run mode with that experiment/run pre-selected
and the archived bundle loaded. Otherwise, Local Baseline mode.

**D15. Read-only YAML files in Experiment Run mode**: When the
Composer is in Experiment Run mode, YAML files from the archived
bundle cannot be edited through noted's file tree. They do not exist
on disk. To iterate on templates, the user switches back to Local
Baseline mode (or manually copies files out per D8).

### 2.6 Drift and Validation

**D16. Drift is impossible by construction**: Because
`hydra_baseline_source` pins to an immutable MLflow artifact, and
because cells compose against whatever the pointer specifies,
recomposition always produces the same result. There is no "warning,
base files changed" scenario because the base files for a
MLflow-sourced baseline are frozen.

**D17. Composition validation on load**: When the Composer loads an
archived bundle and recomposes using the archived selections, the
resulting hash must equal the archived `resolved.yaml`'s hash. A
mismatch indicates a bug in noted's composition logic. This is
internal validation - users do not see it unless something is wrong,
in which case the error is surfaced with the expected vs actual
hashes.

### 2.7 Caching

**D18. In-memory cache only**: The cache for MLflow-fetched bundles
lives in backend process memory. No disk cache. No LRU. Keyed by
`(notebook_uid, run_id)` so that two notebooks pointing at the same
run each have their own cache entry (allowing independent
invalidation).

**D19. Cache population timing**: When the user picks a run in the
Composer's Experiment Run dropdown, the backend fetches the bundle
at that moment. By the time the user runs a cell, the cache is warm.
On backend restart, the cache is empty; the next cell execution in an
MLflow-sourced notebook triggers a fresh fetch. Fetches are tiny (KB
range) so re-fetching is fast.

**D20. Notebook UID**: Notebooks do not have a stable platform ID
today. This plan introduces `notebook.metadata.noted.notebook_uid`
(UUID v4, set once on first save if missing). This UID is used as a
cache key and survives file renames.

### 2.8 Failure Modes

**D21. Fail loud on missing or unreachable baselines**: If a notebook
points at `mlflow://<run_id>` and the run has been deleted, or MLflow
is unreachable, or the `hydra/` artifact is missing from the run, cell
execution fails with a clear error message. The error shows:
- What the notebook metadata says (the pointer value)
- What went wrong (run not found, MLflow unreachable, artifact
  missing)
- A suggestion (switch to Local Baseline via Composer, or retry)

There is no fallback path. The user must explicitly resolve the
issue. No silent degradation.

### 2.9 UI Affordances

**D22. Notebook bar baseline badge**: When a Hydra config is active
for a notebook, the notebook info bar shows a small clickable label:
- `BASELINE` (small letters) when source is `project://config/`.
  Clicking opens the most recent (executing or completed) MLflow run
  for this notebook in the Explorer, if any.
- `RUN <first-6-chars-of-run-id>` when source is `mlflow://<run_id>`.
  Clicking opens that Experiment Run in the Explorer tree.

The badge is derived live from notebook metadata.

**D23. Per-notebook independence**: Baseline source is stored
per-notebook. Multiple notebooks in the same project can point at
different baselines (local, or different MLflow runs) and execute in
parallel without interference. This is the noted promise applied to
config sources.

**D24. Apply semantics in Experiment Run mode**: Clicking Apply in
Experiment Run mode updates notebook metadata to:
- `hydra_baseline_source: mlflow://<run_id>` (pinned to the run)
- `hydra_selections: {group_selections, overrides}` (reflecting any
  user tweaks made in the Composer)

The baseline pointer is independent of selections. The user can pin
to run X while running with slightly different selections than what
run X used.

---

## 3. Architecture Changes

### 3.1 Backend

**hydra_manager.py** becomes source-aware. The current API
(`get_schema(project_id)`, `compose(project_id, overrides,
group_selections)`) is replaced by a source abstraction:

```
class HydraSource:
    # Discriminated by "type"
    pass

class LocalSource(HydraSource):
    project_id: str
    # Reads config/ from get_registry().resolve(project_id)

class MlflowSource(HydraSource):
    run_id: str
    notebook_uid: str  # For cache keying
    # Reads from in-memory cache keyed by (notebook_uid, run_id)

class HydraManager:
    def get_schema(self, source: HydraSource) -> dict: ...
    def compose(
        self,
        source: HydraSource,
        group_selections: dict | None,
        overrides: dict | None
    ) -> dict: ...

    # New: cache population
    def load_mlflow_bundle(self, run_id: str, notebook_uid: str) -> None: ...
    def evict_cache_entry(self, run_id: str, notebook_uid: str) -> None: ...

    # New: bundle download for logging
    def read_local_bundle_files(self, project_id: str) -> dict[str, str]: ...
    def read_cached_bundle_files(self, run_id: str, notebook_uid: str) -> dict[str, str]: ...
```

**New: `backend/app/managers/hydra_source.py`** containing the
source abstraction and the in-memory cache manager. The cache is a
module-level dict keyed by `(notebook_uid, run_id)` with values
being a dict of `relative_path -> file_content`.

**hydra.py (router)** gets new endpoints:
- `POST /api/hydra/load-bundle` - body: `{run_id, notebook_uid}` -
  fetches MLflow bundle into cache, returns `{schema, selections,
  resolved_yaml, hash}`
- `GET /api/hydra/experiments/{project_id}` - lists experiments for
  the project (tagged with project name)
- `GET /api/hydra/runs/{project_id}/{experiment_id}` - lists runs
  from the experiment that have a `hydra/` artifact bundle
- Existing endpoints (`schema/`, `compose/`, `group/`, `templates/`,
  `view/`) are updated to accept a source descriptor in the request
  body or query params.

**auto_instrumentation.py** gets extended to log the full `hydra/`
bundle on every cell execution that has an active Hydra config. The
bundle assembly reuses the existing helper from `snapshot_manager.py`
(lines 158-167). We extract the bundle-logging logic into a shared
helper in `hydra_manager.py` so both the snapshot code path and the
per-run code path call the same function.

**notebook_manager.py / project_registry.py**: first-save handler
ensures `notebook.metadata.noted.notebook_uid` exists (generate UUID
v4 if missing). This happens on any save operation.

### 3.2 Frontend

**ExplorerHydraViews.js** - `_showComposePanel()` gains:
- Mode toggle at the top (`Local Baseline` | `Experiment Run`)
- Experiment + Run dropdowns (disabled in Local mode)
- Baseline source label (e.g., "Baseline: Local" or "Baseline: Run
  ns3jfh")
- Load-into-Composer flow when Experiment Run mode is picked
- Overrides are properly persisted on Apply (current bug fix)

**NotebookEditor.js** - `_loadHydraConfig()`, `_onConfigChange()`,
`setHydraSelections()` updated to:
- Read and write `hydra_baseline_source` from metadata
- Read and write `overrides` from metadata (current bug fix)
- Pass the baseline source in every `executeCell()` payload

**NotebookEditor.js** (info bar) - new small clickable badge showing
`BASELINE` or `RUN <first-6-chars>`. Clickable to Explorer.

### 3.3 Data storage

- `notebook.metadata.noted.notebook_uid`: new, UUID v4
- `notebook.metadata.noted.hydra_baseline_source`: new, defaults to
  `project://config/`
- `notebook.metadata.noted.hydra_selections.overrides`: new (currently
  the structure exists but is not populated by the Composer)

All three are additive metadata fields. Existing notebooks without
them still work - the backend falls back to the defaults documented
in D3.

---

## 4. Regression Risk Analysis

This section enumerates every known surface the changes touch and the
mitigation for each.

### 4.1 Notebook cell execution path

**Risk**: Breaking cell execution for notebooks that have no Hydra
config at all.

**Mitigation**:
- The composition path is only invoked when
  `notebook.metadata.noted.hydra_selections` exists (or a legacy
  `_selectedHydraConfig` is set). Notebooks without config are
  unaffected.
- Backend test: `test_cell_execution_without_hydra_config` must pass
  both before and after the change.
- Manual test: run a cell in a vanilla Python notebook (no config/
  folder in the project). Must execute exactly as today.

**Risk**: Breaking cell execution for existing notebooks that have
the current broken format (group_selections only, no overrides).

**Mitigation**:
- The selections format is additive. Missing `overrides` key defaults
  to empty dict. Missing `notebook_uid` generates one on first save.
- Missing `hydra_baseline_source` defaults to `project://config/`.
- The backend must accept all three legacy states.

### 4.2 Existing MLflow run records

**Risk**: Old runs without `hydra/` artifact bundles cause breakage
when the Composer tries to list them.

**Mitigation**:
- The run dropdown in Experiment Run mode filters out runs without
  a `hydra/` artifact. Old runs are invisible. No error.
- The experiment dropdown filters out experiments that have zero
  runs with bundles.

### 4.3 DAG trigger panel Hydra selectors

**Risk**: The DAG trigger panel in `ExplorerPipelineViews.js` has its
own Hydra group selectors (lines 1251-1345) that call
`api/hydra/schema/{project_id}` and `api/hydra/compose`. These calls
use the old API signature.

**Mitigation**:
- The new backend endpoints are backward-compatible: the old URL
  `api/hydra/schema/{project_id}` continues to work and is treated as
  `LocalSource(project_id)`.
- The old `POST /api/hydra/compose` with `{project_id, overrides,
  group_selections}` continues to work as `LocalSource(project_id)`.
- No changes needed to the DAG trigger panel in this phase. It stays
  local-only. Adding MLflow baseline selection to DAG triggers is a
  future enhancement, out of scope.

### 4.4 Snapshot manager

**Risk**: The snapshot code in `snapshot_manager.py` already logs
`hydra_resolved_config.yaml` as an MLflow artifact under `snapshot/`.
If both snapshot and auto-instrumentation log hydra bundles, there
might be duplication or conflicts.

**Mitigation**:
- Snapshot logs to `snapshot/hydra_resolved_config.yaml` (single file
  under the snapshot folder).
- Auto-instrumentation logs to `hydra/` (folder at run root containing
  full bundle).
- Different paths, different purposes. Both can coexist.
- The shared helper in `hydra_manager.py` can be used by both to
  assemble the resolved YAML, preventing divergent logic.

### 4.5 Notebook metadata writes

**Risk**: Adding `notebook_uid` to existing notebooks on first save
modifies every saved notebook, even if the user didn't intend a
config change. Git diff churn.

**Mitigation**:
- UID is added once and never changes. The first save after this
  feature ships will dirty the notebook metadata on every notebook in
  the user's project. This is a one-time cost.
- Document the expected diff in the User Manual so users aren't
  surprised.
- Consider: add UIDs lazily only when the notebook actually uses a
  Hydra config, instead of every notebook. This limits the blast
  radius to Hydra-using notebooks.
- **Decision**: lazy - only add UID when a Hydra config is loaded for
  the first time. Non-Hydra notebooks are never touched.

### 4.6 Composer UI

**Risk**: The Composer is used from two entry points - the notebook
bar button and the config folder detail view. Changes to the Composer
affect both.

**Mitigation**:
- Both entry points call `openComposePanel(projectId, selections,
  onSelectionsChange)`. The new Composer continues to accept the same
  arguments.
- The detail-view entry point does not pass a notebook UID (because
  it is not tied to a notebook). In that context, Experiment Run
  mode is still available but the "Apply to notebook" button is
  grayed out with a tooltip: "Open a notebook first to apply
  selections".

**Risk**: Switching the Composer between modes with unsaved changes
loses data.

**Mitigation**:
- When the user toggles from one mode to another with uncommitted
  changes (dropdowns changed from loaded state), show a confirmation
  dialog: "You have unsaved changes. Discard and switch modes?".
- On confirm, switch. On cancel, stay.

### 4.7 In-memory cache leak

**Risk**: The cache grows unbounded if users switch between many
runs in the Composer without ever restarting the backend.

**Mitigation**:
- Bundles are tiny (KB per entry). Even 10,000 cached bundles is
  under 100 MB.
- Add a simple cap: e.g., max 500 entries, evict oldest on overflow.
- Cache is cleared on backend restart.

### 4.8 Error paths in auto-instrumentation

**Risk**: Adding bundle logging to every cell execution might slow
down cell execution or fail non-critically and cause the cell to fail.

**Mitigation**:
- Bundle logging happens asynchronously after the cell output is
  delivered (fire-and-forget background task).
- If logging fails, the error is logged to backend logs but the cell
  execution result is not affected.
- This is the only place in the plan where "fire-and-forget" is
  acceptable because the primary operation (cell execution with
  injected `cfg`) has already succeeded by the time logging begins.
- The user can always re-run the cell if they need the bundle logged.
- If logging consistently fails, surface a warning banner in the
  notebook info bar: "Hydra lineage logging is failing - MLflow may
  be unreachable".

---

## 5. Implementation Plan

Work is broken into milestones. Each milestone is independently
shippable. Ordering respects dependencies.

### Milestone 1: Bug fixes and foundation (small, low-risk)

**Goal**: Fix the broken overrides persistence. Introduce
`notebook_uid`. Stabilize the metadata schema. No new features.

**Tasks**:

M1.1. Add `notebook_uid` lazy generation in notebook save path
(backend/app/managers/notebook_manager.py). Only set when missing AND
when the notebook already has or gains Hydra config state.

M1.2. Update `NotebookEditor._onConfigChange()` to read existing
`hydra_selections.overrides` from metadata and pre-populate the
Composer inputs.

M1.3. Update `NotebookEditor.setHydraSelections()` to write both
`group_selections` AND `overrides` to metadata. (Currently only
`group_selections` is persisted.)

M1.4. Update `_showComposePanel()` in ExplorerHydraViews.js so that
Apply (the Compose button, or any input change if auto-compose is
enabled) also writes overrides to metadata via the new callback.

M1.5. Add `hydra_baseline_source` field to metadata, defaulting to
`project://config/`. All existing code paths read this field and
fall back to the default if missing.

M1.6. Backend: accept `hydra_baseline_source` in the cell execution
payload. Currently the compose path ignores it. Wire it through so
composition is source-aware, even though only LocalSource is
supported in this milestone.

**Regression test**:
- Open an existing notebook with group_selections set. Run a cell.
  `cfg.model.type` must still return the selected value.
- Open a notebook with no Hydra config. Run a cell. Must execute
  normally.
- Open a notebook, change an override in Composer, click Apply, close
  Composer, reopen. The override must persist.
- Run a cell after changing an override. The kernel must receive the
  overridden value in `cfg`.

**Exit criteria**: Overrides are persisted end-to-end. No new
features visible to the user yet.

### Milestone 2: Per-run artifact bundle logging (small-medium, low-risk)

**Goal**: Every cell execution with active Hydra config logs a full
`hydra/` bundle to MLflow. No UI changes.

**Tasks**:

M2.1. Extract bundle assembly into a shared helper in
`hydra_manager.py`:
```python
def assemble_bundle_files(
    self,
    project_id: str,
    group_selections: dict,
    overrides: dict,
) -> dict[str, bytes]:
    """Return a dict of relative paths to file content for all
    files in the bundle: config/ tree + selections.json + resolved.yaml.
    """
```

M2.2. Extend `auto_instrumentation.py` to call
`_log_hydra_bundle(run_id, project_id, group_selections, overrides)`
after MLflow run creation. This uses the shared helper from M2.1.

M2.3. Update `snapshot_manager.py` to use the same shared helper for
its own bundle logging, so there is one implementation of the bundle
assembly logic.

M2.4. Bundle logging is fire-and-forget (see 4.8 Mitigation). Failures
log to backend but do not fail the cell.

**Regression test**:
- Run a cell with Hydra config. Check the MLflow run - must have a
  `hydra/` folder with all config files, `selections.json`, and
  `resolved.yaml`.
- Take a snapshot. Check the MLflow run - must have both
  `snapshot/hydra_resolved_config.yaml` and `hydra/...` (both code
  paths fire).
- Run a cell without Hydra config. MLflow run must not have a
  `hydra/` folder (or have one with only empty content - decide based
  on simplicity).

**Exit criteria**: Every Hydra-enabled cell run has a complete,
self-contained bundle in MLflow. Lineage is now reproducible without
snapshots.

### Milestone 3: Source abstraction in backend (medium, contained risk)

**Goal**: Refactor `hydra_manager.py` to accept `HydraSource`. Old
URL endpoints continue to work via adapter. In-memory cache
introduced.

**Tasks**:

M3.1. Create `backend/app/managers/hydra_source.py` with
`LocalSource` and `MlflowSource` classes.

M3.2. Create `backend/app/managers/hydra_cache.py` with the
in-memory cache module. Keyed by `(notebook_uid, run_id)`. Max 500
entries, FIFO eviction.

M3.3. Refactor `HydraManager.get_schema` and `HydraManager.compose`
to accept a `HydraSource` parameter. The original single-arg
signatures continue to work via a LocalSource wrapper.

M3.4. Add `HydraManager.load_mlflow_bundle(run_id, notebook_uid)`
which fetches the bundle from MLflow into the cache.

M3.5. Update the `POST /api/hydra/compose` endpoint to accept an
optional `baseline_source` field in the request body. If present and
non-default, use `MlflowSource`. Otherwise `LocalSource`. Old clients
that omit the field work unchanged.

M3.6. Add `GET /api/hydra/experiments/{project_id}` and
`GET /api/hydra/runs/{project_id}/{experiment_id}` endpoints for the
Composer's dropdowns.

M3.7. Add `POST /api/hydra/load-bundle` endpoint.

**Regression test**:
- Existing test suite for `hydra_manager` and `hydra_router` must
  pass unchanged.
- New test: `test_compose_with_mlflow_source` end-to-end.
- New test: `test_cache_eviction_on_overflow`.
- New test: `test_cache_keyed_by_notebook_uid` (two notebooks with
  same run_id have isolated entries).
- Manual: all current Composer behavior unchanged in Local Baseline
  mode.

**Exit criteria**: Backend supports both sources. Old frontend paths
continue to work. No UI changes.

### Milestone 4: Composer Time Machine UI (medium, contained risk)

**Goal**: The Composer gains the mode toggle and Experiment/Run
dropdowns. Users can load past runs into the Composer.

**Tasks**:

M4.1. Add mode toggle at the top of `_showComposePanel()` in
ExplorerHydraViews.js.

M4.2. Add experiment and run dropdowns. Disabled in Local Baseline
mode.

M4.3. Wire the experiment dropdown to `GET
/api/hydra/experiments/{project_id}` (filtered to current project).

M4.4. Wire the run dropdown to `GET
/api/hydra/runs/{project_id}/{experiment_id}` (only runs with hydra
bundles).

M4.5. On run selection, call `POST /api/hydra/load-bundle`. The
response includes the archived schema, selections, and resolved YAML.
The Composer replaces its local-mode state with the loaded state.

M4.6. Composition validation (D17): after loading, call
`compose()` with the archived selections and verify the hash matches
the archived `resolved.yaml`'s hash. If mismatch, display an error
banner with expected vs actual hashes.

M4.7. Switching modes with uncommitted changes shows a confirmation
dialog (4.6 Mitigation).

M4.8. Apply in Experiment Run mode writes
`hydra_baseline_source: mlflow://<run_id>` AND the selections to
notebook metadata.

M4.9. Composer opens in the mode matching the notebook's metadata
(D14).

M4.10. Baseline source label at the top of the Composer ("Baseline:
Local" or "Baseline: Run <6 chars>").

**Regression test**:
- All Milestone 1-3 regression tests still pass.
- Load a past run into the Composer. The schema and selections
  correspond to the archived state.
- Load a past run, click Apply. The notebook's metadata now has
  `hydra_baseline_source: mlflow://...`.
- Re-open the Composer for that notebook. It opens in Experiment Run
  mode with the correct run pre-selected.
- Run a cell in the notebook. The kernel receives `cfg` composed
  from the archived files. The MLflow run for this new execution has
  its own complete `hydra/` bundle with those same archived files.
- Switch Composer back to Local Baseline, click Apply. Notebook now
  uses local config/ again.

**Exit criteria**: Users can travel back to any past run's config
and continue iterating from there. All values persisted honestly.

### Milestone 5: Notebook bar badge and polish (small, low-risk)

**Goal**: Surface the active baseline source in the notebook info
bar. Enable one-click navigation to the source run.

**Tasks**:

M5.1. Add a small clickable label to the notebook info bar next to
the Hydra icon. Text is `BASELINE` (small letters) or
`RUN <6-chars>`.

M5.2. In `BASELINE` state, clicking opens the most recent executing
or completed MLflow run for this notebook in the Explorer tree, if
any.

M5.3. In `RUN ...` state, clicking opens that run in the Explorer
tree.

M5.4. Label is updated live when notebook metadata changes.

**Regression test**:
- Notebook with local baseline: label shows `BASELINE`.
- Notebook with MLflow baseline: label shows `RUN <6-chars>`.
- Click behavior works in both states.

**Exit criteria**: Active baseline is visually obvious at all times.

### Milestone 6: User Manual Page 2 rewrite (small, documentation)

**Goal**: Update Page 2 of the User Manual to describe the new flow
accurately.

**Tasks**:

M6.1. Rewrite the "Use the config in your notebook" section to
describe the baseline source model honestly.

M6.2. Add a new section "Time travel: loading past runs into the
Composer".

M6.3. Update the UX friction table.

M6.4. Sync `data/documents/files/manual_02_configuring_experiment.md`
with `documents/user-manual/02-configuring-experiment.md`.

**Exit criteria**: The manual accurately reflects the shipped
behavior.

---

## 6. Testing Strategy

### 6.1 Backend unit tests

- `test_hydra_manager_local_source_compose` (existing, must pass)
- `test_hydra_manager_mlflow_source_compose` (new)
- `test_hydra_cache_eviction` (new)
- `test_hydra_cache_keyed_by_notebook_uid` (new)
- `test_bundle_assembly_includes_all_files` (new)
- `test_auto_instrumentation_logs_bundle_to_mlflow` (new)
- `test_compose_fails_loud_when_mlflow_unreachable` (new)

### 6.2 Integration tests

- Open a notebook, run a cell without Hydra config. Must work.
- Open a notebook, enable Hydra View, run a cell with defaults. Must
  work. MLflow run must have the `hydra/` bundle.
- Open the Composer, change an override, Apply, run a cell. Kernel
  receives the overridden value.
- Open the Composer, switch to Experiment Run mode, pick a run,
  Apply, run a cell. Kernel receives the archived values.
- Delete the MLflow run a notebook is pointing at. Run a cell. Must
  fail loud with a clear error.

### 6.3 Manual tests

- Create 3 notebooks in the same project. Point each at a different
  baseline. Run cells in all 3 in parallel. Each must get its own
  config.
- Disable Hydra View for the project. Re-enable it. Existing notebook
  metadata must still be valid.
- Kill the backend during Composer use. Restart. Re-open the
  Composer. Must re-fetch the bundle transparently (on user-facing
  first interaction in Experiment Run mode).

---

## 7. Rollback Plan

Each milestone is behind its own code path and is independently
revertable via `git revert`. The notebook metadata additions are
additive - rolling back the backend still allows old notebooks to
work because the added fields are optional.

**Point of no return**: Milestone 2 (bundle logging) changes the MLflow
storage layout (new `hydra/` folder on every run). Rolling back after
Milestone 2 means runs logged during the milestone still have the new
folder, which is harmless (unused by old code). No data loss.

**Migration out**: If the whole plan is rolled back, users can still
access bundles directly through the MLflow UI or API. No data is
trapped inside noted.

---

## 8. Out of Scope

- **DAG trigger panel baseline source selection**: Airflow triggers
  continue to use local config only. Adding MLflow baseline to DAG
  triggers is a future enhancement.
- **Cross-project run references**: Experiment Run mode only shows
  experiments from the current project. Cross-project loading (e.g.,
  "load a run from a different project as my baseline") is not
  supported.
- **Automatic baseline promotion**: Per D7, noted does not promote
  past runs to local baselines. Users do this by hand.
- **Hydra group composition strategies beyond the defaults list**:
  noted's Composer supports Hydra's `defaults` list semantics. Other
  advanced Hydra features (e.g., structured configs, instantiation
  via `hydra.utils.instantiate`) are out of scope for the Composer UI
  but continue to work in the kernel because `cfg` is a regular
  OmegaConf DictConfig.
- **Snapshot integration changes**: Snapshots continue to work as
  today. The only change is that snapshot bundle assembly is routed
  through the shared helper, which is a refactor, not a behavior
  change.

---

## 9. Acceptance Criteria for the Whole Plan

A user can:

1. Create a Hydra config folder and enable Hydra View via context menu.
2. Open a notebook and see the Composer correctly reflect the current
   state.
3. Change group selections AND overrides in the Composer. Apply.
4. Close the Composer and run a cell. The kernel receives `cfg` with
   both the group selections AND the overrides honored.
5. Open MLflow UI for the run. Find a `hydra/` folder containing the
   full config bundle.
6. Open another notebook in the same project and point it at the
   previous run via Composer's Experiment Run mode.
7. Apply and run a cell. The kernel receives the archived config
   (not the current local config).
8. Switch back to Local Baseline and run a cell. The kernel now
   receives the current local config.
9. Delete the MLflow run. Try to use the notebook that pointed at it.
   See a clear error message. Switch to Local Baseline to recover.
10. Open the notebook after all of this. The baseline label in the
    notebook bar correctly shows the current state and is clickable.

If all 10 of these hold, the plan is done.

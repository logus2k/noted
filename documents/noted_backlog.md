# noted Engineering Backlog

Small known-gap items discovered during development that are not blocking shipped milestones. Bigger architectural items live in their own plan docs (`serving_worker/`, `hydra/`, `noted_plan.md`). This file is for narrower fixes that would otherwise slip through.

Each entry must include: what the problem is, where in the code, why it matters, and what the fix looks like.

---

## MLflow soft-delete foot-gun (logged 2026-04-15)

**Problem**. When the user deletes an MLflow experiment via noted's UI (or directly through the MLflow web UI), MLflow does a *soft-delete*: the experiment is moved to trash with `lifecycle_stage=deleted`. MLflow then refuses to let you `create_experiment` or `set_experiment` with the same name. The only ways out are `restore_experiment` or running `mlflow gc` server-side to permanently purge.

This hits at the worst possible moment: the user clicks Run Manager, Run Manager's `RUN_START_CODE` prelude calls `mlflow.set_experiment("jena_weather")` which raises, and the outer `try: ... except Exception: pass` in [`backend/app/managers/auto_instrumentation.py`](../backend/app/managers/auto_instrumentation.py) (RUN_START_CODE) swallows the failure. The prelude never completes, but subsequent code (`_get_dataset_logging_code` etc.) calls `mlflow.set_tag(...)` without an active run, which makes MLflow's fluent API auto-create a run in the Default experiment with a random name like `rogue-toad-262`. Result: a Frankenstein run in the wrong experiment with some tags set and some missing, and no error propagated to the UI.

This caused a failed Test 2 during Tutorial 3 demo preparation on 2026-04-15 after the user had deleted the `jena_weather` experiment to start from a clean slate.

### Fix 1 - Remove the exception swallow in RUN_START_CODE

Current code in [`backend/app/managers/auto_instrumentation.py`](../backend/app/managers/auto_instrumentation.py) (RUN_START_CODE constant):

```python
RUN_START_CODE = """\
try:
    import mlflow as __mlf_run
    if __mlf_run.active_run() is not None:
        __mlf_run.end_run()
    __mlf_run.set_experiment("{experiment_name}")
    __mlf_run.start_run(run_name="{run_name}")
    __mlf_run.set_tag("instrumentation", "experiments")
    del __mlf_run
except Exception:
    pass
"""
```

The `except Exception: pass` is the forbidden "swallow the failure" pattern. Fix options:

- Remove the try/except entirely. A failed prelude is a critical error that should halt cell execution with a visible message.
- Or re-raise after printing a clear error to the kernel's output so the user sees it in the notebook.

Recommendation: remove the try/except. Same applies to `RUN_END_CODE` and `_get_dataset_logging_code` / `_get_config_hash_logging_code` if they have similar patterns.

Effort: ~15 minutes.

### Fix 2 - Detect deleted experiment at run-start time, offer restore or purge

Intercept in [`backend/app/main.py`](../backend/app/main.py) `on_run_execute` handler, immediately after `experiment_name` is resolved. Call `MlflowClient().get_experiment_by_name(experiment_name)` and branch:

- `None` (never existed) → proceed, MLflow will create it.
- `lifecycle_stage == "active"` → proceed.
- `lifecycle_stage == "deleted"` → halt. Emit a `run:conflict` socket event with `{experiment_name, experiment_id, reason: "experiment_soft_deleted"}`. Frontend shows a modal:

  > The experiment `jena_weather` is in the MLflow trash.
  >
  > - **Restore and continue** - brings the old experiment back, your run will join its history.
  > - **Permanently purge and create fresh** - deletes the trashed experiment for good and starts a new one with the same name.
  > - **Cancel run**

  On user choice, frontend re-emits `run:execute` with a `resolve_conflict` field that the backend handles by either calling `restore_experiment(id)` or invoking `mlflow gc` against the tracking server's backend store URI, then proceeding with the run.

**Subtlety**. `mlflow gc` is a CLI command that runs against the tracking store directly, not via the client API. noted needs to shell out to `mlflow gc --experiment-ids X --backend-store-uri ...` inside the `mlflow` container (via `docker exec` or the container's CLI endpoint). Shell-out is simpler than re-implementing the store-level cleanup in Python.

**UI placement**. Modal lives in the Run Manager panel. Blocks the run dispatch until the user chooses. Not a toast — the user needs to make an informed choice, not dismiss a notification.

Effort: ~50-100 lines across `backend/app/main.py`, `backend/app/managers/execution_bridge.py` (optional caching of the check), `frontend/js/panels/RunManagerPanel.js`, new socket event plumbing, and the `mlflow gc` shell-out path. Roughly 2-3 hours total.

### Why both fixes, not just one

- **Fix 1 alone**: the user sees a clear cell execution error "Cannot set experiment X: experiment is in deleted lifecycle stage". They understand what's wrong but still have to manually restore it via CLI.
- **Fix 2 alone**: works for the Run Manager path but doesn't help if a future code path calls `mlflow.set_experiment(...)` outside RUN_START_CODE. The swallowed exception would still produce a Frankenstein run.
- **Both together**: the UX layer catches 99% of cases at the right moment, and the underlying code fails loudly when something slips past. No more hidden-success-into-wrong-experiment.

---

## Generic model output rendering for the Serving demo client (logged 2026-04-15)

**Problem**. The demo client at `iscte/jena_client/` currently renders a prediction response as a Chart.js line chart (`frontend/app.js` `renderChart`) assuming the output is a 1-D numeric array — a regression forecast. This works for the Jena Weather GRU but will silently render nonsense for classification, multi-output, or non-numeric models.

**Why it matters**. The client is being generalized into a "Model Serving Client" that lets users pick any registered model from a dropdown. As soon as a non-regression model is picked, the chart becomes misleading.

**Fix**. Detect the model's output type from the schema (`modelSchema.output_format` / `output_visualization` — noted-serving already exposes these in the schema response) and switch rendering strategy:

- `output_format == "scalar"` and `output_visualization == "value"` → line chart (current behavior).
- classification / probabilities → bar chart sorted by confidence.
- multi-dimensional tensor → sparse table / heatmap.
- unknown → generic JSON tree view.

Effort: ~1-2 hours. Not blocking the demo; the jena_client is pinned to a regression model so the current chart will keep working for the Apr 21 demo. Add it as a polish pass.

---

## noted should track child processes launched from project terminals (logged 2026-04-15)

**Problem**. When a user launches a long-running process (e.g., `python web/backend/server.py` for the jena_client demo) from a noted terminal tab, noted has no record of it as a "child of the project". The process keeps running even after:
- closing the terminal tab
- rebuilding the noted container (it survives because it's inside the container but not a child of the uvicorn noted process)
- re-opening the project

This hit on 2026-04-15 during Tutorial 3 prep: after editing `jena_client/web/backend/server.py` and rebuilding noted, the OLD server process was still running from a previous terminal session, still serving the browser, still running the pre-fix code. The user saw "undefined vundefined" from the old handler while assuming the new handler was live. Had to kill PID by hand (requiring `docker exec noted kill <container-ns-pid>` because of PID namespacing).

**Fix proposal**. Noted should maintain a registry of "project processes" — anything launched from a terminal tab whose `cwd` is inside a project directory — and offer actions:

1. **On terminal tab close**: prompt "N processes are still running in this terminal. Kill them, keep them, or cancel the close?"
2. **On project unload / switch**: list all processes whose `cwd` is in the project, same prompt.
3. **On noted rebuild**: similar prompt, or a settings flag to "always preserve" / "always kill".
4. **Explorer Processes panel**: a small list under the project node showing PIDs + command + running time, with a kill button per entry.

**Subtlety**. Tracking is non-trivial: terminals spawn shells, shells spawn processes. Noted would need to walk the process tree (`/proc/<shell-pid>/task/*/children`) at tab close time, or track via a pty session id + shell job table. Not impossible but needs design work.

**Effort**. 4-8 hours for a first cut (Processes panel + kill button + close-tab prompt). More for the automatic "kill on rebuild" flow.

---

## Fixed during final delivery (2026-04-15/16)

Two document-viewer bugs discovered and fixed while reviewing the PDF user manual and setup guide in the Knowledge Base, before Tutorial 3 submission. Left as a post-mortem note so the root causes are captured for future reference.

### Fix: PDF content rendered twice on first open

**Symptom**. Opening any of the three Word-generated PDFs (User Manual, Setup & Installation, Final Delivery Report) in the Knowledge Base rendered the whole document twice: scrolling past the last page revealed the cover again, followed by the full content a second time. The fourth PDF (`airflow.pdf`, Chrome-generated) usually did not exhibit the bug, which initially suggested a content issue. It was not — the three Word PDFs are structurally sound (38 / 13 / 26 pages each with matching `/Type /Page` counts in the PDF catalogue).

**Root cause**. Race condition in `_openDocumentTab` at `frontend/js/app.js`. The method called `this._tabBar.addTab({...})` and then immediately called `this._documentViewer.show(doc)`. But `addTab` in `frontend/js/TabBar.js` (line 74) synchronously calls `this.activate(tab.key)`, which synchronously invokes `this._callbacks.onActivateTab?.(key)`. The tab-activation handler in `frontend/js/app-tabs.js` (doc: case) already calls `app._documentViewer.show(doc)` when `_currentDoc !== doc`. Result: `show(doc)` ran **twice** in rapid succession, and both `show()` calls' `_cleanup()` checks ran while `_pdfState` was still `null` (the first call hadn't yet created its state - it was awaiting `getDocument().promise`). Both calls created separate PDF states, both `_setupPdfPlaceholders` loops ran in parallel, and both appended their page divs to the same `_content` element. The DOM ended up with 2×N page divs.

**Why the bigger airflow.pdf did not always exhibit it**. Timing-dependent. The larger 11.7 MB file's `getDocument()` took long enough that the second `_cleanup()` sometimes caught the first state before it mattered. Smaller PDFs resolved `getDocument()` fast enough that both calls overlapped their `_cleanup()` while `_pdfState` was still `null` on both checks.

**Fix**. Remove the explicit `documentViewer.show(doc)` from `_openDocumentTab`. The tab-activation handler already handles both rendering and TOC update in its `.then()`. Left a block comment at the removal site explaining the race so it is not reintroduced.

File: `frontend/js/app.js`

### Fix: clicking an in-PDF TOC link shifted the whole noted app upward

**Symptom**. Clicking an entry in a PDF's built-in table of contents (the table rendered on the first pages of the document itself, as hyperlinked annotations) scrolled the target section into view as expected, but **also** shifted the entire noted application upward by ~50 px. The top icon bar slipped partially off the top of the viewport, the status bar slipped off the bottom, and there was no way to recover short of a browser refresh. The left-side **TocPanel** (noted's own TOC sidebar) did not have the bug.

**Root cause**. The PDF annotation layer click handler in `_renderPdfPage` at `frontend/js/panels/DocumentViewer.js` used `targetDiv.scrollIntoView({ behavior: 'smooth', block: 'start' })`. `scrollIntoView()` walks every scrollable ancestor of the target and scrolls each one so the target lands at the start. In noted's layout, the target page div is inside `.document-viewer-wrapper` (scrollable), which is inside `#below-bar` (`display:flex`, `overflow:hidden`), which is inside `#app`, which is a child of `body` (also `overflow:hidden`). Chromium's `scrollIntoView` implementation in recent versions **bypasses `overflow:hidden` for programmatic scrolls** and still mutates the root viewport's scroll position when walking up the chain. The effect: Chrome scrolled `.document-viewer-wrapper` correctly, then also mutated the root viewport scroll, translating the entire `#app` upward.

**Why TocPanel's own click handler didn't have the bug**. `TocPanel._scrollPdfToPage` at `frontend/js/TocPanel.js` line 461-470 uses the scoped `scrollHost.scrollTop += targetRect.top - hostRect.top` pattern, which only mutates the specific container's scroll position and cannot leak to ancestors.

**Fix**. Replaced `scrollIntoView(...)` with the same scoped arithmetic pattern used by `TocPanel._scrollPdfToPage`. Added a block comment explaining why `scrollIntoView` is not safe in this layout so it is not reintroduced.

File: `frontend/js/panels/DocumentViewer.js`

### Shared lesson

Both bugs had the same abstract shape: a convenient browser API (`show()` called from both a trigger and a callback; `scrollIntoView` walking ancestors) produced behaviour that looked correct in isolation but had a second-order effect in noted's layered layout. The fix in both cases was to use the **explicit, scoped, container-local** operation (remove duplicate `show()`; use `scrollTop +=` on the one container we actually want to scroll). When in doubt, prefer operations that cannot possibly reach beyond the element they are meant to affect.

---

## ArcadeDB pre-rebuild backup + auto-restore (logged 2026-04-23)

**Problem (future).** GraphRAG Phase 1 relies on atomic staging-prefix swap for ingestion safety: staged graph is written under a prefix, swapped in on success, rolled back on failure. This protects against mid-rebuild crashes but NOT against a successful rebuild that produced junk (bad extraction pass, taxonomy drift, etc.). Once the swap completes, the previous graph is gone.

**Where.** `noted-graph` service, ArcadeDB backend. Relevant once the service persists to ArcadeDB — currently in-memory only.

**Why it matters.** In dev, rebuild time is ~30 min. A silent bad rebuild that the user only catches a day later costs that 30 min plus a reversion effort with no baseline to compare against.

**Fix.** Before each rebuild:
1. Call ArcadeDB's built-in backup command (HTTP or Studio API) against the live database.
2. Store the dump under `data/arcadedb/backups/<iso-timestamp>/`.
3. Keep last 3 dumps, evict older.
4. If staging swap fails OR the post-swap sanity check (entity count / community count deltas within expected range) fails, auto-restore from the latest dump.

Deferred from GraphRAG Phase 1 scope (per open_questions.md Q E3, 2026-04-23). Not blocking initial implementation; safety improvement for before production use.

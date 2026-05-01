# Pyright Integration - Implementation Plan

**Status:** Parked. Not scheduled. Document captures the analysis from the 2026-04-14 scoping session so it can be picked up later without redoing the research.

**Recommendation at time of writing:** Do not ship yet. noted's primary audience writes notebook/training code against pandas, numpy, keras, mlflow - libraries with incomplete or noisy type stubs. Pyright on that surface produces more false positives than real finds, and users learn to ignore the squiggles. The effort is better spent on Hydra-aware completions, richer hover docs, or improving notebook cell diagnostics. Revisit when: (a) a meaningful share of users write typed FastAPI backends or utility libraries inside noted, or (b) ML stubs improve enough that Pyright signal-to-noise becomes positive on notebook code.

---

## 1. Goal

Add Pyright as a third Python language server alongside the existing Ruff (lint) + Jedi (completion/navigation) pair, to provide static type checking diagnostics (generics, TypedDict, Protocols, None-safety, argument types, attribute typos). Pyright must be opt-in and must not regress the current ruff+jedi behavior for users who leave it disabled.

### Non-goals
- Replacing Ruff or Jedi.
- Pylance integration (not open source).
- Type-aware refactorings, quick-fixes, or codemods. Pyright diagnostics only in v1.
- Inline type inference hints (inlay hints) in v1.

## 2. Current Architecture (baseline)

The existing Python LSP setup is already dual-server and well-abstracted, which makes this integration additive rather than invasive.

### Key files

- `backend/app/managers/lsp_manager.py` - spawns subprocess-based language servers, handles Content-Length framing, manages process lifecycle.
- `backend/app/lsp/__init__.py` - strategy registry: `language_id -> BaseLspStrategy` subclass.
- `backend/app/lsp/python_strategy.py` - Python strategy. Declares `lint_server_type = "ruff"` and `completion_server_type = "jedi"`. Handles launch commands, URI rewriting (jedi needs real filesystem paths; ruff uses virtual URIs), diagnostic filtering (`drop_diagnostics_from()` suppresses jedi diagnostics), capability merging, init options (jedi's `environment_path` for venv awareness).
- `backend/app/routers/lsp.py` - WebSocket router. Sends `did_open`/`did_change`/`did_close` to both servers. Routes `textDocument/completion`, `textDocument/hover`, etc. to the completion server. Sends formatting, code actions to the primary (ruff). Calls `drop_diagnostics_from()` to suppress jedi `publishDiagnostics`.
- `backend/app/managers/notebook_lsp_bridge.py` - generates a shadow `.py` script per notebook via Jupytext, registers it with both servers, maps line-based diagnostics back to cells.
- `frontend/js/panels/FileEditor.js` - CodeMirror client. Parses enriched diagnostic format (`CODE: message\nCATEGORY\nURL`), renders gutter squiggles + structured tooltip.

### Routing today
- **Initialization**: sent to both servers; capabilities merged by `complete_init_capabilities()`.
- **Document sync**: sent to both servers, with URI rewriting per server.
- **Completions/hover/definition/references**: routed to completion server (jedi) if present.
- **Formatting/code actions**: routed to primary (ruff).
- **Diagnostics**: each server pushes `publishDiagnostics`; strategy's `drop_diagnostics_from()` filters per-source before forwarding to WebSocket clients.

### What is NOT in place
- No per-capability routing (e.g. "pyright diagnostics + ruff style + jedi completions"). Current design is one lint server + one completion server per language.
- No multi-lint-server diagnostic aggregation. The filter is binary per-source: either forward or drop.
- No opt-in feature flag system for LSP strategies.
- No regression fixture harness for diagnostic output.
- No resilience around spawn failures of the non-primary server.

## 3. Design Decisions

### 3.1 Pyright alongside Ruff, not replacing it
Ruff catches style, unused imports, line length, ordering, deprecated APIs - cheap and useful. Pyright catches type errors. Keep both. Users get ruff rules in their own namespace and pyright diagnostics in another, each with its own URL/doc link in the tooltip.

### 3.2 Opt-in via feature flag
Pyright is disabled by default. Enabled via:
- Workspace setting (per-project) stored in `.noted/settings.json` (or equivalent).
- User setting (global fallback) in noted settings.

When disabled: the router must not spawn the pyright process, must not send any messages to it, must not merge its diagnostics. Ruff + Jedi path must be byte-identical to today's behavior. This is the core of the 0% regression guarantee.

### 3.3 Diagnostic ownership split
To avoid duplicate squiggles on the same issue:
- **Pyright owns**: type errors (`reportGeneralTypeIssues`, `reportArgumentType`, `reportAttributeAccessIssue`, `reportOptionalMemberAccess`, `reportOptionalSubscript`, `reportReturnType`, `reportCallIssue`).
- **Ruff owns**: style, import order, unused imports/variables, line length, naming, complexity. Everything non-type.
- **Overlap (undefined name, redefined while unused)**: Ruff owns. Pyright's `reportUndefinedVariable` is suppressed via strategy config to avoid double-reporting.

Ownership is enforced at strategy level, not at router level. Each strategy declares which diagnostic codes it keeps vs drops per source server. This keeps the router generic.

### 3.4 Capability routing
No change. Pyright does not provide completions/hover/go-to-def better than jedi for noted's typical code, and merging three sources of completions introduces ranking problems. Pyright contributes only `publishDiagnostics`; all navigation stays with jedi.

### 3.5 Pyright over Pylyzer, Pyre, mypy-lsp
- **Pylyzer**: faster but much less mature, type inference gaps on common ML code.
- **Pyre**: Facebook-internal feel, heavier, worse error messages, less community stubs.
- **mypy + mypy-lsp**: slower incremental updates, worse editor integration, poorer inference.
- **Pyright**: best signal-to-noise on ML libraries, actively maintained by Microsoft, well-documented diagnostic codes, Node runtime already available in noted's Docker image.

## 4. Task Breakdown

### Phase 0 - Regression baseline (3-5h) - BLOCKING
Must come first. Without this, "0% regression" is assertion-not-guarantee.

**T-P.0.1**: Create `backend/tests/lsp/fixtures/python_regression/` with ~20 representative Python files: notebook cell exports, training scripts, Hydra configs, FastAPI handlers, broken code with known ruff violations, code with known jedi completion expectations.

**T-P.0.2**: Write a harness `backend/tests/lsp/test_python_regression.py` that:
- Starts the Python strategy with pyright disabled.
- For each fixture, captures all `publishDiagnostics` notifications and a set of reference LSP requests (completion at specific cursor positions, hover at specific positions).
- Serializes the captured output to a golden file.

**T-P.0.3**: Commit the golden files. All subsequent work must keep these tests green with pyright disabled.

### Phase 1 - Strategy plumbing (3-5h)

**T-P.1.1**: Extend `BaseLspStrategy` to support an optional tertiary server slot: `type_server_type: str | None = None`. Default `None` for all existing strategies.

**T-P.1.2**: Create `backend/app/lsp/pyright_adapter.py` - pyright-specific logic: launch command (`pyright-langserver --stdio`), init options (`pythonPath`, `venvPath`, `typeCheckingMode: "basic"`), URI handling (pyright accepts real filesystem paths same as jedi), disabled-by-default diagnostic codes (`reportUndefinedVariable`, `reportUnusedImport`, `reportUnusedVariable` - ruff owns these).

**T-P.1.3**: Update `python_strategy.py`:
- Read feature flag from settings; set `type_server_type = "pyright"` only when enabled.
- Extend `drop_diagnostics_from()` to handle the pyright source (drop suppressed codes).
- Extend `complete_init_capabilities()` to suppress pyright's completion/hover/definition/references capabilities (jedi owns these).

**T-P.1.4**: Update `lsp_manager.py` to spawn the type server when declared. Must tolerate spawn failures: log error, continue with ruff + jedi only, emit a one-time user-visible warning in the LSP status panel.

### Phase 2 - Router changes (4-6h)

**T-P.2.1**: Update `routers/lsp.py` document sync handlers (`did_open`, `did_change`, `did_save`, `did_close`) to also send to the type server when present. URI rewriting for pyright is same as jedi (real filesystem paths).

**T-P.2.2**: Update initialization: send `initialize` to type server after ruff+jedi, merge capabilities. Pyright's reported capabilities are mostly suppressed per T-P.1.3.

**T-P.2.3**: Extend diagnostic forwarding loop to accept `publishDiagnostics` from the type server, apply strategy's per-source drop filter, merge with ruff+jedi diagnostics into a single per-URI stream before forwarding to the WebSocket client. Must preserve the enriched format (`CODE: message\nCATEGORY\nURL`) - add pyright diagnostic code URLs (e.g. `https://microsoft.github.io/pyright/#/configuration?id=<code>`).

**T-P.2.4**: Handle type server crash during session: detect dead process, log, stop forwarding its diagnostics, clear stale diagnostics from the frontend, continue ruff+jedi normally. No automatic restart in v1 - a noted restart is required. Document this.

### Phase 3 - Notebook bridge (2-3h)

**T-P.3.1**: Verify `NotebookLSPBridge` shadow-script URI registration works with pyright. Pyright indexes the whole workspace; ensure it sees the shadow scripts under `.noted/notebook_shadows/` or wherever they live.

**T-P.3.2**: Verify cell-to-line mapping still holds for pyright diagnostics. Pyright may emit diagnostics with different line offsets if it considers imports from adjacent cells. Test explicitly with a fixture notebook.

**T-P.3.3**: Handle pyright's workspace symbol resolution across cells. Jedi uses `environment_path`; pyright uses `pythonPath` + `venvPath`. Confirm the bridge passes the right value per notebook kernel.

### Phase 4 - Image & runtime (0.5-1h)

**T-P.4.1**: Add `npm install -g pyright` to the noted Dockerfile after the existing Node setup (Node 20/22 via fnm is already present). Pin version to avoid surprise upgrades.

**T-P.4.2**: Add `pyright --version` to the healthcheck or startup log for observability.

**T-P.4.3**: Rebuild image, verify `pyright-langserver --stdio` spawns from inside the container.

### Phase 5 - Settings + UI (3-5h)

**T-P.5.1**: Add setting `python.type_checking.provider: "none" | "pyright"` to noted's settings schema. Default `"none"`.

**T-P.5.2**: Add setting `python.type_checking.mode: "off" | "basic" | "strict"`. Default `"basic"` when provider is pyright.

**T-P.5.3**: Surface a toggle in the LSP status bar / Explorer context menu so users can enable pyright per project without editing JSON.

**T-P.5.4**: When pyright is toggled on/off at runtime, restart the language server session gracefully (close WebSocket, respawn servers, reopen documents). This can be deferred to v2 if the cost is high; v1 can require a noted restart.

### Phase 6 - Testing & regression gate (3-5h)

**T-P.6.1**: Re-run Phase 0 regression harness. Must pass unchanged (pyright disabled).

**T-P.6.2**: Add `test_python_regression_pyright.py` - new golden files captured with pyright enabled. Acts as a forward-compatibility guard for pyright output.

**T-P.6.3**: Manual test matrix:
- File editor tab, pyright off -> identical to current.
- File editor tab, pyright on, typed code -> expected type errors surface.
- File editor tab, pyright on, untyped ML code -> noise level acceptable (subjective; document observations).
- Notebook cell, pyright off -> identical to current.
- Notebook cell, pyright on, cross-cell import -> diagnostics map to correct cell.
- Venv switch -> pyright re-initializes with new `pythonPath`.
- Pyright spawn fails -> ruff+jedi continue normally, warning surfaced.
- Pyright crashes mid-session -> stale diagnostics cleared, no frontend errors.

### Phase 7 - Docs (1-2h)

**T-P.7.1**: User-facing doc in the Knowledge Base: how to enable pyright, how to choose basic vs strict, how to add `# pyright: ignore[<code>]` suppressions, where to report false positives.

**T-P.7.2**: Internal doc updates: Python strategy file header comment updated, LSP architecture section in noted_plan.md mentions the third server slot.

## 5. Effort Summary

| Phase | Hours |
|-------|-------|
| 0 - Regression baseline | 3-5 |
| 1 - Strategy plumbing | 3-5 |
| 2 - Router changes | 4-6 |
| 3 - Notebook bridge | 2-3 |
| 4 - Image & runtime | 0.5-1 |
| 5 - Settings + UI | 3-5 |
| 6 - Testing & regression gate | 3-5 |
| 7 - Docs | 1-2 |
| **Total** | **19.5-32 hours** |

The earlier rough estimate of 15-25h assumed Phase 0 was optional. With the regression gate as a hard prerequisite (which it must be to hit 0% regression), 20-30h is the honest range. The fixture harness in Phase 0 is the single biggest line item for safety and is reusable for any future LSP work.

## 6. Open Questions To Resolve Before Starting

1. **Which Python version's typeshed does pyright target?** Pyright bundles its own typeshed. Verify it matches noted's supported Python range.
2. **How does pyright handle Hydra's `cfg.model.units1` attribute access on `DictConfig`?** Expect false positives. May need strategy-level suppressions for OmegaConf types, or a noted-shipped `pyrightconfig.json` stub with `reportAttributeAccessIssue: "none"` for `omegaconf.*`.
3. **Keras/TensorFlow stub quality in 2026?** Last time checked, stubs were incomplete for `keras.callbacks.Callback.on_epoch_end`, `model.fit` return types. Re-evaluate before starting Phase 1.
4. **Does `.noted/settings.json` exist as a schema today, or do we need to create the per-project settings mechanism first?** If the latter, it is a prerequisite and adds to the effort.
5. **Does pyright support the same `environment_path`/venv awareness jedi uses for noted's kernel venv?** Pyright uses `pythonPath`/`venvPath`. Confirm mapping.
6. **What is the expected startup cost?** Pyright warms up a workspace index; may be 1-3s on a large project. Verify on jena_weather before committing.

## 7. Rollout Strategy

1. Merge behind flag, default off.
2. Dogfood on noted's own backend for 1 week (typed FastAPI code, highest signal case).
3. Enable on a single user's jena_weather project for 1 week.
4. Collect false-positive report.
5. Decide: ship with default `basic` mode, ship with default `off` and document-only, or abandon.

Decision criteria: if false-positive rate on typical notebook code exceeds ~1 per 50 lines, abandon. Users will disable and forget.

## 8. Revisit Triggers

Reopen this plan when any of the following happen:

- User explicitly asks for type-checking diagnostics.
- noted's user base shifts toward typed FastAPI/backend development inside noted.
- Major pyright release improves ML stub handling.
- A dependent feature (e.g. AI assistant grounding on type info, type-aware refactorings) requires a type checker.
- Notebook cell quality initiative needs richer diagnostics beyond ruff.

Until then, this is research saved, not work scheduled.

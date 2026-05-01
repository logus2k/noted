# Test 34: R LSP Walkthrough (Phase 2 + 2.1 + 2.2)

## Purpose

End-to-end verification of the R integration in noted. This test covers
the kernel layer, the LSP layer, and the legacy/modern R version split.
The walkthrough was originally written for Phase 2 (LSP for modern R)
but was extended on 2026-04-10 with Phase 2.1 (IRkernel for legacy R)
and Phase 2.2 (PPM-binary languageserver for legacy R) so that **all 6
supported R versions are validated end-to-end**.

The first walkthrough run discovered and fixed a substantial cluster of
bugs in noted's R wiring (and a few language-agnostic editor bugs that
happened to surface in the R session). They are listed at the bottom
under "Bugs found and fixed during the walkthrough" so future runs can
guard against regressions.

## Architecture being tested

| R version | Kernel | LSP source | Tier |
|---|---|---|---|
| 4.5.1 | ark 0.1.250 | latest CRAN languageserver | Full |
| 4.4.2 | ark 0.1.250 | latest CRAN languageserver | Full |
| 4.3.3 | ark 0.1.250 | latest CRAN languageserver | Full |
| 4.2.3 | ark 0.1.250 | latest CRAN languageserver | Full |
| 4.0.5 | **IRkernel 1.1.1** (PPM 2021-05-01) | **languageserver 0.3.10** (PPM 2021-05-01 binary) | Full |
| 3.6.3 | **IRkernel 1.1** (PPM 2020-04-01) | **languageserver 0.3.5** (PPM 2020-04-01 binary) | Full |

ark cannot drive R 3.6.3 / R 4.0.5 (R API surface from R 4.x era; older
interpreters die during init silently). IRkernel is used for those
versions because it has stable cross-version bindings dating back to R
3.x and installs cleanly from PPM binary repos.

`languageserver` source-installs into legacy R fail for two distinct
reasons (R 3.6.3 dep resolution mismatch; R 4.0.5 testthat catch.h
glibc 2.34 SIGSTKSZ compile error). Both bypassed by PPM binary repos
which ship a self-consistent prebuilt set per snapshot. **libicu66**
from Ubuntu's focal archive is installed alongside libicu74 because
the 2020-2021 PPM binaries link against `libicui18n.so.66` (used by
stringi via lintr).

## Prerequisites

- noted has been built and started from a Dockerfile that includes:
  - All 6 R versions installed at `/opt/R/<version>/`
  - `/usr/local/bin/R` and `/usr/local/bin/Rscript` symlinks pointing
    at R 4.5.1 (for the no-env script case)
  - `/usr/local/bin/ark` (Posit ark 0.1.250)
  - `libicu66` from Ubuntu focal archive (alongside libicu74)
  - `languageserver` installed for R 4.2.3 / 4.3.3 / 4.4.2 / 4.5.1
    (latest CRAN)
  - `IRkernel` AND `languageserver` installed for R 4.0.5 (PPM
    2021-05-01 binary)
  - `IRkernel` AND `languageserver` installed for R 3.6.3 (PPM
    2020-04-01 binary)
- The noted container is running and you are logged in via the browser
- At least one R environment exists for an R 4.4.2 env named
  `r_test_env` (the modern-R baseline). The walkthrough also asks you
  to create one legacy R env (R 3.6.3 or R 4.0.5) when you reach L7.

## How to use this guide

Walk through the tests in the order below. Each test has:

- The action to perform
- The expected outcome
- What to look for in the backend logs (read via
  `docker logs noted --tail 100 2>&1 | grep -E '<pattern>'`)
- What "failure" looks like vs "success"

If a test passes, move on. If a test fails, capture the relevant log
lines and the browser DevTools console output. Each test points to the
exact source files most likely involved if it breaks.

## Tests

### L1 - File editor LSP startup for an R script (modern R)

**Action**:

1. In any project (e.g. `Examples`), create or open a `.R` file. If
   none exists, create `test.R` at the project root with content like:
   ```r
   x <- 1
   y <- 2
   cat("hello", R.version.string, "\n")
   ```
2. Open the file in noted's editor.

**Expected**:

- The editor opens with R syntax highlighting.
- Within ~5 seconds of opening, the noted backend log shows a line:
  ```
  Starting languageserver language server for <project>/<env> (cwd=<project_root>, runtime=...)
  ```
  The `runtime=` value is `None` for file-editor-only access (no env
  tied to a script-only edit). The languageserver picks `R` from PATH,
  which is the symlink at `/usr/local/bin/R` -> `/opt/R/4.5.1/bin/R`.

**How to check the log**:
```
docker logs noted --tail 100 2>&1 | grep -E "Starting languageserver|languageserver started"
```

You should see one `Starting languageserver` line and one `Language
server languageserver started (pid=...)` line shortly after.

**If it fails**:
- "languageserver R package is not installed" warning, but the
  `/usr/local/bin/R` symlink missing: `docker exec noted readlink
  /usr/local/bin/R` should print `/opt/R/4.5.1/bin/R`. If empty or
  missing, the Dockerfile symlink layer is broken.
- The R LSP process spawns and dies immediately in a loop: usually a
  shared library mismatch (libicui18n.so.66 etc); see the libicu66
  install note at the top.

---

### L2 - Completion in an R script file

**Action**:

In the same `.R` file, type a new line at the bottom:
```r
library(jsonl
```
(Do **not** press Enter or close the parenthesis. Wait for the
completion popup.)

**Expected**:

- A completion popup appears within ~1-15 seconds (the first request
  after LSP startup is slow because the languageserver indexes the
  workspace).
- The popup contains `jsonlite` as a candidate.
- Pressing **Tab** OR Enter accepts the completion.

**Important - cold-start latency**: the R `languageserver` package has
a known cold-start penalty. The **first** completion request after the
server starts can take 5-15 seconds. Subsequent requests are fast
(<1 second).

**If it fails**:
- No popup at all: the completion trigger gate may be too restrictive.
  `_notebookCompletionSource` in `CellEditor.js` and the equivalent
  source in `FileEditor.js` should trigger on `(`, `:`, `$`, `@`, `[`,
  or 2+ word characters - not just after `.`.
- Tab inserts whitespace instead of accepting: Tab-to-accept binding
  needs `Prec.highest` so it wins against the default Tab handler.

---

### L3 - Hover documentation in an R script file

**Action**:

In the `.R` file, hover the mouse over a base R function name like
`cat`, `sum`, `paste`, or `print`. Wait ~1 second.

**Expected**:

- The Documentation panel on the right side shows the function's R
  help documentation - the same content `?cat` would print at an R
  console.

**Known limitation**: the R languageserver returns hover content as
**plaintext** (R's `.Rd`-formatted help with curly quotes and indented
sections), not Markdown. The DocPanel renders it as-is. This is
upstream behavior, not a noted bug.

---

### L4 - Lint diagnostics for an R script file

**Action**:

In the `.R` file, add a deliberately bad line:
```r
if (x = 1) cat("bad")
```
(Single `=` inside `if(...)` is an assignment, not a comparison -
lintr flags this.)

**Expected**:

- Two diagnostics appear within ~3 seconds:
  - lintr: "Use one of <-, <<- for assignment, not =." labeled
    `R - ASSIGNMENT`
  - R parser: "unexpected '='" labeled `R - ERROR`
- Hovering the underline shows both messages.

The `R - ASSIGNMENT` / `R - ERROR` labels confirm that
`RLspStrategy.enrich_diagnostic` correctly formats lintr codes (e.g.
`assignment_linter`) into the standard noted "<message> + R - <Label>"
shape.

---

### L5 - Notebook cell LSP

**Action**:

1. Open or create a notebook in any project.
2. Switch its kernel to an R env (e.g. `r_test_env` against R 4.4.2).
   Wait for the kernel to start (`Project '...' loaded. [renv 1.2.0]`
   log line).
3. In a code cell, type:
   ```r
   library(jsonl
   ```

**Expected**:

- The completion popup appears with `jsonlite` (and possibly other
  matches), the same way it did in the file editor.
- This confirms the notebook bridge wires R cells through the
  languageserver via the `# %%` combined shadow file.

**Backend log to check**:
```
docker logs noted --tail 100 2>&1 | grep -E "Notebook LSP started.*r"
```

You should see something like `Notebook LSP started:
<project>/<notebook> (<n> chars, R)`.

**Look for** (subtle bugs the original walkthrough surfaced):
- Only ONE languageserver process spawned for the env (not a
  spawn-loop). The cache key
  `(project_id, env_name, "languageserver")` should hit on
  subsequent requests.
- `RUST_LOG=warn` injected via the runtime.json `kernel_env` block
  silences ark's INFO `tracing` output that would otherwise pollute
  cell stdout.

---

### L6 - Multi-version R LSP dispatch

**Prerequisite**: a second R env exists against a different version,
e.g. `r_test_env_45` against R 4.5.1. Create one via the Environments
UI if needed.

**Action**:

1. While the notebook is using the R 4.4.2 env's kernel and LSP,
   switch the kernel to the R 4.5.1 env.
2. Wait for the kernel to restart.
3. Run a cell containing `R.version.string` to confirm the new R
   version.
4. Trigger completion in a cell again with `library(jsonl`.

**Expected**:

- A **new** languageserver process started with `runtime=r/4.5.1`
  for the new env. The old one (for the 4.4.2 env) is left running
  but no longer receives requests for this notebook.
- Both processes alive simultaneously, each on the right R version
  binary (`/opt/R/4.4.2/lib/R/bin/exec/R` and
  `/opt/R/4.5.1/lib/R/bin/exec/R`).
- Completion still works in the new R env's cells.
- Cell output for `R.version.string` is `R version 4.5.1 ...`.

**Backend log to check**:
```
docker logs noted --tail 100 2>&1 | grep -E "Starting languageserver.*r/4.5.1|kernel:status"
docker exec noted sh -c 'ps -ef | grep -E "/opt/R/.*/bin/exec/R --slave" | grep -v grep'
```

This is the proof that **per-R-version LSP isolation works**: two envs
with two R versions get two separate languageserver processes with the
right `R_HOME` and `RENV_PATHS_*` env vars baked in. Without per-env
cache keys, both envs would share one languageserver and one would see
the wrong R version.

---

### L7 - Legacy R end-to-end (Phase 2.1 + 2.2)

This is the test that discovered the most bugs. It validates the
**full** legacy R path: kernel via IRkernel + LSP via PPM-binary
languageserver + the renv-isolation bypass via
`RENV_CONFIG_EXTERNAL_LIBRARIES`.

**Prerequisite**: an env exists for one of the legacy R versions
(e.g. `older_r_env` against R 3.6.3, or `senior_r_env` against R
4.0.5). Create one via the Environments UI.

**Action**:

1. Switch the notebook kernel to the legacy R env. Wait for the
   kernel to start (this uses IRkernel, not ark).
2. Run a simple cell:
   ```r
   cat("hello from legacy R", R.version.string, "\n")
   ```
3. In another cell, type:
   ```r
   library(jsonl
   ```
   and wait for the completion popup.
4. Add a deliberately bad line in a cell:
   ```r
   if (x = 1) cat("bad")
   ```

**Expected**:

- The kernel starts successfully via IRkernel and the cell produces
  `hello from legacy R R version 3.6.3 (2020-02-29)` (or 4.0.5
  equivalent).
- Completion popup appears with `jsonlite` after typing
  `library(jsonl` - **without needing Ctrl+Space**.
- Wavy underline appears within ~3 seconds for the bad assignment
  line, with the `R - ASSIGNMENT` / `R - ERROR` labels.
- Hover over `cat` shows R help docs in the Documentation panel.

**Backend log to check**:
```
docker logs noted --tail 100 2>&1 | grep -E "Starting languageserver.*r/3.6|languageserver started|Notebook LSP started.*R"
```

**If it fails** (cluster of issues this test originally exposed):
- `Error in loadNamespace(name) : there is no package called 'IRkernel'`
  -> the kernel R subprocess can't see the system-installed IRkernel
  because the env's `.Rprofile` calls `renv::load()` which narrows
  `.libPaths()` to the env library only. Fix: ensure
  `RENV_CONFIG_EXTERNAL_LIBRARIES=/opt/R/<version>/lib/R/library` is
  in the legacy `runtime.json`'s `kernel_env` block. Then **`docker
  restart noted`** to clear the in-memory `RuntimeRegistry` cache (it
  loads runtime.json once at startup; bind-mounted edits need a
  process restart to be visible).
- `unable to load shared object '.../stringi/libs/stringi.so':
  libicui18n.so.66` -> the libicu66 install layer in the Dockerfile
  is missing or didn't run. The `.deb` from
  `archive.ubuntu.com/ubuntu/pool/main/i/icu/` should be installed
  alongside libicu74.
- Spam of `ERROR:app.main:Failed to update notebook LSP` per
  keystroke -> the bridge `lsp_unavailable` flag isn't being set
  after the first failure. The fix lives in `_start_notebook_lsp`
  and `_update_notebook_lsp` in `main.py`; both should mark the
  bridge and bail out silently after the first failure.
- Completion returns empty even though Ctrl+Space works -> the
  bridge shadow has stale content because `notebook_complete` (and
  `notebook_hover`) routes the `didChange` to the wrong server for R.
  Fix: `_get_notebook_bridge_and_jedi` in
  `backend/app/routers/lsp.py` must use
  `_notebook_completion_server_args(bridge)` to pick the right
  server (`languageserver` for R, not `jedi`).

---

### L8 - Python regression check

**Action**:

1. Open a Python `.py` file in the editor.
2. Type `import os; os.pa` and wait for completion.
3. Hover over a Python builtin to verify hover docs.
4. Make a deliberate ruff error (e.g. unused import) and confirm the
   diagnostic appears.

**Expected**:

- Python LSP behaves exactly as before the R work. Completion, hover,
  diagnostics all working.
- This confirms the multi-language LSP dispatch (added a `runtime_id`
  parameter to `lsp_manager.get_or_start`, etc.) didn't break Python.

---

### L9 - Cell-edit completion regression check

**Action**:

1. Open a Python notebook with an active kernel.
2. In one cell, define a variable: `my_special_var = 42`. Run the
   cell (or just leave it - the bridge picks it up via `cell:update`).
3. In a **new** cell below, type `my_spec` and wait for the
   completion popup.

**Expected**:

- The popup includes `my_special_var` immediately - **without
  needing a kernel restart and without needing Ctrl+Space**.

This is the regression check for the bridge's `_latest_sources` cache
and the `_get_notebook_bridge_and_jedi` `didChange` routing. Without
both fixes:
- `notebook_manager.get_notebook()` reads from disk, so the bridge
  shadow rebuilt during cell 2's edit would lose cell 0's in-flight
  edit (race against the 300ms `cell:update` debounce).
- The `didChange` would go to the wrong server (jedi, but for R
  cells; the same routing function was buggy for R).

If `my_special_var` doesn't appear, capture the backend logs grepping
for `/api/lsp/notebook/complete` and check what content the request
sends. The frontend should send `content: "my_spec"` and the backend
should overlay all known cell sources before regenerating the shadow.

---

## Bugs found and fixed during the walkthrough

The original walkthrough run on 2026-04-10 surfaced this cluster.
They are listed roughly in the order they were discovered:

| # | Bug | Fix location |
|---|---|---|
| 1 | `did_change` referenced in `_update_notebook_lsp` but never built; completion server (jedi/tsserver) never received cell-edit notifications | `backend/app/main.py` `_update_notebook_lsp` |
| 2 | `runtime_id` not forwarded for non-R languages (inconsistent, no functional break) | `backend/app/main.py` `_start_notebook_lsp` |
| 3 | `lsp_manager._resolve_runtime_env` left `{project_root}` placeholder literal in env vars; `NOTED_PROJECT_ROOT` was unusable | `backend/app/managers/lsp_manager.py` |
| 4 | Notebook LSPs were keyed by `(project_id, "", server_type)` for all languages; multiple R envs in the same project shared one languageserver | `backend/app/main.py` `_start_notebook_lsp`, `_update_notebook_lsp`; `backend/app/managers/notebook_lsp_bridge.py` (added `env_name` / `runtime_id` to bridge) |
| 5 | `cmd[0] = "R"` resolved to `/usr/local/bin/R` (a wrapper script that prints "ignoring environment value of R_HOME" and uses its own R version); the LSP for env-tied R never used the right R binary | `backend/app/managers/lsp_manager.py` `get_or_start` (substitutes `cmd[0]` to `/opt/R/<version>/bin/R` for R runtimes) |
| 6 | `renv::load` hides the system library, so the LSP's R process couldn't find `languageserver` itself | `backend/app/managers/lsp_manager.py` `_resolve_runtime_env` (injects `RENV_CONFIG_EXTERNAL_LIBRARIES`) |
| 7 | `notebook_complete` and `notebook_hover` routed all non-JS R requests to `jedi` instead of to the R `languageserver` | `backend/app/routers/lsp.py` `_notebook_completion_server_args` helper |
| 8 | Frontend completion trigger only fired after `.` or Ctrl+Space; `library(jsonl` (typing inside parens) never triggered | `frontend/js/CellEditor.js` `_notebookCompletionSource` (extended to fire after `(`, `:`, `$`, `@`, `[`, or 2+ word chars for any language) |
| 9 | `_kernelLanguage` propagation in `setVenv` only updated DOM datasets, not the `CellEditor` instance property; existing cells stayed on their initial language | `frontend/js/NotebookEditor.js` `setVenv` |
| 10 | Bridge shadow was stale across cells: `update_cell` only overrode the current cell, leaving other cells at the disk version (race with `cell:update` debounce) | `backend/app/managers/notebook_lsp_bridge.py` `_latest_sources` cache |
| 11 | `_update_notebook_lsp` spammed ERROR per keystroke when an R env had no LSP installed | `backend/app/main.py` `_update_notebook_lsp` (`bridge.lsp_unavailable` flag set on first failure, checked at top of subsequent calls) |
| 12 | ark 0.1.250 cannot drive R 3.6.3 / R 4.0.5 - kernel dies during init | Phase 2.1: swap to IRkernel via PPM binary repos for legacy R; update legacy `runtime.json` `kernel_cmd` |
| 13 | IRkernel can't find itself when launched from inside a renv-isolated R env (same `renv::load` issue as #6 but for the kernel path) | Phase 2.1: also inject `RENV_CONFIG_EXTERNAL_LIBRARIES` into legacy `runtime.json` `kernel_env` |
| 14 | languageserver source-install fails for legacy R (R 3.6.3 PPM dep mismatch; R 4.0.5 testthat catch.h glibc 2.34 SIGSTKSZ) | Phase 2.2: install from PPM binary repos (`/cran/__linux__/focal/<date>`) |
| 15 | stringi.so links against libicui18n.so.66; Ubuntu 24.04 only ships libicu74 | Phase 2.2: install libicu66 from focal archive alongside libicu74 in Dockerfile |
| 16 | The probe Dockerfile only called `library(languageserver)` which doesn't trigger the lazy stringi dlopen; bug snuck past the probe and surfaced after the real rebuild | Updated meta-process: probes must exercise the actual entry-point (e.g. `languageserver::run()` with stdin redirected). See `feedback_probe_full_runtime_chain.md`. |
| 17 | ark INFO `tracing` log lines bleeding into cell stdout | Add `RUST_LOG=warn` to all R `runtime.json` `kernel_env` blocks. Caveat: requires `docker restart noted` to flush the in-memory `RuntimeRegistry` cache - editing runtime.json without restart is silently invisible (the cache loads at backend start and never reloads). |
| 18 | `setLintDiagnostics` `RangeError: Invalid position N in document of length M` when diagnostics arrived against an older, longer cell text | `frontend/js/CellEditor.js` `setLintDiagnostics` (clamp character offsets to per-line length) |
| 19 | Tab inside an open completion popup inserted whitespace instead of accepting the highlighted item | `frontend/js/CellEditor.js` and `frontend/js/FileEditor.js`: bind Tab to `acceptCompletion` via `Prec.highest`. Required adding `Prec` to the CodeMirror bundle exports (`scripts/build-codemirror/bundle-entry.js`) and rebuilding the bundle. |
| 20 | Ctrl+Z inside a focused cell crashed the menu's keyboard handler (`app._editor?.undo is not a function`); affected all languages, just discovered while testing R | `frontend/js/MenuBar.js` (skip text-editing shortcuts when focus is in an editable surface) and `frontend/js/NotebookEditor.js` (added public `undo()` method wrapping the existing `_undo()`) |

## What success looks like overall

If all of L1 - L9 pass:

- R LSP works for `.R` files in the editor (L1 - L4)
- R LSP works for cells in R notebooks (L5)
- Multiple R versions can run simultaneously, each with its own
  languageserver (L6)
- **All 6 R versions get full LSP** including the legacy ones via
  IRkernel kernel + PPM-binary languageserver (L7)
- Python and JavaScript LSP still work (L8)
- Cell-edit completions stay in sync without kernel restart and
  without Ctrl+Space (L9)

Test 33 R columns can then be filled in with `OK` for all R-related
features in both the modern and legacy columns. Phase 2 / 2.1 / 2.2
are SHIPPED.

## Two open gaps NOT covered by this walkthrough

1. **R Run from file editor** (T-5.R5): DONE. A per-env `bin/Rscript`
   shell wrapper launcher is generated at env creation time (via
   `env_post_create_files` with `template: true` and `executable: true`).
   The launcher sets R_HOME, LD_LIBRARY_PATH, R_PROFILE_USER, RENV_PATHS_*,
   RENV_CONFIG_EXTERNAL_LIBRARIES, RENV_CONFIG_SYNCHRONIZED_CHECK=FALSE,
   and NOTED_PROJECT_ROOT, then execs the per-version Rscript. Frontend
   `app-file-editors.js` extension check extended to include `.r` files,
   with `isR` branch resolving to `<env_path>/bin/Rscript <filename>`.
   Debug button shows a warning toast for R files. Lazy-generation in
   `env_manager._ensure_post_create_files` regenerates missing or stale
   launchers for existing envs.
2. **R debugger** (T-5.R6, Phase 3 R): ark exposes a DAP only inside
   Positron; the public 0.1.250 release does not expose DAP outside
   that process model. Legacy R via IRkernel will never have debug.
   Decision deferred until ark's DAP story matures. PLANNED, deferred.

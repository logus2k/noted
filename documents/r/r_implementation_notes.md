# noted: R Language Integration - Architecture and Implementation Notes

This document codifies the R integration plan for noted, governed by principle
**P4: Explicit Over Magical**. It is the finalized architectural reference,
revised after empirical verification in Apr 2026.

---

## 1. Core Architectural Pillars

The platform operates on a "Pattern of Three" for every supported language:

1. **Shadow Files** - cell execution maps to a physical file on disk so LSPs and
   debuggers see real source.
2. **Sidecar Proxying** - LSPs and DAP servers run as independent processes; the
   backend acts as a session-aware router.
3. **Deterministic Synchronization** - internal sync points align asynchronous
   execution with synchronous UI state.

---

## 2. Language Implementation Matrix

| Feature             | **Python**            | **JavaScript (Node)**         | **R**                                  |
| :------------------ | :-------------------- | :---------------------------- | :------------------------------------- |
| **Kernel**          | `ipykernel`           | `IJavascript` (NEL child)     | **`ark`** (Posit, Rust)                |
| **Shadow Mapping**  | `compile(..., 'exec')`| `//# sourceURL=path`          | `source(..., keep.source=TRUE)`        |
| **Internal Sync**   | `breakpoint()`        | `debugger;`                   | `browser()`                            |
| **LSP**             | jedi + ruff           | tsserver + biome              | `languageserver` (Phase 2)             |
| **Debugger (DAP)**  | `debugpy`             | `vscode-js-debug`             | Deferred (Phase 3)                     |
| **Env Manager**     | `venv` / `pip`        | `fnm` / `pnpm`                | `renv`                                 |
| **Multi-version**   | 5 Python versions     | 2 Node versions               | **6 R versions**                       |

---

## 3. R Version Set (Phase 1 deliverable)

Six R versions are bundled with the noted image, covering legacy through current:

| Version | Category        | Reason                                                                  |
|---------|-----------------|-------------------------------------------------------------------------|
| 3.6.3   | Legacy LTS      | Final 3.x release; many academic and Bioconductor pipelines depend on it |
| 4.0.5   | Baseline        | First version with `stringsAsFactors = FALSE`; pre-4.0 code often breaks |
| 4.2.3   | Stability       | Widely supported across CRAN; common on institutional servers           |
| 4.3.3   | Workhorse       | Mature 4.3.x; broad CRAN compatibility                                  |
| 4.4.2   | Current Stable  | Settled 4.4.x; Bioconductor 3.19/3.20                                   |
| 4.5.1   | Latest          | Newest release; Bioconductor 3.21                                       |

The Bioconductor constraint is the deciding factor for shipping both 4.4.x and
4.5.x: Bioconductor releases are strictly locked to specific R minor versions,
so dropping either branch would block an entire user community.

All six versions are available as prebuilt Debian packages from Posit's CDN
(`https://cdn.posit.co/r/ubuntu-2404/pkgs/r-<version>_1_amd64.deb`).

Per-version disk footprint: ~100 MB. Total R installation footprint: ~600 MB.

---

## 4. Kernel: Ark

Ark is Posit's Rust-based R kernel, designed as the foundation for Positron and
compatible with any Jupyter frontend. Critical properties:

- **Single 20 MB binary** (`ark-<ver>-linux-x64.zip` from GitHub releases)
- **Version-independent** - one ark binary serves all R versions; the active R
  is selected via `R_HOME` and `LD_LIBRARY_PATH` environment variables at
  kernel launch time
- **Standard Jupyter kernelspec** registered via `ark --install`
- **Active development** by Posit; MIT licensed
- **LSP and DAP features** are present in the binary but **currently exposed
  only to Positron**. noted uses ark for the kernel only; LSP and DAP ride on
  separate paths (Phase 2 / Phase 3)

Ark CLI flags noted relies on:
- `--connection_file FILE` - Jupyter kernel connection (set by jupyter_client)
- `--session-mode notebook` - the noted use case
- `--startup-file FILE` - run an R script at session startup (used in Phase 1.5
  for cell error line mapping)
- `--default-repos posit-ppm` - use Posit Public Package Manager for binary
  package availability (much faster than CRAN source builds)

---

## 5. Environment Management: renv

Each noted R environment is a renv project living in
`data/environments/r/<version>/<env_name>/`. The environment directory contains:

```
data/environments/r/4.5.1/my-env/
├── .Rprofile                 (noted-managed; see section 6)
├── renv.lock                 (created by renv::snapshot)
└── renv/
    └── library/
        └── linux-...-R-4.5/
            └── x86_64-pc-linux-gnu/
                ├── jsonlite/
                ├── glue/
                └── ...
```

The global renv cache lives at `/root/.cache/R/renv` and is shared across all
noted environments via hard-linking. **This cache is mounted as a persistent
Docker volume** so package compilations survive image rebuilds and so the cache
is shared across environment recreations.

---

## 6. Working Directory Architecture (Option E)

This is the architectural decision that took the longest to settle. The full
findings live in section 9 below; the short version is here.

### Goal

R kernels should provide the same UX shape as Python/JS kernels:
- `cwd = project_root` (cells access project files via relative paths)
- Multiple isolated environments per project
- Standard renv lifecycle (`install`, `snapshot`, `restore`, `status`) all work

### The constraint

renv's static analysis (used by `renv::dependencies()` and `renv::snapshot()`)
walks the working directory looking for `.R` files with `library()` calls. If
cwd were the env directory, renv would find zero dependencies and propose to
remove everything from the lockfile - destructive.

`R_LIBS_USER` is silently ignored when `.Rprofile` runs `renv::activate()`, so
the naive approach of "set cwd to project root, redirect library via env var"
does not work either.

### The solution

Decouple **where renv looks for source code** (cwd = project root) from
**where renv stores its state** (env vars override the library and lockfile
paths). Override the `.Rprofile` lookup so noted's startup script runs instead
of any user-provided one.

Per R kernel launch:

```
cwd                  = <project_root>
R_HOME               = /opt/R/<version>/lib/R
LD_LIBRARY_PATH      = /opt/R/<version>/lib/R/lib
R_PROFILE_USER       = <env_path>/.Rprofile
RENV_PATHS_LIBRARY   = <env_path>/renv/library
RENV_PATHS_LOCKFILE  = <env_path>/renv.lock
NOTED_PROJECT_ROOT   = <project_root>
```

The noted-managed `.Rprofile` (in `<env_path>/.Rprofile`) contains:

```r
# noted-managed R startup - do not edit
library(renv)
renv::load(project = getwd())
```

`renv::load(project = getwd())` activates renv at the project root (which is
cwd), and the `RENV_PATHS_*` env vars redirect renv's reads/writes to the
isolated env path.

### What this gives us (verified empirically)

| Property                                              | Status |
|-------------------------------------------------------|--------|
| `cwd = project_root` consistent with Python/JS        | works  |
| Multiple R envs per project                           | works  |
| `renv::snapshot()` detects deps from project source   | works  |
| Lockfile lives in env path, not project root          | works  |
| Library lives in env path, not project root           | works  |
| `renv::restore()` rebuilds env from lockfile          | works  |
| User's existing project `.Rprofile` is preempted      | works  |
| Per-env R version selection via `R_HOME`              | works  |
| Project files accessible via `NOTED_PROJECT_ROOT`     | works  |

### Acceptable trade-off

renv creates a small `renv/` directory (8 KB total) inside the project root the
first time it activates. Contents:

```
<project_root>/renv/
├── .gitignore                (56 bytes; standard renv ignore list)
└── staging/                  (empty scratch dir for installs)
```

This is renv's **standard convention** - any open-source R project on GitHub
that uses renv has the same `renv/.gitignore`. It is **not noted-specific
weirdness**. Users committing to git get exactly one tracked file
(`renv/.gitignore`); the actual library and lockfile are not in the project
tree at all.

For users who want zero git artifacts, the noted user guide will document
adding `renv/` to the project's root `.gitignore`.

The Explorer panel hides the `renv/` directory by default to reduce visual
noise, the same way it already hides `.git/` and `__pycache__/`.

---

## 7. Cell Execution and Error Line Mapping

Cells are executed via ark using a startup script that wraps `source()` in
`withCallingHandlers` to capture line numbers on errors:

```r
.noted_run_cell <- function(shadow_path) {
  withCallingHandlers(
    source(shadow_path, keep.source = TRUE, echo = FALSE),
    error = function(e) {
      calls <- sys.calls()
      for (i in seq_along(calls)) {
        sr <- attr(calls[[i]], "srcref")
        if (!is.null(sr)) {
          srcfile <- attr(sr, "srcfile")
          if (!is.null(srcfile) && !is.null(srcfile$filename) &&
              srcfile$filename == shadow_path) {
            cat(sprintf("\n[noted-error]{\"file\":\"%s\",\"line\":%d}\n",
                        srcfile$filename, sr[1]))
            break
          }
        }
      }
    }
  )
}
```

The wrapper is loaded via the same noted-managed `.Rprofile` from section 6.
noted's R Strategy in `language_strategies.py` writes each cell to a temp file,
calls `.noted_run_cell("/tmp/noted_r_cell_<hash>.R")`, and parses the
`[noted-error]` marker from stdout to map errors back to the cell index.

`sys.calls()` srcref walking under `withCallingHandlers` was empirically
verified to produce the correct file and line number; `tryCatch` does not
preserve the srcref and was rejected.

---

## 8. Implementation Phases

### Phase 1: Runtime, Environment, Kernel Execution

**Backend:**

- 6 `data/runtimes/r/<version>/runtime.json` files (one per R version)
- Extend `runtime.json` schema with optional `kernel_env` field (dict of env
  var name -> value, with `{env_path}` and `{project_root}` template
  substitution)
- Extend `kernel_manager.start_kernel` to merge per-runtime `kernel_env` into
  the subprocess environment
- `env_manager._repair_environments`: skip Python venv repair for
  `language == "r"`
- New `RStrategy` in `language_strategies.py` with stubbed DAP methods
- `env_manager.create_env` for R: run `renv::init(bare=TRUE)` in env_path,
  then write the noted-managed `.Rprofile` from a template
- New template at `data/templates/r/noted_rprofile.R`

**Dockerfile:**

- System libraries: `build-essential gfortran libxml2-dev libssl-dev
  libcurl4-openssl-dev libfontconfig1-dev libfreetype6-dev libpng-dev
  libtiff5-dev libjpeg-dev libharfbuzz-dev libfribidi-dev libgit2-dev`
- Install 6 R versions from Posit's ubuntu-2404 packages
- Install renv into each R version
- Install ark binary from GitHub releases

**docker-compose.yml:**

- Persistent named volume `noted_renv_cache` mounted at `/root/.cache/R/renv`

**Frontend:**

- File type icon for `.R`, `.r`, `.Rmd`, `.qmd`
- CodeMirror R syntax mode via `@codemirror/legacy-modes/mode/r`
- Bundle rebuild adding `@codemirror/legacy-modes` to package.json
- Explorer panel: hide `renv/` directories from the tree by default
- No notebook cell language selector changes (kernel discovery handles this)

**Testing:**

- Update `testing/33_test-language-support-matrix.md` with R column
- Manual E2E: create env, run cell, install package, snapshot, restart, switch
  R version

**Estimated effort: 15-25 hours**

### Phase 2: LSP for R

- Install `languageserver` R package per R version (CRAN, requires compilation)
- New `RLspStrategy` in `backend/app/managers/lsp/r_strategy.py` following the
  established LSP Strategy pattern
- Extend `notebook_lsp_bridge.py` with an R branch (combined shadow file with
  `# %%` markers, similar to Python)
- Update `routers/lsp.py` lint type mapping
- Frontend: add R to `_lspLanguageForFile` in `FileEditor.js`

**Estimated effort: 10-15 hours**

### Phase 3: Debug for R (deferred)

Phase 3 is **deferred indefinitely**. Two reasons:

1. ark's bundled DAP is currently exposed only to Positron, not to other
   Jupyter frontends. The Posit team has stated they plan to make it
   frontend-agnostic in the future.
2. The alternative (Manuel Hentschel's `vscDebugger`) is functional but rough,
   and reproducing its setup outside VS Code's R extension would take
   significant effort for limited polish.

When ark exposes DAP outside Positron, Phase 3 can land in approximately
20-30 hours of additional work, slotting into the existing
`language_strategies.py` DAP Strategy pattern.

### Phase 4: Plotting (optional, parallel to Phase 2)

Use `httpgd` R package for interactive SVG plot rendering. Out of scope for
the initial delivery; can be added when the basic experience is validated.

---

## 9. Empirical Findings (Apr 2026)

Three rounds of probe testing in throwaway containers established the design
above. Key findings worth preserving:

### Round 1 - Basic ark + renv viability

- ark + renv work correctly together
- ark's default kernelspec hardcodes `LD_LIBRARY_PATH` to whichever R was the
  default at install time
- `renv::install()` is fast (~2 seconds for small packages)
- Per-project libraries are heavily hard-linked into the global cache
- Image footprint per R version: ~100 MB

### Round 2 - Multi-version dispatch and source line mapping

- ark accepts `R_HOME` + `LD_LIBRARY_PATH` overrides at process launch time,
  successfully redirecting to a non-default R version
- Cell error line mapping works via `withCallingHandlers` + `sys.calls()`
  srcref walk; `tryCatch` does NOT preserve srcrefs
- Rcpp and data.table compile cleanly with the chosen system library set
- Posit publishes prebuilt deb packages for all 6 target R versions on
  ubuntu-2404

### Round 3 - The renv vs R_LIBS_USER finding

This was the critical round. The naive approach (cwd = project root,
`R_LIBS_USER` for env isolation) **fails** because renv's `.Rprofile`
auto-activation completely overrides `R_LIBS_USER`. The library stays at the
project's cwd, not the noted env.

This forced the architectural search for Option E:

| Option | Description | Verdict |
|--------|-------------|---------|
| A | cwd = env_path, use .Rprofile activation | renv::snapshot() can't find project source - destructive |
| B | cwd = project_root, no renv | loses lockfile workflow, isolates R from R community conventions |
| C | cwd = project_root, project root IS the renv project | one R env per project, conflicts with multi-env model |
| D | cwd = env_path, symlink project files | fragile, hybrid filesystem confusion |
| **E** | **cwd = project_root, env vars redirect renv state** | **all goals met** |

Option E was suggested in a second-opinion review and verified in round 3 with
six explicit tests. All tests passed.

### Round 3 - Pollution analysis

renv creates a small `renv/` directory in the project root (one 56-byte
`.gitignore` and an empty `staging/` dir). This is renv's standard convention
and is accepted as a documented trade-off rather than fought.

---

## 10. Considered and rejected: r2u

**[r2u](https://github.com/eddelbuettel/r2u)** by Dirk Eddelbuettel publishes
prebuilt CRAN binary packages as `.deb` files for Ubuntu, integrated via apt
and the `bspm` shim. Big speedups: tidyverse installs in 18 seconds versus
~10 minutes from source.

**Why it does not fit noted (evaluated 2026-04-09):**

1. **R version coverage gap.** r2u publishes binaries built against R 4.4.x
   and 4.5.x only. Our 6-version set (3.6.3, 4.0.5, 4.2.3, 4.3.3, 4.4.2,
   4.5.1) is mostly outside r2u's coverage. Legacy versions for
   reproducibility get nothing from r2u.
2. **Layout mismatch.** r2u installs into the system R library
   (`/usr/lib/R/site-library/`). noted uses Posit's Debian packages that
   install into `/opt/R/<version>/`. Aligning the two would require
   significant Dockerfile rework to special-case one R version.
3. **renv incompatibility (the dealbreaker).** r2u's speedup comes from the
   `bspm` shim intercepting `install.packages()` calls. **renv bypasses
   `install.packages()` entirely**, going directly to its own download/build
   pipeline. Cell-based `renv::install()` never reaches the bspm shim and
   sees no benefit. Since noted's R workflow is renv-centric, r2u would
   accelerate at most a one-time Dockerfile install (e.g. `languageserver`)
   for a single R version, with zero benefit to user workflows.

**When to revisit:** if Posit's deb packages and r2u ever converge on the
same install layout, OR if user demand emerges for a non-renv R workflow
using direct `install.packages()` calls.

For the languageserver install specifically, the package `r-cran-languageserver`
(version 0.3.17 as of 2026-04) does exist in r2u for noble, but its
dependency on `r-base-core (>= 4.5.0)` means even using it for one R version
would require restructuring the R 4.5.1 install to match r2u's expectations.
Not worth the effort for a one-time Dockerfile build step.

## 11. References

- ark: https://github.com/posit-dev/ark
- renv: https://rstudio.github.io/renv/
- Posit's R deb packages: https://docs.posit.co/resources/install-r/
- Bioconductor R version compatibility: https://bioconductor.org/about/release-announcements/
- r2u (rejected, see section 10): https://github.com/eddelbuettel/r2u

---

**This document is the finalized architectural reference for noted's R
integration. Phase 1 implementation begins from here.**

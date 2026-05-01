# Test 33: Language Support Matrix

## Status

| Feature | Python .ipynb | Python files | JS .ipynb | JS files | HTML | CSS | JSON | YAML | R .ipynb (modern) | R files (modern) | R legacy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Syntax Coloring | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| Auto-Completion | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| Documentation | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| Linting | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| Formatting | - | OK | - | ? | ? | ? | ? | ? | - | ? | ? |
| Go to Definition | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| Find References | ? | ? | ? | ? | ? | ? | ? | ? | - | - | - |
| Run | OK | OK | OK | OK | - | - | - | - | OK | OK | OK |
| Debug | OK | OK | OK | OK | - | - | - | - | - | - | - |

## Legend

- **OK** - Tested and working
- **?** - Not yet tested
- **NOK** - Tested, not working
- **-** - Not applicable / not yet implemented
- **NA** - Not Available on this tier (deliberate, see Tiered R support below)

## Notes

- HTML/CSS/JSON LSP provided by vscode-langservers-extracted
- Python LSP: ruff (linting) + jedi (completions, hover, navigation)
- JavaScript LSP: biome (linting) + tsserver (completions, hover, navigation)
- HTML/CSS/JSON/YAML use single-server mode (one server handles all features)
- YAML LSP provided by yaml-language-server (Red Hat)
- Debug is not applicable for HTML/CSS/JSON/YAML files
- Run is not applicable for HTML/CSS/JSON/YAML files or notebooks

### R Support Matrix (Phase 2 + 2.1 + 2.2)

**All six R versions get full LSP** (completion, hover, lint) and
working kernel execution. The implementation uses two kernels and two
languageserver install paths, dispatched per version compatibility:

| R version | Kernel | languageserver source | Tier |
|---|---|---|---|
| 4.5.1 | ark 0.1.250 | latest CRAN | Full |
| 4.4.2 | ark 0.1.250 | latest CRAN | Full |
| 4.3.3 | ark 0.1.250 | latest CRAN | Full |
| 4.2.3 | ark 0.1.250 | latest CRAN | Full |
| 4.0.5 | **IRkernel 1.1.1** (PPM 2021-05-01) | **languageserver 0.3.10** (PPM 2021-05-01 binary) | Full |
| 3.6.3 | **IRkernel 1.1** (PPM 2020-04-01) | **languageserver 0.3.5** (PPM 2020-04-01 binary) | Full |

**Why two kernels?** ark 0.1.250 cannot drive R 3.6.3 / R 4.0.5 - the
R API surface ark expects is from the R 4.x era and the older
interpreters die silently during init (verified empirically 2026-04-10).
IRkernel is the original Jupyter R kernel from REditorSupport - pure R
+ zeromq, stable cross-version bindings. We use ark for modern R
(richer feature surface, future Phase 3 DAP) and IRkernel for legacy R
(stable, lower ceremony, no glibc tarpit).

**Why two languageserver paths?** Source-installing the latest
languageserver into legacy R fails for two distinct reasons: R 3.6.3
hits a PPM source dep resolution mismatch in the pkgload/withr/waldo
cluster, and R 4.0.5 hits the testthat catch.h glibc 2.34 SIGSTKSZ
compile error. The PPM binary repo path
(`/cran/__linux__/focal/<date>`) bypasses both: prebuilt .so files
from each R version's active era ship a self-consistent dependency
set, and there's no compilation involved. Runtime symbol versions
from 2020/2021 binaries still satisfy Ubuntu 24.04's libssl/libxml2.

**Architecture:**

- R uses **Option E**: cwd = project_root, with R_PROFILE_USER and
  RENV_PATHS_LIBRARY/LOCKFILE redirecting renv state to the env
  directory.
- Modern R uses **ark** (Posit) as the kernel, dispatched per version
  via R_HOME / LD_LIBRARY_PATH. Legacy R uses **IRkernel** invoked
  via the per-version `R --slave -e 'IRkernel::main()'` launcher.
- All R versions use the same **`RENV_CONFIG_EXTERNAL_LIBRARIES`**
  hook to make the system-installed languageserver visible from
  inside renv-isolated envs.
- **Debug for R is Phase 3**, deferred until ark exposes its DAP
  outside Positron. Legacy R via IRkernel will never have debug.
- See `documents/r/r_implementation_notes.md` for the full architecture.

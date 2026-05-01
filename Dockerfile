# ── Stage 1: Base image with CUDA runtime, Python interpreters, and pip deps ──
# Docker caches this stage. It only rebuilds when these layers change
# (new Python versions, system packages, or requirements.txt updates).
FROM nvidia/cuda:13.1.1-runtime-ubuntu24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive

# System packages + deadsnakes PPA for multiple Python versions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common gpg-agent && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        # Python interpreters (latest patch auto-resolved by deadsnakes)
        python3.10 python3.10-venv python3.10-dev \
        python3.11 python3.11-venv python3.11-dev \
        python3.12 python3.12-venv python3.12-dev \
        python3.13 python3.13-venv python3.13-dev \
        python3.13-nogil \
        python3.14 python3.14-venv python3.14-dev \
        python3.14-nogil \
        # Build deps for native extensions (pyzmq, zeromq/node-gyp, etc.)
        gcc g++ make libzmq3-dev \
        # pip bootstrap
        python3-pip \
        # curl for health checks
        curl \
        # git for DVC and version control
        git \
        # unzip for fnm (Node.js version manager) installation
        unzip \
        # pandoc for notebook-to-docx conversion
        pandoc \
        libportaudio2 \
        # Camoufox (headless Firefox) dependencies
        libgtk-3-0 libdbus-glib-1-2 libasound2t64 libx11-xcb1 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libatk1.0-0 \
        libxshmfence1 libxfixes3 && \
    rm -rf /var/lib/apt/lists/* && \
    # Remove broken distutils-precedence.pth (references missing _distutils_hack)
    rm -f /usr/lib/python3/dist-packages/distutils-precedence.pth

# Install uv — fast Python package installer (used internally for env setup)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Ensure pip is available for each Python version
RUN for py in python3.10 python3.11 python3.12 python3.13 python3.14; do \
        $py -m ensurepip --upgrade 2>/dev/null || true; \
    done

WORKDIR /app

# Install Python dependencies (using uv for speed)
COPY backend/requirements.txt backend/requirements.txt
RUN uv pip install --system --break-system-packages --python python3.12 \
    -r backend/requirements.txt && \
    python3.12 -m camoufox fetch

# ── Node.js via fnm (Fast Node Manager) ──
# fnm is a Rust-based Node.js version manager (mirrors Python's multi-runtime model)
ENV FNM_DIR="/root/.local/share/fnm"
ENV PATH="${FNM_DIR}:${PATH}"

RUN curl -fsSL https://fnm.vercel.app/install | bash -s -- --install-dir "${FNM_DIR}" --skip-shell && \
    eval "$(${FNM_DIR}/fnm env)" && \
    fnm install 20 && \
    fnm install 22 && \
    fnm default 20 && \
    ln -sf "$(which node)" /usr/local/bin/node && \
    ln -sf "$(which npm)" /usr/local/bin/npm && \
    ln -sf "$(which npx)" /usr/local/bin/npx

# Install pnpm (disk-efficient package manager) and global JS tools
ENV PNPM_HOME="/root/.local/share/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"

RUN npm install -g pnpm typescript-language-server typescript @biomejs/biome vscode-langservers-extracted yaml-language-server && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/pnpm" /usr/local/bin/pnpm && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/typescript-language-server" /usr/local/bin/typescript-language-server && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/biome" /usr/local/bin/biome && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/vscode-html-language-server" /usr/local/bin/vscode-html-language-server && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/vscode-css-language-server" /usr/local/bin/vscode-css-language-server && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/vscode-json-language-server" /usr/local/bin/vscode-json-language-server && \
    ln -sf "$(dirname "$(readlink -f /usr/local/bin/node)")/yaml-language-server" /usr/local/bin/yaml-language-server


# ── R: system libraries for native CRAN packages ──
# Required by Rcpp, data.table, sf, xml2, ssl-using packages, plotting libs, git2r, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gfortran \
        libxml2-dev libssl-dev libcurl4-openssl-dev \
        libfontconfig1-dev libfreetype6-dev libpng-dev \
        libtiff5-dev libjpeg-dev libharfbuzz-dev libfribidi-dev \
        libgit2-dev && \
    rm -rf /var/lib/apt/lists/*

# ── R: install 6 versions from Posit's prebuilt Ubuntu 24.04 packages ──
# Each version lives at /opt/R/<version>/ and does not collide with the others.
# noted's runtime registry selects between them via R_HOME at kernel launch time.
RUN for V in 3.6.3 4.0.5 4.2.3 4.3.3 4.4.2 4.5.1; do \
        curl -fsSL -O https://cdn.posit.co/r/ubuntu-2404/pkgs/r-${V}_1_amd64.deb && \
        apt-get update && apt-get install -y --no-install-recommends ./r-${V}_1_amd64.deb && \
        rm r-${V}_1_amd64.deb && \
        rm -rf /var/lib/apt/lists/*; \
    done

# ── R: default `R` on PATH for the no-env case ──
# When a `.R` script file is opened in the editor without an env attached,
# the LSP runtime_id is None and no kernel_env is injected. The languageserver
# launcher therefore needs a plain `R` on PATH. We point it at the newest
# modern R version (4.5.1) so script-only edits get full LSP. Envs continue
# to dispatch via R_HOME/LD_LIBRARY_PATH per their runtime.json.
RUN ln -sf /opt/R/4.5.1/bin/R /usr/local/bin/R && \
    ln -sf /opt/R/4.5.1/bin/Rscript /usr/local/bin/Rscript

# ── R: legacy ICU runtime for binary R packages built against ICU 66 ──
#
# Phase 2.2 (2026-04-10): legacy R packages installed from PPM binary
# repos (R 3.6.3 from 2020-04, R 4.0.5 from 2021-05) were built on
# Ubuntu 20.04 (focal) which shipped libicu66. Ubuntu 24.04 (noble)
# only ships libicu74 - the symbol versions are not compatible, so
# any 2020-2021 R package that wraps ICU (notably stringi, which is
# pulled in transitively via languageserver -> lintr -> stringi) fails
# at dlopen time with:
#     unable to load shared object '.../stringi/libs/stringi.so':
#     libicui18n.so.66: cannot open shared object file
# That blocks the entire LSP startup chain for legacy R.
#
# Fix: install the libicu66 .deb directly from Ubuntu's focal archive.
# It coexists with libicu74 (different SONAME, no file conflict) and
# only adds ~30MB. This is exactly the kind of "old runtime alongside
# new runtime" pattern that lets a single image serve both eras of
# binaries cleanly.
#
# Modern R (4.2+) packages installed from latest CRAN are built fresh
# against libicu74, so they don't need this. Only the legacy binary
# install path benefits.
RUN curl -fsSL -O http://archive.ubuntu.com/ubuntu/pool/main/i/icu/libicu66_66.1-2ubuntu2.1_amd64.deb && \
    dpkg -i --force-depends libicu66_66.1-2ubuntu2.1_amd64.deb && \
    rm libicu66_66.1-2ubuntu2.1_amd64.deb

# ── R: install renv into each R version (compiled per version) ──
RUN for V in 3.6.3 4.0.5 4.2.3 4.3.3 4.4.2 4.5.1; do \
        /opt/R/${V}/bin/R --slave --no-save -e \
            "install.packages('renv', repos='https://cloud.r-project.org/')"; \
    done

# ── R: extra system deps required by languageserver dependency chain ──
# fs (CRAN package) needs cmake + pkg-config + libuv to build its vendored
# libuv copy. fs is pulled in by languageserver via the roxygen2 -> pkgload
# -> fs chain. We isolate these in their own layer so the (slow, ~80 min)
# R version installs above stay cached when this layer changes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake pkg-config libuv1-dev && \
    rm -rf /var/lib/apt/lists/*

# ── R: install languageserver (Phase 2 LSP) per R version ──
#
# Tiered support for languageserver across R versions, validated empirically:
#
#   R 4.5.1, 4.4.2, 4.3.3, 4.2.3 -> Full LSP via latest CRAN languageserver
#
#   R 4.0.5                       -> SKIPPED (kernel-only mode)
#                                    PPM 2021-05-01 resolves a coherent
#                                    package set, but `testthat` source
#                                    from that era cannot compile under
#                                    glibc 2.34+ because SIGSTKSZ is no
#                                    longer a constant expression. Modern
#                                    Ubuntu 24.04 ships glibc 2.39 and the
#                                    old `catch.h` test runner uses
#                                    `static char altStackMem[SIGSTKSZ]`
#                                    which is now invalid C++. The
#                                    languageserver -> lintr -> testthat
#                                    chain fails as a result.
#
#   R 3.6.3                       -> SKIPPED (kernel-only mode)
#                                    Multiple PPM snapshots (2019-12 through
#                                    2021-03) all fail dependency resolution
#                                    for the pkgload/withr/waldo cluster.
#                                    Even if dep resolution were fixed, the
#                                    same testthat / glibc 2.34+ problem
#                                    would block the install.
#
# Both legacy versions stay as kernel-only runtimes: users get full
# notebook execution for reproducibility, just no IntelliSense. This is
# documented in `documents/r/r_implementation_notes.md` and shown in
# `testing/33_test-language-support-matrix.md`.
#
# Each install is verified with `quit(status=...)` because R's
# install.packages() reports compile failures only as warnings and exits 0,
# which would otherwise leave the image in a silently broken state.
RUN set -e; \
    for V in 4.2.3 4.3.3 4.4.2 4.5.1; do \
        echo "=== installing languageserver (latest CRAN) for R ${V} ===" && \
        /opt/R/${V}/bin/R --slave --no-save -e " \
            install.packages('languageserver', repos='https://cloud.r-project.org/'); \
            ok <- 'languageserver' %in% rownames(installed.packages()); \
            cat(if (ok) '[OK]' else '[FAIL]', 'languageserver R', '${V}', '\\n'); \
            quit(status = if (ok) 0 else 1) \
        "; \
    done

# ── R: install languageserver for legacy R versions via PPM binary repos ──
#
# Phase 2.2 (2026-04-10): the source-install path for languageserver
# fails for legacy R for two distinct reasons:
#   - R 3.6.3: PPM source dep resolution picks transitively-incompatible
#     versions across the pkgload / withr / waldo / lintr cluster
#   - R 4.0.5: testthat's vendored catch.h uses
#     `static char altStackMem[SIGSTKSZ]` which no longer compiles
#     under glibc 2.34+ (Ubuntu 24.04 ships glibc 2.39)
#
# BUT: the PPM binary repo path (`/cran/__linux__/focal/<date>`)
# bypasses both issues entirely - prebuilt .so files were created back
# when R 3.6 / 4.0 were current and the dep set was self-consistent.
# No source compilation, no glibc-era checks. The runtime libraries
# (libssl, libxml2 etc) on Ubuntu 24.04 still satisfy the symbol
# versions the 2020-2021 binaries were linked against.
#
# Snapshot dates match each R version's active era (same dates as the
# IRkernel install below):
#   R 4.0.5  -> PPM 2021-05-01 -> languageserver 0.3.10 + 40 deps
#   R 3.6.3  -> PPM 2020-04-01 -> languageserver 0.3.5  + 40 deps
#
# Both probed via throwaway Dockerfile builds in /tmp/probe-langsrv-*
# before landing here, per feedback_no_ephemeral_probes.md - we never
# trust running-container probes for "does this install work" claims.
# Both probes built clean in ~95 seconds with all binary installs.
RUN set -e; \
    echo "=== installing languageserver for R 4.0.5 from PPM 2021-05-01 (binary) ===" && \
    /opt/R/4.0.5/bin/R --slave --no-save -e " \
        install.packages('languageserver', repos='https://packagemanager.posit.co/cran/__linux__/focal/2021-05-01'); \
        ok <- 'languageserver' %in% rownames(installed.packages()); \
        if (ok) { suppressMessages(library(languageserver)); cat('[OK] languageserver R 4.0.5 (', as.character(packageVersion('languageserver')), ')\\n') } else { cat('[FAIL] languageserver R 4.0.5\\n') }; \
        quit(status = if (ok) 0 else 1) \
    " && \
    echo "=== installing languageserver for R 3.6.3 from PPM 2020-04-01 (binary) ===" && \
    /opt/R/3.6.3/bin/R --slave --no-save -e " \
        install.packages('languageserver', repos='https://packagemanager.posit.co/cran/__linux__/focal/2020-04-01'); \
        ok <- 'languageserver' %in% rownames(installed.packages()); \
        if (ok) { suppressMessages(library(languageserver)); cat('[OK] languageserver R 3.6.3 (', as.character(packageVersion('languageserver')), ')\\n') } else { cat('[FAIL] languageserver R 3.6.3\\n') }; \
        quit(status = if (ok) 0 else 1) \
    "

# ── R: install IRkernel for the legacy R versions (Phase 2.1) ──
#
# ark 0.1.250 (the modern R kernel we use for R 4.2.3 / 4.3.3 / 4.4.2 /
# 4.5.1) cannot drive R 3.6.3 or R 4.0.5 - the R API surface ark expects
# is from the R 4.x era and the older interpreters die during init,
# silently, before producing any output. Verified empirically during
# Phase 2 LSP walkthrough on 2026-04-10.
#
# The fallback for those legacy versions is IRkernel (the original
# Jupyter R kernel from REditorSupport / IRkernel.org). It's pure R +
# zeromq and has stable bindings dating back to R 3.x. Importantly its
# dependency chain (rlang, glue, jsonlite, pbdZMQ, repr, IRdisplay,
# crayon, evaluate, uuid, digest) does NOT include testthat, so we
# avoid the glibc 2.34 SIGSTKSZ compile failure that killed
# languageserver for R 4.0.5.
#
# We use Posit Public Package Manager binary repos for both versions
# to skip compilation entirely - PPM serves prebuilt .so files for
# Ubuntu 20.04 (focal) which work fine on the noted base (Ubuntu
# 24.04). Snapshot dates picked to match each R version's active era:
#
#   R 4.0.5  -> PPM 2021-05-01 (R 4.0.5 was current March-May 2021)
#   R 3.6.3  -> PPM 2020-04-01 (R 3.6.3 was current Feb-April 2020)
#
# Both probed via throwaway Dockerfile builds in /tmp/probe-irkernel-*
# before landing here, per feedback_no_ephemeral_probes.md - we never
# trust running-container probes for "does this install work" claims.
RUN set -e; \
    echo "=== installing IRkernel for R 4.0.5 from PPM 2021-05-01 ===" && \
    /opt/R/4.0.5/bin/R --slave --no-save -e " \
        install.packages('IRkernel', repos='https://packagemanager.posit.co/cran/__linux__/focal/2021-05-01'); \
        ok <- 'IRkernel' %in% rownames(installed.packages()); \
        if (ok) { suppressMessages(library(IRkernel)); cat('[OK] IRkernel R 4.0.5\\n') } else { cat('[FAIL] IRkernel R 4.0.5\\n') }; \
        quit(status = if (ok) 0 else 1) \
    " && \
    echo "=== installing IRkernel for R 3.6.3 from PPM 2020-04-01 ===" && \
    /opt/R/3.6.3/bin/R --slave --no-save -e " \
        install.packages('IRkernel', repos='https://packagemanager.posit.co/cran/__linux__/focal/2020-04-01'); \
        ok <- 'IRkernel' %in% rownames(installed.packages()); \
        if (ok) { suppressMessages(library(IRkernel)); cat('[OK] IRkernel R 3.6.3\\n') } else { cat('[FAIL] IRkernel R 3.6.3\\n') }; \
        quit(status = if (ok) 0 else 1) \
    "

# ── R: install vscDebugger (Phase 3 R Debug) per R version ──
#
# vscDebugger (ManuelHentschel/vscDebugger) is an R package that
# implements the Debug Adapter Protocol (DAP) for R. It listens on a
# TCP socket and speaks standard DAP wire protocol (Content-Length
# headers + JSON), same as vscode-js-debug does for JavaScript.
#
# noted uses vscDebugger for ALL 6 R versions because Posit's ark
# kernel has a built-in DAP but it's only accessible inside
# Positron's process model (uses Positron-specific Jupyter Comms,
# not a standalone TCP/stdio transport). vscDebugger provides a
# consistent, transport-agnostic debug path regardless of whether
# the kernel is ark (modern R) or IRkernel (legacy R).
#
# The package is NOT on CRAN. Installed from r-universe which
# provides source packages (3 small C files: init.c, ppid.c,
# promise.c - compiles in ~3s per R version). Dependencies are
# minimal: jsonlite, R6 (already installed via languageserver's
# dep chain). Does NOT pull in tcltk (verified on v0.5.6).
#
# All 6 R versions probed via throwaway Dockerfile build before
# landing here. All compile and load cleanly.
RUN set -e; \
    for V in 3.6.3 4.0.5 4.2.3 4.3.3 4.4.2 4.5.1; do \
        echo "=== installing vscDebugger for R ${V} ===" && \
        /opt/R/${V}/bin/R --slave --no-save -e " \
            install.packages('vscDebugger', repos='https://manuelhentschel.r-universe.dev'); \
            ok <- 'vscDebugger' %in% rownames(installed.packages()); \
            if (ok) { suppressMessages(library(vscDebugger)); cat('[OK] vscDebugger', as.character(packageVersion('vscDebugger')), 'R', '${V}', '\\n') } else { cat('[FAIL] vscDebugger R', '${V}', '\\n') }; \
            quit(status = if (ok) 0 else 1) \
        "; \
    done

# ── R: install ark kernel binary (single binary serves all R versions) ──
# noted uses ark only as the Jupyter kernel; its bundled LSP and DAP are
# currently Positron-only so noted's LSP/DAP rides on separate paths.
# We do NOT run `ark --install` here because it tries to autodetect an R
# install at image-build time and would hardcode one R version into the
# kernelspec. noted launches ark directly via the kernel_cmd in each
# runtime.json, which points at /usr/local/bin/ark and sets R_HOME and
# LD_LIBRARY_PATH per R version.
RUN curl -fsSL -O https://github.com/posit-dev/ark/releases/download/0.1.250/ark-0.1.250-linux-x64.zip && \
    unzip ark-0.1.250-linux-x64.zip -d /tmp/ark-extract && \
    mv /tmp/ark-extract/ark /usr/local/bin/ark && \
    chmod +x /usr/local/bin/ark && \
    rm -rf ark-0.1.250-linux-x64.zip /tmp/ark-extract


# ── Stage 2: App image — copies application code onto the cached base ──
# Fast rebuild (~1s) on every code change.
FROM base

WORKDIR /app

COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/
COPY data/templates/ data/templates/
COPY vendor/js-debug/ vendor/js-debug/

# Fix CRLF line endings (Windows Git may convert LF to CRLF despite .gitattributes)
RUN sed -i 's/\r$//' scripts/*.sh && chmod +x scripts/*.sh

# Ensure data directories exist
RUN mkdir -p data/projects data/environments

# Trust all git directories (bind-mounted repos have different ownership)
RUN git config --global --add safe.directory '*'

EXPOSE 8123

ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:socket_app", "--host", "0.0.0.0", "--port", "8123", "--app-dir", "backend"]

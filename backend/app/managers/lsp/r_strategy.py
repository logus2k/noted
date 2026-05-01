"""R LSP strategy: languageserver R package via stdio.

Single-server language. The `languageserver` R package (REditorSupport) is
installed per R version in the Docker image - noted's lsp_manager picks the
right R via R_HOME / LD_LIBRARY_PATH at process spawn time, mirroring the
Phase 1 kernel dispatch.

The diagnostic stream comes from lintr (which languageserver invokes), so
the enrichment branch shapes lintr-style codes into noted's standard
"message + label" format.

Phase 1 / Phase 2 split:
- Phase 1 (done): kernel execution via ark, multi-version R, renv envs
- Phase 2 (this file): LSP via languageserver - completion, hover, lint,
  formatting
- Phase 3 (deferred): debug, deferred until ark exposes its DAP outside
  Positron

R versions that lack languageserver (R 3.6.3, R 4.0.5 in our deployment)
are still usable as kernels but get no LSP. The strategy itself does not
encode that exclusion - lsp_manager checks at startup time whether the
binary actually exists for the requested env's R version and falls back
gracefully if not.
"""

import logging

from .base import BaseLspStrategy

logger = logging.getLogger(__name__)


class RLspStrategy(BaseLspStrategy):
    language_id = "r"
    extensions = (".r", ".rmd", ".qmd")

    # Single-server: languageserver does linting + completion + hover.
    lint_server_type = "languageserver"
    completion_server_type = None

    # languageserver operates on real filesystem paths via the project root
    # cwd that lsp_manager sets when launching the process. We use virtual
    # URIs from the frontend without rewriting because the frontend already
    # sends file:///<project_id>/... and the server resolves them relative
    # to its cwd.
    hover_uses_real_uri = False

    @classmethod
    def build_command(cls, server_type: str) -> list[str]:
        if server_type != "languageserver":
            raise ValueError(f"RLspStrategy: unknown server_type {server_type}")
        # The launcher is the noted-managed wrapper script that picks the
        # right R version via env vars (set by lsp_manager from runtime.json
        # kernel_env). Falls back to /opt/R/4.5.1/bin/R via the env's R_HOME.
        # Using `--slave` for quiet startup, `--no-save` to skip workspace
        # save prompts, and `-e languageserver::run()` to enter the LSP loop.
        return ["R", "--slave", "--no-save", "-e", "languageserver::run()"]

    @classmethod
    def complete_init_capabilities(cls, result, has_completion_server):
        # Single-server mode: ensure completionProvider is populated since
        # codemirror-languageserver does not handle dynamic registration.
        # resolveProvider is disabled so per-item docs do not render as an
        # inline side panel - hover docs live in noted's external
        # Documentation panel.
        caps = result.setdefault("capabilities", {})
        provider = caps.get("completionProvider") or {}
        caps["completionProvider"] = {
            "triggerCharacters": provider.get(
                "triggerCharacters",
                [".", ":", "$", "@", "(", "["],
            ),
            "resolveProvider": False,
        }
        return result

    @classmethod
    def enrich_diagnostic(cls, diag, code, msg):
        # languageserver surfaces lintr findings. Codes look like
        # "object_name_linter", "assignment_linter", etc. Show them in the
        # standard "<message> <unit-separator> <label>" shape that noted's
        # frontend understands.
        if code:
            label = str(code).replace("_linter", "").replace("_", " ").title()
            diag["message"] = "\x1f".join([msg, f"R - {label}"])
        else:
            diag["message"] = "\x1f".join([msg, "R - Lint"])
        return True

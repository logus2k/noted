"""Base class for language-specific LSP behavior.

Each supported language provides a concrete strategy that encapsulates:
- Which linter/completion servers are used
- How to launch them
- How to enrich diagnostics
- Whether/how URI rewriting is applied
- Per-language initialization tweaks (init options, capability merging)

Adding a new language should only require creating a new strategy file
plus one registry entry; no edits to lsp_manager.py or routers/lsp.py
beyond that.
"""

from abc import ABC, abstractmethod
from typing import ClassVar


class BaseLspStrategy(ABC):
    """Abstract interface for a language's LSP integration."""

    # Public identity
    language_id: ClassVar[str] = ""
    extensions: ClassVar[tuple[str, ...]] = ()

    # Server types this language uses. The "lint" server is always present
    # and also handles formatting/code actions. The "completion" server is
    # optional - for single-server languages (HTML/CSS/JSON) it is None.
    lint_server_type: ClassVar[str] = ""
    completion_server_type: ClassVar[str | None] = None

    # Hover REST endpoint URI form:
    #   False: virtual URIs (file:///<project_id>/...)
    #   True:  real filesystem URIs (file://<real_root>/...)
    hover_uses_real_uri: ClassVar[bool] = False

    # --- Launch commands ------------------------------------------------

    @classmethod
    @abstractmethod
    def build_command(cls, server_type: str) -> list[str]:
        """Return the subprocess argv for the requested server_type.

        The strategy is guaranteed to be asked only for its own server
        types (lint_server_type or completion_server_type).
        """

    # --- Message routing -----------------------------------------------

    @classmethod
    def rewrite_to_real_for(cls, server_type: str) -> bool:
        """Whether outgoing messages to this server require virtual->real
        URI translation (because the server operates on real paths)."""
        return False

    @classmethod
    def rewrite_to_virtual_for(cls, server_type: str) -> bool:
        """Whether incoming messages from this server require real->virtual
        URI translation before they are sent to the frontend."""
        return False

    @classmethod
    def drop_diagnostics_from(cls, server_type: str) -> bool:
        """Whether publishDiagnostics from this server should be suppressed
        (e.g. jedi diagnostics are ignored because ruff is the source of
        truth for Python diagnostics)."""
        return False

    # --- Initialization ------------------------------------------------

    @classmethod
    def inject_init_options(
        cls,
        params: dict,
        server_type: str,
        venv_env_path: str | None,
    ) -> None:
        """Mutate the LSP initialize params in place before sending.

        Default: no-op. Python strategy injects jedi environment_path.
        """
        return None

    @classmethod
    def complete_init_capabilities(cls, result: dict, has_completion_server: bool) -> dict:
        """Apply language-specific capability overrides to the merged
        initialize response that noted sends back to the frontend.

        - Dual-server languages disable primary-server hover and advertise
          completion/navigation capabilities from the completion server.
        - Single-server languages may need to fill in completionProvider
          if the server returned nothing under dynamic registration.
        """
        return result

    # --- Diagnostic enrichment -----------------------------------------

    @classmethod
    def enrich_diagnostic(cls, diag: dict, code, msg: str) -> bool:
        """Apply language-specific tweaks to a single diagnostic.

        Return True if the strategy fully handled enrichment (the generic
        enricher should leave the diagnostic alone). Return False to let
        the generic fallback run.

        Default: do nothing, defer to the generic enricher.
        """
        return False

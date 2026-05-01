"""HTML / CSS / JSON strategies.

Single-server languages provided by vscode-langservers-extracted.
Each server handles linting and completions itself, so there is no
completion_server_type and no URI rewriting.
"""

from .base import BaseLspStrategy


class _WebLangStrategy(BaseLspStrategy):
    """Common behaviour for vscode-langservers-extracted languages."""

    # Subclasses set:
    #   language_id, extensions, lint_server_type, _display_label

    _display_label: str = ""
    hover_uses_real_uri = False  # single-server mode uses virtual URIs

    @classmethod
    def build_command(cls, server_type):
        if server_type == cls.lint_server_type:
            return [f"vscode-{cls.language_id}-language-server", "--stdio"]
        raise ValueError(
            f"{cls.__name__}: unknown server_type {server_type}"
        )

    @classmethod
    def complete_init_capabilities(cls, result, has_completion_server):
        # Single-server mode: ensure completionProvider is populated if the
        # server returned nothing under dynamic registration (which
        # codemirror-languageserver does not support). resolveProvider is
        # disabled so per-item docs do not render as an inline side panel
        # (docs live in noted's external Documentation panel).
        caps = result.setdefault("capabilities", {})
        provider = caps.get("completionProvider") or {}
        caps["completionProvider"] = {
            "triggerCharacters": provider.get(
                "triggerCharacters",
                [".", ":", "<", "\"", "=", "/"],
            ),
            "resolveProvider": False,
        }
        return result

    @classmethod
    def enrich_diagnostic(cls, diag, code, msg):
        error_type = (
            str(code).replace('-', ' ').title() if code else 'Syntax Error'
        )
        diag["message"] = "\x1f".join(
            [msg, f"{cls._display_label} - {error_type}"]
        )
        return True


class HtmlLspStrategy(_WebLangStrategy):
    language_id = "html"
    extensions = (".html", ".htm")
    lint_server_type = "html"
    _display_label = "HTML"


class CssLspStrategy(_WebLangStrategy):
    language_id = "css"
    extensions = (".css",)
    lint_server_type = "css"
    _display_label = "CSS"


class JsonLspStrategy(_WebLangStrategy):
    language_id = "json"
    extensions = (".json", ".jsonc")
    lint_server_type = "json"
    _display_label = "JSON"

"""YAML LSP strategy: yaml-language-server (Red Hat).

Single-server language. Provides syntax/structure validation, completion,
hover, and (with optional schema associations) schema-aware validation.

Schemas can be wired up later via initializationOptions; for now we
launch with defaults so editors get syntax and structural validation
out of the box.
"""

from .base import BaseLspStrategy


class YamlLspStrategy(BaseLspStrategy):
    language_id = "yaml"
    extensions = (".yml", ".yaml")

    lint_server_type = "yaml"
    completion_server_type = None
    hover_uses_real_uri = False

    @classmethod
    def build_command(cls, server_type):
        if server_type == "yaml":
            return ["yaml-language-server", "--stdio"]
        raise ValueError(f"YamlLspStrategy: unknown server_type {server_type}")

    @classmethod
    def complete_init_capabilities(cls, result, has_completion_server):
        # Single-server mode: ensure completionProvider is populated since
        # codemirror-languageserver does not handle dynamic registration.
        # resolveProvider disabled so per-item docs do not render as an
        # inline side panel (docs live in noted's external Documentation
        # panel).
        caps = result.setdefault("capabilities", {})
        provider = caps.get("completionProvider") or {}
        caps["completionProvider"] = {
            "triggerCharacters": provider.get(
                "triggerCharacters",
                [":", "-", " "],
            ),
            "resolveProvider": False,
        }
        return result

    @classmethod
    def enrich_diagnostic(cls, diag, code, msg):
        error_type = (
            str(code).replace('-', ' ').title() if code else 'YAML Issue'
        )
        diag["message"] = "\x1f".join([msg, f"YAML - {error_type}"])
        return True

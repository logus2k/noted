"""JavaScript / TypeScript LSP strategy: biome + typescript-language-server.

Biome provides diagnostics and formatting; tsserver provides completions,
hover, definitions, and references. tsserver operates on real filesystem
paths, so sync messages to it are rewritten virtual->real (matching the
historical behaviour of the router).
"""

from .base import BaseLspStrategy


# Biome lint category -> (LSP severity, display label)
_BIOME_CATEGORIES = {
    'correctness': (1, 'Correctness'),
    'suspicious':  (2, 'Suspicious'),
    'style':       (3, 'Style'),
    'complexity':  (2, 'Complexity'),
    'nursery':     (3, 'Nursery'),
    'a11y':        (2, 'Accessibility'),
    'security':    (2, 'Security'),
    'performance': (2, 'Performance'),
}


def _enrich_biome(diag: dict, code, msg: str) -> None:
    code = str(code)
    if code == "parse":
        diag["severity"] = 1
        diag["message"] = "\x1f".join([msg, "JavaScript - Parse Error"])
        return
    parts = code.split("/")
    if len(parts) >= 3 and parts[0] == "lint":
        category_key = parts[1]
        rule_name = parts[2]
        severity, category_label = _BIOME_CATEGORIES.get(
            category_key, (2, category_key.title())
        )
        diag["severity"] = severity
        diag["message"] = "\x1f".join(
            [f"{rule_name}: {msg}", f"Biome - {category_label}"]
        )
    else:
        diag["message"] = "\x1f".join([msg, f"Biome - {code}"])


class JavaScriptLspStrategy(BaseLspStrategy):
    language_id = "javascript"
    extensions = (".js", ".ts", ".mjs", ".cjs")

    lint_server_type = "biome"
    completion_server_type = "tsserver"
    hover_uses_real_uri = True

    @classmethod
    def build_command(cls, server_type):
        if server_type == "biome":
            return ["biome", "lsp-proxy"]
        if server_type == "tsserver":
            return ["typescript-language-server", "--stdio"]
        raise ValueError(f"JavaScriptLspStrategy: unknown server_type {server_type}")

    @classmethod
    def rewrite_to_real_for(cls, server_type):
        # tsserver operates on real filesystem paths (sync stream only).
        return server_type == "tsserver"

    @classmethod
    def complete_init_capabilities(cls, result, has_completion_server):
        # resolveProvider=False prevents codemirror-languageserver from
        # fetching per-item documentation (rendered as an inline side panel
        # next to the completion dropdown). Hover docs live in noted's
        # external Documentation panel instead.
        caps = result.setdefault("capabilities", {})
        caps.pop("hoverProvider", None)
        caps.update({
            "completionProvider": {
                "triggerCharacters": ["."],
                "resolveProvider": False,
            },
            "hoverProvider": False,
            "definitionProvider": True,
            "referencesProvider": True,
            "signatureHelpProvider": {"triggerCharacters": ["(", ","]},
        })
        return result

    @classmethod
    def enrich_diagnostic(cls, diag, code, msg):
        if code is None:
            return False
        _enrich_biome(diag, code, msg)
        return True

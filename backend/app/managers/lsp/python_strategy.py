"""Python LSP strategy: ruff (diagnostics/formatting) + jedi (completions/navigation).

Jedi operates on real filesystem paths; the strategy signals that sync
messages and responses must be rewritten between virtual and real URIs.
Ruff diagnostic enrichment is handled by the generic enricher in the
router (it is the historical default path, left in place to keep the
diff small).
"""

import re

from .base import BaseLspStrategy

# Ruff rule prefix -> category name
_RULE_CATEGORIES = {
    'F': 'Pyflakes - Logic errors',
    'E': 'pycodestyle - Style errors',
    'W': 'pycodestyle - Style warnings',
    'I': 'isort - Import ordering',
    'N': 'pep8-naming - Naming conventions',
    'UP': 'pyupgrade - Python upgrade',
    'ANN': 'flake8-annotations - Type annotations',
    'B': 'flake8-bugbear - Bug risks',
    'A': 'flake8-builtins - Builtin shadowing',
    'C4': 'flake8-comprehensions - Comprehensions',
    'DTZ': 'flake8-datetimez - Timezone-aware datetimes',
    'ISC': 'flake8-implicit-str-concat - String concat',
    'PIE': 'flake8-pie - Misc improvements',
    'PT': 'flake8-pytest-style - Pytest style',
    'RET': 'flake8-return - Return statements',
    'SIM': 'flake8-simplify - Simplification',
    'ARG': 'flake8-unused-arguments - Unused args',
    'ERA': 'eradicate - Commented-out code',
    'PL': 'Pylint - Code analysis',
    'RUF': 'Ruff-specific rules',
    'S': 'flake8-bandit - Security',
    'T20': 'flake8-print - Print statements',
    'D': 'pydocstyle - Docstring style',
    'C90': 'mccabe - Complexity',
    'TID': 'flake8-tidy-imports - Import tidying',
    'TCH': 'flake8-type-checking - Type checking imports',
    'PERF': 'Perflint - Performance',
    'FURB': 'refurb - Modernization',
}

# Ruff reports everything as severity 1 (Error). Remap based on rule prefix.
_SEVERITY_ERROR = {'E999', 'F821', 'F811'}
_SEVERITY_INFO = {'D', 'ERA', 'T20', 'ANN', 'N'}
_SEVERITY_HINT: set[str] = set()


def _match_prefix(code: str, prefix_set: set) -> bool:
    for length in (4, 3, 2, 1):
        if code[:length] in prefix_set:
            return True
    return False


def _get_category(code: str) -> str:
    if not code:
        return ''
    for length in (4, 3, 2, 1):
        if code[:length] in _RULE_CATEGORIES:
            return _RULE_CATEGORIES[code[:length]]
    return ''


def _remap_severity(code: str, current: int) -> int:
    if not code:
        return current
    if code in _SEVERITY_ERROR or code.startswith('E9') or 'syntax' in code.lower():
        return 1
    if _match_prefix(code, _SEVERITY_INFO):
        return 3
    if _match_prefix(code, _SEVERITY_HINT):
        return 4
    return 2


class PythonLspStrategy(BaseLspStrategy):
    language_id = "python"
    extensions = (".py",)

    lint_server_type = "ruff"
    completion_server_type = "jedi"
    hover_uses_real_uri = True

    @classmethod
    def build_command(cls, server_type: str) -> list[str]:
        if server_type == "ruff":
            return ["ruff", "server", "--preview"]
        if server_type == "jedi":
            return ["jedi-language-server"]
        raise ValueError(f"PythonLspStrategy: unknown server_type {server_type}")

    # Jedi needs real paths for its sync stream and responses.
    @classmethod
    def rewrite_to_real_for(cls, server_type: str) -> bool:
        return server_type == "jedi"

    @classmethod
    def rewrite_to_virtual_for(cls, server_type: str) -> bool:
        return server_type == "jedi"

    # Jedi publishDiagnostics are suppressed; ruff owns diagnostics.
    @classmethod
    def drop_diagnostics_from(cls, server_type: str) -> bool:
        return server_type == "jedi"

    @classmethod
    def inject_init_options(cls, params, server_type, venv_env_path):
        if server_type != "jedi" or not venv_env_path:
            return
        # codemirror-languageserver sends "initializationOptions": null
        # explicitly, so setdefault is not enough - handle the None case.
        if not params.get("initializationOptions"):
            params["initializationOptions"] = {}
        init_opts = params["initializationOptions"]
        if not init_opts.get("workspace"):
            init_opts["workspace"] = {}
        init_opts["workspace"]["environment_path"] = venv_env_path

    @classmethod
    def complete_init_capabilities(cls, result, has_completion_server):
        # Dual-server: disable primary hover, advertise jedi capabilities.
        # resolveProvider=False prevents codemirror-languageserver from
        # fetching per-item documentation (which it renders as an inline
        # side panel next to the completion dropdown). Hover docs live in
        # noted's external Documentation panel instead.
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
        # Remap ruff severity
        if code and "severity" in diag:
            diag["severity"] = _remap_severity(str(code), diag["severity"])

        url = (diag.get("codeDescription") or {}).get("href")
        is_ruff_code = code and re.match(r'^[A-Z]+\d+$', str(code))
        if is_ruff_code and not msg.startswith(f"{code}"):
            category = _get_category(str(code))
            parts = [f"{code}: {msg}"]
            if category:
                parts.append(category)
            if url:
                parts.append(url)
            diag["message"] = "\x1f".join(parts)
            return True
        if not is_ruff_code:
            # Python syntax/parser errors
            error_type = str(code).replace('-', ' ').upper() if code else 'SYNTAX ERROR'
            diag["message"] = "\x1f".join([msg, f"Python - {error_type}"])
            return True
        return False

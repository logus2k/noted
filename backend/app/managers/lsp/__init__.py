"""LSP strategy registry.

Each supported language registers a BaseLspStrategy subclass here.
Adding a new language means:

1. Create a new file `<lang>_strategy.py` implementing BaseLspStrategy.
2. Import the class below and append it to `_ALL_STRATEGIES`.
3. (Optional) Add a frontend mapping in FileEditor.js.

No other file in the LSP stack should need to change.
"""

from typing import Type

from .base import BaseLspStrategy
from .python_strategy import PythonLspStrategy
from .javascript_strategy import JavaScriptLspStrategy
from .web_strategies import HtmlLspStrategy, CssLspStrategy, JsonLspStrategy
from .yaml_strategy import YamlLspStrategy
from .r_strategy import RLspStrategy


_ALL_STRATEGIES: tuple[Type[BaseLspStrategy], ...] = (
    PythonLspStrategy,
    JavaScriptLspStrategy,
    HtmlLspStrategy,
    CssLspStrategy,
    JsonLspStrategy,
    YamlLspStrategy,
    RLspStrategy,
)


# Fast lookups
_BY_LANGUAGE_ID: dict[str, Type[BaseLspStrategy]] = {
    s.language_id: s for s in _ALL_STRATEGIES
}

_BY_SERVER_TYPE: dict[str, Type[BaseLspStrategy]] = {}
for _s in _ALL_STRATEGIES:
    _BY_SERVER_TYPE[_s.lint_server_type] = _s
    if _s.completion_server_type:
        _BY_SERVER_TYPE[_s.completion_server_type] = _s


def get_strategy_by_language(language_id: str) -> Type[BaseLspStrategy]:
    """Look up a strategy by LSP language identifier.

    Falls back to Python when the identifier is unknown, matching the
    historical default in the WebSocket router.
    """
    return _BY_LANGUAGE_ID.get(language_id, PythonLspStrategy)


def get_strategy_by_server_type(server_type: str) -> Type[BaseLspStrategy]:
    """Look up a strategy by a specific server_type string.

    Raises KeyError if the server_type is unknown.
    """
    return _BY_SERVER_TYPE[server_type]


def get_strategy_by_file(filename: str) -> Type[BaseLspStrategy]:
    """Look up a strategy by filename extension.

    Falls back to Python when no strategy claims the extension.
    """
    lower = filename.lower()
    for s in _ALL_STRATEGIES:
        for ext in s.extensions:
            if lower.endswith(ext):
                return s
    return PythonLspStrategy


def build_command_for(server_type: str) -> list[str]:
    """Build the launch command for a server_type via its owning strategy."""
    strategy = get_strategy_by_server_type(server_type)
    return strategy.build_command(server_type)


__all__ = [
    "BaseLspStrategy",
    "PythonLspStrategy",
    "JavaScriptLspStrategy",
    "HtmlLspStrategy",
    "CssLspStrategy",
    "JsonLspStrategy",
    "YamlLspStrategy",
    "get_strategy_by_language",
    "get_strategy_by_server_type",
    "get_strategy_by_file",
    "build_command_for",
]

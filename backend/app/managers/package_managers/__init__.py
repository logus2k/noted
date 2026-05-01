"""Package manager strategy registry.

Each supported language has a BasePackageManager subclass registered here.
Adding a new language means creating a new strategy file and appending it
to `_ALL_MANAGERS`. No changes to env_manager.py beyond that.

The registry mirrors the LSP strategy pattern in `app.managers.lsp` and the
DAP strategy pattern in `app.managers.language_strategies`. Three concerns,
three strategies, one consistent shape.
"""

from typing import Optional, Type

from .base import BasePackageManager, PmContext
from .pip_manager import PipPackageManager
from .pnpm_manager import PnpmPackageManager
from .renv_manager import RenvPackageManager


_ALL_MANAGERS: tuple[BasePackageManager, ...] = (
    PipPackageManager(),
    PnpmPackageManager(),
    RenvPackageManager(),
)

_BY_LANGUAGE: dict[str, BasePackageManager] = {
    m.language_id: m for m in _ALL_MANAGERS
}


def get_package_manager(language: str) -> Optional[BasePackageManager]:
    """Look up a package manager strategy by runtime language id."""
    return _BY_LANGUAGE.get(language)


__all__ = [
    "BasePackageManager",
    "PmContext",
    "PipPackageManager",
    "PnpmPackageManager",
    "RenvPackageManager",
    "get_package_manager",
]

"""Base class for per-language package managers.

Each supported language provides a strategy that encapsulates:
- How to list installed packages and normalize the output to [{name, version}]
- How to install packages (foreground subprocess)
- How to install packages with streamed output (PTY-based for terminal feel)
- How to remove packages

The dispatcher in `__init__.py` looks up the right strategy by `language`
and the `EnvironmentManager` becomes a thin facade. Cancellation tracking
stays on the EnvironmentManager so process state survives strategy hot-reload
and so a single index handles all running installs across languages.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional


@dataclass
class PmContext:
    """Per-call context handed to a package manager strategy.

    Strategies do NOT keep references to the EnvironmentManager or the
    runtime registry. Everything they need to act on a single env arrives
    via this dataclass:

    - `runtime` is the parsed runtime.json dict for the env's runtime
    - `env_path` is the resolved environment directory path
    - `resolve_template` is the registry's template resolver, bound to the
      relevant kwargs callers can pass at use time
    - `register_proc` is a callback strategies use to publish a started
      subprocess into the dispatcher's cancellation index. The handle can
      be any object with `terminate()`, `kill()`, `returncode`, and an
      awaitable `wait()` - matching `asyncio.subprocess.Process`.
    """

    runtime: dict
    env_path: str
    resolve_template: Callable[..., list[str]]
    register_proc: Optional[Callable[[object], None]] = None
    unregister_proc: Optional[Callable[[object], None]] = None


class BasePackageManager(ABC):
    """Abstract interface for per-language package management.

    A strategy implementation must NOT raise on unsupported `installer`
    values - it should fall back to its native installer. The `installer`
    parameter is a UI hint, not a hard contract.
    """

    # Public identity. Subclasses set this to the language id used in
    # runtime.json (e.g. "python", "javascript", "r").
    language_id: str = ""

    @abstractmethod
    async def list_packages(self, ctx: PmContext) -> list[dict]:
        """Return installed packages as [{name, version}, ...]."""

    @abstractmethod
    async def install_packages(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "uv",
    ) -> dict:
        """Install packages synchronously, returning {installed, output}.
        Raises RuntimeError on failure with the captured stderr/stdout.
        """

    @abstractmethod
    def install_stream(
        self,
        ctx: PmContext,
        packages: list[str],
        installer: str = "uv",
    ) -> AsyncIterator[str]:
        """Async generator yielding install output chunks.

        The strategy MUST call `ctx.register_proc(proc)` after spawning the
        subprocess and `ctx.unregister_proc(proc)` in a finally block, so
        the dispatcher's cancel path can find the running process.
        """

    @abstractmethod
    async def remove_packages(
        self,
        ctx: PmContext,
        packages: list[str],
    ) -> dict:
        """Remove packages, returning {removed, output}."""

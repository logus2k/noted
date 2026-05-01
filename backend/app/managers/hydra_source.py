"""Hydra config source abstraction.

Per the Hydra unification plan (M3), HydraManager reads base config files
from one of two sources:

  - LocalSource: the user's on-disk `config/` folder in a project.
  - MlflowSource: an archived `hydra/` bundle from a past MLflow run,
    fetched once and cached in memory.

Both sources expose the same interface (read file, list files, walk),
so the composition code in HydraManager does not need to know which
source is being used.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Iterator

logger = logging.getLogger(__name__)


# Common config directory names, checked in order by LocalSource.
CONFIG_DIR_NAMES = ['config', 'conf', 'configs']


class HydraSource:
    """Base class for a Hydra config source."""

    @property
    def config_top_name(self) -> str:
        """Return the name of the top-level config folder (e.g. 'config')."""
        raise NotImplementedError

    def exists(self) -> bool:
        """Return True if the source has a resolvable config directory."""
        raise NotImplementedError

    def read_text(self, relative_path: str) -> Optional[str]:
        """Read a file from the source, given a path relative to the config
        top folder (e.g. 'model/gru.yaml'). Returns None if not found."""
        raise NotImplementedError

    def walk(self) -> Iterator[tuple[str, list[str], list[str]]]:
        """Walk the source like os.walk(), yielding
        (dirpath_relative_to_config_top, dirnames, filenames) tuples.
        """
        raise NotImplementedError

    def describe(self) -> str:
        """Human-readable description, used in error messages."""
        raise NotImplementedError


@dataclass
class LocalSource(HydraSource):
    """Source backed by a project's on-disk config/ folder."""

    project_id: str
    # Resolved absolute path to the config directory. Populated lazily by
    # `_resolve()`.
    _config_dir: Optional[str] = None

    def _resolve(self) -> Optional[str]:
        if self._config_dir is not None:
            return self._config_dir
        from app.managers.project_registry import get_registry
        project_path = get_registry().resolve(self.project_id)
        for name in CONFIG_DIR_NAMES:
            candidate = os.path.join(project_path, name)
            if os.path.isdir(candidate):
                self._config_dir = candidate
                return candidate
        return None

    @property
    def config_top_name(self) -> str:
        d = self._resolve()
        if not d:
            return 'config'
        return os.path.basename(d.rstrip('/'))

    def exists(self) -> bool:
        return self._resolve() is not None

    def read_text(self, relative_path: str) -> Optional[str]:
        base = self._resolve()
        if not base:
            return None
        full = os.path.join(base, relative_path)
        try:
            with open(full, 'r') as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return None

    def walk(self) -> Iterator[tuple[str, list[str], list[str]]]:
        base = self._resolve()
        if not base:
            return
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, base)
            if rel_dir == '.':
                rel_dir = ''
            yield (rel_dir, dirnames, filenames)

    def describe(self) -> str:
        d = self._resolve()
        return f"LocalSource(project={self.project_id}, dir={d or 'NOT FOUND'})"


@dataclass
class MlflowSource(HydraSource):
    """Source backed by an archived MLflow run's `hydra/` bundle.

    Bundles are fetched lazily from MLflow on first access and cached via
    HydraCache, keyed by (notebook_uid, run_id). Once cached, reads are
    in-memory.
    """

    run_id: str
    notebook_uid: str
    # Cached bundle as {relative_path: content_bytes}. Populated by
    # _load_bundle() via HydraCache.
    _bundle: Optional[dict[str, bytes]] = None
    # The detected top-level config folder name (e.g. 'config').
    _top_name: Optional[str] = None

    def _load_bundle(self) -> Optional[dict[str, bytes]]:
        if self._bundle is not None:
            return self._bundle
        from app.managers.hydra_cache import get_cache
        cache = get_cache()
        self._bundle = cache.get(self.notebook_uid, self.run_id)
        if self._bundle is not None:
            self._detect_top_name()
        return self._bundle

    def _detect_top_name(self):
        if not self._bundle:
            return
        # The bundle contains entries like "config/model/gru.yaml",
        # "selections.json", "resolved.yaml". The top folder is whichever
        # CONFIG_DIR_NAMES prefix exists in the bundle.
        for key in self._bundle.keys():
            for name in CONFIG_DIR_NAMES:
                if key.startswith(f"{name}/") or key == name:
                    self._top_name = name
                    return
        self._top_name = 'config'

    @property
    def config_top_name(self) -> str:
        if self._top_name is None:
            self._load_bundle()
        return self._top_name or 'config'

    def exists(self) -> bool:
        b = self._load_bundle()
        return b is not None and len(b) > 0

    def read_text(self, relative_path: str) -> Optional[str]:
        b = self._load_bundle()
        if not b:
            return None
        key = f"{self.config_top_name}/{relative_path}" if relative_path else self.config_top_name
        data = b.get(key)
        if data is None:
            return None
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            return None

    def walk(self) -> Iterator[tuple[str, list[str], list[str]]]:
        b = self._load_bundle()
        if not b:
            return
        top = self.config_top_name
        prefix = f"{top}/"

        # Build a directory tree from flat bundle keys.
        files: dict[str, set[str]] = {}  # dir -> set of filenames
        dirs: dict[str, set[str]] = {}   # dir -> set of subdir names

        # Every directory the walk must yield, including the root ''.
        all_dirs: set[str] = {''}

        for key in b.keys():
            if not key.startswith(prefix):
                continue
            rel = key[len(prefix):]
            parts = rel.split('/')
            # Register each ancestor directory AND its child entry.
            for i in range(len(parts) - 1):
                parent = '/'.join(parts[:i])       # '' for root, then 'model', 'model/sub', ...
                child = parts[i]
                dirs.setdefault(parent, set()).add(child)
                # The child itself is a directory that must be walked.
                nested = f'{parent}/{child}' if parent else child
                all_dirs.add(nested)
            # Register the file in its parent dir.
            parent = '/'.join(parts[:-1])
            files.setdefault(parent, set()).add(parts[-1])
            all_dirs.add(parent)

        for d in sorted(all_dirs):
            yield (d, sorted(dirs.get(d, set())), sorted(files.get(d, set())))

    def describe(self) -> str:
        return f"MlflowSource(run_id={self.run_id}, notebook_uid={self.notebook_uid})"


def parse_source(
    baseline_source: str,
    project_id: str,
    notebook_uid: Optional[str] = None,
) -> HydraSource:
    """Parse a baseline_source string into a concrete HydraSource.

    Accepts:
      - 'project://config/' -> LocalSource(project_id)
      - 'project://' (variant) -> LocalSource(project_id)
      - 'mlflow://<run_id>' -> MlflowSource(run_id, notebook_uid)

    Raises ValueError if the source cannot be parsed or if an MlflowSource
    is requested without a notebook_uid.
    """
    if not baseline_source:
        return LocalSource(project_id=project_id)
    if baseline_source.startswith('project://'):
        return LocalSource(project_id=project_id)
    if baseline_source.startswith('mlflow://'):
        run_id = baseline_source[len('mlflow://'):].strip('/')
        if not run_id:
            raise ValueError("mlflow:// baseline source must include a run_id")
        if not notebook_uid:
            raise ValueError(
                "MlflowSource requires a notebook_uid for cache keying. "
                "Ensure the notebook has a stable UID in its metadata."
            )
        return MlflowSource(run_id=run_id, notebook_uid=notebook_uid)
    raise ValueError(
        f"Unsupported baseline source: {baseline_source}. "
        "Expected 'project://...' or 'mlflow://<run_id>'."
    )

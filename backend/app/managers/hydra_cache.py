"""In-memory cache for MLflow-fetched Hydra bundles.

Per the Hydra unification plan (D18, D19):
  - In-memory only, no disk persistence
  - Keyed by (notebook_uid, run_id) so two notebooks pointing at the same
    run have isolated entries
  - FIFO eviction at MAX_ENTRIES to prevent unbounded growth
  - Cleared on backend restart (by design - re-fetches are fast)

Bundles are dicts of {relative_path: content_bytes} as produced by
HydraManager.assemble_bundle_files() (when logged) or by
HydraCache.fetch_from_mlflow() (when loaded back for time-travel).
"""

import logging
import os
import tempfile
from collections import OrderedDict
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES = 500


class HydraCache:
    """Module-level in-memory cache for MLflow-fetched Hydra bundles."""

    def __init__(self):
        self._entries: OrderedDict[tuple[str, str], dict[str, bytes]] = OrderedDict()
        self._lock = Lock()

    def _key(self, notebook_uid: str, run_id: str) -> tuple[str, str]:
        return (notebook_uid, run_id)

    def get(self, notebook_uid: str, run_id: str) -> Optional[dict[str, bytes]]:
        """Return the cached bundle for (notebook_uid, run_id), or None."""
        with self._lock:
            return self._entries.get(self._key(notebook_uid, run_id))

    def put(self, notebook_uid: str, run_id: str, bundle: dict[str, bytes]) -> None:
        """Store a bundle in the cache. Evicts the oldest entry if full."""
        with self._lock:
            key = self._key(notebook_uid, run_id)
            if key in self._entries:
                del self._entries[key]
            self._entries[key] = bundle
            while len(self._entries) > MAX_ENTRIES:
                self._entries.popitem(last=False)

    def evict(self, notebook_uid: str, run_id: str) -> None:
        """Remove a specific entry from the cache."""
        with self._lock:
            self._entries.pop(self._key(notebook_uid, run_id), None)

    def evict_run(self, run_id: str) -> None:
        """Remove all entries for a given run_id across all notebook UIDs."""
        with self._lock:
            to_remove = [k for k in self._entries if k[1] == run_id]
            for k in to_remove:
                del self._entries[k]

    def fetch_from_mlflow(
        self,
        notebook_uid: str,
        run_id: str,
    ) -> dict[str, bytes]:
        """Fetch the `hydra/` artifact folder for a run from MLflow and
        cache it. Returns the cached bundle.

        Fails loud if:
          - MLflow is unreachable
          - The run does not exist
          - The run has no `hydra/` artifact folder
          - The artifact is empty

        Per the plan (D21), there is no silent fallback. Callers must
        handle the exception and propagate a clear error to the user.
        """
        # Check cache first
        existing = self.get(notebook_uid, run_id)
        if existing is not None:
            return existing

        from app.managers.mlflow_manager import MlflowManager
        mlf = MlflowManager()

        # Download the hydra/ artifact path to a temporary directory.
        # MlflowClient.download_artifacts returns the local path.
        try:
            client = mlf._get_client()
        except Exception as e:
            raise RuntimeError(
                f"MLflow unreachable: {e}. "
                "The notebook metadata points to an MLflow-archived "
                "Hydra baseline, but the MLflow server cannot be reached. "
                "Open the Configuration Composer and switch to Local Baseline "
                "to continue, or retry once MLflow is available."
            ) from e

        try:
            # Verify the run exists
            try:
                run = client.get_run(run_id)
            except Exception as e:
                raise RuntimeError(
                    f"MLflow run '{run_id}' not found: {e}. "
                    "The notebook metadata points to this run but it no "
                    "longer exists. Open the Configuration Composer and "
                    "switch to Local Baseline or pick a different run."
                ) from e

            # Download the hydra/ artifact folder
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    local_path = client.download_artifacts(
                        run_id, 'hydra', tmpdir
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"MLflow run '{run_id}' has no `hydra/` artifact "
                        f"folder: {e}. This run was created before Hydra "
                        "bundle logging was enabled, or the artifact was "
                        "deleted. Open the Configuration Composer and switch "
                        "to Local Baseline or pick a different run."
                    ) from e

                if not os.path.isdir(local_path):
                    raise RuntimeError(
                        f"MLflow run '{run_id}' hydra/ artifact is not a "
                        "directory (unexpected shape). Open the Configuration "
                        "Composer and switch to Local Baseline."
                    )

                # Read everything into memory
                bundle: dict[str, bytes] = {}
                for dirpath, _dirnames, filenames in os.walk(local_path):
                    for fname in filenames:
                        full = os.path.join(dirpath, fname)
                        rel = os.path.relpath(full, local_path)
                        rel = rel.replace(os.sep, '/')
                        try:
                            with open(full, 'rb') as f:
                                bundle[rel] = f.read()
                        except OSError as e:
                            logger.warning(
                                "Skipping bundle file %s: %s", full, e
                            )

                if not bundle:
                    raise RuntimeError(
                        f"MLflow run '{run_id}' hydra/ artifact is empty. "
                        "Open the Configuration Composer and switch to Local "
                        "Baseline or pick a different run."
                    )

                self.put(notebook_uid, run_id, bundle)
                logger.info(
                    "Cached Hydra bundle for run %s (notebook %s): %d files",
                    run_id, notebook_uid, len(bundle),
                )
                return bundle
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Hydra bundle from MLflow run '{run_id}': {e}"
            ) from e


_cache_singleton: Optional[HydraCache] = None


def get_cache() -> HydraCache:
    """Return the process-wide HydraCache singleton."""
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = HydraCache()
    return _cache_singleton

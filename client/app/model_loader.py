"""Model loader - fetches and loads models from MLflow Registry.

Manages the currently loaded model lifecycle: load, unload, status.
"""

import logging
import os
import time
import threading

logger = logging.getLogger(__name__)


class ModelLoader:
    """Thread-safe model loader with status tracking."""

    def __init__(self):
        self._model = None
        self._model_info = {}
        # RLock so the load() path can be wrapped in a single outer lock
        # without deadlocking on existing nested acquires.
        self._lock = threading.RLock()
        self._status = 'idle'  # idle, loading, ready, error
        self._error = None
        self._load_time = None
        # Progress indicator - a short string describing what the loader is
        # currently doing, plus a free-text detail line (e.g. the latest uv
        # output line). Updated via _set_phase() which also notifies any
        # registered callback so the streaming /load endpoint can push
        # events to the frontend in real time.
        self._phase = ''
        self._phase_detail = ''
        self._phase_callback = None  # Optional[Callable[[str, str], None]]

    def set_phase_callback(self, callback):
        """Register a callback invoked on every phase transition.

        The callback receives (phase, detail) whenever _set_phase() is
        called. Pass None to clear. Exceptions in the callback are
        swallowed so the load path cannot be broken by a buggy listener.
        """
        self._phase_callback = callback

    def _set_phase(self, phase: str, detail: str = ''):
        """Update phase + detail in one place and notify the callback."""
        self._phase = phase
        self._phase_detail = detail
        cb = self._phase_callback
        if cb is not None:
            try:
                cb(phase, detail)
            except Exception:
                logger.exception("Phase callback raised; ignoring")

    @property
    def status(self) -> str:
        return self._status

    @property
    def model(self):
        return self._model

    @property
    def model_info(self) -> dict:
        return self._model_info

    def load(self, model_name: str, version: str | None = None,
             alias: str | None = None) -> dict:
        """Load a model from MLflow Registry.

        Serialized via self._lock so concurrent /load requests don't race.
        Early-returns if the requested model is already loaded.

        Args:
            model_name: Registered model name
            version: Specific version number (e.g., "1")
            alias: Alias to resolve (e.g., "champion"). Ignored if version is set.

        Returns:
            {"status": "ready", "model_name": ..., "version": ..., ...}
        """
        # Hold the RLock for the ENTIRE load path. Concurrent /load requests
        # queue on this lock so they cannot race. /health does NOT take the
        # lock, so it stays responsive even while a load is in flight -
        # though the primary progress channel is the phase callback driving
        # the NDJSON stream emitted by the /load endpoint itself.
        with self._lock:
            # Early-return: same model + version already loaded.
            if (self._status == 'ready' and self._model is not None
                    and self._model_info.get('model_name') == model_name
                    and (version is None or str(self._model_info.get('version')) == str(version))):
                logger.info(
                    "Model %s v%s already loaded - skipping reload",
                    model_name, self._model_info.get('version'),
                )
                return self.get_health()

            self._status = 'loading'
            self._error = None
            self._set_phase('resolving', '')

            return self._load_inner(model_name, version, alias)

    def _load_inner(self, model_name, version, alias):
        try:
            import mlflow
            from app.config import MLFLOW_TRACKING_URI, MLFLOW_TRACKING_USERNAME, MLFLOW_TRACKING_PASSWORD

            # Configure MLflow
            os.environ['MLFLOW_TRACKING_URI'] = MLFLOW_TRACKING_URI
            if MLFLOW_TRACKING_USERNAME:
                os.environ['MLFLOW_TRACKING_USERNAME'] = MLFLOW_TRACKING_USERNAME
            if MLFLOW_TRACKING_PASSWORD:
                os.environ['MLFLOW_TRACKING_PASSWORD'] = MLFLOW_TRACKING_PASSWORD

            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            client = mlflow.tracking.MlflowClient()

            # Resolve version from alias if needed
            resolved_version = version
            if not resolved_version and alias:
                try:
                    mv = client.get_model_version_by_alias(model_name, alias)
                    resolved_version = mv.version
                except Exception as e:
                    raise ValueError(f"Alias @{alias} not found for model {model_name}: {e}")

            if not resolved_version:
                # Get latest version
                versions = client.search_model_versions(f"name='{model_name}'")
                if not versions:
                    raise ValueError(f"No versions found for model {model_name}")
                resolved_version = str(max(int(v.version) for v in versions))

            # Resolve model version and download artifacts
            model_version_info = client.get_model_version(model_name, resolved_version)
            logger.info("Loading model: %s (v%s)", model_name, resolved_version)
            start = time.time()
            self._set_phase('downloading', f'{model_name} v{resolved_version}')

            # MLflow 3.x model loading strategy:
            # 1. Check for noted.model_uri tag (direct URI from log_model)
            # 2. Scan models/ directory for matching model_id
            # 3. Fallback to runs:/ URI (slow, 4min timeout)
            run_id = model_version_info.run_id
            run = client.get_run(run_id)
            experiment_id = run.info.experiment_id

            local_path = None

            # Strategy 1: Use direct model_uri tag if available
            model_uri_tag = run.data.tags.get('noted.model_uri')
            if model_uri_tag:
                try:
                    logger.info("Loading from noted.model_uri tag: %s", model_uri_tag)
                    local_path = mlflow.artifacts.download_artifacts(artifact_uri=model_uri_tag)
                except Exception as e:
                    logger.warning("Direct model_uri failed: %s", e)
                    local_path = None

            # Strategy 2: Scan models/ directory
            if not local_path:
                try:
                    import urllib.request, json as _json
                    tracking_uri = os.environ.get('MLFLOW_TRACKING_URI', 'http://mlflow:5000')
                    list_url = f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts?path={experiment_id}/models"
                    resp = urllib.request.urlopen(list_url, timeout=10)
                    model_dirs = _json.loads(resp.read())
                    for entry in model_dirs.get('files', []):
                        if not entry.get('is_dir'):
                            continue
                        mid = entry['path']
                        try:
                            ml_url = f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts/{experiment_id}/models/{mid}/artifacts/MLmodel"
                            ml_resp = urllib.request.urlopen(ml_url, timeout=5)
                            ml_content = ml_resp.read().decode()
                            if run_id in ml_content:
                                artifact_uri = f"mlflow-artifacts:/{experiment_id}/models/{mid}/artifacts"
                                logger.info("Found model at: %s", artifact_uri)
                                local_path = mlflow.artifacts.download_artifacts(artifact_uri=artifact_uri)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning("Model ID scan failed: %s", e)

            if not local_path:
                logger.info("Fallback: downloading via run_id (may be slow)")
                local_path = mlflow.artifacts.download_artifacts(
                    run_id=run_id, artifact_path='model'
                )
            logger.info("Artifacts downloaded to: %s (%.1fs)", local_path, time.time() - start)

            # Runtime dependency install is intentionally disabled. Step 1
            # of the serving unblock (2026-04-15): the noted-serving image
            # bakes a superset baseline (latest TF/mlflow/numpy) and relies
            # on MLflow's warning-mode loading for model pins that differ
            # from the baseline. Installing at runtime triggered the
            # Protobuf stale-import crash because Python cannot hot-swap
            # C extensions in a running interpreter. Phase 0b will replace
            # this with a per-Deploy worker subprocess.
            self._set_phase('loading_model', '')
            loaded_model = mlflow.pyfunc.load_model(local_path)

            load_duration = time.time() - start
            logger.info("Model loaded in %.2fs", load_duration)

            # Extract signature and metadata
            signature = None
            flavors = {}
            example_input = None
            try:
                model_info_obj = client.get_model_version(model_name, resolved_version)
                run = client.get_run(model_info_obj.run_id)

                # Get MLmodel metadata
                if hasattr(loaded_model, 'metadata'):
                    meta = loaded_model.metadata
                    signature = meta.signature if hasattr(meta, 'signature') else None
                    flavors = meta.flavors if hasattr(meta, 'flavors') else {}
                    if hasattr(meta, 'saved_input_example_info'):
                        example_input = meta.saved_input_example_info
            except Exception as e:
                logger.debug("Could not extract full model metadata: %s", e)

            # Technical details: disk size, framework, parameter count.
            artifact_size_bytes = self._compute_artifact_size(local_path)
            framework = self._detect_framework(flavors)
            num_parameters = self._count_parameters(loaded_model, framework)

            with self._lock:
                self._model = loaded_model
                self._model_info = {
                    'model_name': model_name,
                    'version': resolved_version,
                    'alias': alias,
                    'model_uri': local_path,
                    'signature': signature,
                    'flavors': flavors,
                    'example_input': example_input,
                    'load_time': load_duration,
                    'loaded_at': time.time(),
                    'run_id': model_info_obj.run_id if model_info_obj else None,
                    'artifact_size_bytes': artifact_size_bytes,
                    'framework': framework,
                    'num_parameters': num_parameters,
                }
                self._status = 'ready'
                self._load_time = load_duration

            return self.get_health()

        except Exception as e:
            logger.exception("Failed to load model")
            with self._lock:
                self._status = 'error'
                self._error = str(e)
                self._model = None
                self._model_info = {}
            raise

    @staticmethod
    def _compute_artifact_size(local_path: str) -> int:
        """Sum the size of every file under the model's artifact directory."""
        try:
            total = 0
            for root, _dirs, files in os.walk(local_path):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
            return total
        except Exception:
            return 0

    @staticmethod
    def _detect_framework(flavors: dict) -> str | None:
        """Return the primary framework flavor (anything other than pyfunc)."""
        if not isinstance(flavors, dict):
            return None
        for key in flavors.keys():
            if key != 'python_function':
                return key
        return 'python_function' if 'python_function' in flavors else None

    @staticmethod
    def _count_parameters(loaded_model, framework: str | None) -> int | None:
        """Best-effort parameter count per framework. Returns None on failure."""
        if not framework:
            return None
        try:
            # Unwrap the pyfunc wrapper to get the real framework-native model.
            impl = getattr(loaded_model, '_model_impl', None)
            raw = None
            if impl is not None:
                # tensorflow flavor: impl has .keras_model or .model
                raw = getattr(impl, 'keras_model', None) or getattr(impl, 'model', None)
                # sklearn flavor: impl has .sklearn_model
                if raw is None:
                    raw = getattr(impl, 'sklearn_model', None)
                # pytorch flavor: impl has .pytorch_model
                if raw is None:
                    raw = getattr(impl, 'pytorch_model', None)
            if raw is None:
                return None

            if framework == 'tensorflow':
                if hasattr(raw, 'count_params'):
                    return int(raw.count_params())
            elif framework == 'pytorch':
                try:
                    return int(sum(p.numel() for p in raw.parameters()))
                except Exception:
                    return None
            elif framework == 'sklearn':
                coefs = getattr(raw, 'coef_', None)
                if coefs is not None:
                    try:
                        return int(coefs.size)
                    except Exception:
                        return None
            return None
        except Exception:
            return None

    def unload(self) -> dict:
        """Unload the current model and free memory / GPU VRAM.

        Refuses to run while a load is in progress, because the load holds
        self._lock for its entire duration. We try-acquire non-blocking: if
        the lock is held by another thread, a load is happening - refuse
        without waiting. Otherwise we got the lock cleanly and can proceed.

        After dropping the Python reference we run a framework-specific
        cleanup pass to actually release GPU memory. Most frameworks (llama.cpp,
        ONNX Runtime, scikit-learn, custom pyfunc models) release correctly
        via their __del__ destructors once gc.collect() destroys the object;
        only TF/Keras (global session) and PyTorch (caching allocator) need
        explicit cleanup calls. Frameworks are detected via sys.modules so
        we never import a framework that isn't already loaded.

        Full VRAM reclamation is not guaranteed in-process - CUDA contexts
        and driver memory pools may linger. Hard-guarantee zero-VRAM reset
        requires restarting the serving container.
        """
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return {
                'status': 'loading',
                'message': 'Refused: a load is in progress',
                'refused': True,
            }
        try:
            self._model = None
            self._model_info = {}
            self._status = 'idle'
            self._error = None
            self._load_time = None
            self._set_phase('', '')

            # Force Python GC to actually destroy the framework objects
            # we just dropped references to. Without this, __del__ methods
            # (and therefore native resource release) can run lazily.
            import gc
            gc.collect()

            # Framework-specific cleanup - only runs if the framework is
            # already imported in this process. sys.modules check prevents
            # us from dragging in frameworks the current model never used.
            import sys
            if 'tensorflow' in sys.modules:
                try:
                    import tensorflow as tf
                    tf.keras.backend.clear_session()
                except Exception:
                    logger.exception("TF clear_session failed")
            if 'torch' in sys.modules:
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    # Clear torch.compile / dynamo cache. Only meaningful
                    # if the user compiled their model (common with HF
                    # Transformers), but safe to call unconditionally.
                    try:
                        torch._dynamo.reset()
                    except Exception:
                        pass
                except Exception:
                    logger.exception("torch cleanup failed")
            if 'jax' in sys.modules:
                try:
                    import jax
                    jax.clear_caches()
                except Exception:
                    logger.exception("jax.clear_caches failed")
        finally:
            self._lock.release()
        return {'status': 'idle', 'message': 'Model unloaded'}

    def get_health(self) -> dict:
        """Return current serving status.

        Does NOT acquire the lock so it stays responsive while a load is
        in flight. The frontend uses it to discover the initial Deploy
        button state on the Registry page; live progress during a deploy
        is streamed via the /load endpoint's NDJSON response (see
        deploy_stream.py), not by polling this endpoint.
        """
        info = self._model_info.copy()
        return {
            'status': self._status,
            'error': self._error,
            'model_name': info.get('model_name'),
            'version': info.get('version'),
            'alias': info.get('alias'),
            'model_uri': info.get('model_uri'),
            'load_time': self._load_time,
            'run_id': info.get('run_id'),
            'artifact_size_bytes': info.get('artifact_size_bytes'),
            'framework': info.get('framework'),
            'num_parameters': info.get('num_parameters'),
            'phase': self._phase,
            'phase_detail': self._phase_detail,
        }

    def is_ready(self) -> bool:
        return self._status == 'ready' and self._model is not None

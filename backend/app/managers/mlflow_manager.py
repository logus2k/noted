"""MLflow experiment and run browser — wraps the MLflow tracking SDK."""

import os
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")


class MlflowManager:
    """Thin wrapper around mlflow.tracking.MlflowClient."""

    def __init__(self):
        self._client = None

    def warm_up(self):
        """Pre-import MLflow SDK and create client connection (call on startup)."""
        try:
            self._get_client()
            logger.info("MLflow client warmed up (tracking URI: %s)", MLFLOW_TRACKING_URI)
        except Exception as e:
            logger.warning("MLflow warm-up failed: %s", e)

    def _get_client(self):
        if self._client is None:
            from mlflow.tracking import MlflowClient
            self._client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        return self._client

    @staticmethod
    def _ts(ms):
        """Convert millisecond timestamp to ISO string."""
        if not ms:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

    def list_experiments(self) -> list[dict]:
        client = self._get_client()
        experiments = client.search_experiments(order_by=["name ASC"])
        return [
            {
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "lifecycle_stage": exp.lifecycle_stage,
                "creation_time": self._ts(exp.creation_time),
                "artifact_location": exp.artifact_location,
            }
            for exp in experiments
            if exp.lifecycle_stage == "active"
        ]

    def list_runs(
        self,
        experiment_id: str,
        max_results: int = 100,
        filter_string: str = "",
    ) -> list[dict]:
        """List runs for an experiment. `filter_string` uses MLflow's search
        DSL (e.g. `tags._sweep_id = 'abc123'` or `metrics.val_r2 > 0.8`).
        Empty string returns all runs."""
        client = self._get_client()
        runs = client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=filter_string,
            order_by=["start_time DESC"],
            max_results=max_results,
        )
        return [
            {
                "run_id": run.info.run_id,
                "run_name": run.info.run_name or "",
                "status": run.info.status,
                "start_time": self._ts(run.info.start_time),
                "end_time": self._ts(run.info.end_time),
                "duration_ms": (
                    (run.info.end_time - run.info.start_time)
                    if run.info.end_time and run.info.start_time
                    else None
                ),
                "metrics": dict(run.data.metrics),
                "params": dict(run.data.params),
                "tags": {
                    k: v for k, v in run.data.tags.items()
                    if not k.startswith("mlflow.")
                },
            }
            for run in runs
        ]

    def stop_run(self, run_id: str, status: str = "FINISHED") -> dict:
        """End a run by setting its status to FINISHED or FAILED."""
        client = self._get_client()
        client.set_terminated(run_id, status=status)
        return self.get_run(run_id)

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        """Set a tag on a run."""
        client = self._get_client()
        client.set_tag(run_id, key, str(value))

    def delete_tag(self, run_id: str, key: str) -> None:
        """Delete a tag from a run."""
        client = self._get_client()
        try:
            client.delete_tag(run_id, key)
        except Exception:
            pass  # Tag may not exist

    def log_artifact(self, run_id: str, local_path: str, artifact_path: str | None = None) -> None:
        """Log a local file as an artifact on a run."""
        client = self._get_client()
        client.log_artifact(run_id, local_path, artifact_path)

    def log_artifacts(self, run_id: str, local_dir: str, artifact_path: str | None = None) -> None:
        """Log all files in a local directory as artifacts on a run.

        Preserves directory structure under artifact_path. Used by the Hydra
        bundle logger to upload the full config/ tree in one call.
        """
        client = self._get_client()
        client.log_artifacts(run_id, local_dir, artifact_path)

    def search_runs(self, experiment_ids: list[str], filter_string: str = "",
                    order_by: list[str] | None = None, max_results: int = 100) -> list[dict]:
        """Search runs across experiments with optional filter and ordering."""
        client = self._get_client()
        runs = client.search_runs(
            experiment_ids=experiment_ids,
            filter_string=filter_string,
            order_by=order_by or ["start_time DESC"],
            max_results=max_results,
        )
        return [self._format_run(r) for r in runs]

    def create_experiment(self, name: str) -> str:
        """Create a new MLflow experiment. Returns experiment_id."""
        client = self._get_client()
        return client.create_experiment(name)

    def _format_run(self, run) -> dict:
        """Format an MLflow Run object into a dict."""
        info = run.info
        data = run.data
        return {
            'run_id': info.run_id,
            'run_name': info.run_name or data.tags.get('mlflow.runName', ''),
            'experiment_id': info.experiment_id,
            'status': info.status,
            'start_time': self._ts(info.start_time),
            'end_time': self._ts(info.end_time),
            'metrics': dict(data.metrics),
            'params': dict(data.params),
            'tags': {k: v for k, v in data.tags.items() if not k.startswith('mlflow.')},
            'system_tags': {k: v for k, v in data.tags.items() if k.startswith('mlflow.')},
        }

    def delete_run(self, run_id: str) -> None:
        """Delete (archive) a run."""
        client = self._get_client()
        client.delete_run(run_id)

    def delete_experiment(self, experiment_id: str) -> None:
        """Delete (archive) an experiment."""
        client = self._get_client()
        client.delete_experiment(experiment_id)

    def get_metric_history(self, run_id: str, metric_key: str) -> list[dict]:
        """Return the full history of a metric for a run."""
        client = self._get_client()
        history = client.get_metric_history(run_id, metric_key)
        return [
            {
                "key": m.key,
                "value": m.value,
                "step": m.step,
                "timestamp": self._ts(m.timestamp),
            }
            for m in history
        ]

    # ── Artifacts ────────────────────────────────────────────────

    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
    CHART_EXTS = {".html", ".htm"}
    MODEL_EXTS = {".keras", ".h5", ".pt", ".pth", ".pkl", ".joblib", ".onnx",
                  ".pmml", ".safetensors", ".bin"}

    def list_artifacts(self, run_id: str, path: str = "") -> list[dict]:
        """List immediate children at a given artifact path."""
        client = self._get_client()
        items = client.list_artifacts(run_id, path)
        return [
            {"path": fi.path, "file_size": fi.file_size, "is_dir": fi.is_dir}
            for fi in items
        ]

    def list_artifacts_classified(self, run_id: str) -> dict:
        """List all top-level artifacts classified into models/images/charts/files."""
        top = self.list_artifacts(run_id)
        result = {"models": [], "images": [], "charts": [], "files": []}

        for item in top:
            if item["is_dir"]:
                # Check if directory contains an MLmodel file (model artifact)
                children = self.list_artifacts(run_id, item["path"])
                child_names = {PurePosixPath(c["path"]).name for c in children}
                if "MLmodel" in child_names:
                    result["models"].append({**item, "children": children})
                else:
                    # Classify directory contents individually
                    for child in children:
                        cat = self._classify_file(child["path"])
                        result[cat].append(child)
            else:
                cat = self._classify_file(item["path"])
                result[cat].append(item)

        return result

    def download_artifact(self, run_id: str, path: str) -> str:
        """Download an artifact to a temp directory. Returns local file path."""
        if ".." in path:
            raise ValueError("Invalid artifact path")
        client = self._get_client()
        dst = tempfile.mkdtemp(prefix="noted_artifact_")
        local_path = client.download_artifacts(run_id, path, dst_path=dst)
        return local_path

    def list_logged_models_for_run(self, run_id: str) -> list[dict]:
        """Return the MLflow 3.x Logged Model entities linked to a run.

        MLflow 3.x stores models created by `mlflow.<flavor>.log_model(...)`
        under `<experiment_id>/models/<model_id>/artifacts/` rather than
        attaching them directly to the run's artifact tree. This method
        scans the experiment's models/ directory and returns every model
        whose MLmodel file references the given run_id, together with the
        listing of its artifact root (MLmodel, conda.yaml, python_env.yaml,
        requirements.txt, data/, ...).

        Returns a list of:
            {
                "model_id": str,
                "artifact_uri": str,   # mlflow-artifacts:// URI
                "artifacts": [{"path": str, "file_size": int, "is_dir": bool}, ...]
            }
        """
        import urllib.request
        import json as _json

        client = self._get_client()
        run = client.get_run(run_id)
        experiment_id = run.info.experiment_id
        tracking_uri = MLFLOW_TRACKING_URI.rstrip('/')

        out: list[dict] = []
        try:
            list_url = (
                f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts"
                f"?path={experiment_id}/models"
            )
            with urllib.request.urlopen(list_url, timeout=10) as resp:
                entries = _json.loads(resp.read()).get('files', [])
        except Exception as e:
            logger.warning(
                "list_logged_models_for_run: could not list %s/models: %s",
                experiment_id, e,
            )
            return out

        for entry in entries:
            if not entry.get('is_dir'):
                continue
            model_id = PurePosixPath(entry['path']).name
            # Read MLmodel and check if it references this run_id
            try:
                ml_url = (
                    f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts/"
                    f"{experiment_id}/models/{model_id}/artifacts/MLmodel"
                )
                with urllib.request.urlopen(ml_url, timeout=5) as resp:
                    mlmodel_text = resp.read().decode()
            except Exception:
                continue
            if run_id not in mlmodel_text:
                continue

            # Walk the model's artifact root. The MLflow artifacts API
            # returns item.path RELATIVE to the queried path, so we compose
            # it into a model-root-relative path ourselves.
            artifacts: list[dict] = []
            def _walk(sub: str = ""):
                api_path = (
                    f"{experiment_id}/models/{model_id}/artifacts"
                    + (f"/{sub}" if sub else "")
                )
                url = (
                    f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts"
                    f"?path={api_path}"
                )
                try:
                    with urllib.request.urlopen(url, timeout=5) as resp:
                        items = _json.loads(resp.read()).get('files', [])
                except Exception:
                    return
                for it in items:
                    name = it['path']
                    rel = f"{sub}/{name}" if sub else name
                    artifacts.append({
                        "path": rel,
                        "file_size": it.get("file_size") or 0,
                        "is_dir": bool(it.get("is_dir")),
                    })
                    if it.get("is_dir"):
                        _walk(rel)
            _walk()

            out.append({
                "model_id": model_id,
                "experiment_id": experiment_id,
                "artifact_uri": f"mlflow-artifacts:/{experiment_id}/models/{model_id}/artifacts",
                "artifacts": artifacts,
            })

        return out

    def download_logged_model_artifact(
        self, experiment_id: str, model_id: str, path: str,
    ) -> str:
        """Download a single file from a Logged Model's artifact root.

        Mirrors `download_artifact` but for MLflow 3.x Logged Models which
        live outside of run artifact trees. Fetches via the MLflow artifact
        proxy HTTP API directly (NOT via `mlflow.artifacts.download_artifacts`)
        because the noted backend's global MLflow tracking URI is set to the
        backend store (SQLite) and cannot resolve `mlflow-artifacts://` URIs;
        the artifact proxy at `{server}/api/2.0/mlflow-artifacts/artifacts/...`
        is the same HTTP endpoint the Logged Model scanner already uses.
        Returns the local temp path.
        """
        if ".." in path or ".." in model_id or ".." in experiment_id:
            raise ValueError("Invalid path component")
        import urllib.request
        tracking_uri = MLFLOW_TRACKING_URI.rstrip('/')
        proxy_url = (
            f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts/"
            f"{experiment_id}/models/{model_id}/artifacts/{path}"
        )
        dst_dir = tempfile.mkdtemp(prefix="noted_logged_model_")
        local_path = os.path.join(dst_dir, PurePosixPath(path).name or "artifact")
        with urllib.request.urlopen(proxy_url, timeout=30) as resp, open(local_path, 'wb') as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
        return local_path

    @classmethod
    def _classify_file(cls, path: str) -> str:
        ext = PurePosixPath(path).suffix.lower()
        if ext in cls.MODEL_EXTS:
            return "models"
        if ext in cls.IMAGE_EXTS:
            return "images"
        if ext in cls.CHART_EXTS:
            return "charts"
        return "files"

    def get_run(self, run_id: str) -> dict:
        client = self._get_client()
        run = client.get_run(run_id)
        return {
            "run_id": run.info.run_id,
            "run_name": run.info.run_name or "",
            "experiment_id": run.info.experiment_id,
            "status": run.info.status,
            "start_time": self._ts(run.info.start_time),
            "end_time": self._ts(run.info.end_time),
            "duration_ms": (
                (run.info.end_time - run.info.start_time)
                if run.info.end_time and run.info.start_time
                else None
            ),
            "artifact_uri": run.info.artifact_uri,
            "metrics": dict(run.data.metrics),
            "params": dict(run.data.params),
            "tags": {
                k: v for k, v in run.data.tags.items()
                if not k.startswith("mlflow.")
            },
            "system_tags": {
                k: v for k, v in run.data.tags.items()
                if k.startswith("mlflow.")
            },
        }

    # ── Model Registry ───────────────────────────────────────────

    def register_model(self, run_id: str, artifact_path: str, model_name: str,
                       tags: dict | None = None) -> dict:
        """Register a model from a run's artifacts in the MLflow Model Registry.

        Creates the registered model if it doesn't exist, then creates a new version.
        """
        client = self._get_client()

        # Create registered model if needed
        try:
            client.create_registered_model(model_name)
        except Exception:
            pass  # Already exists

        # Build the model URI
        run = client.get_run(run_id)
        model_uri = f"runs:/{run_id}/{artifact_path}"

        # Create version
        version = client.create_model_version(
            name=model_name,
            source=model_uri,
            run_id=run_id,
            tags=tags or {},
        )

        return {
            'model_name': model_name,
            'version': version.version,
            'source': version.source,
            'run_id': run_id,
            'status': version.status,
            'creation_timestamp': self._ts(version.creation_timestamp),
        }

    def list_registered_models(self) -> list[dict]:
        """List all registered models."""
        client = self._get_client()
        models = client.search_registered_models()
        result = []
        for m in models:
            aliases = {}
            if hasattr(m, 'aliases') and m.aliases:
                # MLflow's RegisteredModel.aliases is a dict[str, str]
                # (alias -> version) in current versions; older / mocked
                # variants exposed it as an iterable of objects. Handle both.
                if isinstance(m.aliases, dict):
                    aliases = {str(a): str(v) for a, v in m.aliases.items()}
                else:
                    for alias_info in m.aliases:
                        if hasattr(alias_info, 'alias'):
                            aliases[alias_info.alias] = alias_info.version
                        elif isinstance(alias_info, dict):
                            aliases[alias_info.get('alias', '')] = alias_info.get('version', '')

            result.append({
                'name': m.name,
                'description': m.description or '',
                'creation_timestamp': self._ts(m.creation_timestamp),
                'last_updated_timestamp': self._ts(m.last_updated_timestamp),
                'aliases': aliases,
                'tags': dict(m.tags) if m.tags else {},
            })
        return result

    def list_model_versions(self, model_name: str) -> list[dict]:
        """List all versions of a registered model."""
        client = self._get_client()
        versions = client.search_model_versions(f"name='{model_name}'")
        result = []
        for v in versions:
            # Collect aliases for this version
            version_aliases = []
            try:
                model = client.get_registered_model(model_name)
                if hasattr(model, 'aliases') and model.aliases:
                    aliases = model.aliases
                    if isinstance(aliases, dict):
                        for alias, ver in aliases.items():
                            if str(ver) == str(v.version):
                                version_aliases.append(alias)
                    else:
                        for alias_info in aliases:
                            ver = alias_info.version if hasattr(alias_info, 'version') else alias_info.get('version', '')
                            alias = alias_info.alias if hasattr(alias_info, 'alias') else alias_info.get('alias', '')
                            if str(ver) == str(v.version):
                                version_aliases.append(alias)
            except Exception:
                pass

            result.append({
                'version': v.version,
                'source': v.source,
                'run_id': v.run_id,
                'status': v.status,
                'creation_timestamp': self._ts(v.creation_timestamp),
                'last_updated_timestamp': self._ts(v.last_updated_timestamp),
                'description': v.description or '',
                'aliases': version_aliases,
                'tags': dict(v.tags) if v.tags else {},
            })
        return sorted(result, key=lambda x: int(x['version']), reverse=True)

    def set_model_alias(self, model_name: str, version: str, alias: str) -> dict:
        """Set an alias on a model version (e.g., @champion, @staging)."""
        client = self._get_client()
        client.set_registered_model_alias(model_name, alias, version)
        return {'model_name': model_name, 'version': version, 'alias': alias}

    def delete_registered_model(self, model_name: str) -> dict:
        """Delete a registered model and all its versions."""
        client = self._get_client()
        client.delete_registered_model(model_name)
        return {'model_name': model_name, 'deleted': True}

    def delete_model_version(self, model_name: str, version: str) -> dict:
        """Delete a specific model version."""
        client = self._get_client()
        client.delete_model_version(model_name, version)
        return {'model_name': model_name, 'version': version, 'deleted': True}

    def delete_model_alias(self, model_name: str, alias: str) -> dict:
        """Remove an alias from a model."""
        client = self._get_client()
        client.delete_registered_model_alias(model_name, alias)
        return {'model_name': model_name, 'alias': alias, 'deleted': True}

    def resolve_model_artifact_uri(self, model_name: str, version: str) -> dict:
        """Resolve the direct artifact URI for a model version.

        In MLflow 3.x, models logged with name= are stored under
        models/m-{id}/artifacts/ instead of {run_id}/artifacts/model/.
        This scans the artifact store to find the correct path.
        """
        import urllib.request, json as _json, yaml

        client = self._get_client()
        v = client.get_model_version(model_name, version)
        run = client.get_run(v.run_id)
        experiment_id = run.info.experiment_id
        tracking_uri = str(client.tracking_uri)

        # Scan models directory for the one matching this run_id
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
                if v.run_id in ml_content:
                    return {
                        'artifact_uri': f"mlflow-artifacts:/{experiment_id}/models/{mid}/artifacts",
                        'model_id': mid,
                        'run_id': v.run_id,
                        'experiment_id': experiment_id,
                    }
            except Exception:
                continue

        raise FileNotFoundError(f"Could not resolve artifact path for {model_name} v{version}")

    def get_model_version(self, model_name: str, version: str) -> dict:
        """Get details of a specific model version."""
        client = self._get_client()
        v = client.get_model_version(model_name, version)
        result = {
            'version': v.version,
            'source': v.source,
            'run_id': v.run_id,
            'status': v.status,
            'creation_timestamp': self._ts(v.creation_timestamp),
            'description': v.description or '',
            'tags': dict(v.tags) if v.tags else {},
            'aliases': list(v.aliases) if hasattr(v, 'aliases') and v.aliases else [],
            'signature': None,
            'flavors': None,
        }
        # Try to read signature and flavors from the MLmodel artifact
        try:
            import yaml, urllib.request, json
            run = client.get_run(v.run_id)
            exp_id = run.info.experiment_id
            tracking_uri = str(client.tracking_uri)
            list_url = f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts?path={exp_id}/models"
            resp = urllib.request.urlopen(list_url, timeout=5)
            model_dirs = json.loads(resp.read())
            for entry in model_dirs.get('files', []):
                if not entry.get('is_dir'):
                    continue
                mid = entry['path']
                try:
                    ml_url = f"{tracking_uri}/api/2.0/mlflow-artifacts/artifacts/{exp_id}/models/{mid}/artifacts/MLmodel"
                    ml_resp = urllib.request.urlopen(ml_url, timeout=5)
                    ml_content = ml_resp.read().decode()
                    if v.run_id in ml_content:
                        mlmodel = yaml.safe_load(ml_content)
                        sig = mlmodel.get('signature')
                        if sig:
                            result['signature'] = {
                                'inputs': sig.get('inputs', ''),
                                'outputs': sig.get('outputs', ''),
                            }
                        result['flavors'] = list(mlmodel.get('flavors', {}).keys())
                        break
                except Exception:
                    continue
        except Exception:
            pass
        return result

    def get_model_lineage(self, model_name: str, version: str) -> dict:
        """Get the full lineage chain for a model version.

        Traces: Data (DVC) -> Config (Hydra) -> Code (git) -> Run (MLflow) -> Model (Registry)
        """
        v = self.get_model_version(model_name, version)
        run_id = v.get('run_id')
        if not run_id:
            return {'model': v, 'run': None, 'lineage': {}}

        run = self.get_run(run_id)
        tags = run.get('tags', {})
        params = run.get('params', {})

        lineage = {
            # Data layer (DVC)
            'data': {
                'dvc_data_hash': tags.get('dvc.data_hash', params.get('dvc_data_hash', '')),
                'dvc_data_file': tags.get('dvc.data_file', params.get('dvc_data_file', '')),
                'dvc_hashes': tags.get('noted.dvc_hashes', ''),
            },
            # Config layer (Hydra) - tag is set as 'noted.hydra_config_hash' by
            # the execution bridge; older runs may also have 'hydra_config_hash'
            # as a plain tag or param.
            'config': {
                'hydra_config_hash': (
                    tags.get('noted.hydra_config_hash')
                    or tags.get('hydra_config_hash')
                    or tags.get('hydra.config_hash')
                    or params.get('hydra_config_hash', '')
                ),
            },
            # Code layer (Git) - MLflow's autologging sets mlflow.source.git.commit
            # and mlflow.source.git.branch when the process runs inside a git repo.
            # The noted-specific snapshot tags are set by SnapshotManager.
            'code': {
                'git_commit': (
                    tags.get('mlflow.source.git.commit')
                    or tags.get('noted.git_commit')
                    or ''
                ),
                'snapshot_branch': (
                    tags.get('noted.snapshot_branch')
                    or tags.get('mlflow.source.git.branch')
                    or ''
                ),
                'snapshot_name': tags.get('noted.snapshot_name', ''),
                'is_snapshot': tags.get('noted.snapshot') == 'true',
            },
            # Run layer (MLflow)
            'run': {
                'run_id': run_id,
                'run_name': run.get('run_name', ''),
                'experiment_id': run.get('experiment_id', ''),
                'status': run.get('status', ''),
                'metrics': run.get('metrics', {}),
                'start_time': run.get('start_time'),
            },
            # Model layer (Registry)
            'model': {
                'name': model_name,
                'version': version,
                'source': v.get('source', ''),
                'aliases': v.get('aliases', []),
                'creation_timestamp': v.get('creation_timestamp'),
            },
            # Pipeline layer (Airflow - if applicable)
            'pipeline': {
                'dag_run_id': tags.get('airflow.dag_run_id', ''),
                'dag_id': tags.get('airflow.dag_id', ''),
            },
        }

        return {'model': v, 'run': run, 'lineage': lineage}

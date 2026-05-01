"""MLflow scanner - discovers experiments, runs, snapshots, and registered models."""

import logging
import requests

from app.models import Entity, Relationship
from app.config import MLFLOW_TRACKING_URI

logger = logging.getLogger(__name__)


class MlflowScanner:
    """Scans MLflow tracking server for entities and relationships."""

    def __init__(self):
        self._base_url = MLFLOW_TRACKING_URI

    def scan(self, project_id: str) -> tuple[list[Entity], list[Relationship]]:
        """Scan MLflow for all entities related to a project.

        Returns (entities, relationships).
        """
        entities = []
        relationships = []

        experiments = self._get_experiments(project_id)
        for exp in experiments:
            exp_entity = Entity(
                id=f"experiment:{exp['experiment_id']}",
                type='experiment',
                label=exp['name'],
                properties={
                    'experiment_id': exp['experiment_id'],
                    'lifecycle_stage': exp.get('lifecycle_stage', 'active'),
                },
            )
            entities.append(exp_entity)

            # Runs within experiment
            runs = self._get_runs(exp['experiment_id'])
            for run in runs:
                run_entity = self._build_run_entity(run)
                entities.append(run_entity)
                relationships.append(Relationship(
                    source=run_entity.id,
                    target=exp_entity.id,
                    type='belongs_to',
                ))

                # Snapshot check
                tags = run.get('tags', {})
                if tags.get('noted.snapshot') == 'true':
                    snap_entity = Entity(
                        id=f"snapshot:{run['run_id']}",
                        type='snapshot',
                        label=tags.get('noted.snapshot_name', run['run_id'][:8]),
                        properties={
                            'branch': tags.get('noted.snapshot_branch', ''),
                            'version': tags.get('noted.snapshot_version', ''),
                            'git_commit': tags.get('noted.git_commit', ''),
                        },
                    )
                    entities.append(snap_entity)
                    relationships.append(Relationship(
                        source=snap_entity.id,
                        target=run_entity.id,
                        type='snapshot_of',
                    ))

        # Registered models
        models = self._get_models()
        for model in models:
            model_entity = Entity(
                id=f"model:{model['name']}",
                type='model',
                label=model['name'],
                properties={
                    'description': model.get('description', ''),
                    'aliases': model.get('aliases', {}),
                },
            )
            entities.append(model_entity)

            # Model versions
            versions = self._get_model_versions(model['name'])
            for v in versions:
                version_entity = Entity(
                    id=f"model_version:{model['name']}:{v['version']}",
                    type='model_version',
                    label=f"{model['name']} v{v['version']}",
                    properties={
                        'version': v['version'],
                        'source': v.get('source', ''),
                        'status': v.get('status', ''),
                        'aliases': v.get('aliases', []),
                        'run_id': v.get('run_id', ''),
                    },
                )
                entities.append(version_entity)
                relationships.append(Relationship(
                    source=version_entity.id,
                    target=model_entity.id,
                    type='version_of',
                ))

                # Link to source run
                if v.get('run_id'):
                    relationships.append(Relationship(
                        source=f"run:{v['run_id']}",
                        target=version_entity.id,
                        type='produces',
                    ))

                # Alias relationships
                for alias in v.get('aliases', []):
                    relationships.append(Relationship(
                        source=version_entity.id,
                        target=model_entity.id,
                        type='promoted_to',
                        properties={'alias': alias},
                    ))

        return entities, relationships

    def _build_run_entity(self, run: dict) -> Entity:
        """Build an Entity from an MLflow run dict."""
        tags = run.get('tags', {})
        params = run.get('params', {})
        return Entity(
            id=f"run:{run['run_id']}",
            type='run',
            label=run.get('run_name', run['run_id'][:8]),
            properties={
                'run_id': run['run_id'],
                'status': run.get('status', ''),
                'start_time': run.get('start_time', ''),
                'end_time': run.get('end_time', ''),
                'metrics': run.get('metrics', {}),
                'params': params,
                'is_snapshot': tags.get('noted.snapshot') == 'true',
                'dvc_data_hash': tags.get('dvc.data_hash', params.get('dvc_data_hash', '')),
                'hydra_config_hash': tags.get('hydra.config_hash', params.get('hydra_config_hash', '')),
                'git_commit': tags.get('noted.git_commit', ''),
            },
        )

    # ── API Calls ─────────────────────────────────────────────────

    def _api_get(self, path: str) -> dict:
        """Make a GET request to MLflow API."""
        try:
            resp = requests.get(f'{self._base_url}{path}', timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("MLflow API call failed: %s %s", path, e)
            return {}

    def _api_post(self, path: str, json_data: dict) -> dict:
        """Make a POST request to MLflow API."""
        try:
            resp = requests.post(f'{self._base_url}{path}', json=json_data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("MLflow API call failed: %s %s", path, e)
            return {}

    def _get_experiments(self, project_id: str) -> list[dict]:
        """Get all experiments, optionally filtered by project."""
        data = self._api_post('/api/2.0/mlflow/experiments/search', {
            'max_results': 200,
        })
        experiments = []
        for exp in data.get('experiments', []):
            if exp.get('lifecycle_stage') != 'active':
                continue
            experiments.append({
                'experiment_id': exp['experiment_id'],
                'name': exp.get('name', ''),
                'lifecycle_stage': exp.get('lifecycle_stage', ''),
            })
        return experiments

    def _get_runs(self, experiment_id: str) -> list[dict]:
        """Get all runs for an experiment."""
        data = self._api_post('/api/2.0/mlflow/runs/search', {
            'experiment_ids': [experiment_id],
            'max_results': 200,
        })
        runs = []
        for run in data.get('runs', []):
            info = run.get('info', {})
            run_data = run.get('data', {})
            tags = {}
            for t in run_data.get('tags', []):
                tags[t['key']] = t['value']
            metrics = {}
            for m in run_data.get('metrics', []):
                metrics[m['key']] = m['value']
            params = {}
            for p in run_data.get('params', []):
                params[p['key']] = p['value']

            runs.append({
                'run_id': info.get('run_id', ''),
                'run_name': tags.get('mlflow.runName', info.get('run_name', '')),
                'status': info.get('status', ''),
                'start_time': info.get('start_time'),
                'end_time': info.get('end_time'),
                'metrics': metrics,
                'params': params,
                'tags': tags,
            })
        return runs

    def _get_models(self) -> list[dict]:
        """Get all registered models."""
        data = self._api_get('/api/2.0/mlflow/registered-models/search?max_results=100')
        models = []
        for m in data.get('registered_models', []):
            aliases = {}
            for alias in m.get('aliases', []):
                if isinstance(alias, dict):
                    aliases[alias.get('alias', '')] = alias.get('version', '')
            models.append({
                'name': m.get('name', ''),
                'description': m.get('description', ''),
                'aliases': aliases,
            })
        return models

    def _get_model_versions(self, model_name: str) -> list[dict]:
        """Get all versions for a model."""
        data = self._api_get(
            f'/api/2.0/mlflow/registered-models/get?name={requests.utils.quote(model_name)}'
        )
        model = data.get('registered_model', {})
        versions = []
        for v in model.get('latest_versions', []):
            version_aliases = []
            for alias in model.get('aliases', []):
                if isinstance(alias, dict) and str(alias.get('version', '')) == str(v.get('version', '')):
                    version_aliases.append(alias.get('alias', ''))
            versions.append({
                'version': v.get('version', ''),
                'source': v.get('source', ''),
                'run_id': v.get('run_id', ''),
                'status': v.get('status', ''),
                'aliases': version_aliases,
            })
        return versions

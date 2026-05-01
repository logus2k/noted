"""Airflow scanner - discovers DAGs, tasks, and runs."""

import logging
import time

import requests

from app.models import Entity, Relationship
from app.config import AIRFLOW_API_URL, AIRFLOW_BASE_PATH, AIRFLOW_USERNAME, AIRFLOW_PASSWORD

logger = logging.getLogger(__name__)


class AirflowScanner:
    """Scans Airflow API for DAGs, tasks, and runs."""

    def __init__(self):
        self._token = None
        self._token_expiry = 0

    def scan(self, project_id: str) -> tuple[list[Entity], list[Relationship]]:
        """Scan Airflow for all DAGs, tasks, and recent runs."""
        entities = []
        relationships = []

        dags = self._get_dags()
        for dag in dags:
            dag_entity = Entity(
                id=f"dag:{dag['dag_id']}",
                type='dag',
                label=dag['dag_id'],
                properties={
                    'is_paused': dag.get('is_paused', False),
                    'schedule': dag.get('timetable_summary', 'None'),
                    'tags': dag.get('tags', []),
                    'owners': dag.get('owners', []),
                    'fileloc': dag.get('fileloc', ''),
                },
            )
            entities.append(dag_entity)

            # Tasks
            tasks = self._get_tasks(dag['dag_id'])
            for task in tasks:
                task_entity = Entity(
                    id=f"dag_task:{dag['dag_id']}:{task['task_id']}",
                    type='dag_task',
                    label=task['task_id'],
                    properties={
                        'operator': task.get('operator_name', ''),
                        'trigger_rule': task.get('trigger_rule', 'all_success'),
                        'dag_id': dag['dag_id'],
                    },
                )
                entities.append(task_entity)
                relationships.append(Relationship(
                    source=dag_entity.id,
                    target=task_entity.id,
                    type='has_task',
                ))

                # Task dependencies
                for downstream in task.get('downstream_task_ids', []):
                    relationships.append(Relationship(
                        source=task_entity.id,
                        target=f"dag_task:{dag['dag_id']}:{downstream}",
                        type='depends_on',
                    ))

            # Recent runs (last 10)
            runs = self._get_runs(dag['dag_id'], limit=10)
            for run in runs:
                run_entity = Entity(
                    id=f"dag_run:{dag['dag_id']}:{run['dag_run_id']}",
                    type='dag_run',
                    label=run['dag_run_id'][:30],
                    properties={
                        'state': run.get('state', ''),
                        'start_date': run.get('start_date', ''),
                        'end_date': run.get('end_date', ''),
                        'dag_id': dag['dag_id'],
                        'conf': run.get('conf', {}),
                        'mlflow_run_id': run.get('conf', {}).get('mlflow_run_id', ''),
                    },
                )
                entities.append(run_entity)
                relationships.append(Relationship(
                    source=dag_entity.id,
                    target=run_entity.id,
                    type='executed_as',
                ))

        return entities, relationships

    # ── API Helpers ───────────────────────────────────────────────

    def _ensure_token(self):
        if self._token and time.time() < self._token_expiry:
            return
        try:
            resp = requests.post(
                f'{AIRFLOW_API_URL}{AIRFLOW_BASE_PATH}/auth/token',
                json={'username': AIRFLOW_USERNAME, 'password': AIRFLOW_PASSWORD},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                self._token = data.get('access_token', '')
                self._token_expiry = time.time() + 3500  # ~1h
        except Exception as e:
            logger.warning("Airflow token failed: %s", e)

    def _api_get(self, path: str) -> dict:
        self._ensure_token()
        headers = {}
        if self._token:
            headers['Authorization'] = f'Bearer {self._token}'
        try:
            resp = requests.get(f'{AIRFLOW_API_URL}{AIRFLOW_BASE_PATH}/api/v2{path}',
                                headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug("Airflow API failed: %s %s", path, e)
            return {}

    def _get_dags(self) -> list[dict]:
        data = self._api_get('/dags?limit=100')
        dags = []
        for d in data.get('dags', []):
            tags = [t.get('name', t) if isinstance(t, dict) else t for t in d.get('tags', [])]
            dags.append({
                'dag_id': d['dag_id'],
                'is_paused': d.get('is_paused', False),
                'timetable_summary': d.get('timetable_summary', ''),
                'tags': tags,
                'owners': d.get('owners', []),
                'fileloc': d.get('fileloc', ''),
            })
        return dags

    def _get_tasks(self, dag_id: str) -> list[dict]:
        data = self._api_get(f'/dags/{dag_id}/tasks')
        return [
            {
                'task_id': t['task_id'],
                'operator_name': t.get('operator_name', ''),
                'downstream_task_ids': t.get('downstream_task_ids', []),
                'trigger_rule': t.get('trigger_rule', 'all_success'),
            }
            for t in data.get('tasks', [])
        ]

    def _get_runs(self, dag_id: str, limit: int = 10) -> list[dict]:
        data = self._api_get(f'/dags/{dag_id}/dagRuns?limit={limit}&order_by=-start_date')
        return [
            {
                'dag_run_id': r.get('dag_run_id', ''),
                'state': r.get('state', ''),
                'start_date': r.get('start_date', ''),
                'end_date': r.get('end_date', ''),
                'conf': r.get('conf', {}),
            }
            for r in data.get('dag_runs', [])
        ]

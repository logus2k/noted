"""Airflow pipeline manager.

Discovers DAGs, triggers runs, monitors task status via the Airflow REST API (v2).
"""

import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

AIRFLOW_API_URL = os.environ.get('AIRFLOW_API_URL', 'http://noted-airflow-apiserver:8080')
AIRFLOW_BASE_PATH = os.environ.get('AIRFLOW_BASE_PATH', '/airflow')  # Matches AIRFLOW__WEBSERVER__BASE_URL path
AIRFLOW_USERNAME = os.environ.get('AIRFLOW_USERNAME', 'airflow')
AIRFLOW_PASSWORD = os.environ.get('AIRFLOW_PASSWORD', 'airflow')


class AirflowManager:
    """Airflow REST API client for DAG discovery, triggering, and monitoring."""

    def __init__(self):
        self._session = None
        self._token = None
        self._token_expiry = 0

    def _get_session(self):
        if self._session is None:
            self._session = requests.Session()
            self._session.headers['Content-Type'] = 'application/json'
        return self._session

    def _ensure_token(self):
        """Obtain or refresh JWT token from Airflow."""
        if self._token and time.time() < self._token_expiry - 60:
            return  # Token still valid (with 60s buffer)
        session = self._get_session()
        # Try multiple token endpoint paths (varies by Airflow base URL config)
        token_paths = [f'{AIRFLOW_BASE_PATH}/auth/token', '/auth/token']
        for path in token_paths:
            try:
                resp = session.post(
                    f'{AIRFLOW_API_URL}{path}',
                    json={'username': AIRFLOW_USERNAME, 'password': AIRFLOW_PASSWORD},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    self._token = data.get('access_token')
                    expires_in = data.get('expires_in', 1800)
                    self._token_expiry = time.time() + expires_in
                    session.headers['Authorization'] = f'Bearer {self._token}'
                    session.auth = None  # Clear any stale basic-auth fallback
                    logger.info('Airflow JWT token obtained via %s (expires in %ds)', path, expires_in)
                    return
            except Exception:
                continue

        # Fallback to basic auth if JWT not available
        logger.warning('JWT token not available, falling back to basic auth')
        session.auth = (AIRFLOW_USERNAME, AIRFLOW_PASSWORD)
        self._token = None

    def _api(self, method, path, **kwargs):
        """Make an Airflow API request with auto-authentication."""
        self._ensure_token()
        # Try with /airflow prefix first (when base URL is configured), then without
        url = f'{AIRFLOW_API_URL}{AIRFLOW_BASE_PATH}/api/v2{path}'
        session = self._get_session()
        resp = session.request(method, url, **kwargs)
        if resp.status_code == 401:
            # Token may have expired, retry once
            self._token = None
            self._token_expiry = 0
            self._ensure_token()
            resp = session.request(method, url, **kwargs)
        if resp.status_code == 401:
            raise PermissionError('Airflow authentication failed')
        if resp.status_code == 404:
            raise FileNotFoundError(f'Not found: {path}')
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _api_safe(self, method, path, **kwargs):
        """Make an API request, return None on failure."""
        try:
            return self._api(method, path, **kwargs)
        except Exception as e:
            logger.warning('Airflow API call failed: %s %s - %s', method, path, e)
            return None

    # ── Health check ─────────────────────────────────────────────────

    def health(self) -> dict:
        """Check Airflow API connectivity."""
        try:
            data = self._api('GET', '/monitor/health')
            return {'healthy': True, 'data': data}
        except Exception as e:
            return {'healthy': False, 'error': str(e)}

    # ── DAG Discovery ────────────────────────────────────────────────

    def list_dags(self, tag: str | None = None) -> list[dict]:
        """List all DAGs, optionally filtered by tag."""
        params = {'limit': 100}
        if tag:
            params['tags'] = [tag]
        data = self._api('GET', '/dags', params=params)
        dags = data.get('dags', [])
        return [
            {
                'dag_id': d['dag_id'],
                'description': d.get('description', ''),
                'is_paused': d.get('is_paused', False),
                'is_active': d.get('is_active', True),
                'tags': [t.get('name', t) if isinstance(t, dict) else t for t in d.get('tags', [])],
                'schedule': d.get('timetable_summary') or d.get('schedule_interval') or 'None',
                'file_token': d.get('file_token', ''),
                'owners': d.get('owners', []),
                'last_parsed_time': d.get('last_parsed_time'),
                'next_dagrun': d.get('next_dagrun'),
            }
            for d in dags
        ]

    def get_dag(self, dag_id: str) -> dict:
        """Get details for a specific DAG (merges /dags and /dags/details for params)."""
        d = self._api('GET', f'/dags/{dag_id}')
        # Params are in the /details endpoint in Airflow 3.0
        params = {}
        details = self._api_safe('GET', f'/dags/{dag_id}/details')
        if details and details.get('params'):
            for key, info in details['params'].items():
                params[key] = {
                    'value': info.get('value'),
                    'description': info.get('description', ''),
                    'type': info.get('schema', {}).get('type', 'string'),
                }
        return {
            'dag_id': d['dag_id'],
            'description': d.get('description', ''),
            'is_paused': d.get('is_paused', False),
            'is_active': d.get('is_active', True),
            'tags': [t.get('name', t) if isinstance(t, dict) else t for t in d.get('tags', [])],
            'schedule': d.get('timetable_summary') or d.get('schedule_interval') or 'None',
            'owners': d.get('owners', []),
            'params': params,
            'last_parsed_time': d.get('last_parsed_time'),
            'next_dagrun': d.get('next_dagrun'),
        }

    def get_dag_tasks(self, dag_id: str) -> list[dict]:
        """Get tasks for a DAG (for visualization)."""
        data = self._api('GET', f'/dags/{dag_id}/tasks')
        tasks = data.get('tasks', [])
        return [
            {
                'task_id': t['task_id'],
                'operator_name': t.get('operator_name', ''),
                'downstream_task_ids': t.get('downstream_task_ids', []),
                'is_mapped': t.get('is_mapped', False),
                'ui_color': t.get('ui_color', '#ffefeb'),
                'ui_fgcolor': t.get('ui_fgcolor', '#000'),
                'trigger_rule': t.get('trigger_rule', 'all_success'),
            }
            for t in tasks
        ]

    def get_dag_structure(self, dag_id: str) -> dict:
        """Get DAG task dependency graph for visualization."""
        tasks = self.get_dag_tasks(dag_id)
        nodes = []
        edges = []
        for t in tasks:
            nodes.append({
                'id': t['task_id'],
                'operator': t['operator_name'],
                'ui_color': t['ui_color'],
                'ui_fgcolor': t['ui_fgcolor'],
                'trigger_rule': t['trigger_rule'],
            })
            for downstream in t['downstream_task_ids']:
                edges.append({
                    'source': t['task_id'],
                    'target': downstream,
                })
        return {'nodes': nodes, 'edges': edges}

    # ── DAG Triggering ───────────────────────────────────────────────

    def trigger_dag(self, dag_id: str, conf: dict | None = None,
                    logical_date: str | None = None) -> dict:
        """Trigger a DAG run."""
        from datetime import datetime, timezone
        body = {
            'logical_date': logical_date or datetime.now(timezone.utc).isoformat(),
        }
        if conf:
            body['conf'] = conf

        data = self._api('POST', f'/dags/{dag_id}/dagRuns', json=body)
        return {
            'dag_run_id': data.get('dag_run_id'),
            'dag_id': data.get('dag_id'),
            'state': data.get('state'),
            'logical_date': data.get('logical_date'),
            'start_date': data.get('start_date'),
            'conf': data.get('conf', {}),
        }

    # ── Sweep (Parallel Parameter Grid) ─────────────────────────────

    def sweep(self, dag_id: str, param_grid: dict, base_conf: dict | None = None) -> dict:
        """Trigger multiple DAG runs for all combinations of param values.

        Args:
            dag_id: The DAG to sweep
            param_grid: Dict of param_name -> list of values.
                e.g. {"model_type": ["GRU", "LSTM"], "learning_rate": [0.001, 0.0005]}
            base_conf: Optional base config merged into each combination

        Returns:
            {"sweep_id": "...", "combinations": 4, "runs": [...]}
        """
        import itertools
        from datetime import datetime, timezone

        if not param_grid:
            raise ValueError("param_grid is empty")

        # Generate all combinations
        keys = list(param_grid.keys())
        value_lists = [param_grid[k] if isinstance(param_grid[k], list) else [param_grid[k]] for k in keys]
        combinations = list(itertools.product(*value_lists))

        sweep_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        runs = []

        for i, combo in enumerate(combinations):
            conf = dict(base_conf or {})
            for k, v in zip(keys, combo):
                conf[k] = v
            conf['_sweep_id'] = sweep_id
            conf['_sweep_index'] = i

            try:
                result = self.trigger_dag(dag_id, conf=conf)
                runs.append({
                    'index': i,
                    'params': dict(zip(keys, combo)),
                    'dag_run_id': result['dag_run_id'],
                    'state': result['state'],
                })
            except Exception as e:
                runs.append({
                    'index': i,
                    'params': dict(zip(keys, combo)),
                    'error': str(e),
                })

        return {
            'sweep_id': sweep_id,
            'dag_id': dag_id,
            'combinations': len(combinations),
            'runs': runs,
        }

    # ── DAG Run Monitoring ───────────────────────────────────────────

    def list_dag_runs(self, dag_id: str, limit: int = 50) -> list[dict]:
        """List recent DAG runs with duration and MLflow link."""
        data = self._api('GET', f'/dags/{dag_id}/dagRuns',
                         params={'limit': limit, 'order_by': '-start_date'})
        runs = data.get('dag_runs', [])
        result = []
        for r in runs:
            duration = None
            if r.get('start_date') and r.get('end_date'):
                try:
                    from datetime import datetime
                    start = datetime.fromisoformat(r['start_date'].replace('Z', '+00:00'))
                    end = datetime.fromisoformat(r['end_date'].replace('Z', '+00:00'))
                    duration = (end - start).total_seconds()
                except Exception:
                    pass
            conf = r.get('conf', {}) or {}
            # Try to get MLflow run ID from XCom (pushed by the training task).
            # TaskFlow tasks push their return dict as 'return_value', so
            # the run_id is inside that dict, not as a standalone key.
            # We try both the current task name and the legacy name.
            mlflow_run_id = conf.get('mlflow_run_id')
            if not mlflow_run_id and r.get('state') == 'success':
                for task_name in ('train_model_task', 'train_model'):
                    xcom_val = self.get_xcom_value(
                        dag_id, r.get('dag_run_id'), task_name, 'return_value')
                    if isinstance(xcom_val, dict):
                        mlflow_run_id = xcom_val.get('run_id')
                    elif isinstance(xcom_val, str):
                        mlflow_run_id = xcom_val
                    if mlflow_run_id:
                        break
            result.append({
                'dag_run_id': r.get('dag_run_id'),
                'state': r.get('state'),
                'logical_date': r.get('logical_date'),
                'start_date': r.get('start_date'),
                'end_date': r.get('end_date'),
                'duration': duration,
                'conf': conf,
                'note': r.get('note', ''),
                'mlflow_run_id': mlflow_run_id,
            })
        return result

    def get_xcom_value(self, dag_id: str, dag_run_id: str, task_id: str, key: str):
        """Get an XCom value for a specific task instance."""
        try:
            data = self._api('GET', f'/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries/{key}')
            return data.get('value')
        except Exception:
            return None

    def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict:
        """Get details for a specific DAG run."""
        return self._api('GET', f'/dags/{dag_id}/dagRuns/{dag_run_id}')

    def delete_dag_run(self, dag_id: str, dag_run_id: str) -> dict:
        """Delete a specific DAG run."""
        from urllib.parse import quote
        return self._api('DELETE', f'/dags/{dag_id}/dagRuns/{quote(dag_run_id, safe="")}')

    def stop_dag_run(self, dag_id: str, dag_run_id: str) -> dict:
        """Stop a running DAG run by marking it as failed."""
        from urllib.parse import quote
        return self._api('PATCH',
            f'/dags/{dag_id}/dagRuns/{quote(dag_run_id, safe="")}',
            json={'state': 'failed'})

    def get_task_instances(self, dag_id: str, dag_run_id: str) -> list[dict]:
        """Get task instances for a DAG run (for status monitoring)."""
        data = self._api('GET', f'/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances')
        instances = data.get('task_instances', [])
        return [
            {
                'task_id': t.get('task_id'),
                'state': t.get('state'),
                'start_date': t.get('start_date'),
                'end_date': t.get('end_date'),
                'duration': t.get('duration'),
                'try_number': t.get('try_number'),
                'operator': t.get('operator'),
            }
            for t in instances
        ]

    def get_task_log(self, dag_id: str, dag_run_id: str, task_id: str,
                     try_number: int = 1) -> str:
        """Get log content for a specific task instance."""
        try:
            self._ensure_token()
            url = f'{AIRFLOW_API_URL}{AIRFLOW_BASE_PATH}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}'
            session = self._get_session()
            resp = session.get(url, headers={'Accept': 'application/json'})
            resp.raise_for_status()
            data = resp.json()
            # Airflow 3.0 returns JSON with content array of log entries
            content = data.get('content', [])
            lines = []
            for entry in content:
                ts = entry.get('timestamp', '')
                event = entry.get('event', '')
                level = entry.get('level', '')
                if ts:
                    ts_short = ts[11:19] if len(ts) > 19 else ts
                    lines.append(f'[{ts_short}] [{level.upper()}] {event}')
                elif event:
                    lines.append(event)
                # Render error_detail as a Python-style traceback
                error_detail = entry.get('error_detail')
                if error_detail:
                    for exc in error_detail:
                        lines.append('Traceback (most recent call last):')
                        for frame in exc.get('frames', []):
                            fname = frame.get('filename', '?')
                            lineno = frame.get('lineno', '?')
                            name = frame.get('name', '?')
                            lines.append(f'  File "{fname}", line {lineno}, in {name}')
                        exc_type = exc.get('exc_type', 'Exception')
                        exc_value = exc.get('exc_value', '')
                        lines.append(f'{exc_type}: {exc_value}')
            return '\n'.join(lines) if lines else 'No log content available'
        except Exception as e:
            return f'Failed to fetch log: {e}'

    # ── Run Status Polling ─────────────────────────────────────────

    def get_run_state(self, dag_id: str, dag_run_id: str) -> str:
        """Get the current state of a DAG run."""
        data = self._api('GET', f'/dags/{dag_id}/dagRuns/{dag_run_id}')
        return data.get('state', 'unknown')

    # ── DAG Pause/Unpause ────────────────────────────────────────────

    def set_dag_paused(self, dag_id: str, is_paused: bool) -> dict:
        """Pause or unpause a DAG."""
        data = self._api('PATCH', f'/dags/{dag_id}', json={'is_paused': is_paused})
        return {'dag_id': dag_id, 'is_paused': data.get('is_paused')}

    # ── Schedule Management (via Airflow Variables) ───────────────

    def get_schedule(self, dag_id: str) -> dict:
        """Get the schedule variable for a DAG.

        Convention: variable key is '{dag_id}_schedule'.
        Returns None schedule if variable doesn't exist.
        """
        key = f'{dag_id}_schedule'
        try:
            data = self._api('GET', f'/variables/{key}')
            return {'dag_id': dag_id, 'schedule': data.get('value'), 'key': key}
        except Exception:
            return {'dag_id': dag_id, 'schedule': None, 'key': key}

    def set_schedule(self, dag_id: str, schedule: str | None) -> dict:
        """Set or clear the schedule variable for a DAG.

        Pass schedule=None or empty string to clear (revert to no schedule).
        The DAG must use Variable.get('{dag_id}_schedule', default_var=None) for this to work.
        Changes take effect on the next DAG parse cycle (typically within 30 seconds).
        """
        key = f'{dag_id}_schedule'
        if not schedule or schedule.strip() == '':
            # Delete the variable to revert to no schedule
            try:
                self._api('DELETE', f'/variables/{key}')
            except Exception:
                pass  # Variable may not exist
            return {'dag_id': dag_id, 'schedule': None, 'key': key}

        # Create or update the variable
        try:
            self._api('PATCH', f'/variables/{key}', json={'key': key, 'value': schedule.strip()})
        except Exception:
            # Variable doesn't exist yet, create it
            self._api('POST', '/variables', json={'key': key, 'value': schedule.strip()})
        return {'dag_id': dag_id, 'schedule': schedule.strip(), 'key': key}

    def clear_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict:
        """Clear a task instance so it can be retried.

        This resets the task state, causing Airflow to re-queue and re-execute it.
        """
        data = self._api(
            'POST',
            f'/dags/{dag_id}/clearTaskInstances',
            json={
                'dry_run': False,
                'task_ids': [task_id],
                'dag_run_id': dag_run_id,
                'reset_dag_runs': True,
            },
        )
        return data

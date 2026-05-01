"""Relationship resolver - builds cross-entity edges from entity properties.

Entities from different scanners (MLflow, DVC, Hydra, Airflow, filesystem) are
connected here based on shared identifiers: DVC hashes, Hydra config hashes,
git commits, run IDs, file paths, etc.
"""

import logging
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


class RelationshipResolver:
    """Resolves cross-entity relationships from entity properties."""

    def resolve(self, entities: list[Entity]) -> list[Relationship]:
        """Examine all entities and create edges based on shared properties.

        This runs AFTER all scanners have produced entities and their
        scanner-local relationships. It adds cross-scanner connections.
        """
        relationships = []

        # Build lookup indexes
        by_id = {e.id: e for e in entities}
        by_type = {}
        for e in entities:
            by_type.setdefault(e.type, []).append(e)

        # 1. Run -> Data (via DVC hash)
        relationships += self._resolve_run_data(by_type)

        # 2. Run -> Config (via Hydra hash)
        relationships += self._resolve_run_config(by_type)

        # 3. Run -> Code (via git commit)
        relationships += self._resolve_run_code(by_type)

        # 4. DAG Run -> MLflow Run (via conf.mlflow_run_id or tags)
        relationships += self._resolve_dagrun_mlrun(by_type)

        # 5. Notebook -> Environment (via venv name in properties)
        relationships += self._resolve_notebook_env(by_type)

        # 6. Project -> Experiment (via naming convention)
        relationships += self._resolve_project_experiment(by_type)

        # 7. Project -> Config (via project_id in properties)
        relationships += self._resolve_project_config(by_type)

        # 8. Project -> Data File (via project_id in properties)
        relationships += self._resolve_project_data(by_type)

        # 9. DAG -> File (defined_in, via fileloc matching)
        relationships += self._resolve_dag_file(by_type)

        return relationships

    def _resolve_run_data(self, by_type: dict) -> list[Relationship]:
        """Link runs to data files via DVC hash."""
        rels = []
        runs = by_type.get('run', [])
        data_versions = by_type.get('data_version', [])
        data_files = by_type.get('data_file', [])

        # Build hash -> data entity lookup
        hash_to_data = {}
        for dv in data_versions:
            h = dv.properties.get('md5', '')
            if h:
                hash_to_data[h] = dv.id
        for df in data_files:
            h = df.properties.get('current_hash', '')
            if h:
                hash_to_data[h] = df.id

        for run in runs:
            dvc_hash = run.properties.get('dvc_data_hash', '')
            if dvc_hash and dvc_hash in hash_to_data:
                rels.append(Relationship(
                    source=run.id,
                    target=hash_to_data[dvc_hash],
                    type='uses_data',
                    properties={'hash': dvc_hash},
                ))

        return rels

    def _resolve_run_config(self, by_type: dict) -> list[Relationship]:
        """Link runs to configs via Hydra hash."""
        rels = []
        runs = by_type.get('run', [])
        configs = by_type.get('config', [])

        hash_to_config = {}
        for cfg in configs:
            h = cfg.properties.get('hash', '')
            if h:
                hash_to_config[h] = cfg.id

        for run in runs:
            config_hash = run.properties.get('hydra_config_hash', '')
            if config_hash and config_hash in hash_to_config:
                rels.append(Relationship(
                    source=run.id,
                    target=hash_to_config[config_hash],
                    type='uses_config',
                    properties={'hash': config_hash},
                ))

        return rels

    def _resolve_run_code(self, by_type: dict) -> list[Relationship]:
        """Link snapshots to their git commit."""
        rels = []
        snapshots = by_type.get('snapshot', [])

        for snap in snapshots:
            commit = snap.properties.get('git_commit', '')
            if commit:
                rels.append(Relationship(
                    source=snap.id,
                    target=f"git_commit:{commit[:7]}",
                    type='code_at',
                    properties={'commit': commit},
                ))

        return rels

    def _resolve_dagrun_mlrun(self, by_type: dict) -> list[Relationship]:
        """Link DAG runs to MLflow runs via conf parameters."""
        rels = []
        dag_runs = by_type.get('dag_run', [])
        runs = by_type.get('run', [])

        run_ids = {r.properties.get('run_id', ''): r.id for r in runs if r.properties.get('run_id')}

        for dr in dag_runs:
            mlflow_run_id = dr.properties.get('mlflow_run_id', '')
            if mlflow_run_id and mlflow_run_id in run_ids:
                rels.append(Relationship(
                    source=run_ids[mlflow_run_id],
                    target=dr.id,
                    type='executed_by',
                ))

        return rels

    def _resolve_notebook_env(self, by_type: dict) -> list[Relationship]:
        """Link notebooks to their environments."""
        rels = []
        notebooks = by_type.get('notebook', [])
        envs = by_type.get('environment', [])

        env_names = {e.label: e.id for e in envs}

        for nb in notebooks:
            venv = nb.properties.get('venv', '')
            if venv and venv in env_names:
                rels.append(Relationship(
                    source=nb.id,
                    target=env_names[venv],
                    type='runs_in',
                ))

        return rels

    def _resolve_project_config(self, by_type: dict) -> list[Relationship]:
        """Link projects to their configs via project_id."""
        rels = []
        projects = by_type.get('project', [])
        configs = by_type.get('config', [])

        project_ids = {p.id: p for p in projects}
        for cfg in configs:
            pid = cfg.properties.get('project_id', '')
            project_id = f"project:{pid}"
            if project_id in project_ids:
                rels.append(Relationship(
                    source=project_id,
                    target=cfg.id,
                    type='contains',
                ))
        return rels

    def _resolve_project_data(self, by_type: dict) -> list[Relationship]:
        """Link projects to their data files via project_id."""
        rels = []
        projects = by_type.get('project', [])
        data_files = by_type.get('data_file', [])

        project_ids = {p.id: p for p in projects}
        for df in data_files:
            pid = df.properties.get('project_id', '')
            project_id = f"project:{pid}"
            if project_id in project_ids:
                rels.append(Relationship(
                    source=project_id,
                    target=df.id,
                    type='contains',
                ))
        return rels

    def _resolve_dag_file(self, by_type: dict) -> list[Relationship]:
        """Link DAGs to their source files."""
        rels = []
        dags = by_type.get('dag', [])
        files = by_type.get('file', [])

        # Build path -> file entity lookup
        file_by_path = {}
        for f in files:
            path = f.properties.get('path', '')
            if path:
                file_by_path[path] = f.id
                # Also match by filename only
                file_by_path[path.split('/')[-1]] = f.id

        for dag in dags:
            fileloc = dag.properties.get('fileloc', '')
            if fileloc:
                filename = fileloc.split('/')[-1]
                if filename in file_by_path:
                    rels.append(Relationship(
                        source=dag.id,
                        target=file_by_path[filename],
                        type='defined_in',
                    ))
        return rels

    def _resolve_project_experiment(self, by_type: dict) -> list[Relationship]:
        """Link projects to experiments via naming convention.

        MLflow experiments are named either as project names or __mount__:mount_name.
        """
        rels = []
        projects = by_type.get('project', [])
        experiments = by_type.get('experiment', [])

        project_names = {}
        for p in projects:
            project_names[p.label] = p.id
            # Also match __mount__:name
            if p.properties.get('is_mount'):
                project_names[f"__mount__:{p.label}"] = p.id

        for exp in experiments:
            exp_name = exp.label
            if exp_name in project_names:
                rels.append(Relationship(
                    source=project_names[exp_name],
                    target=exp.id,
                    type='contains',
                ))

        return rels

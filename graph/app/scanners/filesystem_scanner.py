"""Filesystem scanner - discovers projects, notebooks, DAG files, and other project files."""

import json
import logging
import os

from app.models import Entity, Relationship
from app.config import PROJECTS_DIR, MOUNTS_DIR

logger = logging.getLogger(__name__)

SKIP_DIRS = {'.git', '.dvc', '__pycache__', '.noted', 'node_modules', '.venvs', '.venv'}


class FilesystemScanner:
    """Scans project directories for files, notebooks, and DAGs."""

    def scan(self, project_id: str) -> tuple[list[Entity], list[Relationship]]:
        """Scan a project's filesystem for notable entities."""
        entities = []
        relationships = []

        project_path = self._resolve_path(project_id)
        if not project_path:
            return entities, relationships

        is_mount = project_id.startswith('__mount__:')

        # Project entity
        project_entity = Entity(
            id=f"project:{project_id}",
            type='project',
            label=project_id.replace('__mount__:', '') if is_mount else project_id,
            properties={
                'path': project_path,
                'is_mount': is_mount,
            },
        )
        entities.append(project_entity)

        # Walk project tree (limited depth to avoid huge scans)
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            depth = root.replace(project_path, '').count(os.sep)
            if depth > 4:
                dirs.clear()
                continue

            for f in files:
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, project_path)

                # Notebooks
                if f.endswith('.ipynb'):
                    nb_entity = self._scan_notebook(project_id, rel_path, file_path)
                    if nb_entity:
                        entities.append(nb_entity)
                        relationships.append(Relationship(
                            source=project_entity.id,
                            target=nb_entity.id,
                            type='contains',
                        ))

                # DAG files
                elif rel_path.startswith('dags/') and f.endswith('.py'):
                    dag_file_entity = Entity(
                        id=f"file:{project_id}:{rel_path}",
                        type='file',
                        label=f,
                        properties={
                            'path': rel_path,
                            'is_dag': True,
                            'project_id': project_id,
                        },
                    )
                    entities.append(dag_file_entity)
                    relationships.append(Relationship(
                        source=project_entity.id,
                        target=dag_file_entity.id,
                        type='contains',
                    ))

                # Python source files (not in dags/)
                elif f.endswith('.py') and not rel_path.startswith('dags/'):
                    py_entity = Entity(
                        id=f"file:{project_id}:{rel_path}",
                        type='file',
                        label=f,
                        properties={
                            'path': rel_path,
                            'project_id': project_id,
                        },
                    )
                    entities.append(py_entity)
                    relationships.append(Relationship(
                        source=project_entity.id,
                        target=py_entity.id,
                        type='contains',
                    ))

                # Config files (YAML in config/)
                elif rel_path.startswith(('config/', 'conf/', 'configs/')) and f.endswith(('.yaml', '.yml')):
                    # Handled by Hydra scanner - skip to avoid duplicates
                    pass

        return entities, relationships

    def scan_all_projects(self) -> tuple[list[Entity], list[Relationship]]:
        """Scan all projects and mounts."""
        all_entities = []
        all_relationships = []

        # Internal projects
        if os.path.isdir(PROJECTS_DIR):
            for name in os.listdir(PROJECTS_DIR):
                path = os.path.join(PROJECTS_DIR, name)
                if os.path.isdir(path) and not name.startswith('.'):
                    ents, rels = self.scan(name)
                    all_entities.extend(ents)
                    all_relationships.extend(rels)

        # Mounts
        if os.path.isdir(MOUNTS_DIR):
            for name in os.listdir(MOUNTS_DIR):
                path = os.path.join(MOUNTS_DIR, name)
                if os.path.isdir(path) and not name.startswith('.'):
                    ents, rels = self.scan(f'__mount__:{name}')
                    all_entities.extend(ents)
                    all_relationships.extend(rels)

        return all_entities, all_relationships

    def _resolve_path(self, project_id: str) -> str | None:
        if project_id.startswith('__mount__:'):
            name = project_id[len('__mount__:'):]
            path = os.path.join(MOUNTS_DIR, name)
        else:
            path = os.path.join(PROJECTS_DIR, project_id)
        return os.path.realpath(path) if os.path.isdir(path) else None

    def _scan_notebook(self, project_id: str, rel_path: str, file_path: str) -> Entity | None:
        """Extract notebook metadata."""
        try:
            with open(file_path) as f:
                nb = json.load(f)
            cell_count = len(nb.get('cells', []))
            kernel = nb.get('metadata', {}).get('kernelspec', {}).get('display_name', '')
            venv = nb.get('metadata', {}).get('noted', {}).get('venv', '')
            return Entity(
                id=f"notebook:{project_id}:{rel_path}",
                type='notebook',
                label=os.path.basename(rel_path),
                properties={
                    'path': rel_path,
                    'cell_count': cell_count,
                    'kernel': kernel,
                    'venv': venv,
                    'project_id': project_id,
                },
            )
        except Exception:
            return None

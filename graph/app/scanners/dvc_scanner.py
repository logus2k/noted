"""DVC scanner - discovers tracked data files and their versions."""

import logging
import os
import subprocess

import yaml

from app.models import Entity, Relationship
from app.config import PROJECTS_DIR, MOUNTS_DIR

logger = logging.getLogger(__name__)


class DvcScanner:
    """Scans project directories for DVC-tracked files."""

    def scan(self, project_id: str) -> tuple[list[Entity], list[Relationship]]:
        """Scan a project for DVC-tracked data files and versions."""
        entities = []
        relationships = []

        project_path = self._resolve_path(project_id)
        if not project_path or not os.path.isdir(project_path):
            return entities, relationships

        # Find all .dvc files
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ('.git', '.dvc', '__pycache__', '.noted', 'node_modules', '.venvs')]
            for f in files:
                if not f.endswith('.dvc'):
                    continue
                dvc_path = os.path.join(root, f)
                rel_path = os.path.relpath(dvc_path, project_path)
                data_name = f[:-4]  # Strip .dvc

                # Parse .dvc file for current hash and size
                try:
                    with open(dvc_path) as fh:
                        doc = yaml.safe_load(fh) or {}
                    outs = doc.get('outs', [])
                    if not outs:
                        continue
                    md5 = outs[0].get('md5', '')
                    size = outs[0].get('size', 0)
                    data_path = outs[0].get('path', data_name)
                except Exception:
                    continue

                # Data file entity
                file_entity = Entity(
                    id=f"data_file:{project_id}:{rel_path}",
                    type='data_file',
                    label=data_name,
                    properties={
                        'dvc_file': rel_path,
                        'data_path': data_path,
                        'current_hash': md5,
                        'size': size,
                        'project_id': project_id,
                    },
                )
                entities.append(file_entity)

                # Current version entity
                version_entity = Entity(
                    id=f"data_version:{md5}",
                    type='data_version',
                    label=f"{data_name} ({md5[:8]})",
                    properties={
                        'md5': md5,
                        'size': size,
                        'data_path': data_path,
                    },
                )
                entities.append(version_entity)
                relationships.append(Relationship(
                    source=version_entity.id,
                    target=file_entity.id,
                    type='version_of',
                ))

                # Historical versions from git log
                history = self._get_file_history(project_path, rel_path)
                for h in history:
                    if h['md5'] == md5:
                        continue  # Skip current
                    hist_entity = Entity(
                        id=f"data_version:{h['md5']}",
                        type='data_version',
                        label=f"{data_name} ({h['md5'][:8]})",
                        properties={
                            'md5': h['md5'],
                            'size': h.get('size', 0),
                            'commit': h.get('commit', ''),
                            'date': h.get('date', ''),
                            'message': h.get('message', ''),
                        },
                    )
                    entities.append(hist_entity)
                    relationships.append(Relationship(
                        source=hist_entity.id,
                        target=file_entity.id,
                        type='version_of',
                    ))

        return entities, relationships

    def _resolve_path(self, project_id: str) -> str | None:
        """Resolve project ID to filesystem path."""
        if project_id.startswith('__mount__:'):
            name = project_id[len('__mount__:'):]
            path = os.path.join(MOUNTS_DIR, name)
        else:
            path = os.path.join(PROJECTS_DIR, project_id)
        return os.path.realpath(path) if os.path.isdir(path) else None

    def _get_file_history(self, project_path: str, dvc_file: str) -> list[dict]:
        """Get version history for a .dvc file from git log."""
        try:
            result = subprocess.run(
                ['git', 'log', '--pretty=format:%H|%ai|%s', '--follow', '--', dvc_file],
                cwd=project_path, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            versions = []
            for line in result.stdout.strip().split('\n'):
                if not line or '|' not in line:
                    continue
                parts = line.split('|', 2)
                commit = parts[0].strip()
                date = parts[1].strip() if len(parts) > 1 else ''
                message = parts[2].strip() if len(parts) > 2 else ''

                # Read .dvc content at that commit
                show_result = subprocess.run(
                    ['git', 'show', f'{commit}:{dvc_file}'],
                    cwd=project_path, capture_output=True, text=True, timeout=5,
                )
                if show_result.returncode != 0:
                    continue
                try:
                    doc = yaml.safe_load(show_result.stdout) or {}
                    outs = doc.get('outs', [])
                    if outs:
                        versions.append({
                            'md5': outs[0].get('md5', ''),
                            'size': outs[0].get('size', 0),
                            'commit': commit,
                            'date': date,
                            'message': message,
                        })
                except Exception:
                    pass

            return versions
        except Exception:
            return []

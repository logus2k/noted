"""Hydra scanner - discovers config directories, groups, and options."""

import hashlib
import logging
import os

import yaml

from app.models import Entity, Relationship
from app.config import PROJECTS_DIR, MOUNTS_DIR

logger = logging.getLogger(__name__)

CONFIG_DIR_NAMES = ['config', 'conf', 'configs']


class HydraScanner:
    """Scans project directories for Hydra configuration files."""

    def scan(self, project_id: str) -> tuple[list[Entity], list[Relationship]]:
        """Scan a project for Hydra configs."""
        entities = []
        relationships = []

        project_path = self._resolve_path(project_id)
        if not project_path:
            return entities, relationships

        config_dir = self._find_config_dir(project_path)
        if not config_dir:
            return entities, relationships

        config_dir_name = os.path.basename(config_dir)

        # Main config entity
        main_config = self._load_main_config(config_dir)
        config_hash = ''
        if main_config:
            config_yaml = yaml.dump(main_config, default_flow_style=False, sort_keys=False)
            config_hash = f"sha256:{hashlib.sha256(config_yaml.encode()).hexdigest()}"

        config_entity = Entity(
            id=f"config:{project_id}:{config_dir_name}",
            type='config',
            label=f"{project_id} config",
            properties={
                'config_dir': config_dir_name,
                'hash': config_hash,
                'project_id': project_id,
            },
        )
        entities.append(config_entity)

        # Config groups
        for entry in sorted(os.listdir(config_dir)):
            group_path = os.path.join(config_dir, entry)
            if not os.path.isdir(group_path) or entry.startswith('.') or entry == '__pycache__':
                continue

            options = []
            for f in sorted(os.listdir(group_path)):
                if f.endswith(('.yaml', '.yml')) and not f.startswith('.'):
                    options.append(f.rsplit('.', 1)[0])

            if not options:
                continue

            # Get default from main config
            default = self._get_group_default(config_dir, entry)

            group_entity = Entity(
                id=f"config_group:{project_id}:{entry}",
                type='config_group',
                label=entry,
                properties={
                    'options': options,
                    'default': default,
                    'option_count': len(options),
                    'project_id': project_id,
                },
            )
            entities.append(group_entity)
            relationships.append(Relationship(
                source=config_entity.id,
                target=group_entity.id,
                type='contains',
            ))

            # Config options
            for opt in options:
                opt_entity = Entity(
                    id=f"config_option:{project_id}:{entry}:{opt}",
                    type='config_option',
                    label=f"{entry}/{opt}",
                    properties={
                        'group': entry,
                        'is_default': opt == default,
                        'project_id': project_id,
                    },
                )
                entities.append(opt_entity)
                relationships.append(Relationship(
                    source=group_entity.id,
                    target=opt_entity.id,
                    type='contains',
                ))

        return entities, relationships

    def _resolve_path(self, project_id: str) -> str | None:
        if project_id.startswith('__mount__:'):
            name = project_id[len('__mount__:'):]
            path = os.path.join(MOUNTS_DIR, name)
        else:
            path = os.path.join(PROJECTS_DIR, project_id)
        return os.path.realpath(path) if os.path.isdir(path) else None

    def _find_config_dir(self, project_path: str) -> str | None:
        for name in CONFIG_DIR_NAMES:
            path = os.path.join(project_path, name)
            if os.path.isdir(path):
                return path
        return None

    def _load_main_config(self, config_dir: str) -> dict | None:
        for name in ['config.yaml', 'config.yml', 'default.yaml', 'default.yml']:
            path = os.path.join(config_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        return yaml.safe_load(f) or {}
                except Exception:
                    pass
        return None

    def _get_group_default(self, config_dir: str, group: str) -> str | None:
        for name in ['config.yaml', 'config.yml', 'default.yaml', 'default.yml']:
            path = os.path.join(config_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        doc = yaml.safe_load(f) or {}
                    for item in doc.get('defaults', []):
                        if isinstance(item, dict) and group in item:
                            return item[group]
                except Exception:
                    pass
        return None

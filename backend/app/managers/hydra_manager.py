"""Hydra configuration manager.

Discovers config structure, parses YAML groups, composes resolved configs.
Supports both flat configs (single config.yaml) and Hydra config groups
(model/gru.yaml, model/lstm.yaml, etc.).
"""

import os
import json
import hashlib
import logging

import yaml

from app.managers.project_registry import get_registry

logger = logging.getLogger(__name__)

# Common config directory names (checked in order)
CONFIG_DIR_NAMES = ['config', 'conf', 'configs']


class HydraManager:
    """Hydra config operations for projects and mounts."""

    def _resolve_project_path(self, project_id: str) -> str:
        """Resolve project ID to filesystem path."""
        return get_registry().resolve(project_id)

    def _find_config_dir(self, project_path: str) -> str | None:
        """Find the Hydra config directory in a project."""
        for name in CONFIG_DIR_NAMES:
            config_dir = os.path.join(project_path, name)
            if os.path.isdir(config_dir):
                return config_dir
        return None

    # ── Bundle assembly (per Hydra unification plan M2.1) ────────

    def assemble_bundle_files(
        self,
        project_id: str,
        group_selections: dict | None = None,
        overrides: dict | None = None,
    ) -> dict[str, bytes]:
        """Backward-compatible bundle assembly from a project's local config/.

        New callers should prefer assemble_bundle_from_source().
        """
        from app.managers.hydra_source import LocalSource
        return self.assemble_bundle_from_source(
            LocalSource(project_id=project_id),
            group_selections=group_selections,
            overrides=overrides,
        )

    def assemble_bundle_from_source(
        self,
        source,
        group_selections: dict | None = None,
        overrides: dict | None = None,
    ) -> dict[str, bytes]:
        """Return a dict of relative-path -> file-content bytes for the full
        Hydra bundle that should be logged for a run:

          - Every YAML file under the source's config directory (preserving
            directory structure)
          - selections.json  - the group_selections + overrides used
          - resolved.yaml    - the composed output

        Used by both the per-run auto-instrumentation code path and the
        snapshot code path so there is a single implementation of bundle
        assembly. The dict can then be written to a temp directory and
        passed to MLflow's log_artifacts().

        Per D5, this always re-reads the baseline files from `source` so
        every run is self-contained regardless of whether the baseline was
        local or previously archived.
        """
        if not source.exists():
            raise FileNotFoundError(
                f"No Hydra config directory found: {source.describe()}"
            )

        bundle: dict[str, bytes] = {}
        config_top = source.config_top_name

        # 1. Copy every file under the source's config directory
        for rel_dir, _dirnames, filenames in source.walk():
            for fname in filenames:
                rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
                content = source.read_text(rel_path)
                if content is None:
                    continue
                bundle[f"{config_top}/{rel_path}"] = content.encode('utf-8')

        # 2. selections.json - what was actually used
        selections_doc = {
            'group_selections': group_selections or {},
            'overrides': overrides or {},
        }
        bundle['selections.json'] = json.dumps(
            selections_doc, indent=2, sort_keys=True
        ).encode('utf-8')

        # 3. resolved.yaml - the composed output
        try:
            result = self.compose_from_source(
                source,
                overrides=overrides or None,
                group_selections=group_selections or None,
            )
            resolved_yaml = result.get('yaml', '')
            bundle['resolved.yaml'] = resolved_yaml.encode('utf-8')
        except Exception as e:
            logger.warning(
                "Hydra bundle resolved.yaml composition failed: %s", e
            )
            bundle['resolved.yaml'] = b''

        return bundle

    def write_bundle_to_dir(
        self,
        bundle: dict[str, bytes],
        target_dir: str,
    ) -> None:
        """Write a bundle dict (from assemble_bundle_files) to a target
        directory, creating subdirectories as needed. Used before calling
        mlflow.log_artifacts(target_dir, 'hydra').
        """
        for rel_path, content in bundle.items():
            full = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(full) or target_dir, exist_ok=True)
            with open(full, 'wb') as f:
                f.write(content)

    def get_schema(self, project_id: str) -> dict:
        """Return the config structure for a project's local config/ folder.

        Backward-compatible wrapper around get_schema_from_source() using a
        LocalSource. New callers should prefer get_schema_from_source().
        """
        from app.managers.hydra_source import LocalSource
        return self.get_schema_from_source(LocalSource(project_id=project_id))

    def get_schema_from_source(self, source) -> dict:
        """Return the config structure for an arbitrary HydraSource.

        Returns:
            {
                "config_dir": "config",
                "has_config": true,
                "config_name": "config",
                "groups": {
                    "model": {
                        "options": ["gru", "lstm", "linear"],
                        "default": "gru"
                    }
                },
                "flat_config": { ... },  # If no groups, the raw parsed YAML
                "schema": [
                    {"key": "data.file", "type": "str", "default": "data/file.csv"},
                    {"key": "data.split.train", "type": "float", "default": 0.7},
                    ...
                ]
            }
        """
        if not source.exists():
            return {
                'config_dir': None,
                'has_config': False,
                'config_name': None,
                'groups': {},
                'flat_config': None,
                'schema': [],
            }

        config_dir_name = source.config_top_name

        # Find the main config file by walking the source's top directory
        config_name = None
        top_dirnames = []
        top_filenames = []
        for rel_dir, dirnames, filenames in source.walk():
            if rel_dir == '':
                top_dirnames = sorted(dirnames)
                top_filenames = sorted(filenames)
                break

        for candidate in ['config.yaml', 'config.yml', 'default.yaml', 'default.yml']:
            if candidate in top_filenames:
                config_name = candidate.rsplit('.', 1)[0]
                break

        # Discover config groups (direct subdirectories with YAML files)
        groups = {}
        for entry in top_dirnames:
            if entry.startswith('.') or entry == '__pycache__':
                continue
            # List files in this group directory
            group_files = []
            for rel_dir, _dn, fn in source.walk():
                if rel_dir == entry:
                    group_files = sorted(fn)
                    break
            options = []
            for f in group_files:
                if f.endswith(('.yaml', '.yml')) and not f.startswith('.'):
                    options.append(f.rsplit('.', 1)[0])
            if options:
                default = self._get_group_default_from_source(source, config_name, entry)
                groups[entry] = {
                    'options': options,
                    'default': default,
                }

        # Parse the main config
        flat_config = None
        schema = []
        if config_name:
            for ext in ('.yaml', '.yml'):
                content = source.read_text(f'{config_name}{ext}')
                if content is not None:
                    try:
                        flat_config = yaml.safe_load(content) or {}
                        schema = self._extract_schema(flat_config)
                    except Exception as e:
                        logger.warning(
                            "Failed to parse config %s from %s: %s",
                            f'{config_name}{ext}', source.describe(), e,
                        )
                    break

        return {
            'config_dir': config_dir_name,
            'has_config': True,
            'config_name': config_name,
            'groups': groups,
            'flat_config': flat_config,
            'schema': schema,
        }

    def _get_group_default_from_source(self, source, config_name, group):
        """Source-aware version of _get_group_default."""
        if not config_name:
            return None
        for ext in ('.yaml', '.yml'):
            content = source.read_text(f'{config_name}{ext}')
            if content is None:
                continue
            try:
                doc = yaml.safe_load(content) or {}
                defaults = doc.get('defaults', [])
                for item in defaults:
                    if isinstance(item, dict) and group in item:
                        return item[group]
            except Exception:
                pass
        return None

    def _get_group_default(self, config_dir: str, config_name: str | None, group: str) -> str | None:
        """Extract the default selection for a config group from the main config's defaults list."""
        if not config_name:
            return None
        for ext in ['.yaml', '.yml']:
            config_file = os.path.join(config_dir, config_name + ext)
            if os.path.exists(config_file):
                try:
                    with open(config_file) as f:
                        doc = yaml.safe_load(f) or {}
                    defaults = doc.get('defaults', [])
                    for item in defaults:
                        if isinstance(item, dict) and group in item:
                            return item[group]
                except Exception:
                    pass
        return None

    def _extract_schema(self, config: dict, prefix: str = '') -> list:
        """Flatten a config dict into a list of schema entries with dotted keys."""
        entries = []
        for key, value in config.items():
            if key == 'defaults':
                continue  # Skip Hydra defaults list
            full_key = f'{prefix}{key}' if not prefix else f'{prefix}.{key}'
            if isinstance(value, dict):
                entries.extend(self._extract_schema(value, full_key))
            elif isinstance(value, list):
                entries.append({
                    'key': full_key,
                    'type': 'list',
                    'default': value,
                })
            else:
                vtype = type(value).__name__ if value is not None else 'null'
                entries.append({
                    'key': full_key,
                    'type': vtype,
                    'default': value,
                })
        return entries

    def compose(self, project_id: str, overrides: dict | None = None,
                group_selections: dict | None = None) -> dict:
        """Compose a resolved Hydra config from the project's local config/.

        Backward-compatible wrapper. New callers should prefer
        compose_from_source().
        """
        from app.managers.hydra_source import LocalSource
        return self.compose_from_source(
            LocalSource(project_id=project_id),
            overrides=overrides,
            group_selections=group_selections,
        )

    def compose_from_source(
        self,
        source,
        overrides: dict | None = None,
        group_selections: dict | None = None,
    ) -> dict:
        """Compose a resolved Hydra config from an arbitrary HydraSource.

        Args:
            source: HydraSource (LocalSource or MlflowSource)
            overrides: Dotted-key overrides
            group_selections: Config group selections

        Returns:
            {
                "resolved": { ... },
                "yaml": "...",
                "hash": "sha256:...",
                "sources": { ... },
            }
        """
        if not source.exists():
            raise FileNotFoundError(
                f"No config directory found in source: {source.describe()}"
            )

        # Find main config by looking at the top-level files
        top_filenames = []
        for rel_dir, _dn, filenames in source.walk():
            if rel_dir == '':
                top_filenames = filenames
                break

        config_file_name = None
        for candidate in ['config.yaml', 'config.yml', 'default.yaml', 'default.yml']:
            if candidate in top_filenames:
                config_file_name = candidate
                break

        if not config_file_name:
            raise FileNotFoundError(
                f"No main config file found in source: {source.describe()}"
            )

        base_text = source.read_text(config_file_name)
        if base_text is None:
            raise FileNotFoundError(
                f"Could not read main config file {config_file_name} from source: "
                f"{source.describe()}"
            )
        resolved = yaml.safe_load(base_text) or {}

        # Remove defaults key (Hydra internal)
        raw = dict(resolved)  # save for defaults list extraction
        resolved.pop('defaults', None)

        # Track key sources (which file defined each top-level key)
        sources = {k: config_file_name for k in resolved}

        # Collect defaults from the config file's defaults list
        defaults_list = []
        for entry in raw.get('defaults', []):
            if isinstance(entry, dict):
                for g, s in entry.items():
                    defaults_list.append((g, s))

        # Merge: explicit selections override defaults
        effective_selections = {g: s for g, s in defaults_list}
        if group_selections:
            effective_selections.update(group_selections)

        if effective_selections:
            for group, selection in effective_selections.items():
                group_content = None
                group_rel = None
                for ext in ['.yaml', '.yml']:
                    candidate = f'{group}/{selection}{ext}'
                    text = source.read_text(candidate)
                    if text is not None:
                        group_content = text
                        group_rel = candidate
                        break
                if group_content is not None:
                    group_config = yaml.safe_load(group_content) or {}
                    self._deep_merge(resolved, {group: group_config})
                    sources[group] = group_rel

        # Apply dotted-key overrides
        if overrides:
            for dotted_key, value in overrides.items():
                self._set_nested(resolved, dotted_key, value)
                top_key = dotted_key.split('.')[0]
                sources[top_key] = 'override'

        # Generate YAML and hash
        resolved_yaml = yaml.dump(resolved, default_flow_style=False, sort_keys=False)
        config_hash = hashlib.sha256(resolved_yaml.encode()).hexdigest()

        return {
            'resolved': resolved,
            'yaml': resolved_yaml,
            'hash': f'sha256:{config_hash}',
            'sources': sources,
        }

    def get_group_config(self, project_id: str, group: str, option: str) -> dict:
        """Return the content of a specific config group option file."""
        project_path = self._resolve_project_path(project_id)
        config_dir = self._find_config_dir(project_path)
        if not config_dir:
            raise FileNotFoundError("No config directory found")

        for ext in ['.yaml', '.yml']:
            path = os.path.join(config_dir, group, option + ext)
            if os.path.isfile(path):
                with open(path) as f:
                    content = yaml.safe_load(f) or {}
                with open(path) as f:
                    raw = f.read()
                return {'config': content, 'yaml': raw}

        raise FileNotFoundError(f"Config option not found: {group}/{option}")

    @staticmethod
    def _deep_merge(base: dict, override: dict):
        """Recursively merge override into base (mutates base)."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                HydraManager._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _set_nested(d: dict, dotted_key: str, value):
        """Set a value in a nested dict using a dotted key path."""
        keys = dotted_key.split('.')
        for key in keys[:-1]:
            if key not in d or not isinstance(d[key], dict):
                d[key] = {}
            d = d[key]
        # Try to preserve type (parse numbers, booleans)
        d[keys[-1]] = HydraManager._coerce_value(value)

    # ── Config Templates ──────────────────────────────────────────

    def _templates_dir(self, project_id: str) -> str:
        """Return the templates directory for a project, creating it if needed."""
        project_path = self._resolve_project_path(project_id)
        tpl_dir = os.path.join(project_path, '.noted', 'config_templates')
        os.makedirs(tpl_dir, exist_ok=True)
        return tpl_dir

    def list_templates(self, project_id: str) -> list[dict]:
        """List all saved config templates for a project."""
        tpl_dir = self._templates_dir(project_id)
        templates = []
        for f in sorted(os.listdir(tpl_dir)):
            if not f.endswith('.yaml'):
                continue
            path = os.path.join(tpl_dir, f)
            try:
                with open(path) as fh:
                    data = yaml.safe_load(fh) or {}
                templates.append({
                    'name': f[:-5],  # strip .yaml
                    'description': data.get('description', ''),
                    'group_selections': data.get('group_selections', {}),
                    'overrides': data.get('overrides', {}),
                })
            except Exception as e:
                logger.warning("Failed to parse template %s: %s", f, e)
        return templates

    def save_template(self, project_id: str, name: str, description: str = '',
                      group_selections: dict | None = None,
                      overrides: dict | None = None) -> dict:
        """Save a config template."""
        if not name or not name.strip():
            raise ValueError("Template name is required")
        safe_name = name.strip().replace(' ', '_').replace('/', '_')
        tpl_dir = self._templates_dir(project_id)
        path = os.path.join(tpl_dir, f'{safe_name}.yaml')

        data = {
            'name': name.strip(),
            'description': description.strip(),
            'group_selections': group_selections or {},
            'overrides': overrides or {},
        }
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return {'name': safe_name, 'saved': True}

    def delete_template(self, project_id: str, name: str) -> dict:
        """Delete a config template."""
        tpl_dir = self._templates_dir(project_id)
        path = os.path.join(tpl_dir, f'{name}.yaml')
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Template not found: {name}")
        os.remove(path)
        return {'name': name, 'deleted': True}

    def get_template(self, project_id: str, name: str) -> dict:
        """Load a specific config template."""
        tpl_dir = self._templates_dir(project_id)
        path = os.path.join(tpl_dir, f'{name}.yaml')
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Template not found: {name}")
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data

    # ── Hydra View Setting ────────────────────────────────────────

    def _settings_path(self, project_id: str) -> str:
        """Return the .noted/settings.json path for a project."""
        project_path = self._resolve_project_path(project_id)
        return os.path.join(project_path, '.noted', 'settings.json')

    def _read_settings(self, project_id: str) -> dict:
        path = self._settings_path(project_id)
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_settings(self, project_id: str, settings: dict):
        path = self._settings_path(project_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(settings, f, indent=2)

    def get_hydra_view(self, project_id: str) -> dict:
        """Get whether Hydra view is enabled for this project."""
        settings = self._read_settings(project_id)
        return {'enabled': settings.get('hydra_view', False)}

    def set_hydra_view(self, project_id: str, enabled: bool) -> dict:
        """Enable or disable Hydra view for this project."""
        settings = self._read_settings(project_id)
        settings['hydra_view'] = enabled
        self._write_settings(project_id, settings)
        return {'enabled': enabled}

    @staticmethod
    def _coerce_value(value):
        """Attempt to coerce string values to their natural types."""
        if not isinstance(value, str):
            return value
        # Boolean
        if value.lower() in ('true', 'yes'):
            return True
        if value.lower() in ('false', 'no'):
            return False
        # Null
        if value.lower() in ('null', 'none', '~'):
            return None
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        return value

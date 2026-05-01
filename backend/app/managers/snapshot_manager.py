"""Snapshot Manager - immutable reproducible experiment records.

A Snapshot captures the entire state that produced a result:
- Git commit SHA (code, notebooks, DAGs, configs)
- DVC file hashes (data versions)
- Resolved Hydra config hash + YAML
- MLflow run (metrics, params, model artifacts)
- Python environment (pip freeze)

Convention: one Snapshot per Experiment. The best Run is marked as the Snapshot.
"""

import json
import logging
import os
import subprocess
import tempfile

from app.managers.project_registry import get_registry

logger = logging.getLogger(__name__)


class SnapshotManager:
    """Orchestrates snapshot creation, restoration, and forking."""

    def __init__(self, git_manager, dvc_manager, mlflow_manager, hydra_manager):
        self._git = git_manager
        self._dvc = dvc_manager
        self._mlflow = mlflow_manager
        self._hydra = hydra_manager

    def _resolve_project_path(self, project_id: str) -> str:
        """Resolve project ID to filesystem path."""
        return get_registry().resolve(project_id)
        return real

    # ── Create Snapshot ──────────────────────────────────────────

    def check_git_state(self, project_id: str) -> dict:
        """Check git state before snapshot creation.

        Returns categorized file lists for the UI to display.
        """
        git_status = self._git.status(project_id)
        files = git_status.get('files', [])

        modified = [f for f in files if f.get('label') in ('modified', 'added', 'deleted', 'renamed', 'changed')]
        untracked = [f for f in files if f.get('label') == 'untracked']

        return {
            'clean': len(modified) == 0,
            'modified': [f.get('path', '') for f in modified],
            'untracked': [f.get('path', '') for f in untracked],
            'branch': git_status.get('branch', 'main'),
        }

    def create_snapshot(self, project_id: str, experiment_id: str, run_id: str,
                        name: str, description: str = '',
                        auto_commit: bool = False,
                        kernel_venv_path: str | None = None) -> dict:
        """Create an immutable snapshot of the best run in an experiment.

        Args:
            project_id: Project or mount ID
            experiment_id: MLflow experiment ID
            run_id: MLflow run ID to snapshot
            name: Human-readable snapshot name
            description: Optional description
            auto_commit: If True, auto-commit modified files before snapshot
            kernel_venv_path: Optional path to venv for pip freeze

        Returns:
            {"snapshot_branch": str, "version": int, "git_commit": str, ...}
        """
        if not name or not name.strip():
            raise ValueError("Snapshot name is required")

        project_path = self._resolve_project_path(project_id)
        name = name.strip()

        # 1. Validate run exists and is finished
        run = self._mlflow.get_run(run_id)
        if not run:
            raise FileNotFoundError(f"Run not found: {run_id}")
        if run.get('status') != 'FINISHED':
            raise ValueError(f"Run is not finished (status: {run.get('status')}). Only finished runs can be snapshotted.")
        if run.get('experiment_id') != experiment_id:
            raise ValueError(f"Run {run_id} does not belong to experiment {experiment_id}")

        # 2. Check git state
        git_state = self.check_git_state(project_id)
        original_branch = git_state.get('branch', 'main')

        # 3. Handle modified files
        if git_state['modified']:
            if auto_commit:
                logger.info("Auto-committing %d modified files for snapshot", len(git_state['modified']))
                self._git.commit(project_id, f"[noted] snapshot: {name}")
            else:
                raise ValueError(
                    f"Cannot create snapshot with {len(git_state['modified'])} uncommitted modified file(s). "
                    "Please commit your changes first or enable auto-commit."
                )

        # 4. Get commit SHA after potential auto-commit
        git_status = self._git.status(project_id)
        commit_sha = self._get_head_commit(project_path)

        # 5. Collect DVC hashes
        dvc_hashes = self._collect_dvc_hashes(project_path)

        # 6. Compose Hydra config (optional)
        hydra_hash = None
        hydra_yaml = None
        try:
            result = self._hydra.compose(project_id)
            hydra_hash = result.get('hash', '')
            hydra_yaml = result.get('yaml', '')
        except Exception:
            logger.debug("No Hydra config found for %s (optional)", project_id)

        # 7. Pip freeze (optional)
        requirements = None
        if kernel_venv_path:
            requirements = self._pip_freeze(kernel_venv_path)

        # 8. Determine snapshot version
        experiment = self._get_experiment_name(experiment_id)
        version = self._next_snapshot_version(project_path, experiment)
        safe_experiment = experiment.replace(':', '_').replace('/', '_').replace(' ', '_')
        branch_name = f"snapshot/{safe_experiment}_{version:03d}"

        # 9. Create snapshot branch (then return to original)
        try:
            self._git.create_branch(project_id, branch_name)
        except RuntimeError as e:
            if 'already exists' in str(e):
                version = self._next_snapshot_version(project_path, experiment, force_increment=True)
                branch_name = f"snapshot/{safe_experiment}_{version:03d}"
                self._git.create_branch(project_id, branch_name)
            else:
                raise

        try:
            # 10. Tag MLflow run
            self._remove_previous_snapshot(experiment_id)
            self._mlflow.set_tag(run_id, 'noted.snapshot', 'true')
            self._mlflow.set_tag(run_id, 'noted.snapshot_name', name)
            self._mlflow.set_tag(run_id, 'noted.snapshot_description', description)
            self._mlflow.set_tag(run_id, 'noted.snapshot_branch', branch_name)
            self._mlflow.set_tag(run_id, 'noted.snapshot_version', str(version))
            self._mlflow.set_tag(run_id, 'noted.git_commit', commit_sha)
            self._mlflow.set_tag(run_id, 'noted.project_id', project_id)
            if dvc_hashes:
                self._mlflow.set_tag(run_id, 'noted.dvc_hashes', json.dumps(dvc_hashes))
            if hydra_hash:
                self._mlflow.set_tag(run_id, 'noted.hydra_config_hash', hydra_hash)

            # 11. Log artifacts
            with tempfile.TemporaryDirectory() as tmpdir:
                if hydra_yaml:
                    config_path = os.path.join(tmpdir, 'hydra_resolved_config.yaml')
                    with open(config_path, 'w') as f:
                        f.write(hydra_yaml)
                    self._mlflow.log_artifact(run_id, config_path, 'snapshot')

                if requirements:
                    req_path = os.path.join(tmpdir, 'requirements.txt')
                    with open(req_path, 'w') as f:
                        f.write(requirements)
                    self._mlflow.log_artifact(run_id, req_path, 'snapshot')

            # 12. DVC push (ensure data in remote)
            try:
                self._dvc.push(project_path)
            except Exception as e:
                logger.warning("DVC push failed during snapshot (data may not be in remote): %s", e)

        except Exception:
            # Cleanup: return to original branch, delete snapshot branch on failure
            try:
                self._git.checkout(project_id, original_branch)
                self._delete_branch(project_path, branch_name)
            except Exception:
                pass
            raise

        # 13. Return to original branch
        self._git.checkout(project_id, original_branch)

        return {
            'snapshot_branch': branch_name,
            'version': version,
            'git_commit': commit_sha,
            'experiment_id': experiment_id,
            'experiment_name': experiment,
            'run_id': run_id,
            'name': name,
            'description': description,
            'dvc_hashes': dvc_hashes,
            'hydra_config_hash': hydra_hash,
            'has_requirements': requirements is not None,
        }

    # ── Restore Snapshot ─────────────────────────────────────────

    def restore_snapshot(self, project_id: str, experiment_id: str) -> dict:
        """Restore workspace to a snapshot state.

        Checks out the snapshot branch and runs dvc checkout to restore data files.
        """
        project_path = self._resolve_project_path(project_id)

        # Find snapshot run
        snapshot_run = self._find_snapshot_run(experiment_id)
        if not snapshot_run:
            raise FileNotFoundError(f"No snapshot found for experiment {experiment_id}")

        branch = snapshot_run.get('tags', {}).get('noted.snapshot_branch')
        if not branch:
            raise ValueError("Snapshot run is missing branch tag")

        # Stash dirty changes
        git_status = self._git.status(project_id)
        dirty = bool(git_status.get('files'))
        if dirty:
            self._run_git(project_path, ['git', 'stash', 'push', '-m', 'noted-snapshot-restore'])

        # Checkout snapshot branch
        try:
            self._git.checkout(project_id, branch)
        except Exception:
            # Restore stash if checkout fails
            if dirty:
                self._run_git(project_path, ['git', 'stash', 'pop'])
            raise

        # DVC checkout to restore data files
        try:
            self._dvc.pull(project_path)
        except Exception as e:
            logger.warning("DVC pull during restore: %s", e)

        try:
            self._run_git(project_path, ['dvc', 'checkout'], use_dvc_env=True)
        except Exception as e:
            logger.warning("DVC checkout during restore: %s", e)

        return {
            'restored': True,
            'branch': branch,
            'snapshot_name': snapshot_run.get('tags', {}).get('noted.snapshot_name', ''),
            'run_id': snapshot_run.get('run_id'),
            'stashed': dirty,
        }

    # ── Fork Experiment from Snapshot ────────────────────────────

    def fork_experiment(self, project_id: str, source_experiment_id: str,
                        new_experiment_name: str) -> dict:
        """Create a new experiment branching from a snapshot.

        1. Restores the source snapshot
        2. Creates a new git branch
        3. Creates a new MLflow experiment
        """
        if not new_experiment_name or not new_experiment_name.strip():
            raise ValueError("New experiment name is required")
        new_experiment_name = new_experiment_name.strip()

        # Restore the source snapshot
        restore_result = self.restore_snapshot(project_id, source_experiment_id)

        # Create new git branch from snapshot state
        safe_name = new_experiment_name.replace(' ', '_').replace('/', '_')
        branch_name = f"experiment/{safe_name}"
        try:
            self._git.create_branch(project_id, branch_name)
        except RuntimeError:
            # Branch might already exist - just checkout
            self._git.checkout(project_id, branch_name)

        # Create new MLflow experiment
        new_experiment_id = self._mlflow.create_experiment(new_experiment_name)

        return {
            'forked': True,
            'source_experiment_id': source_experiment_id,
            'new_experiment_id': new_experiment_id,
            'new_experiment_name': new_experiment_name,
            'branch': branch_name,
            'restored_from': restore_result.get('branch'),
        }

    # ── List Snapshots ───────────────────────────────────────────

    def list_snapshots(self, project_id: str) -> list[dict]:
        """List all snapshots across all experiments for a project."""
        experiments = self._mlflow.list_experiments()
        snapshots = []

        for exp in experiments:
            exp_id = exp['experiment_id']
            try:
                runs = self._mlflow.search_runs(
                    experiment_ids=[exp_id],
                    filter_string="tags.`noted.snapshot` = 'true'",
                    max_results=10,
                )
                for run in runs:
                    tags = run.get('tags', {})
                    snapshots.append({
                        'experiment_id': exp_id,
                        'experiment_name': exp['name'],
                        'run_id': run['run_id'],
                        'run_name': run.get('run_name', ''),
                        'name': tags.get('noted.snapshot_name', ''),
                        'description': tags.get('noted.snapshot_description', ''),
                        'branch': tags.get('noted.snapshot_branch', ''),
                        'version': tags.get('noted.snapshot_version', ''),
                        'git_commit': tags.get('noted.git_commit', ''),
                        'metrics': run.get('metrics', {}),
                        'start_time': run.get('start_time'),
                    })
            except Exception as e:
                logger.debug("Error searching snapshots in experiment %s: %s", exp_id, e)

        return snapshots

    # ── Private Helpers ──────────────────────────────────────────

    def _get_head_commit(self, project_path: str) -> str:
        """Get the HEAD commit SHA."""
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=project_path, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def _collect_dvc_hashes(self, project_path: str) -> dict:
        """Scan all .dvc files and collect their md5 hashes."""
        import yaml
        hashes = {}
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ('.git', '.dvc', '__pycache__', '.noted', 'node_modules')]
            for f in files:
                if f.endswith('.dvc'):
                    dvc_path = os.path.join(root, f)
                    try:
                        with open(dvc_path) as fh:
                            doc = yaml.safe_load(fh) or {}
                        outs = doc.get('outs', [])
                        if outs and isinstance(outs, list):
                            rel_path = os.path.relpath(dvc_path, project_path)
                            hashes[rel_path] = {
                                'md5': outs[0].get('md5', ''),
                                'size': outs[0].get('size', 0),
                                'path': outs[0].get('path', ''),
                            }
                    except Exception:
                        pass
        return hashes

    def _pip_freeze(self, venv_path: str) -> str | None:
        """Run pip freeze in the given venv and return the output."""
        pip_path = os.path.join(venv_path, 'bin', 'pip')
        if not os.path.isfile(pip_path):
            return None
        try:
            result = subprocess.run(
                [pip_path, 'freeze'],
                capture_output=True, text=True, timeout=30,
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None

    def _get_experiment_name(self, experiment_id: str) -> str:
        """Get experiment name from MLflow."""
        experiments = self._mlflow.list_experiments()
        for exp in experiments:
            if exp['experiment_id'] == experiment_id:
                return exp['name']
        return f"experiment_{experiment_id}"

    def _next_snapshot_version(self, project_path: str, experiment_name: str,
                               force_increment: bool = False) -> int:
        """Determine the next sequential snapshot version for an experiment."""
        safe_name = experiment_name.replace(':', '_').replace('/', '_').replace(' ', '_')
        prefix = f"snapshot/{safe_name}_"

        result = subprocess.run(
            ['git', 'branch', '--list', f'{prefix}*'],
            cwd=project_path, capture_output=True, text=True,
        )
        versions = []
        for line in result.stdout.strip().split('\n'):
            branch = line.strip().lstrip('* ')
            if branch.startswith(prefix):
                suffix = branch[len(prefix):]
                try:
                    versions.append(int(suffix))
                except ValueError:
                    pass

        if not versions:
            return 1
        return max(versions) + 1

    def _remove_previous_snapshot(self, experiment_id: str):
        """Remove noted.snapshot=true tag from any existing snapshot in the experiment."""
        try:
            runs = self._mlflow.search_runs(
                experiment_ids=[experiment_id],
                filter_string="tags.`noted.snapshot` = 'true'",
                max_results=10,
            )
            for run in runs:
                self._mlflow.delete_tag(run['run_id'], 'noted.snapshot')
                logger.info("Removed previous snapshot tag from run %s", run['run_id'])
        except Exception as e:
            logger.warning("Failed to remove previous snapshot tags: %s", e)

    def _find_snapshot_run(self, experiment_id: str) -> dict | None:
        """Find the snapshot run in an experiment."""
        try:
            runs = self._mlflow.search_runs(
                experiment_ids=[experiment_id],
                filter_string="tags.`noted.snapshot` = 'true'",
                max_results=1,
            )
            return runs[0] if runs else None
        except Exception:
            return None

    def _delete_branch(self, project_path: str, branch: str):
        """Delete a git branch (cleanup on failure)."""
        subprocess.run(
            ['git', 'branch', '-D', branch],
            cwd=project_path, capture_output=True, text=True,
        )

    def _run_git(self, project_path: str, cmd: list[str], use_dvc_env: bool = False):
        """Run a git/dvc command in the project directory."""
        env = os.environ.copy()
        if use_dvc_env:
            env['AWS_ACCESS_KEY_ID'] = os.environ.get('DVC_MINIO_ACCESS_KEY', '')
            env['AWS_SECRET_ACCESS_KEY'] = os.environ.get('DVC_MINIO_SECRET_KEY', '')
        subprocess.run(cmd, cwd=project_path, capture_output=True, text=True, check=True, env=env)

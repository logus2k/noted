"""DVC (Data Version Control) integration manager.

Handles DVC init, tracking, push/pull, and status queries.
Uses MinIO as the built-in DVC remote (noted-dvc bucket).
"""

import os
import subprocess
import time
import yaml

from app.config import PROJECTS_DIR, MOUNTS_DIR
from app.managers.project_registry import get_registry

# Extensions considered DVC-trackable (data / model / media / archive files)
DVC_EXTENSIONS = {
    # Tabular / structured data
    '.csv', '.parquet', '.feather', '.arrow', '.tsv',
    # Binary / serialized
    '.h5', '.hdf5', '.pkl', '.pickle', '.joblib', '.npy', '.npz',
    # ML model formats
    '.pt', '.pth', '.onnx', '.safetensors', '.pb', '.tflite',
    '.model', '.bin', '.tfrecord',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif',
    '.svg',
    # Audio / Video
    '.mp4', '.avi', '.mov', '.mkv', '.wav', '.mp3', '.flac', '.ogg',
    # Archives
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    # Database
    '.db', '.sqlite', '.sqlite3',
}

# MinIO defaults (overridable via env vars)
MINIO_ENDPOINT = os.environ.get('DVC_MINIO_ENDPOINT', 'http://noted-minio:9000')
MINIO_ACCESS_KEY = os.environ.get('DVC_MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.environ.get('DVC_MINIO_SECRET_KEY', 'password')
MINIO_BUCKET = os.environ.get('DVC_MINIO_BUCKET', 'noted-dvc')


class DvcManager:
    """DVC operations using subprocess, matching GitManager patterns."""

    def __init__(self):
        self._status_cache = {}  # repo_path -> (timestamp, result)
        self._cache_ttl = 5  # seconds

    # ── Subprocess runner ─────────────────────────────────────────────

    def _run(self, args: list, cwd: str,
             check: bool = False, timeout: int = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        # S3 credentials for DVC remote access
        env['AWS_ACCESS_KEY_ID'] = MINIO_ACCESS_KEY
        env['AWS_SECRET_ACCESS_KEY'] = MINIO_SECRET_KEY
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=check, env=env,
            timeout=timeout,
        )

    # ── Path validation ───────────────────────────────────────────────

    def _resolve_repo_path(self, repo_path: str) -> str:
        """Validate that a repo path is within allowed project roots."""
        real = os.path.realpath(repo_path)
        # Check against all registered project paths
        for proj in get_registry().list_projects():
            proj_real = os.path.realpath(proj["path"])
            if real == proj_real or real.startswith(proj_real + os.sep):
                if not os.path.isdir(real):
                    raise FileNotFoundError(f"Path not found: {repo_path}")
                return real
        # Legacy fallback: check raw directories
        for base in [PROJECTS_DIR, MOUNTS_DIR]:
            real_base = os.path.realpath(base)
            if real.startswith(real_base + os.sep) or real == real_base:
                if not os.path.isdir(real):
                    raise FileNotFoundError(f"Path not found: {repo_path}")
                return real
        raise ValueError(f"Path outside allowed roots: {repo_path}")

    # ── DVC state checks ─────────────────────────────────────────────

    def is_dvc_initialized(self, repo_path: str) -> bool:
        real = self._resolve_repo_path(repo_path)
        return os.path.isdir(os.path.join(real, '.dvc'))

    @staticmethod
    def is_dvc_trackable(filename: str) -> bool:
        """Check if a filename has a DVC-trackable extension."""
        _, ext = os.path.splitext(filename.lower())
        return ext in DVC_EXTENSIONS

    # ── MinIO bucket setup ────────────────────────────────────────────

    def _ensure_bucket(self):
        """Create the noted-dvc bucket in MinIO if it doesn't exist."""
        try:
            import botocore.session
            from botocore.exceptions import ClientError
            session = botocore.session.get_session()
            s3 = session.create_client(
                's3',
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
            )
            try:
                s3.head_bucket(Bucket=MINIO_BUCKET)
            except ClientError:
                s3.create_bucket(Bucket=MINIO_BUCKET)
        except Exception as e:
            # Non-fatal: DVC push/pull will fail with a clear error anyway
            print(f"[DVC] Warning: could not ensure bucket '{MINIO_BUCKET}': {e}")

    # ── Lazy initialization ───────────────────────────────────────────

    def _ensure_initialized(self, repo_path: str) -> str:
        """Initialize DVC + MinIO remote on first use. Returns resolved path."""
        real = self._resolve_repo_path(repo_path)
        dvc_dir = os.path.join(real, '.dvc')
        already_init = os.path.isdir(dvc_dir)

        if already_init and self._has_remote(real):
            self._ensure_bucket()
            return real

        # Require git repo
        if not os.path.isdir(os.path.join(real, '.git')):
            raise ValueError("DVC requires a git repository. Initialize git first.")

        # Ensure MinIO bucket exists
        self._ensure_bucket()

        # Init DVC (skip if already initialized)
        if not already_init:
            result = self._run(['dvc', 'init'], real)
            if result.returncode != 0:
                raise RuntimeError(f"dvc init failed: {result.stderr.strip()}")

        # Configure MinIO remote (idempotent — overwrites if exists)
        self._run(['dvc', 'remote', 'add', '-d', '-f', 'minio',
                    f's3://{MINIO_BUCKET}'], real)
        self._run(['dvc', 'remote', 'modify', 'minio',
                    'endpointurl', MINIO_ENDPOINT], real)
        self._run(['dvc', 'remote', 'modify', 'minio',
                    'access_key_id', MINIO_ACCESS_KEY], real)
        self._run(['dvc', 'remote', 'modify', 'minio',
                    'secret_access_key', MINIO_SECRET_KEY], real)

        # Install git hooks (auto-checkout on branch switch)
        self._run(['dvc', 'install'], real)

        # Commit DVC init to git
        self._run(['git', 'add', '.dvc', '.dvcignore'], real)

        # Set git config if needed (container env)
        cfg = subprocess.run(
            ['git', 'config', 'user.email'], cwd=real,
            capture_output=True, text=True, check=False
        )
        if not cfg.stdout.strip():
            subprocess.run(['git', 'config', 'user.email', 'noted@local'],
                           cwd=real, check=False)
            subprocess.run(['git', 'config', 'user.name', 'noted'],
                           cwd=real, check=False)

        subprocess.run(
            ['git', 'commit', '-m', 'Initialize DVC with MinIO remote'],
            cwd=real, capture_output=True, text=True, check=False
        )

        return real

    def _has_remote(self, real: str) -> bool:
        """Check if a DVC remote is fully configured (URL + endpoint)."""
        config_path = os.path.join(real, '.dvc', 'config')
        try:
            with open(config_path) as f:
                content = f.read()
                return 'remote' in content and 'endpointurl' in content
        except (OSError, IOError):
            return False

    # ── Track a file with DVC ─────────────────────────────────────────

    def track(self, repo_path: str, rel_path: str) -> dict:
        """Run dvc add on a file, then stage the .dvc pointer and .gitignore."""
        real = self._ensure_initialized(repo_path)

        # Validate file exists
        full_path = os.path.join(real, rel_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {rel_path}")

        # If file is tracked by Git, remove from Git index first (keep on disk)
        check = self._run(['git', 'ls-files', '--error-unmatch', rel_path], real)
        if check.returncode == 0:
            self._run(['git', 'rm', '-r', '--cached', rel_path], real)

        result = self._run(['dvc', 'add', rel_path], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc add failed: {result.stderr.strip()}")

        # Stage the pointer file and updated .gitignore
        dvc_file = rel_path + '.dvc'
        self._run(['git', 'add', dvc_file, '.gitignore'], real)

        # Invalidate cache
        self._status_cache.pop(real, None)

        return {'tracked': True, 'file': rel_path, 'dvc_file': dvc_file}

    # ── Status ────────────────────────────────────────────────────────

    def status(self, repo_path: str) -> dict:
        """Return DVC status: initialization state, tracked files, changed files."""
        real = self._resolve_repo_path(repo_path)

        # Check cache
        cached = self._status_cache.get(real)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]

        initialized = os.path.isdir(os.path.join(real, '.dvc'))
        if not initialized:
            result = {
                'initialized': False,
                'tracked_files': [],
                'changed_files': [],
            }
            self._status_cache[real] = (time.time(), result)
            return result

        # Find tracked files by parsing *.dvc YAML files
        tracked_files = []
        for dirpath, _dirs, files in os.walk(real):
            # Skip .dvc internal directory
            if '.dvc' in dirpath.split(os.sep):
                continue
            for fname in files:
                if fname.endswith('.dvc'):
                    dvc_path = os.path.join(dirpath, fname)
                    try:
                        with open(dvc_path) as f:
                            doc = yaml.safe_load(f)
                        if doc and 'outs' in doc:
                            for out in doc['outs']:
                                rel = os.path.relpath(
                                    os.path.join(dirpath, out['path']), real
                                )
                                tracked_files.append({
                                    'path': rel,
                                    'hash': out.get('md5', out.get('hash', '')),
                                    'size': out.get('size', 0),
                                })
                    except Exception:
                        pass

        # Get changed status via dvc status
        changed_files = []
        st_result = self._run(['dvc', 'status', '--json'], real)
        if st_result.returncode == 0 and st_result.stdout.strip():
            try:
                import json
                st_data = json.loads(st_result.stdout)
                for dvc_file, changes in st_data.items():
                    if isinstance(changes, list):
                        for change in changes:
                            changed_files.append({
                                'dvc_file': dvc_file,
                                'status': change.get('changed', 'unknown'),
                            })
            except (json.JSONDecodeError, AttributeError):
                pass

        result = {
            'initialized': True,
            'tracked_files': tracked_files,
            'changed_files': changed_files,
        }
        self._status_cache[real] = (time.time(), result)
        return result

    def cloud_status(self, repo_path: str) -> dict:
        """Check which tracked files are pushed to remote.

        Returns a dict mapping file paths to their push status:
        'pushed' (in remote), 'not_pushed' (local only), or 'unknown'.
        """
        real = self._resolve_repo_path(repo_path)
        if not os.path.isdir(os.path.join(real, '.dvc')):
            return {'files': {}}

        cached = self._status_cache.get(f'{real}:cloud')
        if cached and (time.time() - cached[0]) < 30:  # 30s TTL for cloud status
            return cached[1]

        files = {}
        st_result = self._run(['dvc', 'status', '--cloud', '--json'], real, timeout=15)
        if st_result.returncode == 0 and st_result.stdout.strip():
            try:
                import json
                st_data = json.loads(st_result.stdout)
                # dvc status --cloud shows files that differ from remote
                for dvc_file, changes in st_data.items():
                    if isinstance(changes, list):
                        for change in changes:
                            path = change.get('path', dvc_file.replace('.dvc', ''))
                            files[path] = 'not_pushed'
            except Exception:
                pass

        result = {'files': files}
        self._status_cache[f'{real}:cloud'] = (time.time(), result)
        return result

    # ── Remove tracking ─────────────────────────────────────────────

    def remove(self, repo_path: str, dvc_file: str, delete_data: bool = True) -> dict:
        """Remove DVC tracking for a file.

        If `delete_data` is True, also remove the data file from disk.
        If False, stop DVC tracking but keep the data on disk (untrack only).
        """
        real = self._ensure_initialized(repo_path)
        # Accept either the .dvc pointer path or the data file path
        if not dvc_file.endswith('.dvc'):
            dvc_file = dvc_file + '.dvc'
        dvc_path = os.path.join(real, dvc_file)
        if not os.path.exists(dvc_path):
            raise FileNotFoundError(f"DVC file not found: {dvc_file}")

        # dvc remove deletes the .dvc pointer and updates .gitignore
        result = self._run(['dvc', 'remove', dvc_file], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc remove failed: {result.stderr.strip()}")

        data_file = dvc_file.replace('.dvc', '')
        data_path = os.path.join(real, data_file)
        if delete_data and os.path.exists(data_path):
            os.remove(data_path)

        # Stage the changes in git
        self._run(['git', 'add', '-A'], real)

        # Invalidate cache
        self._status_cache.pop(real, None)

        return {'success': True, 'removed': data_file, 'data_deleted': delete_data}

    def rename(self, repo_path: str, old_dvc_file: str, new_rel_path: str) -> dict:
        """Rename a DVC-tracked file (dvc remove + rename + dvc add)."""
        real = self._ensure_initialized(repo_path)
        old_dvc_path = os.path.join(real, old_dvc_file)
        if not os.path.exists(old_dvc_path):
            raise FileNotFoundError(f"DVC file not found: {old_dvc_file}")

        old_data_file = old_dvc_file.replace('.dvc', '')
        old_data_path = os.path.join(real, old_data_file)
        new_data_path = os.path.join(real, new_rel_path)

        # 1. dvc remove (cleans .dvc file and .gitignore)
        result = self._run(['dvc', 'remove', old_dvc_file], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc remove failed: {result.stderr.strip()}")

        # 2. Rename the data file
        if os.path.exists(old_data_path):
            os.makedirs(os.path.dirname(new_data_path), exist_ok=True)
            os.rename(old_data_path, new_data_path)

        # 3. dvc add the new path
        result = self._run(['dvc', 'add', new_rel_path], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc add failed: {result.stderr.strip()}")

        # 4. Stage everything
        new_dvc_file = new_rel_path + '.dvc'
        self._run(['git', 'add', new_dvc_file, '.gitignore'], real)

        # Invalidate cache
        self._status_cache.pop(real, None)

        return {'success': True, 'old_path': old_data_file, 'new_path': new_rel_path}

    # ── Data overview (cross-project) ────────────────────────────────

    def data_overview(self) -> list:
        """Scan all projects for DVC-tracked files.
        Returns a list of collections (one per project with DVC data)."""
        collections = []
        for proj in get_registry().list_projects():
            name = proj["name"]
            repo_path = proj["path"]
            if not os.path.isdir(repo_path):
                continue
            if not os.path.isdir(os.path.join(repo_path, '.dvc')):
                continue
            try:
                status = self.status(repo_path)
                tracked = status.get('tracked_files', [])
                if not tracked:
                    continue
                files = []
                for tf in tracked:
                    dvc_file = tf['path'] + '.dvc'
                    files.append({
                        'path': tf['path'],
                        'dvc_file': dvc_file,
                        'hash': tf.get('hash', ''),
                        'size': tf.get('size', 0),
                    })
                collections.append({
                    'name': name,
                    'root_type': proj["source"],
                    'repo_path': repo_path,
                    'files': files,
                })
            except Exception:
                pass
        return collections

    # ── Push / Pull ───────────────────────────────────────────────────

    def push(self, repo_path: str) -> dict:
        """Push DVC-tracked files to MinIO remote."""
        real = self._ensure_initialized(repo_path)
        result = self._run(['dvc', 'push'], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc push failed: {result.stderr.strip()}")
        return {'success': True, 'output': result.stdout.strip() or result.stderr.strip()}

    def pull(self, repo_path: str) -> dict:
        """Pull DVC-tracked files from MinIO remote."""
        real = self._ensure_initialized(repo_path)
        result = self._run(['dvc', 'pull'], real)
        if result.returncode != 0:
            raise RuntimeError(f"dvc pull failed: {result.stderr.strip()}")
        return {'success': True, 'output': result.stdout.strip() or result.stderr.strip()}

    # ── File version history ───────────────────────────────────────────

    def file_history(self, repo_path: str, dvc_file: str) -> dict:
        """Return version history for a .dvc pointer file by walking git log."""
        real = self._resolve_repo_path(repo_path)

        # Get commits that touched this .dvc file
        fmt = '%H%x00%h%x00%s%x00%an%x00%ai%x00%ar'
        result = self._run(
            ['git', 'log', f'--pretty=format:{fmt}', '--', dvc_file], real
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {'file': dvc_file, 'versions': []}

        versions = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split('\x00')
            if len(parts) < 6:
                continue
            commit_hash, short_hash, message, author, date, date_rel = parts

            # Read the .dvc file content at this commit
            show = self._run(['git', 'show', f'{commit_hash}:{dvc_file}'], real)
            md5 = ''
            size = 0
            path = dvc_file.replace('.dvc', '')
            if show.returncode == 0 and show.stdout.strip():
                try:
                    doc = yaml.safe_load(show.stdout)
                    if doc and 'outs' in doc:
                        out = doc['outs'][0]
                        md5 = out.get('md5', out.get('hash', ''))
                        size = out.get('size', 0)
                        path = out.get('path', path)
                except Exception:
                    pass

            versions.append({
                'commit_hash': commit_hash,
                'short_hash': short_hash,
                'message': message,
                'author': author,
                'date': date,
                'date_relative': date_rel,
                'md5': md5,
                'size': size,
                'path': path,
            })

        return {'file': dvc_file, 'versions': versions}

    def checkout_version(self, repo_path: str, dvc_file: str, commit_hash: str) -> dict:
        """Restore a .dvc pointer file from a specific git commit, then dvc checkout."""
        import re
        real = self._resolve_repo_path(repo_path)

        # Validate inputs
        if '..' in dvc_file:
            raise ValueError("Invalid dvc file path")
        if not dvc_file.endswith('.dvc'):
            raise ValueError("File must be a .dvc pointer file")
        if not re.match(r'^[a-fA-F0-9]{7,40}$', commit_hash):
            raise ValueError("Invalid commit hash")

        # Verify commit exists
        check = self._run(['git', 'cat-file', '-t', commit_hash], real)
        if check.returncode != 0 or check.stdout.strip() != 'commit':
            raise ValueError(f"Commit {commit_hash} not found")

        # Restore .dvc file from the target commit
        result = self._run(['git', 'checkout', commit_hash, '--', dvc_file], real)
        if result.returncode != 0:
            raise RuntimeError(f"git checkout failed: {result.stderr.strip()}")

        # Materialize the actual data file
        pulled = False
        co = self._run(['dvc', 'checkout', dvc_file], real)
        if co.returncode != 0:
            # Data not in local cache - try pulling from remote
            pull = self._run(['dvc', 'pull', dvc_file], real)
            if pull.returncode != 0:
                raise RuntimeError(
                    f"Data not available locally or on remote. "
                    f"Try using the terminal: cd {real} && dvc pull {dvc_file}"
                )
            pulled = True
            # Retry checkout after pull
            co2 = self._run(['dvc', 'checkout', dvc_file], real)
            if co2.returncode != 0:
                raise RuntimeError(f"dvc checkout failed after pull: {co2.stderr.strip()}")

        # Invalidate status cache
        self._status_cache.pop(real, None)

        return {
            'success': True,
            'dvc_file': dvc_file,
            'commit_hash': commit_hash,
            'pulled': pulled,
        }

import json
import os
import stat
import subprocess
import tempfile
from app.config import DATA_DIR, PROJECTS_DIR, MOUNTS_DIR
from app.managers.project_registry import get_registry

GITIGNORE_DEFAULTS = """\
__pycache__/
.ipynb_checkpoints/
*.pyc
*.pyo
.DS_Store
"""

CREDENTIALS_FILE = os.path.join(DATA_DIR, "git-credentials.json")


def _load_credentials() -> dict:
    if os.path.isfile(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    return {}


def _save_credentials(data: dict):
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=2)


class GitManager:
    """Git repository management using subprocess.
    Supports both project-based (by ID) and path-based (by abs path) operations.
    """

    def _validate_project(self, project_id: str):
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError(f"Invalid project ID: {project_id}")

    def _project_path(self, project_id: str) -> str:
        return get_registry().resolve(project_id)

    def _resolve_repo_path(self, repo_path: str) -> str:
        """Validate that a repo path is within allowed roots (projects or mounts)."""
        real = os.path.realpath(repo_path)
        real_projects = os.path.realpath(PROJECTS_DIR)
        real_mounts = os.path.realpath(MOUNTS_DIR)
        if (real.startswith(real_projects + os.sep) or real == real_projects or
                real.startswith(real_mounts + os.sep) or real == real_mounts):
            if not os.path.isdir(real):
                raise FileNotFoundError(f"Path not found: {repo_path}")
            return real
        raise ValueError(f"Path outside allowed roots: {repo_path}")

    def _get_repo_path(self, project_id: str = None, repo_path: str = None) -> str:
        """Get the working directory for git operations."""
        if repo_path:
            return self._resolve_repo_path(repo_path)
        if project_id:
            return self._project_path(project_id)
        raise ValueError("Either project_id or repo_path is required")

    def _get_cred_key(self, project_id: str = None, repo_path: str = None) -> str:
        """Get the credentials key for a repo."""
        if project_id:
            return project_id
        if repo_path:
            return repo_path
        return ""

    def _run(self, args: list, cwd: str, check: bool = True,
             extra_env: dict = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=check, env=env
        )

    def _run_with_auth(self, args: list, cwd: str, project_id: str,
                       check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command with PAT authentication via GIT_ASKPASS."""
        creds = _load_credentials()
        pat = creds.get(project_id, {}).get("pat", "")

        if not pat:
            return self._run(args, cwd, check=check)

        # Create a temporary askpass script that echoes the PAT
        askpass_fd, askpass_path = tempfile.mkstemp(prefix="noted_askpass_", suffix=".sh")
        try:
            with os.fdopen(askpass_fd, "w") as f:
                f.write(f"#!/bin/sh\necho '{pat}'\n")
            os.chmod(askpass_path, stat.S_IRWXU)
            return self._run(args, cwd, check=check, extra_env={
                "GIT_ASKPASS": askpass_path,
                "GIT_USERNAME": "x-access-token",
            })
        finally:
            os.unlink(askpass_path)

    def _ensure_git_config(self, path: str):
        """Set local git user if not already configured (needed in container)."""
        result = self._run(["git", "config", "user.email"], path, check=False)
        if not result.stdout.strip():
            self._run(["git", "config", "user.email", "noted@local"], path)
            self._run(["git", "config", "user.name", "noted"], path)

    def is_initialized(self, project_id: str) -> bool:
        try:
            path = self._project_path(project_id)
        except (ValueError, FileNotFoundError):
            return False
        return os.path.isdir(os.path.join(path, ".git"))

    def init(self, project_id: str) -> dict:
        path = self._project_path(project_id)
        self._run(["git", "init"], path)
        self._ensure_git_config(path)

        gitignore = os.path.join(path, ".gitignore")
        if not os.path.exists(gitignore):
            with open(gitignore, "w") as f:
                f.write(GITIGNORE_DEFAULTS)

        return {"initialized": True, "path": path}

    def status(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            return {"initialized": False, "branch": None, "files": [],
                    "ahead": 0, "behind": 0, "remote": None}

        path = self._project_path(project_id)

        branch_res = self._run(["git", "branch", "--show-current"], path, check=False)
        branch = branch_res.stdout.strip() or "main"

        status_res = self._run(["git", "status", "--porcelain=v1", "--untracked-files=all"], path)
        files = []
        for line in status_res.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            filepath = line[3:]
            if " -> " in filepath:
                filepath = filepath.split(" -> ", 1)[1]
            files.append({
                "path": filepath.strip(),
                "index": xy[0],
                "worktree": xy[1],
                "label": _status_label(xy),
            })

        # Ahead/behind tracking
        ahead, behind = 0, 0
        ab_res = self._run(
            ["git", "rev-list", "--left-right", "--count", f"{branch}...@{{u}}"],
            path, check=False
        )
        if ab_res.returncode == 0 and ab_res.stdout.strip():
            parts = ab_res.stdout.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        # Remote URL for display
        remote_url = None
        remote_res = self._run(["git", "remote", "get-url", "origin"], path, check=False)
        if remote_res.returncode == 0:
            remote_url = remote_res.stdout.strip()

        return {
            "initialized": True,
            "branch": branch,
            "files": files,
            "ahead": ahead,
            "behind": behind,
            "remote": remote_url,
        }

    def commit(self, project_id: str, message: str, files: list = None,
               author_name: str = None, author_email: str = None) -> dict:
        if not message or not message.strip():
            raise ValueError("Commit message cannot be empty")

        if not self.is_initialized(project_id):
            self.init(project_id)

        path = self._project_path(project_id)
        self._ensure_git_config(path)

        if files:
            for f in files:
                self._run(["git", "add", "--", f], path)
        else:
            self._run(["git", "add", "-A"], path)

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if author_name:
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email

        result = subprocess.run(
            ["git", "commit", "-m", message.strip()],
            cwd=path, capture_output=True, text=True, check=True, env=env
        )

        hash_res = self._run(["git", "rev-parse", "HEAD"], path)
        return {
            "commit_hash": hash_res.stdout.strip(),
            "short_hash": hash_res.stdout.strip()[:7],
            "message": message.strip(),
        }

    def log(self, project_id: str, limit: int = 30, file_path: str = None) -> dict:
        if not self.is_initialized(project_id):
            return {"commits": []}

        path = self._project_path(project_id)
        fmt = "%H%x00%h%x00%s%x00%an%x00%ai%x00%ar"
        args = ["git", "log", f"--pretty=format:{fmt}", f"-{limit}"]
        if file_path:
            args += ["--", file_path]

        result = self._run(args, path, check=False)
        if result.returncode != 0:
            # No commits yet
            return {"commits": []}

        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("\x00")
            if len(parts) == 6:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "message": parts[2],
                    "author": parts[3],
                    "date": parts[4],
                    "date_relative": parts[5],
                })

        return {"commits": commits}

    def diff(self, project_id: str, file_path: str = None, ref: str = None) -> dict:
        if not self.is_initialized(project_id):
            return {"diff": ""}

        path = self._project_path(project_id)

        if ref:
            args = ["git", "show", ref, "--stat", "--patch"]
            if file_path:
                args += ["--", file_path]
        else:
            args = ["git", "diff", "HEAD"]
            if file_path:
                args += ["--", file_path]

        result = self._run(args, path, check=False)
        return {"diff": result.stdout}

    def branches(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            return {"branches": [], "current": None}

        path = self._project_path(project_id)
        current_res = self._run(["git", "branch", "--show-current"], path, check=False)
        current = current_res.stdout.strip() or None

        list_res = self._run(["git", "branch", "--format=%(refname:short)"], path, check=False)
        branches = [b.strip() for b in list_res.stdout.splitlines() if b.strip()]

        return {"branches": branches, "current": current}

    def checkout(self, project_id: str, branch: str) -> dict:
        if not branch or ".." in branch or " " in branch:
            raise ValueError(f"Invalid branch name: {branch}")

        path = self._project_path(project_id)
        self._run(["git", "checkout", branch], path)
        return {"branch": branch}

    def create_branch(self, project_id: str, branch: str) -> dict:
        if not branch or ".." in branch or " " in branch:
            raise ValueError(f"Invalid branch name: {branch}")

        path = self._project_path(project_id)
        self._run(["git", "checkout", "-b", branch], path)
        return {"branch": branch}

    def show_commit(self, project_id: str, ref: str) -> dict:
        if not self.is_initialized(project_id):
            return {"diff": "", "files": []}

        path = self._project_path(project_id)

        # Get list of files changed
        name_res = self._run(
            ["git", "show", "--name-status", "--pretty=format:", ref], path, check=False
        )
        files = []
        for line in name_res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append({"status": parts[0], "path": parts[1]})

        # Get patch
        diff_res = self._run(["git", "show", "--patch", "--stat", ref], path, check=False)

        return {"diff": diff_res.stdout, "files": files}

    # --- Credentials ---

    def get_credentials(self, project_id: str) -> dict:
        self._validate_project(project_id)
        creds = _load_credentials()
        entry = creds.get(project_id, {})
        pat = entry.get("pat", "")
        return {
            "has_pat": bool(pat),
            "pat_hint": f"{'*' * (len(pat) - 4)}{pat[-4:]}" if len(pat) > 4 else "",
        }

    def set_credentials(self, project_id: str, pat: str) -> dict:
        self._validate_project(project_id)
        creds = _load_credentials()
        if not pat:
            creds.pop(project_id, None)
        else:
            creds.setdefault(project_id, {})["pat"] = pat.strip()
        _save_credentials(creds)
        return {"saved": True}

    # --- Remotes ---

    def get_remotes(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            return {"remotes": []}
        path = self._project_path(project_id)
        result = self._run(["git", "remote", "-v"], path, check=False)
        remotes = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                direction = parts[2].strip("()") if len(parts) > 2 else "fetch"
                remotes.setdefault(name, {"name": name})
                remotes[name][direction] = url
        return {"remotes": list(remotes.values())}

    def set_remote(self, project_id: str, url: str, name: str = "origin") -> dict:
        if not url or not url.strip():
            raise ValueError("Remote URL cannot be empty")
        if not self.is_initialized(project_id):
            self.init(project_id)

        path = self._project_path(project_id)

        # Check if remote exists
        existing = self._run(["git", "remote"], path, check=False)
        if name in existing.stdout.splitlines():
            self._run(["git", "remote", "set-url", name, url.strip()], path)
        else:
            self._run(["git", "remote", "add", name, url.strip()], path)

        return {"name": name, "url": url.strip()}

    def remove_remote(self, project_id: str, name: str = "origin") -> dict:
        if not self.is_initialized(project_id):
            return {"removed": False}
        path = self._project_path(project_id)
        self._run(["git", "remote", "remove", name], path)
        return {"removed": True}

    # --- Fetch / Pull / Push ---

    def fetch(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            raise ValueError("Repository not initialized")
        path = self._project_path(project_id)
        result = self._run_with_auth(
            ["git", "fetch", "--all", "--prune"], path, project_id, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Fetch failed")
        return {"success": True, "output": result.stderr.strip()}

    def pull(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            raise ValueError("Repository not initialized")
        path = self._project_path(project_id)
        result = self._run_with_auth(
            ["git", "pull", "--ff-only"], path, project_id, check=False
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(error or "Pull failed")
        return {"success": True, "output": result.stdout.strip()}

    def push(self, project_id: str, set_upstream: bool = False) -> dict:
        if not self.is_initialized(project_id):
            raise ValueError("Repository not initialized")
        path = self._project_path(project_id)

        branch_res = self._run(["git", "branch", "--show-current"], path, check=False)
        branch = branch_res.stdout.strip()

        args = ["git", "push"]
        if set_upstream:
            args += ["--set-upstream", "origin", branch]

        result = self._run_with_auth(args, path, project_id, check=False)
        if result.returncode != 0:
            error = result.stderr.strip()
            # Detect missing upstream and auto-retry with --set-upstream
            if "no upstream branch" in error or "has no upstream" in error:
                args = ["git", "push", "--set-upstream", "origin", branch]
                result = self._run_with_auth(args, path, project_id, check=False)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "Push failed")
            else:
                raise RuntimeError(error or "Push failed")
        return {"success": True, "output": result.stderr.strip()}

    # --- Remote branches ---

    def remote_branches(self, project_id: str) -> dict:
        if not self.is_initialized(project_id):
            return {"branches": []}
        path = self._project_path(project_id)
        result = self._run(
            ["git", "branch", "-r", "--format=%(refname:short)"], path, check=False
        )
        branches = []
        for b in result.stdout.splitlines():
            b = b.strip()
            if b and "HEAD" not in b:
                branches.append(b)
        return {"branches": branches}

    # ═══════════════════════════════════════════════════════════════════
    # Path-based operations (for multi-repo support)
    # ═══════════════════════════════════════════════════════════════════

    def _run_with_auth_path(self, args: list, cwd: str, cred_key: str,
                            check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command with PAT authentication, keyed by repo path."""
        creds = _load_credentials()
        pat = creds.get(cred_key, {}).get("pat", "")
        if not pat:
            return self._run(args, cwd, check=check)
        askpass_fd, askpass_path = tempfile.mkstemp(prefix="noted_askpass_", suffix=".sh")
        try:
            with os.fdopen(askpass_fd, "w") as f:
                f.write(f"#!/bin/sh\necho '{pat}'\n")
            os.chmod(askpass_path, stat.S_IRWXU)
            return self._run(args, cwd, check=check, extra_env={
                "GIT_ASKPASS": askpass_path,
                "GIT_USERNAME": "x-access-token",
            })
        finally:
            os.unlink(askpass_path)

    def _repo_init(self, path: str) -> dict:
        """Initialize a git repo at the given path."""
        self._run(["git", "init"], path)
        self._ensure_git_config(path)
        gitignore = os.path.join(path, ".gitignore")
        if not os.path.exists(gitignore):
            with open(gitignore, "w") as f:
                f.write(GITIGNORE_DEFAULTS)
        return {"initialized": True, "path": path}

    def _repo_status(self, path: str) -> dict:
        branch_res = self._run(["git", "branch", "--show-current"], path, check=False)
        branch = branch_res.stdout.strip() or "main"

        status_res = self._run(["git", "status", "--porcelain=v1", "--untracked-files=all"], path)
        files = []
        for line in status_res.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            filepath = line[3:]
            if " -> " in filepath:
                filepath = filepath.split(" -> ", 1)[1]
            files.append({
                "path": filepath.strip(),
                "index": xy[0],
                "worktree": xy[1],
                "label": _status_label(xy),
            })

        ahead, behind = 0, 0
        ab_res = self._run(
            ["git", "rev-list", "--left-right", "--count", f"{branch}...@{{u}}"],
            path, check=False
        )
        if ab_res.returncode == 0 and ab_res.stdout.strip():
            parts = ab_res.stdout.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        remote_url = None
        remote_res = self._run(["git", "remote", "get-url", "origin"], path, check=False)
        if remote_res.returncode == 0:
            remote_url = remote_res.stdout.strip()

        return {
            "initialized": True, "branch": branch, "files": files,
            "ahead": ahead, "behind": behind, "remote": remote_url,
        }

    def _repo_commit(self, path: str, message: str, files: list = None,
                     author_name: str = None, author_email: str = None) -> dict:
        if not message or not message.strip():
            raise ValueError("Commit message cannot be empty")

        self._ensure_git_config(path)
        if files:
            for f in files:
                self._run(["git", "add", "--", f], path)
        else:
            self._run(["git", "add", "-A"], path)

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if author_name:
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email

        subprocess.run(
            ["git", "commit", "-m", message.strip()],
            cwd=path, capture_output=True, text=True, check=True, env=env
        )
        hash_res = self._run(["git", "rev-parse", "HEAD"], path)
        return {
            "commit_hash": hash_res.stdout.strip(),
            "short_hash": hash_res.stdout.strip()[:7],
            "message": message.strip(),
        }

    def _repo_log(self, path: str, limit: int = 30) -> dict:
        fmt = "%H%x00%h%x00%s%x00%an%x00%ai%x00%ar"
        args = ["git", "log", f"--pretty=format:{fmt}", f"-{limit}"]
        result = self._run(args, path, check=False)
        if result.returncode != 0:
            return {"commits": []}
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("\x00")
            if len(parts) == 6:
                commits.append({
                    "hash": parts[0], "short_hash": parts[1],
                    "message": parts[2], "author": parts[3],
                    "date": parts[4], "date_relative": parts[5],
                })
        return {"commits": commits}

    def _repo_diff(self, path: str, file_path: str = None, ref: str = None) -> dict:
        if ref:
            args = ["git", "show", ref, "--stat", "--patch"]
            if file_path:
                args += ["--", file_path]
        else:
            args = ["git", "diff", "HEAD"]
            if file_path:
                args += ["--", file_path]
        result = self._run(args, path, check=False)
        return {"diff": result.stdout}

    def _repo_branches(self, path: str) -> dict:
        current_res = self._run(["git", "branch", "--show-current"], path, check=False)
        current = current_res.stdout.strip() or None
        list_res = self._run(["git", "branch", "--format=%(refname:short)"], path, check=False)
        branches = [b.strip() for b in list_res.stdout.splitlines() if b.strip()]
        return {"branches": branches, "current": current}

    def _repo_checkout(self, path: str, branch: str) -> dict:
        if not branch or ".." in branch or " " in branch:
            raise ValueError(f"Invalid branch name: {branch}")
        self._run(["git", "checkout", branch], path)
        return {"branch": branch}

    def _repo_create_branch(self, path: str, branch: str) -> dict:
        if not branch or ".." in branch or " " in branch:
            raise ValueError(f"Invalid branch name: {branch}")
        self._run(["git", "checkout", "-b", branch], path)
        return {"branch": branch}

    def _repo_show_commit(self, path: str, ref: str) -> dict:
        name_res = self._run(
            ["git", "show", "--name-status", "--pretty=format:", ref], path, check=False
        )
        files = []
        for line in name_res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append({"status": parts[0], "path": parts[1]})
        diff_res = self._run(["git", "show", "--patch", "--stat", ref], path, check=False)
        return {"diff": diff_res.stdout, "files": files}

    def _repo_get_credentials(self, cred_key: str) -> dict:
        creds = _load_credentials()
        entry = creds.get(cred_key, {})
        pat = entry.get("pat", "")
        return {
            "has_pat": bool(pat),
            "pat_hint": f"{'*' * (len(pat) - 4)}{pat[-4:]}" if len(pat) > 4 else "",
        }

    def _repo_set_credentials(self, cred_key: str, pat: str) -> dict:
        creds = _load_credentials()
        if not pat:
            creds.pop(cred_key, None)
        else:
            creds.setdefault(cred_key, {})["pat"] = pat.strip()
        _save_credentials(creds)
        return {"saved": True}

    def _repo_get_remotes(self, path: str) -> dict:
        result = self._run(["git", "remote", "-v"], path, check=False)
        remotes = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                direction = parts[2].strip("()") if len(parts) > 2 else "fetch"
                remotes.setdefault(name, {"name": name})
                remotes[name][direction] = url
        return {"remotes": list(remotes.values())}

    def _repo_set_remote(self, path: str, url: str, name: str = "origin") -> dict:
        if not url or not url.strip():
            raise ValueError("Remote URL cannot be empty")
        existing = self._run(["git", "remote"], path, check=False)
        if name in existing.stdout.splitlines():
            self._run(["git", "remote", "set-url", name, url.strip()], path)
        else:
            self._run(["git", "remote", "add", name, url.strip()], path)
        return {"name": name, "url": url.strip()}

    def _repo_fetch(self, path: str, cred_key: str) -> dict:
        result = self._run_with_auth_path(
            ["git", "fetch", "--all", "--prune"], path, cred_key, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Fetch failed")
        return {"success": True, "output": result.stderr.strip()}

    def _repo_pull(self, path: str, cred_key: str, strategy: str = "ff-only") -> dict:
        flag_map = {
            "ff-only": "--ff-only",
            "rebase": "--rebase",
            "merge": "--no-rebase",
        }
        flag = flag_map.get(strategy, "--ff-only")
        result = self._run_with_auth_path(
            ["git", "pull", flag], path, cred_key, check=False
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(error or "Pull failed")
        return {"success": True, "output": result.stdout.strip()}

    def _repo_push(self, path: str, cred_key: str, set_upstream: bool = False) -> dict:
        branch_res = self._run(["git", "branch", "--show-current"], path, check=False)
        branch = branch_res.stdout.strip()
        args = ["git", "push"]
        if set_upstream:
            args += ["--set-upstream", "origin", branch]
        result = self._run_with_auth_path(args, path, cred_key, check=False)
        if result.returncode != 0:
            error = result.stderr.strip()
            if "no upstream branch" in error or "has no upstream" in error:
                args = ["git", "push", "--set-upstream", "origin", branch]
                result = self._run_with_auth_path(args, path, cred_key, check=False)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "Push failed")
            else:
                raise RuntimeError(error or "Push failed")
        return {"success": True, "output": result.stderr.strip()}

    def _repo_remote_branches(self, path: str) -> dict:
        result = self._run(
            ["git", "branch", "-r", "--format=%(refname:short)"], path, check=False
        )
        branches = []
        for b in result.stdout.splitlines():
            b = b.strip()
            if b and "HEAD" not in b:
                branches.append(b)
        return {"branches": branches}

    # --- Tags (path-based) ---

    def _repo_tags(self, path: str) -> dict:
        """List tags sorted by creation date (newest first)."""
        result = self._run(
            ["git", "tag", "-l", "--sort=-creatordate",
             "--format=%(refname:short)%00%(creatordate:short)%00%(creatordate:relative)%00%(subject)"],
            path, check=False,
        )
        tags = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x00")
            name = parts[0]
            tags.append({
                "name": name,
                "date": parts[1] if len(parts) > 1 else "",
                "date_relative": parts[2] if len(parts) > 2 else "",
                "message": parts[3] if len(parts) > 3 else "",
            })
        return {"tags": tags}

    def _repo_create_tag(self, path: str, tag: str, message: str = None) -> dict:
        if not tag or ".." in tag or " " in tag:
            raise ValueError(f"Invalid tag name: {tag}")
        args = ["git", "tag"]
        if message:
            args += ["-a", tag, "-m", message]
        else:
            args += [tag]
        self._run(args, path)
        return {"tag": tag}

    def _repo_delete_tag(self, path: str, tag: str) -> dict:
        if not tag or ".." in tag or " " in tag:
            raise ValueError(f"Invalid tag name: {tag}")
        self._run(["git", "tag", "-d", tag], path)
        return {"tag": tag, "deleted": True}

    def _repo_discard(self, path: str, files: list) -> dict:
        """Discard changes for specific files.

        Tracked files: git checkout -- <file>
        Untracked files: remove from disk
        """
        if not files:
            raise ValueError("No files specified")

        # Get current status to distinguish tracked vs untracked
        status_res = self._run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], path
        )
        untracked = set()
        for line in status_res.stdout.splitlines():
            if len(line) >= 4 and line[:2] == '??':
                untracked.add(line[3:].strip())

        tracked = []
        for f in files:
            if f in untracked:
                # Untracked file - delete it
                fpath = os.path.join(path, f)
                if os.path.exists(fpath):
                    if os.path.isdir(fpath):
                        import shutil
                        shutil.rmtree(fpath)
                    else:
                        os.remove(fpath)
            else:
                tracked.append(f)

        if tracked:
            # Unstage first (in case file is staged)
            self._run(["git", "reset", "HEAD", "--"] + tracked, path, check=False)
            # Restore working tree
            self._run(["git", "checkout", "--"] + tracked, path)

        return {"discarded": files}

    # --- Clone ---

    def clone(self, url: str, project_id: str, pat: str = None) -> dict:
        """Clone a GitHub repo as a new project."""
        self._validate_project(project_id)
        target = os.path.join(PROJECTS_DIR, project_id)
        if os.path.exists(target):
            raise ValueError(f"Project '{project_id}' already exists")

        # Save PAT before cloning so _run_with_auth can use it
        if pat:
            creds = _load_credentials()
            creds.setdefault(project_id, {})["pat"] = pat.strip()
            _save_credentials(creds)

        args = ["git", "clone", url.strip(), target]
        result = self._run_with_auth(args, PROJECTS_DIR, project_id, check=False)
        if result.returncode != 0:
            # Clean up on failure
            if pat:
                creds = _load_credentials()
                creds.pop(project_id, None)
                _save_credentials(creds)
            error = result.stderr.strip()
            raise RuntimeError(error or "Clone failed")

        self._ensure_git_config(target)
        return {"project_id": project_id, "cloned": True}


def _status_label(xy: str) -> str:
    x, y = xy[0], xy[1]
    if x == "?" and y == "?":
        return "untracked"
    if x == "A":
        return "added"
    if x == "D" or y == "D":
        return "deleted"
    if x == "R":
        return "renamed"
    if x == "M" or y == "M":
        return "modified"
    return "changed"

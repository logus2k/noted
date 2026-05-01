import os
import subprocess
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from app.managers.git_manager import GitManager

router = APIRouter(prefix="/api", tags=["git"])
git_mgr = GitManager()


class CommitRequest(BaseModel):
    message: str
    files: Optional[List[str]] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None


@router.get("/git/version")
def git_version():
    """Return the installed git version."""
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=5
        )
        # "git version 2.43.0" → "2.43.0"
        version = result.stdout.strip().replace("git version ", "")
        return {"version": f"git {version}"}
    except Exception:
        return {"version": "git"}


@router.post("/projects/{project_id}/git/init")
def init_repo(project_id: str):
    try:
        return git_mgr.init(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.get("/projects/{project_id}/git/status")
def get_status(project_id: str):
    try:
        return git_mgr.status(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/projects/{project_id}/git/commit")
def commit(project_id: str, body: CommitRequest):
    try:
        return git_mgr.commit(project_id, body.message, body.files, body.author_name, body.author_email)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.get("/projects/{project_id}/git/log")
def get_log(
    project_id: str,
    limit: int = Query(30, le=100),
    path: Optional[str] = None,
):
    try:
        return git_mgr.log(project_id, limit, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/git/diff")
def get_diff(
    project_id: str,
    path: Optional[str] = Query(None),
    ref: Optional[str] = Query(None),
):
    try:
        return git_mgr.diff(project_id, path, ref)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/git/show/{ref}")
def show_commit(project_id: str, ref: str):
    try:
        return git_mgr.show_commit(project_id, ref)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class BranchRequest(BaseModel):
    branch: str


@router.get("/projects/{project_id}/git/branches")
def get_branches(project_id: str):
    try:
        return git_mgr.branches(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/git/checkout")
def checkout(project_id: str, body: BranchRequest):
    try:
        return git_mgr.checkout(project_id, body.branch)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/projects/{project_id}/git/branches")
def create_branch(project_id: str, body: BranchRequest):
    try:
        return git_mgr.create_branch(project_id, body.branch)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


# --- GitHub integration: Credentials ---

class CredentialsRequest(BaseModel):
    pat: str


@router.get("/projects/{project_id}/git/credentials")
def get_credentials(project_id: str):
    try:
        return git_mgr.get_credentials(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/projects/{project_id}/git/credentials")
def set_credentials(project_id: str, body: CredentialsRequest):
    try:
        return git_mgr.set_credentials(project_id, body.pat)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- GitHub integration: Remotes ---

class RemoteRequest(BaseModel):
    url: str
    name: Optional[str] = "origin"


@router.get("/projects/{project_id}/git/remotes")
def get_remotes(project_id: str):
    try:
        return git_mgr.get_remotes(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/projects/{project_id}/git/remotes")
def set_remote(project_id: str, body: RemoteRequest):
    try:
        return git_mgr.set_remote(project_id, body.url, body.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


class RemoteDeleteRequest(BaseModel):
    name: Optional[str] = "origin"


@router.delete("/projects/{project_id}/git/remotes")
def remove_remote(project_id: str, body: RemoteDeleteRequest):
    try:
        return git_mgr.remove_remote(project_id, body.name)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


# --- GitHub integration: Fetch / Pull / Push ---

@router.post("/projects/{project_id}/git/fetch")
def fetch(project_id: str):
    try:
        return git_mgr.fetch(project_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/projects/{project_id}/git/pull")
def pull(project_id: str):
    try:
        return git_mgr.pull(project_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


class PushRequest(BaseModel):
    set_upstream: Optional[bool] = False


@router.post("/projects/{project_id}/git/push")
def push(project_id: str, body: PushRequest = PushRequest()):
    try:
        return git_mgr.push(project_id, body.set_upstream)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


# --- GitHub integration: Remote branches ---

@router.get("/projects/{project_id}/git/remote-branches")
def get_remote_branches(project_id: str):
    try:
        return git_mgr.remote_branches(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- GitHub integration: Clone ---

class CloneRequest(BaseModel):
    url: str
    project_id: str
    pat: Optional[str] = None


@router.post("/git/clone")
def clone_repo(body: CloneRequest):
    try:
        return git_mgr.clone(body.url, body.project_id, body.pat)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


# ═══════════════════════════════════════════════════════════════════════
# Path-based git endpoints (for multi-repo support across projects/mounts)
# ═══════════════════════════════════════════════════════════════════════

def _resolve_repo(repo_path: str = "", project_id: str = "") -> str:
    """Resolve to filesystem path, preferring project_id."""
    if project_id:
        from app.managers.project_registry import get_registry
        return get_registry().resolve(project_id)
    return repo_path


class RepoRequest(BaseModel):
    repo_path: str = ""
    project_id: str = ""
    strategy: Optional[str] = None

    def resolve(self) -> str:
        return _resolve_repo(self.repo_path, self.project_id)


class RepoCommitRequest(BaseModel):
    repo_path: str = ""
    project_id: str = ""
    message: str
    files: Optional[List[str]] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None

    def resolve(self) -> str:
        return _resolve_repo(self.repo_path, self.project_id)


class RepoBranchRequest(BaseModel):
    repo_path: str = ""
    project_id: str = ""
    branch: str

    def resolve(self) -> str:
        return _resolve_repo(self.repo_path, self.project_id)


class RepoRemoteRequest(BaseModel):
    repo_path: str
    url: str
    name: Optional[str] = "origin"


class RepoCredentialsRequest(BaseModel):
    repo_path: str
    pat: str


class RepoDiscardRequest(BaseModel):
    repo_path: str = ""
    files: List[str]

class RepoTagRequest(BaseModel):
    repo_path: str
    tag: str
    message: str = None


class RepoPushRequest(BaseModel):
    repo_path: str
    set_upstream: Optional[bool] = False


@router.post("/git/repo/init")
def repo_init(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_init(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/status")
def repo_status(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        # Check if git is initialized
        if not os.path.isdir(os.path.join(path, ".git")):
            return {"initialized": False, "branch": None, "files": [],
                    "ahead": 0, "behind": 0, "remote": None}
        return git_mgr._repo_status(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/commit")
def repo_commit(body: RepoCommitRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_commit(path, body.message, body.files,
                                     body.author_name, body.author_email)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/log")
def repo_log(body: RepoRequest, limit: int = Query(30, le=100)):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_log(path, limit)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/diff")
def repo_diff(body: RepoRequest, path: Optional[str] = Query(None),
              ref: Optional[str] = Query(None)):
    try:
        repo = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_diff(repo, path, ref)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/branches")
def repo_branches(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_branches(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/checkout")
def repo_checkout(body: RepoBranchRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_checkout(path, body.branch)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/create-branch")
def repo_create_branch(body: RepoBranchRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_create_branch(path, body.branch)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/fetch")
def repo_fetch(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_fetch(path, body.repo_path)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/pull")
def repo_pull(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        strategy = body.strategy or "ff-only"
        return git_mgr._repo_pull(path, body.repo_path, strategy=strategy)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/push")
def repo_push(body: RepoPushRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_push(path, body.repo_path, body.set_upstream)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/show")
def repo_show_commit(body: RepoRequest, ref: str = Query(...)):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_show_commit(path, ref)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/credentials")
def repo_get_credentials(body: RepoRequest):
    try:
        return git_mgr._repo_get_credentials(body.repo_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/git/repo/credentials")
def repo_set_credentials(body: RepoCredentialsRequest):
    try:
        return git_mgr._repo_set_credentials(body.repo_path, body.pat)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/remotes")
def repo_get_remotes(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_get_remotes(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/git/repo/remotes")
def repo_set_remote(body: RepoRemoteRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_set_remote(path, body.url, body.name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/remote-branches")
def repo_remote_branches(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_remote_branches(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/tags")
def repo_tags(body: RepoRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_tags(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/repo/create-tag")
def repo_create_tag(body: RepoTagRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_create_tag(path, body.tag, body.message)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/delete-tag")
def repo_delete_tag(body: RepoTagRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_delete_tag(path, body.tag)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))


@router.post("/git/repo/discard")
def repo_discard(body: RepoDiscardRequest):
    try:
        path = git_mgr._resolve_repo_path(body.repo_path)
        return git_mgr._repo_discard(path, body.files)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or str(e))

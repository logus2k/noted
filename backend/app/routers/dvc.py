"""DVC integration API — data versioning with MinIO remote."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.managers.dvc_manager import DvcManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dvc", tags=["dvc"])
dvc_mgr = DvcManager()


class RepoRequest(BaseModel):
    repo_path: str = ""
    project_id: str = ""

    def resolve_path(self) -> str:
        """Resolve to filesystem path, preferring project_id."""
        if self.project_id:
            from app.managers.project_registry import get_registry
            return get_registry().resolve(self.project_id)
        return self.repo_path


class TrackRequest(BaseModel):
    repo_path: str
    rel_path: str
    delete_data: bool = True  # for /remove only: also delete the data file from disk


class RenameRequest(BaseModel):
    repo_path: str
    old_dvc_file: str
    new_rel_path: str


class FileHistoryRequest(BaseModel):
    repo_path: str
    dvc_file: str


class CheckoutVersionRequest(BaseModel):
    repo_path: str
    dvc_file: str
    commit_hash: str


@router.get("/data-overview")
def dvc_data_overview():
    """Scan all projects/mounts for DVC-tracked data files."""
    try:
        return dvc_mgr.data_overview()
    except Exception as e:
        logger.exception("DVC data overview failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/remove")
def dvc_remove(body: TrackRequest):
    """Remove DVC tracking for a file.

    If `delete_data` is True (default), the data file is also removed from disk.
    If False, the data file is kept (useful for "untrack" without losing data).
    """
    try:
        return dvc_mgr.remove(body.repo_path, body.rel_path, delete_data=body.delete_data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC remove failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/rename")
def dvc_rename(body: RenameRequest):
    """Rename a DVC-tracked file (dvc remove + rename + dvc add)."""
    try:
        return dvc_mgr.rename(body.repo_path, body.old_dvc_file, body.new_rel_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC rename failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/status")
def dvc_status(body: RepoRequest):
    """Get DVC status: initialization state, tracked files, changed files."""
    try:
        return dvc_mgr.status(body.resolve_path())
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("DVC status failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/cloud-status")
def dvc_cloud_status(body: RepoRequest):
    """Check which tracked files are pushed to remote storage."""
    try:
        return dvc_mgr.cloud_status(body.repo_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("DVC cloud status failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/track")
def dvc_track(body: TrackRequest):
    """Track a file with DVC (dvc add + git add pointer)."""
    try:
        return dvc_mgr.track(body.repo_path, body.rel_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC track failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/push")
def dvc_push(body: RepoRequest):
    """Push DVC-tracked files to MinIO remote."""
    try:
        return dvc_mgr.push(body.repo_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC push failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/pull")
def dvc_pull(body: RepoRequest):
    """Pull DVC-tracked files from MinIO remote."""
    try:
        return dvc_mgr.pull(body.repo_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC pull failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/checkout-version")
def dvc_checkout_version(body: CheckoutVersionRequest):
    """Switch a DVC-tracked file to a specific version from git history."""
    try:
        return dvc_mgr.checkout_version(body.repo_path, body.dvc_file, body.commit_hash)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("DVC checkout version failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/file-history")
def dvc_file_history(body: FileHistoryRequest):
    """Get version history for a .dvc pointer file."""
    try:
        return dvc_mgr.file_history(body.repo_path, body.dvc_file)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("DVC file history failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

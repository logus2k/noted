"""Snapshot API - create, restore, fork, and list experiment snapshots."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.managers.snapshot_manager import SnapshotManager
from app.managers.git_manager import GitManager
from app.managers.dvc_manager import DvcManager
from app.managers.mlflow_manager import MlflowManager
from app.managers.hydra_manager import HydraManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

# Initialize managers
_git = GitManager()
_dvc = DvcManager()
_mlflow = MlflowManager()
_hydra = HydraManager()
snapshot_mgr = SnapshotManager(_git, _dvc, _mlflow, _hydra)


class CreateSnapshotRequest(BaseModel):
    project_id: str
    experiment_id: str
    run_id: str
    name: str
    description: str = ''
    auto_commit: bool = False
    kernel_venv_path: str | None = None


class RestoreSnapshotRequest(BaseModel):
    project_id: str
    experiment_id: str


class ForkExperimentRequest(BaseModel):
    project_id: str
    source_experiment_id: str
    new_experiment_name: str


@router.get("/git-state/{project_id}")
def check_git_state(project_id: str):
    """Check git state before creating a snapshot."""
    try:
        return snapshot_mgr.check_git_state(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/create")
def create_snapshot(body: CreateSnapshotRequest):
    """Create a snapshot of the best run in an experiment."""
    try:
        return snapshot_mgr.create_snapshot(
            body.project_id, body.experiment_id, body.run_id,
            body.name, body.description, body.auto_commit,
            body.kernel_venv_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create snapshot")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/restore")
def restore_snapshot(body: RestoreSnapshotRequest):
    """Restore workspace to a snapshot state."""
    try:
        return snapshot_mgr.restore_snapshot(body.project_id, body.experiment_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to restore snapshot")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/fork")
def fork_experiment(body: ForkExperimentRequest):
    """Create a new experiment by forking from a snapshot."""
    try:
        return snapshot_mgr.fork_experiment(
            body.project_id, body.source_experiment_id,
            body.new_experiment_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to fork experiment")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/{project_id}")
def list_snapshots(project_id: str):
    """List all snapshots for a project."""
    try:
        return {'snapshots': snapshot_mgr.list_snapshots(project_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list snapshots")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

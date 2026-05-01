"""MLflow experiment browser API — list experiments, runs, and run details."""

import os
import logging
import mimetypes
import shutil
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.managers.mlflow_manager import MlflowManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mlflow", tags=["mlflow"])
mlflow_mgr = MlflowManager()


@router.get("/experiments")
def list_experiments():
    """List all active MLflow experiments."""
    try:
        return {"experiments": mlflow_mgr.list_experiments()}
    except Exception as e:
        logger.exception("MLflow list experiments failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/experiments/{experiment_id}/runs")
def list_runs(experiment_id: str):
    """List runs for an experiment."""
    try:
        return {"runs": mlflow_mgr.list_runs(experiment_id)}
    except Exception as e:
        logger.exception("MLflow list runs failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    """Get full details for a single run."""
    try:
        return mlflow_mgr.get_run(run_id)
    except Exception as e:
        logger.exception("MLflow get run failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str, path: str = Query("")):
    """List artifacts for a run. Empty path returns classified top-level artifacts."""
    try:
        if path:
            return {"artifacts": mlflow_mgr.list_artifacts(run_id, path)}
        return mlflow_mgr.list_artifacts_classified(run_id)
    except Exception as e:
        logger.exception("MLflow list artifacts failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/runs/{run_id}/logged_models")
def list_logged_models_for_run(run_id: str):
    """List MLflow 3.x Logged Model entities linked to a run.

    MLflow 3.x stores `log_model(...)` outputs in a separate artifact
    location (`<experiment_id>/models/<model_id>/artifacts/`) rather than
    attaching them to the run's own artifact tree. This endpoint surfaces
    them so the Run detail UI can show MLmodel / requirements.txt /
    conda.yaml / python_env.yaml next to the run.
    """
    try:
        return {"logged_models": mlflow_mgr.list_logged_models_for_run(run_id)}
    except Exception as e:
        logger.exception("MLflow list logged models failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/logged_models/{experiment_id}/{model_id}/download")
def download_logged_model_artifact(
    experiment_id: str, model_id: str, path: str = Query(...),
):
    """Download a single file from a Logged Model's artifact root."""
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    try:
        local_path = mlflow_mgr.download_logged_model_artifact(
            experiment_id, model_id, path,
        )
        if os.path.isdir(local_path):
            raise HTTPException(status_code=400, detail="Cannot download a directory")
        media_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        tmp_root = local_path
        while os.path.dirname(tmp_root) != tmp_root:
            parent = os.path.dirname(tmp_root)
            if os.path.basename(parent).startswith("noted_logged_model_"):
                tmp_root = parent
                break
            tmp_root = parent
        cleanup = BackgroundTask(shutil.rmtree, tmp_root, ignore_errors=True)
        return FileResponse(local_path, media_type=media_type, background=cleanup)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("MLflow download logged model artifact failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/runs/{run_id}/artifacts/download")
def download_artifact(run_id: str, path: str = Query(...)):
    """Download a single artifact file."""
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    try:
        local_path = mlflow_mgr.download_artifact(run_id, path)
        if os.path.isdir(local_path):
            raise HTTPException(status_code=400, detail="Cannot download a directory")
        media_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        # Clean up the temp directory after response is sent
        tmp_root = local_path
        while os.path.dirname(tmp_root) != tmp_root:
            parent = os.path.dirname(tmp_root)
            if os.path.basename(parent).startswith("noted_artifact_"):
                tmp_root = parent
                break
            tmp_root = parent
        cleanup = BackgroundTask(shutil.rmtree, tmp_root, ignore_errors=True)
        return FileResponse(local_path, media_type=media_type, background=cleanup)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("MLflow download artifact failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/runs/{run_id}/metrics/{metric_key}")
def get_metric_history(run_id: str, metric_key: str):
    """Get the full history of a metric for a run."""
    try:
        return {"history": mlflow_mgr.get_metric_history(run_id, metric_key)}
    except Exception as e:
        logger.exception("MLflow get metric history failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str):
    """Stop a running run (set status to FINISHED)."""
    try:
        return mlflow_mgr.stop_run(run_id, status="KILLED")
    except Exception as e:
        logger.exception("MLflow stop run failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/runs/{run_id}")
def delete_run(run_id: str):
    """Delete (archive) a run."""
    try:
        mlflow_mgr.delete_run(run_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.exception("MLflow delete run failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/experiments/{experiment_id}")
def delete_experiment(experiment_id: str):
    """Delete (archive) an experiment."""
    try:
        mlflow_mgr.delete_experiment(experiment_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.exception("MLflow delete experiment failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/experiments/{experiment_id}/leaderboard")
def get_leaderboard(experiment_id: str,
                    sort_by: str = Query(default="", description="Metric key to sort by"),
                    sort_order: str = Query(default="asc", description="asc or desc"),
                    limit: int = Query(default=100, description="Max runs to return")):
    """Return all runs for an experiment in a leaderboard format.

    Each run includes all metrics, params, tags, snapshot status, and lineage hashes.
    """
    try:
        runs = mlflow_mgr.search_runs(
            experiment_ids=[experiment_id],
            max_results=limit,
        )

        # Enrich with snapshot and lineage info
        rows = []
        for run in runs:
            tags = run.get('tags', {})
            rows.append({
                'run_id': run['run_id'],
                'run_name': run.get('run_name', ''),
                'status': run.get('status', ''),
                'start_time': run.get('start_time'),
                'end_time': run.get('end_time'),
                'metrics': run.get('metrics', {}),
                'params': run.get('params', {}),
                'is_snapshot': tags.get('noted.snapshot') == 'true',
                'snapshot_name': tags.get('noted.snapshot_name', ''),
                'snapshot_branch': tags.get('noted.snapshot_branch', ''),
                'dvc_data_hash': tags.get('dvc.data_hash', run.get('params', {}).get('dvc_data_hash', '')),
                'hydra_config_hash': tags.get('hydra.config_hash', run.get('params', {}).get('hydra_config_hash', '')),
            })

        # Sort by metric if specified
        if sort_by:
            reverse = sort_order.lower() == 'desc'
            rows.sort(
                key=lambda r: r['metrics'].get(sort_by, float('inf') if not reverse else float('-inf')),
                reverse=reverse,
            )

        # Collect all metric and param keys across all runs
        all_metric_keys = sorted(set(k for r in rows for k in r['metrics']))
        all_param_keys = sorted(set(k for r in rows for k in r['params']))

        return {
            'experiment_id': experiment_id,
            'runs': rows,
            'metric_keys': all_metric_keys,
            'param_keys': all_param_keys,
            'total': len(rows),
        }
    except Exception as e:
        logger.exception("Failed to get leaderboard")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

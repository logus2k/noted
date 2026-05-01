"""Model Registry API - register, list, version, and alias management."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.managers.mlflow_manager import MlflowManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/registry", tags=["registry"])
mlflow_mgr = MlflowManager()


class RegisterModelRequest(BaseModel):
    run_id: str
    artifact_path: str
    model_name: str
    tags: dict | None = None


class AliasRequest(BaseModel):
    alias: str


# ── Models ────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    """List all registered models."""
    try:
        return {'models': mlflow_mgr.list_registered_models()}
    except Exception as e:
        logger.exception("Failed to list models")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/models/register")
def register_model(body: RegisterModelRequest):
    """Register a model from a run's artifacts."""
    try:
        return mlflow_mgr.register_model(
            body.run_id, body.artifact_path, body.model_name, body.tags,
        )
    except Exception as e:
        logger.exception("Failed to register model")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Versions ──────────────────────────────────────────────────

@router.get("/models/{model_name}/versions")
def list_versions(model_name: str):
    """List all versions of a registered model."""
    try:
        return {'versions': mlflow_mgr.list_model_versions(model_name)}
    except Exception as e:
        logger.exception("Failed to list model versions")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/models/{model_name}/versions/{version}")
def get_version(model_name: str, version: str):
    """Get details of a specific model version."""
    try:
        return mlflow_mgr.get_model_version(model_name, version)
    except Exception as e:
        logger.exception("Failed to get model version")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Aliases ───────────────────────────────────────────────────

@router.put("/models/{model_name}/versions/{version}/alias")
def set_alias(model_name: str, version: str, body: AliasRequest):
    """Set an alias on a model version (e.g., champion, staging)."""
    try:
        return mlflow_mgr.set_model_alias(model_name, version, body.alias)
    except Exception as e:
        logger.exception("Failed to set alias")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/models/{model_name}/aliases/{alias}")
def delete_alias(model_name: str, alias: str):
    """Remove an alias from a model."""
    try:
        return mlflow_mgr.delete_model_alias(model_name, alias)
    except Exception as e:
        logger.exception("Failed to delete alias")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/models/{model_name}")
def delete_model(model_name: str):
    """Delete a registered model and all its versions."""
    try:
        return mlflow_mgr.delete_registered_model(model_name)
    except Exception as e:
        logger.exception("Failed to delete model")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/models/{model_name}/versions/{version}")
def delete_model_version(model_name: str, version: str):
    """Delete a specific model version."""
    try:
        return mlflow_mgr.delete_model_version(model_name, version)
    except Exception as e:
        logger.exception("Failed to delete model version")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/models/{model_name}/versions/{version}/artifact-uri")
def resolve_model_artifact_uri(model_name: str, version: str):
    """Resolve the direct artifact URI for a model version (MLflow 3.x compatible)."""
    try:
        return mlflow_mgr.resolve_model_artifact_uri(model_name, version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to resolve model artifact URI")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Lineage ───────────────────────────────────────────────────

@router.get("/models/{model_name}/versions/{version}/lineage")
def get_lineage(model_name: str, version: str):
    """Get the full lineage chain for a model version."""
    try:
        return mlflow_mgr.get_model_lineage(model_name, version)
    except Exception as e:
        logger.exception("Failed to get lineage")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Comparison ────────────────────────────────────────────────

class CompareRequest(BaseModel):
    model_name: str
    version_a: str
    version_b: str


@router.post("/models/compare")
def compare_versions(body: CompareRequest):
    """Compare two model versions side by side."""
    try:
        lineage_a = mlflow_mgr.get_model_lineage(body.model_name, body.version_a)
        lineage_b = mlflow_mgr.get_model_lineage(body.model_name, body.version_b)

        run_a = lineage_a.get('run', {})
        run_b = lineage_b.get('run', {})
        lin_a = lineage_a.get('lineage', {})
        lin_b = lineage_b.get('lineage', {})

        # Metrics diff
        metrics_a = run_a.get('metrics', {}) if run_a else {}
        metrics_b = run_b.get('metrics', {}) if run_b else {}
        all_metric_keys = sorted(set(list(metrics_a.keys()) + list(metrics_b.keys())))
        metrics_diff = []
        for k in all_metric_keys:
            va = metrics_a.get(k)
            vb = metrics_b.get(k)
            delta = None
            if va is not None and vb is not None and isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                delta = vb - va
            metrics_diff.append({'key': k, 'a': va, 'b': vb, 'delta': delta})

        # Params diff
        params_a = run_a.get('params', {}) if run_a else {}
        params_b = run_b.get('params', {}) if run_b else {}
        all_param_keys = sorted(set(list(params_a.keys()) + list(params_b.keys())))
        params_diff = []
        for k in all_param_keys:
            va = params_a.get(k)
            vb = params_b.get(k)
            params_diff.append({'key': k, 'a': va, 'b': vb, 'changed': va != vb})

        return {
            'version_a': body.version_a,
            'version_b': body.version_b,
            'model_name': body.model_name,
            'metrics_diff': metrics_diff,
            'params_diff': params_diff,
            'lineage_a': lin_a,
            'lineage_b': lin_b,
        }
    except Exception as e:
        logger.exception("Failed to compare versions")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

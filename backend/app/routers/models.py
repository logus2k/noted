"""/api/models/* — runtime CRUD for the local-model fleet.

See ModelManager for the heavy lifting; this router is thin.
Documented contract in
documents/performance/phase_12_models_crud_plan.md.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.managers.model_manager import SLOTS, get_model_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])


class SetActiveRequest(BaseModel):
    slot: str = Field(..., description="One of: chat, embed, rerank")
    model_id: str = Field(..., min_length=1)


class SetNameRequest(BaseModel):
    friendly_name: Optional[str] = Field(
        default=None,
        description="User-visible name. Empty/null clears the alias (UI falls back to model id).",
    )


@router.get("")
def list_models() -> dict:
    """Full picture for the Models panel: per-model metadata + active mapping."""
    try:
        return get_model_manager().list_models()
    except Exception as e:
        logger.exception("list_models failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/health")
def models_health() -> dict:
    """Lightweight active-state probe. Suitable for status-bar polling."""
    try:
        return get_model_manager().health()
    except Exception as e:
        logger.exception("models_health failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/{model_id}/load")
def load_model(model_id: str) -> dict:
    try:
        return get_model_manager().load(model_id)
    except Exception as e:
        logger.exception("load_model failed for %s", model_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/{model_id}/unload")
def unload_model(model_id: str) -> dict:
    try:
        return get_model_manager().unload(model_id)
    except PermissionError as e:
        # Baseline model OR currently active — caller needs to switch first
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("unload_model failed for %s", model_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/active")
def set_active(req: SetActiveRequest) -> dict:
    try:
        return get_model_manager().set_active(req.slot, req.model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("set_active failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.put("/{model_id}/name")
def set_friendly_name(model_id: str, req: SetNameRequest) -> dict:
    try:
        return get_model_manager().set_friendly_name(model_id, req.friendly_name)
    except Exception as e:
        logger.exception("set_friendly_name failed for %s", model_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

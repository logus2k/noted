"""Project-level settings API."""

from fastapi import APIRouter, HTTPException
from app.managers import project_settings

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/{project_id}/settings")
def get_settings(project_id: str):
    return project_settings.get_settings(project_id)


@router.put("/{project_id}/settings")
def put_settings(project_id: str, body: dict):
    try:
        return project_settings.update_settings(project_id, body)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

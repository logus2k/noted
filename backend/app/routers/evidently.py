"""Evidently API - proxy endpoints for the Evidently workspace."""

from fastapi import APIRouter
from app.managers.evidently_manager import EvidentlyManager

router = APIRouter(prefix="/api/evidently", tags=["evidently"])

_manager = EvidentlyManager()


@router.get("/health")
async def health():
    return await _manager.health()


@router.get("/projects")
async def list_projects():
    return await _manager.list_projects()


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    return await _manager.get_project(project_id)


@router.get("/projects/{project_id}/reports")
async def list_reports(project_id: str):
    return await _manager.list_reports(project_id)


@router.get("/projects/{project_id}/reports/{run_id}")
async def get_report(project_id: str, run_id: str):
    return await _manager.get_report_data(project_id, run_id)


@router.get("/projects/{project_id}/data-health")
async def data_health(project_id: str):
    return await _manager.get_data_health_status(project_id)


@router.get("/projects/{project_id}/drift-status")
async def drift_status(project_id: str):
    return await _manager.get_drift_status(project_id)

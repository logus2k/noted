import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.managers.notebook_manager import NotebookManager
from app.config import PROJECTS_DIR

router = APIRouter(prefix="/api", tags=["notebooks"])
notebook_mgr = NotebookManager()


class CreateProjectRequest(BaseModel):
    project_id: str


class CreateNotebookRequest(BaseModel):
    name: str
    content: Optional[dict] = None


class RenameProjectRequest(BaseModel):
    new_id: str


class RenameNotebookRequest(BaseModel):
    new_name: str


class UpdateNotebookRequest(BaseModel):
    content: dict


@router.get("/projects")
def list_projects():
    return notebook_mgr.list_projects()


@router.post("/projects")
def create_project(req: CreateProjectRequest):
    try:
        return notebook_mgr.create_project(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    try:
        return notebook_mgr.delete_project(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/projects/{project_id}/rename")
def rename_project(project_id: str, req: RenameProjectRequest):
    try:
        return notebook_mgr.rename_project(project_id, req.new_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/notebooks")
def list_notebooks(project_id: str):
    return notebook_mgr.list_notebooks(project_id)


@router.get("/projects/{project_id}/notebooks/{notebook_name}")
def get_notebook(project_id: str, notebook_name: str):
    try:
        return notebook_mgr.get_notebook(project_id, notebook_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/projects/{project_id}/notebooks/{notebook_name}/summary")
def notebook_summary(project_id: str, notebook_name: str):
    try:
        return notebook_mgr.notebook_summary(project_id, notebook_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/notebooks")
def create_notebook(project_id: str, req: CreateNotebookRequest):
    try:
        return notebook_mgr.create_notebook(project_id, req.name, req.content)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/projects/{project_id}/notebooks/{notebook_name}")
def update_notebook(project_id: str, notebook_name: str, req: UpdateNotebookRequest):
    try:
        return notebook_mgr.update_notebook(project_id, notebook_name, req.content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/projects/{project_id}/notebooks/{notebook_name}/rename")
def rename_notebook(project_id: str, notebook_name: str, req: RenameNotebookRequest):
    try:
        return notebook_mgr.rename_notebook(project_id, notebook_name, req.new_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}/notebooks/{notebook_name}")
def delete_notebook(project_id: str, notebook_name: str):
    try:
        return notebook_mgr.delete_notebook(project_id, notebook_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/projects/{project_id}/files/{file_path:path}")
def get_project_file(project_id: str, file_path: str):
    """Serve files (images, etc.) from a project's notebooks directory."""
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    full_path = os.path.realpath(
        os.path.join(PROJECTS_DIR, project_id, "notebooks", file_path)
    )
    # Ensure resolved path stays within the project directory
    project_dir = os.path.realpath(os.path.join(PROJECTS_DIR, project_id))
    if not full_path.startswith(project_dir + os.sep) and full_path != project_dir:
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)

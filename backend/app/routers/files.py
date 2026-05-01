"""Generic filesystem API — replaces separate notebooks/src endpoints for browsing."""

import os
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.managers.file_manager import FileManager
from app.managers import config_manager

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

router = APIRouter(prefix="/api/files", tags=["files"])
file_mgr = FileManager()


# ── Discovery: projects, mounts, git repos ───────────────────────────
# IMPORTANT: These specific routes must come BEFORE the parameterized
# /{root_type}/{root_name} routes to avoid being swallowed by them.

@router.get("/")
def list_roots():
    """List all projects and mounts."""
    mounts = file_mgr.list_mounts()
    # Enrich with host_path from config
    cfg_mounts = {m["name"]: m.get("host_path", "") for m in config_manager.get_mounts()}
    for m in mounts:
        m["host_path"] = cfg_mounts.get(m["name"], "")
    return {
        "projects": file_mgr.list_projects(),
        "mounts": mounts,
    }


@router.get("/git/repos")
def discover_git_repos():
    """Discover all git repositories across projects and mounts."""
    return file_mgr.discover_git_repos()


# ── Mount management ─────────────────────────────────────────────────

@router.get("/mounts/config")
def get_mounts_config():
    """Get configured mounts from NOTED.md."""
    return {"mounts": config_manager.get_mounts()}


class AddMountRequest(BaseModel):
    name: str
    host_path: str


@router.post("/mounts/config")
def add_mount(body: AddMountRequest):
    """Add a new mount and update docker-compose.yml."""
    try:
        result = config_manager.add_mount(body.name, body.host_path)
        # Also generate the compose update info
        compose_info = config_manager.get_docker_compose_update()
        result["volumes"] = compose_info["volumes"]
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RemoveMountRequest(BaseModel):
    name: str


@router.delete("/mounts/config")
def remove_mount(body: RemoveMountRequest):
    """Remove a mount and update docker-compose.yml."""
    try:
        result = config_manager.remove_mount(body.name)
        compose_info = config_manager.get_docker_compose_update()
        result["volumes"] = compose_info["volumes"]
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateComposeRequest(BaseModel):
    compose_path: str


@router.post("/mounts/apply")
def apply_mounts(body: UpdateComposeRequest):
    """Update docker-compose.yml with current mount configuration."""
    try:
        return config_manager.update_docker_compose(body.compose_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── File upload (auth-gated) ──────────────────────────────────────────

@router.post("/upload/{root_type}/{root_name}")
async def upload_file(
    root_type: str,
    root_name: str,
    file: UploadFile = File(...),
    path: str = Form(""),
    x_terminal_secret: Optional[str] = Header(None, alias="X-Terminal-Secret"),
):
    """Upload a file to a project or mount directory. Requires terminal access key."""
    # Auth check
    secret = os.environ.get("NOTED_TERMINAL_SECRET", "")
    if secret and x_terminal_secret != secret:
        raise HTTPException(status_code=401, detail="Invalid access key")

    # Size check
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_SIZE // (1024*1024)} MB)")

    # Resolve target path
    try:
        root = file_mgr._resolve_root(root_type, root_name)
        rel = os.path.join(path, file.filename) if path else file.filename
        filepath = file_mgr._secure_path(root, rel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Write file
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(contents)

    return {
        "uploaded": True,
        "path": os.path.relpath(filepath, root),
        "size": len(contents),
        "filename": file.filename,
    }


# ── Parameterized routes (must come AFTER specific routes) ───────────

# ── List directory contents (lazy loading) ───────────────────────────

@router.get("/{root_type}/{root_name}")
def list_dir(root_type: str, root_name: str,
             path: str = Query("", alias="path")):
    """List directory contents for lazy-loading tree expansion."""
    try:
        return file_mgr.list_dir(root_type, root_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Read file ────────────────────────────────────────────────────────

@router.get("/{root_type}/{root_name}/read")
def read_file(root_type: str, root_name: str,
              path: str = Query(...)):
    """Read a file's contents."""
    try:
        return file_mgr.read_file(root_type, root_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Serve raw file (for images, etc.) ────────────────────────────────

@router.get("/{root_type}/{root_name}/raw")
def serve_file(root_type: str, root_name: str,
               path: str = Query(...)):
    """Serve a file directly (for images, assets, etc.)."""
    try:
        root = file_mgr._resolve_root(root_type, root_name)
        filepath = file_mgr._secure_path(root, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import os
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)


# ── Write / update file ─────────────────────────────────────────────

class WriteRequest(BaseModel):
    content: str


@router.put("/{root_type}/{root_name}/write")
def write_file(root_type: str, root_name: str,
               body: WriteRequest, path: str = Query(...)):
    """Write text content to a file."""
    try:
        return file_mgr.write_file(root_type, root_name, path, body.content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Create file or folder ───────────────────────────────────────────

class CreateRequest(BaseModel):
    path: str
    is_dir: bool = False
    content: str = ""


@router.post("/{root_type}/{root_name}")
def create_entry(root_type: str, root_name: str, body: CreateRequest):
    """Create a new file or directory."""
    try:
        return file_mgr.create(root_type, root_name, body.path,
                               body.is_dir, body.content)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Delete file or folder ───────────────────────────────────────────

@router.delete("/{root_type}/{root_name}")
def delete_entry(root_type: str, root_name: str,
                 path: str = Query(...)):
    """Delete a file or directory."""
    try:
        return file_mgr.delete(root_type, root_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Rename ───────────────────────────────────────────────────────────

class RenameRequest(BaseModel):
    new_name: str


@router.put("/{root_type}/{root_name}/rename")
def rename_entry(root_type: str, root_name: str,
                 body: RenameRequest, path: str = Query(...)):
    """Rename a file or directory."""
    try:
        return file_mgr.rename(root_type, root_name, path, body.new_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

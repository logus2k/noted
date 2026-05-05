"""Generic filesystem API — replaces separate notebooks/src endpoints for browsing."""

import os
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.managers.file_manager import FileManager
from app.managers import config_manager

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB — terminal-secret-gated upload (existing endpoint)

# ── Chat-input asset upload config (image / audio / document) ─────────
# Cap is read from NOTED_MAX_UPLOAD_MB env var (services/.env). Same
# value is used server-side for enforcement and exposed via
# GET /api/files/upload-config so the frontend can pre-validate.
# Whitelists are intentionally narrow: no executables, no scripts, no
# archives — uploads from the chat input are user-content payloads, not
# code distribution.
def _max_upload_mb() -> int:
    try:
        return max(1, int(os.environ.get("NOTED_MAX_UPLOAD_MB", "20")))
    except (TypeError, ValueError):
        return 20


def _chat_context_max_chars() -> int:
    """Cap on per-attachment text length when a file is attached to the
    chat as in-context (NOT to the KB). Read by the frontend extractor
    registry to truncate before sending; also enforceable server-side
    later if a wire-level guard becomes useful."""
    try:
        return max(1000, int(os.environ.get("NOTED_CHAT_CONTEXT_MAX_CHARS", "50000")))
    except (TypeError, ValueError):
        return 50000


# Extensions the chat-context "Attach file" path treats as plain text.
# Distinct from KB's ALLOWED_DOCUMENT_EXTS — context-attach reads bytes
# client-side as text via FileReader and never persists, so the threat
# model is "could this file be parsed as text" not "could this be
# executed". Code files are deliberately included; the BLOCKED_EXTS
# server-side guard does not apply because nothing is uploaded.
ALLOWED_CONTEXT_TEXT_EXTS = [
    # Plain text + markdown
    '.txt', '.md', '.markdown', '.rst',
    # Data formats
    '.json', '.csv', '.tsv', '.xml', '.yaml', '.yml', '.toml', '.ini',
    '.cfg', '.conf', '.env', '.log', '.properties',
    # Web / styling
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    # Code (read as text only — never executed by frontend)
    '.py', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.vue', '.svelte',
    '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.cc', '.cs',
    '.java', '.kt', '.kts', '.swift', '.rb', '.php', '.lua',
    '.sh', '.bash', '.zsh', '.fish', '.ps1',
    '.sql', '.r', '.m', '.dart', '.scala', '.clj', '.cljs',
    '.ex', '.exs', '.erl', '.pl', '.f', '.f90',
]

ALLOWED_IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.heif', '.svg']
ALLOWED_AUDIO_EXTS = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.opus', '.webm', '.mp4']

# Mirrors the KB document_converter whitelist (corpus.add_uploaded_file
# in noted-rag). Kept aligned so a "Document" upload through the + menu
# is a strict subset of what the KB ingestion accepts.
ALLOWED_DOCUMENT_EXTS = ['.md', '.pdf', '.docx', '.pptx', '.html', '.htm', '.txt']

# Defense-in-depth: even if the whitelist is bypassed (e.g., file
# renamed to a permitted extension), refuse anything in the deny set
# regardless of advertised extension. Catches double-extension tricks
# like "innocent.pdf.exe".
BLOCKED_EXTS = {
    '.exe', '.dll', '.so', '.dylib', '.bat', '.cmd', '.com', '.scr', '.msi',
    '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
    '.sh', '.bash', '.zsh', '.fish', '.app', '.deb', '.rpm', '.dmg',
    '.jar', '.class', '.war', '.ear',
    '.py', '.pyc', '.pyo', '.rb', '.pl', '.php', '.phtml', '.cgi',
    '.lnk', '.url', '.iso', '.img',
}

router = APIRouter(prefix="/api/files", tags=["files"])
file_mgr = FileManager()


@router.get("/upload-config")
def get_upload_config():
    """Configuration for chat-input asset uploads. Frontend reads this
    once at init to populate file-picker accept lists and to do
    client-side size validation BEFORE the network round-trip."""
    return {
        "max_size_mb": _max_upload_mb(),
        "image_extensions": ALLOWED_IMAGE_EXTS,
        "audio_extensions": ALLOWED_AUDIO_EXTS,
        "document_extensions": ALLOWED_DOCUMENT_EXTS,
        "chat_context_text_extensions": ALLOWED_CONTEXT_TEXT_EXTS,
        "chat_context_max_chars": _chat_context_max_chars(),
    }


def _ext_lower(filename: str) -> str:
    if '.' not in filename:
        return ''
    return '.' + filename.rsplit('.', 1)[-1].lower()


def _validate_upload(file: UploadFile, kind: str) -> tuple[str, list[str]]:
    """Validate kind + filename + extension. Returns (safe_ext, allowed_list).
    Raises HTTPException on rejection. Does NOT read file bytes."""
    if kind not in ('image', 'audio', 'document'):
        raise HTTPException(status_code=400, detail=f"Invalid kind '{kind}' (allowed: image, audio, document)")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    # Reject path-injection attempts in the filename (defense in depth;
    # _secure_path also normalises but we want to fail fast).
    if any(c in file.filename for c in ('/', '\\', '\x00')) or '..' in file.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = _ext_lower(file.filename)
    if not ext:
        raise HTTPException(status_code=400, detail="Filename has no extension")
    if ext in BLOCKED_EXTS:
        raise HTTPException(status_code=400, detail=f"Extension '{ext}' is not permitted (executable / script / archive)")
    allowed = {
        'image': ALLOWED_IMAGE_EXTS,
        'audio': ALLOWED_AUDIO_EXTS,
        'document': ALLOWED_DOCUMENT_EXTS,
    }[kind]
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '{ext}' is not allowed for kind '{kind}'. Allowed: {', '.join(allowed)}",
        )
    return ext, allowed


@router.post("/upload-asset")
async def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form(...),
    project_id: str = Form(...),
):
    """Chat-input asset upload (image / audio / document) into the
    current project's `assets/<kind>s/` subdirectory.

    Differs from the auth-gated `/upload/{root_type}/{root_name}`:
      - No terminal-secret header required (chat-input is part of
        normal user interaction, not a privileged terminal operation).
      - Hard size cap from NOTED_MAX_UPLOAD_MB env var (default 20 MB)
        instead of the 500 MB terminal-upload cap.
      - Extension whitelist enforced per `kind`, plus a deny list of
        executable / script / archive extensions regardless of kind.
      - Auto-routes into project assets folder by kind so files stay
        organised.
    """
    _ext_lower(file.filename or '')  # touch to keep the helper used
    _validate_upload(file, kind)

    # Read with a hard ceiling. We could stream-and-bail, but for a
    # 20 MB cap a one-shot read is simpler and safe. If the env cap
    # ever climbs above ~50 MB, switch to streaming.
    max_bytes = _max_upload_mb() * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(contents) // (1024*1024)} MB > {_max_upload_mb()} MB limit). "
                   "Adjust NOTED_MAX_UPLOAD_MB in services/.env if you need a higher cap.",
        )

    # Resolve target inside the project root. _secure_path enforces no
    # escape (no ../ traversal, no absolute paths).
    try:
        root = file_mgr._resolve_root("project", project_id)
        subdir = {
            'image': 'assets/images',
            'audio': 'assets/audio',
            'document': 'assets/documents',
        }[kind]
        rel = os.path.join(subdir, file.filename)
        filepath = file_mgr._secure_path(root, rel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # Disambiguate filename collisions (file.png, file (1).png, ...)
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        n = 1
        while os.path.exists(f"{base} ({n}){ext}"):
            n += 1
        filepath = f"{base} ({n}){ext}"
    with open(filepath, "wb") as f:
        f.write(contents)

    return {
        "uploaded": True,
        "kind": kind,
        "project_id": project_id,
        "path": os.path.relpath(filepath, root),
        "size": len(contents),
        "filename": os.path.basename(filepath),
    }


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

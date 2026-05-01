import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.managers.document_manager import DocumentManager, DOCUMENTS_DIR

router = APIRouter(prefix="/api", tags=["documents"])
doc_mgr = DocumentManager()


class RemoveDocumentRequest(BaseModel):
    name: str
    category: str


class RenameDocumentRequest(BaseModel):
    name: str
    category: str
    new_name: str


@router.get("/documents")
def list_documents():
    """Return the full document catalog."""
    return doc_mgr.list_documents()


@router.get("/documents/categories")
def list_categories():
    """Return list of document categories."""
    return doc_mgr.list_categories()


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(""),
):
    """Upload a file and register it in the catalog."""
    filename = file.filename or "untitled"
    # Sanitize filename
    safe_name = "".join(c for c in filename if c.isalnum() or c in ".-_ ").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in (".md", ".pdf", ".txt", ".rst"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    files_dir = doc_mgr.ensure_files_dir()
    dest = os.path.join(files_dir, safe_name)

    # Avoid overwriting
    if os.path.exists(dest):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest):
            safe_name = f"{base}_{counter}{ext}"
            dest = os.path.join(files_dir, safe_name)
            counter += 1

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        result = doc_mgr.add_document(name, category, safe_name)
        return result
    except FileExistsError as e:
        # Clean up uploaded file
        os.remove(dest)
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/documents")
def remove_document(req: RemoveDocumentRequest):
    """Remove a document from the catalog and delete the file."""
    try:
        return doc_mgr.remove_document(req.name, req.category)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/documents/rename")
def rename_document(req: RenameDocumentRequest):
    """Rename a document in the catalog."""
    try:
        return doc_mgr.rename_document(req.name, req.category, req.new_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/files/{file_path:path}")
def serve_document_file(file_path: str):
    """Serve a document file (PDF, MD, etc.) from a Domain's sources/ dir.

    URL shape: /api/documents/files/<domain_id>/<rel_path>
    Resolves to: data/domains/<domain_id>/sources/<rel_path>

    The legacy flat layout (data/documents/files/<name>) was retired when
    uploads moved to per-Domain `data/domains/<id>/sources/`. The endpoint
    URL is preserved so the DocumentViewer + onDocumentPreview wiring keeps
    working without changes; only the resolution logic moved.
    """
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    parts = file_path.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise HTTPException(
            status_code=400,
            detail="Path must be <domain_id>/<rel_path>",
        )
    domain_id, rel_path = parts
    from app.config import DATA_DIR
    sources_dir = os.path.realpath(
        os.path.join(DATA_DIR, "domains", domain_id, "sources")
    )
    full_path = os.path.realpath(os.path.join(sources_dir, rel_path))
    if not full_path.startswith(sources_dir + os.sep) and full_path != sources_dir:
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)

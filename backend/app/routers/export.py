import logging
import tempfile
import shutil
from pathlib import Path
from typing import Literal, Optional

import nbformat as nbf
from nbconvert import HTMLExporter, MarkdownExporter
from traitlets.config import Config
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.config import PROJECTS_DIR, MOUNTS_DIR
from app.managers.document_converter import DocumentConverter, ConversionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


def _resolve_notebook_path(project_id: str, notebook_path: str) -> Path:
    """Resolve project_id + relative notebook_path to absolute filesystem path."""
    from app.managers.project_registry import get_registry
    base = Path(get_registry().resolve(project_id))
    return base / notebook_path


class WordExportRequest(BaseModel):
    project_id: str
    notebook_path: str
    hide_code: bool = False
    keep_text: bool = False
    include_toc: bool = False
    paper_size: Literal["A4", "Letter"] = "A4"
    header_text: Optional[str] = None
    page_number_pos: str = "right"
    show_page_word: bool = False
    text_align: str = "justify"
    font_family: str = "Aptos"
    font_size_body: int = 12
    font_size_table: int = 11
    font_size_code: int = 10
    font_size_header: int = 9
    resize_images: bool = True
    resize_tables: bool = True


class SimpleExportRequest(BaseModel):
    project_id: str
    notebook_path: str
    hide_code: bool = False


@router.post("/word")
def export_word(req: WordExportRequest):
    """Export a notebook to DOCX using the DocumentConverter pipeline."""
    nb_path = _resolve_notebook_path(req.project_id, req.notebook_path)
    if not nb_path.is_file():
        raise HTTPException(status_code=404, detail=f"Notebook not found: {req.notebook_path}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="noted_export_"))
    try:
        converter = DocumentConverter(
            hide_code=req.hide_code,
            keep_text=req.keep_text,
            include_toc=req.include_toc,
            paper_size=req.paper_size,
            header_text=req.header_text,
            page_number_pos=req.page_number_pos,
            show_page_word=req.show_page_word,
            text_align=req.text_align,
            font_family=req.font_family,
            font_size_body=req.font_size_body,
            font_size_table=req.font_size_table,
            font_size_code=req.font_size_code,
            font_size_header=req.font_size_header,
            resize_images=req.resize_images,
            resize_tables=req.resize_tables,
        )
        result = converter.convert(nb_path, output_dir=tmp_dir)
        if result.docx is None or not result.docx.exists():
            raise HTTPException(status_code=500, detail="Conversion produced no output file")

        download_name = nb_path.stem + ".docx"
        return FileResponse(
            path=str(result.docx),
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        )
    except ConversionError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Export to Word failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/markdown")
def export_markdown(req: SimpleExportRequest):
    """Export a notebook to Markdown via nbconvert."""
    nb_path = _resolve_notebook_path(req.project_id, req.notebook_path)
    if not nb_path.is_file():
        raise HTTPException(status_code=404, detail=f"Notebook not found: {req.notebook_path}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="noted_export_"))
    try:
        nb = nbf.read(str(nb_path), as_version=4)
        c = Config()
        c.MarkdownExporter.exclude_input_prompt = True
        c.MarkdownExporter.exclude_output_prompt = True
        if req.hide_code:
            c.MarkdownExporter.exclude_input = True

        exporter = MarkdownExporter(config=c)
        body, resources = exporter.from_notebook_node(nb)

        out_path = tmp_dir / (nb_path.stem + ".md")
        out_path.write_text(body, encoding="utf-8")

        # Write any extracted images alongside the markdown
        for fname, data in resources.get("outputs", {}).items():
            img_path = tmp_dir / fname
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(data)

        return FileResponse(
            path=str(out_path),
            filename=nb_path.stem + ".md",
            media_type="text/markdown",
            background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        )
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Export to Markdown failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/html")
def export_html(req: SimpleExportRequest):
    """Export a notebook to HTML via nbconvert."""
    nb_path = _resolve_notebook_path(req.project_id, req.notebook_path)
    if not nb_path.is_file():
        raise HTTPException(status_code=404, detail=f"Notebook not found: {req.notebook_path}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="noted_export_"))
    try:
        nb = nbf.read(str(nb_path), as_version=4)
        c = Config()
        c.HTMLExporter.exclude_input_prompt = True
        c.HTMLExporter.exclude_output_prompt = True
        if req.hide_code:
            c.HTMLExporter.exclude_input = True

        exporter = HTMLExporter(config=c)
        body, _ = exporter.from_notebook_node(nb)

        out_path = tmp_dir / (nb_path.stem + ".html")
        out_path.write_text(body, encoding="utf-8")

        return FileResponse(
            path=str(out_path),
            filename=nb_path.stem + ".html",
            media_type="text/html",
            background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        )
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Export to HTML failed")
        raise HTTPException(status_code=500, detail=str(exc))



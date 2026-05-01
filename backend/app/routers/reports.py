"""Experiment Report API - generate experiment comparison reports."""

import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.managers.report_generator import ReportGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])
report_gen = ReportGenerator()


@router.get("/experiment/{experiment_id}")
def generate_report(
    experiment_id: str,
    format: str = Query(default='word', description='word or markdown'),
    sort_by: str = Query(default='', description='Metric key to sort by'),
    sort_order: str = Query(default='asc', description='asc or desc'),
    top_n: int = Query(default=10, description='Number of top runs to include'),
):
    """Generate an experiment comparison report."""
    try:
        output_path = report_gen.generate(
            experiment_id, top_n=top_n,
            sort_by=sort_by, sort_order=sort_order,
            format=format,
        )

        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Report generation produced no output")

        media_type = (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            if output_path.suffix == '.docx'
            else 'text/markdown'
        )
        filename = output_path.name

        return FileResponse(
            path=str(output_path),
            filename=filename,
            media_type=media_type,
            background=BackgroundTask(shutil.rmtree, output_path.parent, True),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to generate report")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

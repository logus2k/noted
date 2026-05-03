"""PDF / DOCX / PPTX / HTML scanner via Docling.

Produces extraction-scale chunks with full provenance (page_no + bbox)
back to the source document. Output schema matches md_scanner.MdChunk
so downstream entity-extraction + storage paths are unchanged - the
only difference is that chunks coming through this path carry non-null
page_no / bbox / section_level fields.

Dispatch (file extension -> scanner) is the responsibility of the
per-doc add path; this module is just the format adapter for
non-markdown sources.

Docling models (TableFormer + layout) are large and expensive to load,
so the converter and chunker are constructed lazily on first call and
reused for the lifetime of the process. The model cache is bind-mounted
at /root/.cache/docling so weights survive container rebuilds.
"""

from __future__ import annotations

import logging
import os

from app.config import (
    DOCLING_MAX_PAGES,
    DOCLING_OCR,
    DOCLING_TABLE_MODE,
    EXTRACT_CHUNK_TARGET_TOKENS,
)
from app.scanners.md_scanner import MdChunk

logger = logging.getLogger(__name__)

# Drop chunks whose underlying doc_items are mostly TOC / index entries.
# Docling's layout model already classifies these as DocItemLabel.DOCUMENT_INDEX,
# so we just filter on the label — no string heuristics, no language coupling.
# Default ratio = 1.0 means "only drop chunks that are 100 % DOCUMENT_INDEX
# items" (strict, near-zero false positives). Lower to 0.5 for majority vote
# if mixed-content TOC merges become a problem in practice. Set to 0.0
# (or any negative value) to disable the filter entirely.
TOC_FILTER_RATIO: float = float(os.environ.get('TOC_FILTER_RATIO', '1.0'))


_converter = None
_chunker = None


def _ensure_loaded() -> None:
    """Lazy-init Docling converter + chunker. Idempotent."""
    global _converter, _chunker
    if _converter is not None:
        return

    # Imported lazily so module import is free even when no PDFs are
    # ingested in a given process (e.g. during a markdown-only rebuild).
    from docling.chunking import HybridChunker
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # PdfPipelineOptions.do_ocr defaults to True, which causes Docling to
    # eagerly load RapidOCR (~40 MB of weights into the container's
    # site-packages, NOT our cache mount). Honor DOCLING_OCR explicitly.
    #
    # artifacts_path: point Docling at the bind-mounted on-disk model
    # cache. Without this, Docling falls back to ~/.cache/huggingface/hub
    # which is NOT bind-mounted, so every container rebuild re-downloads
    # ~3 GB of layout/tableformer/figure-classifier weights from HF. The
    # on-disk layout under /data/models/docling/models/ matches Docling's
    # `artifacts_path` format (`<repo_id_with_dashes>/`), populated once
    # on the host. Guarded with isdir() so missing-mount falls back to
    # the default behavior instead of breaking.
    artifacts_root = '/data/models/docling/models'
    pdf_opts = PdfPipelineOptions(
        do_ocr=DOCLING_OCR,
        artifacts_path=artifacts_root if os.path.isdir(artifacts_root) else None,
    )

    _converter = DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.DOCX,
            InputFormat.PPTX,
            InputFormat.HTML,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
        },
    )
    # Tokenizer: prefer the on-disk bge-m3 (under the bind-mounted models
    # tree); fall back to the HF id only if the local copy is missing.
    # Without this, HybridChunker calls HuggingFace on every container
    # restart for the tokenizer config files even though the full model
    # is on disk.
    bge_m3_local = '/data/models/bge-m3'
    _chunker = HybridChunker(
        tokenizer=bge_m3_local if os.path.isdir(bge_m3_local) else 'BAAI/bge-m3',
        max_tokens=EXTRACT_CHUNK_TARGET_TOKENS,
        merge_peers=True,
    )
    logger.info(
        'Docling loaded: table_mode=%s ocr=%s max_pages=%s tokenizer=bge-m3 max_tokens=%d',
        DOCLING_TABLE_MODE, DOCLING_OCR, DOCLING_MAX_PAGES,
        EXTRACT_CHUNK_TARGET_TOKENS,
    )


def scan_pdf(abs_path: str, repo_root: str | None = None) -> list[MdChunk]:
    """Convert one PDF (or DOCX / PPTX / HTML) into MdChunk instances.

    Returned chunks carry the same fields as md_scanner output plus the
    optional provenance trio (page_no, bbox, section_level). Caller
    appends the same Entity + chunked_into edges as for markdown chunks.

    `repo_root` is the Domain's sources/ directory so doc_path comes out
    Domain-relative (e.g. `foo.pdf`). Required in production paths;
    callers compute it via `corpus.sources_dir(domain_id)`. When omitted
    (tests), doc_path falls back to the file's basename.

    Raises ValueError if the document exceeds DOCLING_MAX_PAGES (a safety
    cap against runaway uploads).
    """
    _ensure_loaded()
    if repo_root:
        rel_path = os.path.relpath(abs_path, repo_root)
    else:
        rel_path = os.path.basename(abs_path)

    result = _converter.convert(abs_path)
    doc = result.document  # DoclingDocument

    page_count = len(getattr(doc, 'pages', []) or [])
    if DOCLING_MAX_PAGES and page_count > DOCLING_MAX_PAGES:
        raise ValueError(
            f'page count {page_count} exceeds DOCLING_MAX_PAGES={DOCLING_MAX_PAGES} for {rel_path}'
        )

    # Lazy-import the label enum so module import stays Docling-free.
    from docling_core.types.doc import DocItemLabel

    chunks: list[MdChunk] = []
    n_toc_dropped = 0
    for i, raw in enumerate(_chunker.chunk(doc)):
        text = raw.text or ''
        if not text.strip():
            continue

        # TOC / document-index filter. Drops chunks whose constituent
        # doc_items are mostly DOCUMENT_INDEX (Docling's TOC label). At
        # the default TOC_FILTER_RATIO=1.0, only fully-TOC chunks are
        # skipped; raise/lower via env var. Indexes pollute retrieval
        # (no semantic content) and graph extraction (one entity per
        # heading) without adding signal.
        items = raw.meta.doc_items or []
        if items and TOC_FILTER_RATIO > 0:
            n_toc = sum(1 for it in items if getattr(it, 'label', None) == DocItemLabel.DOCUMENT_INDEX)
            if n_toc / len(items) >= TOC_FILTER_RATIO:
                n_toc_dropped += 1
                continue

        first_item = raw.meta.doc_items[0] if raw.meta.doc_items else None
        prov = first_item.prov[0] if first_item and first_item.prov else None
        section_path = ' > '.join(raw.meta.headings or []) or '(root)'

        # HybridChunker(merge_peers=True) merges adjacent doc_items into one
        # chunk. Two consequences:
        #   1. Marginalia labels and cross-reference glyphs are extracted by
        #      Docling as their own (tiny) doc_items and get merged with the
        #      body paragraph. Taking only the first prov's bbox highlighted
        #      a 50x5pt margin label instead of the body.
        #   2. A merged chunk can span page breaks. The body of one
        #      paragraph may end on page N+1 while its earlier doc_items
        #      sit on page N.
        # Group every prov by page_no, union the bboxes per page, and emit
        # `regions` so the deep-jump highlight can paint a rectangle on
        # each page the chunk touches. `page_no`/`bbox` mirror regions[0]
        # for code paths that still consume the single-region fields.
        regions: list[dict] | None = None
        bbox = None
        page_no = None
        per_page_bboxes: dict[int, list[tuple[float, float, float, float]]] = {}
        first_page_seen: int | None = None
        for item in (raw.meta.doc_items or []):
            for p in (getattr(item, 'prov', None) or []):
                p_page = getattr(p, 'page_no', None)
                bb = getattr(p, 'bbox', None)
                if p_page is None or bb is None:
                    continue
                try:
                    tup = tuple(float(v) for v in bb.as_tuple())
                except Exception:
                    continue
                per_page_bboxes.setdefault(int(p_page), []).append(tup)
                if first_page_seen is None:
                    first_page_seen = int(p_page)
        if per_page_bboxes:
            # Region order: first page seen first (matches reading order),
            # then any other pages sorted ascending. Deep-jump scrolls to
            # regions[0] so this picks the earliest-touched page.
            other_pages = sorted(p for p in per_page_bboxes if p != first_page_seen)
            ordered_pages = [first_page_seen] + other_pages
            regions = []
            for p_page in ordered_pages:
                bbs = per_page_bboxes[p_page]
                xs0 = [b[0] for b in bbs]; ys0 = [b[1] for b in bbs]
                xs1 = [b[2] for b in bbs]; ys1 = [b[3] for b in bbs]
                regions.append({
                    'page_no': p_page,
                    'bbox': [min(xs0), min(ys0), max(xs1), max(ys1)],
                })
            page_no = regions[0]['page_no']
            bbox = regions[0]['bbox']

        section_level = getattr(raw.meta, 'headings_level', None)

        chunks.append(MdChunk(
            doc_path=rel_path,
            chunk_index=i,
            section_path=section_path,
            text=text,
            token_count=_chunker.tokenizer.count_tokens(text),
            page_no=int(page_no) if page_no is not None else None,
            bbox=bbox,
            regions=regions,
            section_level=int(section_level) if section_level is not None else None,
        ))

    logger.info(
        'pdf scan: %s -> %d chunks across %d pages (toc_dropped=%d, ratio=%.2f)',
        rel_path, len(chunks), page_count, n_toc_dropped, TOC_FILTER_RATIO,
    )
    return chunks

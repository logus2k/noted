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

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.config import (
    DOC_DESCRIPTION_PARALLELISM,
    DOCLING_MAX_PAGES,
    DOCLING_OCR,
    DOCLING_TABLE_MODE,
    ENABLE_DOC_DESCRIPTIONS,
    EXTRACT_CHUNK_TARGET_TOKENS,
    PICTURE_DESCRIPTION_MIN_AREA_PX,
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
        # Generate the actual cropped image bytes for every PictureItem so
        # the captioner can send them to the vision LLM. Off by default in
        # Docling because most consumers don't need the bytes; we do when
        # ENABLE_DOC_DESCRIPTIONS is on.
        generate_picture_images=ENABLE_DOC_DESCRIPTIONS,
        # Image scale: the default (1.0) yields ~72 DPI. The vision encoder
        # benefits from a slightly higher resolution for charts / diagrams
        # without ballooning the payload.
        images_scale=2.0 if ENABLE_DOC_DESCRIPTIONS else 1.0,
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


def scan_pdf(
    abs_path: str,
    repo_root: str | None = None,
    progress_writer: Callable[[dict], None] | None = None,
) -> list[MdChunk]:
    """Convert one PDF (or DOCX / PPTX / HTML) into MdChunk instances.

    Returned chunks carry the same fields as md_scanner output plus the
    optional provenance trio (page_no, bbox, section_level). Caller
    appends the same Entity + chunked_into edges as for markdown chunks.

    `repo_root` is the Domain's sources/ directory so doc_path comes out
    Domain-relative (e.g. `foo.pdf`). Required in production paths;
    callers compute it via `corpus.sources_dir(domain_id)`. When omitted
    (tests), doc_path falls back to the file's basename.

    `progress_writer` is an optional callable that merges its dict argument
    into the caller's progress dict. Used during the picture/table
    captioning pass to surface live `sub_phase` data + persistent
    `pictures_total` / `tables_total` etc. counters in the KB Monitor.
    Wrapped in try/except so a misbehaving consumer never breaks scanning.

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

    # ── Picture + table captioning pass (Path A) ──────────────────────
    # When ENABLE_DOC_DESCRIPTIONS is on, walk every PictureItem and
    # TableItem in the converted doc, generate an LLM caption for each,
    # and stash the result in a manifest keyed by the item's `self_ref`.
    # The chunk loop below consults this manifest to inject captions
    # into the appropriate chunks (or emit standalone caption chunks
    # for orphan pictures whose chunks would otherwise be empty).
    caption_manifest: dict[str, dict[str, Any]] = _build_caption_manifest(
        doc, rel_path, progress_writer,
    )

    # Track which manifest entries got consumed by the chunk loop, so we
    # know which orphan items still need standalone chunks at the end.
    consumed_self_refs: set[str] = set()

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

        # Inject captions for any PictureItem/TableItem this chunk
        # contains. Caption text is prepended so it acts as framing for
        # the (sparse) cell content or surrounding prose. `kind` flips
        # to 'picture_caption' / 'table_caption' only when the chunk is
        # exclusively that one item — i.e. the caption IS the chunk's
        # primary content. Mixed chunks (table + paragraph, picture +
        # text) stay 'text' because the prose framing remains the
        # dominant content; the caption is supplementary.
        chunk_kind, caption_for, caption_text = _resolve_chunk_caption(
            raw.meta.doc_items or [], caption_manifest,
        )
        if caption_text:
            text = caption_text + '\n\n' + text
            for it in (raw.meta.doc_items or []):
                ref = getattr(it, 'self_ref', None)
                if ref and ref in caption_manifest:
                    consumed_self_refs.add(ref)

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
            kind=chunk_kind,
            caption_for=caption_for,
        ))

    # ── Orphan caption chunks ──────────────────────────────────────────
    # Pictures with no surrounding text get dropped by the chunker (text
    # was empty). Emit standalone caption chunks for them so the picture
    # is still indexable, citable, and bbox-highlightable. Same applies
    # to any TableItem whose chunk got filtered out — rare but possible.
    next_idx = len(chunks)
    for self_ref, entry in caption_manifest.items():
        if self_ref in consumed_self_refs:
            continue
        prov = entry.get('prov')
        page_no = prov.get('page_no') if prov else None
        bbox = prov.get('bbox') if prov else None
        regions = [{'page_no': page_no, 'bbox': bbox}] if (page_no and bbox) else None
        caption = entry.get('caption') or ''
        if not caption.strip():
            continue
        chunks.append(MdChunk(
            doc_path=rel_path,
            chunk_index=next_idx,
            section_path=entry.get('section_path') or '(root)',
            text=caption,
            token_count=_chunker.tokenizer.count_tokens(caption),
            page_no=int(page_no) if page_no is not None else None,
            bbox=bbox,
            regions=regions,
            section_level=None,
            kind=entry.get('kind') or 'text',
            caption_for=self_ref,
        ))
        next_idx += 1

    logger.info(
        'pdf scan: %s -> %d chunks across %d pages (toc_dropped=%d, ratio=%.2f, captions=%d)',
        rel_path, len(chunks), page_count, n_toc_dropped, TOC_FILTER_RATIO,
        sum(1 for c in chunks if c.kind in ('picture_caption', 'table_caption')),
    )
    return chunks


# ── Caption manifest helpers ─────────────────────────────────────────


def _safe_progress(writer: Callable[[dict], None] | None, payload: dict) -> None:
    if writer is None:
        return
    try:
        writer(payload)
    except Exception:
        logger.exception('progress_writer raised; ignoring')


def _build_caption_manifest(
    doc,
    rel_path: str,
    progress_writer: Callable[[dict], None] | None,
) -> dict[str, dict[str, Any]]:
    """Caption every PictureItem + TableItem in `doc`. Returns a manifest
    keyed by `self_ref` → {caption, prov, kind, section_path}.

    Returns an empty dict when ENABLE_DOC_DESCRIPTIONS is off — the chunk
    loop then skips all caption-injection logic transparently.
    """
    if not ENABLE_DOC_DESCRIPTIONS:
        return {}

    pictures = list(getattr(doc, 'pictures', None) or [])
    tables = list(getattr(doc, 'tables', None) or [])

    # Filter pictures by minimum area to skip decorative icons / bullets.
    pictures = [p for p in pictures if _picture_above_min_area(p)]

    n_pic = len(pictures)
    n_tab = len(tables)

    _safe_progress(progress_writer, {
        'pictures_total': n_pic,
        'pictures_captioned': 0,
        'pictures_failed': 0,
        'tables_total': n_tab,
        'tables_captioned': 0,
        'tables_failed': 0,
    })

    if not pictures and not tables:
        return {}

    manifest: dict[str, dict[str, Any]] = {}

    # Pictures pass — vision LLM via picture_describer preset.
    if pictures:
        _safe_progress(progress_writer, {
            'sub_phase': 'captioning_pictures',
            'sub_done': 0,
            'sub_total': n_pic,
            'sub_pct': 0.0,
        })
        from app.extractors.picture_describer import describe_picture
        captioned = 0
        failed = 0
        with ThreadPoolExecutor(
            max_workers=max(1, DOC_DESCRIPTION_PARALLELISM),
            thread_name_prefix='pic-caption',
        ) as pool:
            results = pool.map(
                lambda pic: (pic, _caption_picture(pic, describe_picture)),
                pictures,
            )
            for i, (pic, caption) in enumerate(results, 1):
                self_ref = getattr(pic, 'self_ref', None) or f'#/pictures/{i}'
                if caption:
                    manifest[self_ref] = {
                        'caption': caption,
                        'prov': _first_prov(pic),
                        'section_path': _section_for_item(doc, pic),
                        'kind': 'picture_caption',
                    }
                    captioned += 1
                else:
                    failed += 1
                _safe_progress(progress_writer, {
                    'sub_phase': 'captioning_pictures',
                    'sub_done': i,
                    'sub_total': n_pic,
                    'sub_pct': round(100 * i / n_pic, 1),
                    'pictures_captioned': captioned,
                    'pictures_failed': failed,
                })

    # Tables pass — text-only LLM via table_describer preset.
    if tables:
        _safe_progress(progress_writer, {
            'sub_phase': 'captioning_tables',
            'sub_done': 0,
            'sub_total': n_tab,
            'sub_pct': 0.0,
        })
        from app.extractors.table_describer import describe_table
        captioned = 0
        failed = 0
        with ThreadPoolExecutor(
            max_workers=max(1, DOC_DESCRIPTION_PARALLELISM),
            thread_name_prefix='tab-caption',
        ) as pool:
            results = pool.map(
                lambda tab: (tab, _caption_table(doc, tab, describe_table)),
                tables,
            )
            for i, (tab, caption) in enumerate(results, 1):
                self_ref = getattr(tab, 'self_ref', None) or f'#/tables/{i}'
                if caption:
                    manifest[self_ref] = {
                        'caption': caption,
                        'prov': _first_prov(tab),
                        'section_path': _section_for_item(doc, tab),
                        'kind': 'table_caption',
                    }
                    captioned += 1
                else:
                    failed += 1
                _safe_progress(progress_writer, {
                    'sub_phase': 'captioning_tables',
                    'sub_done': i,
                    'sub_total': n_tab,
                    'sub_pct': round(100 * i / n_tab, 1),
                    'tables_captioned': captioned,
                    'tables_failed': failed,
                })

    # Clear sub_phase so the next phase starts fresh.
    _safe_progress(progress_writer, {
        'sub_phase': None,
        'sub_done': None,
        'sub_total': None,
        'sub_pct': None,
    })
    return manifest


def _picture_above_min_area(pic) -> bool:
    """Skip pictures smaller than PICTURE_DESCRIPTION_MIN_AREA_PX. Falls
    back to True if dimensions can't be determined (don't accidentally
    drop everything when the image attribute is missing in some Docling
    edge case)."""
    img = getattr(pic, 'image', None)
    if img is None:
        return True
    pil = getattr(img, 'pil_image', None)
    if pil is None:
        return True
    try:
        w, h = pil.size
    except Exception:
        return True
    return (w * h) >= PICTURE_DESCRIPTION_MIN_AREA_PX


def _caption_picture(pic, describe_picture_fn) -> str | None:
    """Extract bytes from a Docling PictureItem and run the captioner.
    Returns None on any failure (logger warns inside the callee)."""
    img = getattr(pic, 'image', None)
    if img is None:
        return None
    pil = getattr(img, 'pil_image', None)
    if pil is None:
        return None
    try:
        import io
        buf = io.BytesIO()
        # PNG keeps things lossless and Gemma's vision encoder is fine
        # with PNG; JPEG would shave bytes but adds a quality knob.
        pil.save(buf, format='PNG')
        return describe_picture_fn(buf.getvalue(), mime='image/png')
    except Exception as e:
        logger.warning('picture caption failed for %s: %s',
                       getattr(pic, 'self_ref', '?'), e)
        return None


def _caption_table(doc, tab, describe_table_fn) -> str | None:
    """Render a Docling TableItem to markdown, gather surrounding context,
    and run the table captioner. Returns None on any failure."""
    try:
        md = tab.export_to_markdown(doc)
    except Exception as e:
        logger.warning('table caption: export_to_markdown failed for %s: %s',
                       getattr(tab, 'self_ref', '?'), e)
        return None
    if not md or not md.strip():
        return None
    section = _section_for_item(doc, tab)
    preceding, following = _surrounding_text(doc, tab)
    try:
        return describe_table_fn(
            md,
            section=section,
            preceding=preceding,
            following=following,
        )
    except Exception as e:
        logger.warning('table caption call failed for %s: %s',
                       getattr(tab, 'self_ref', '?'), e)
        return None


def _first_prov(item) -> dict | None:
    """Best-effort extraction of (page_no, bbox) from a Docling item."""
    provs = getattr(item, 'prov', None) or []
    if not provs:
        return None
    p = provs[0]
    page_no = getattr(p, 'page_no', None)
    bb = getattr(p, 'bbox', None)
    if page_no is None or bb is None:
        return None
    try:
        bbox = list(float(v) for v in bb.as_tuple())
    except Exception:
        return None
    return {'page_no': int(page_no), 'bbox': bbox}


def _section_for_item(doc, item) -> str | None:
    """Walk up the doc's parent chain to find the most-specific heading.
    Returns None if no heading ancestor exists."""
    # Docling items carry a `parent` reference resolvable via doc.resolve.
    cur = item
    seen = 0
    from docling_core.types.doc import DocItemLabel
    while seen < 16:  # bounded climb to avoid pathological cycles
        seen += 1
        parent_ref = getattr(cur, 'parent', None)
        if parent_ref is None:
            return None
        try:
            cur = parent_ref.resolve(doc) if hasattr(parent_ref, 'resolve') else doc.resolve(parent_ref)
        except Exception:
            return None
        if cur is None:
            return None
        label = getattr(cur, 'label', None)
        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            return (getattr(cur, 'text', None) or '').strip() or None
    return None


def _surrounding_text(doc, item) -> tuple[str | None, str | None]:
    """Return (preceding, following) plain-text neighbours of a TableItem
    within the doc's body sequence. Each is at most one short paragraph;
    None when nothing usable lies on that side."""
    body_items = list(getattr(doc, 'texts', None) or [])
    if not body_items:
        return None, None
    target_prov = _first_prov(item)
    if not target_prov:
        return None, None
    target_page = target_prov['page_no']
    target_y = target_prov['bbox'][1]  # y0 — bottom edge in PDF coords

    # Find text items on the same page; sort by reading order (y descending
    # since PDF coords have origin at bottom-left).
    same_page = []
    for t in body_items:
        prov = _first_prov(t)
        if not prov or prov['page_no'] != target_page:
            continue
        text = (getattr(t, 'text', None) or '').strip()
        if not text:
            continue
        same_page.append((prov['bbox'][1], text))
    same_page.sort(key=lambda x: -x[0])  # top to bottom in reading order

    preceding = None
    following = None
    for y, text in same_page:
        if y > target_y:  # above the table → comes before in reading order
            preceding = text  # last one wins (closest above)
        elif y < target_y and following is None:
            following = text  # first one wins (closest below)
            break

    # Cap each context piece at ~600 chars to keep prompts compact.
    if preceding and len(preceding) > 600:
        preceding = preceding[-600:]
    if following and len(following) > 600:
        following = following[:600]
    return preceding, following


def _resolve_chunk_caption(
    doc_items: list,
    manifest: dict[str, dict[str, Any]],
) -> tuple[str, str | None, str | None]:
    """Decide what kind/caption to assign to a chunk based on which of
    its doc_items have manifest entries.

    Returns (kind, caption_for, caption_text):
      - kind:           'text' | 'picture_caption' | 'table_caption'
      - caption_for:    self_ref of the captioned item (if pure caption)
      - caption_text:   joined caption string to prepend to chunk text
                        (None when nothing to inject)

    If multiple captioned items appear in one chunk, all their captions
    are joined; kind reflects the dominant case (picture > table > text).
    """
    captions: list[str] = []
    refs_in_chunk: list[str] = []
    has_picture = False
    has_table = False
    has_other = False

    from docling_core.types.doc import DocItemLabel

    for it in doc_items:
        ref = getattr(it, 'self_ref', None)
        label = getattr(it, 'label', None)
        if ref and ref in manifest:
            captions.append(manifest[ref]['caption'])
            refs_in_chunk.append(ref)
        if label == DocItemLabel.PICTURE:
            has_picture = True
        elif label == DocItemLabel.TABLE:
            has_table = True
        else:
            has_other = True

    caption_text = '\n\n'.join(captions) if captions else None

    # `kind` is "pure caption" only when the chunk is exclusively a
    # picture or a table item with nothing else around it. Mixed chunks
    # (table + paragraph) keep kind='text' — prose is the dominant
    # content and the caption is supplementary framing.
    if not has_other and (has_picture or has_table):
        kind = 'picture_caption' if has_picture else 'table_caption'
        caption_for = refs_in_chunk[0] if refs_in_chunk else None
    else:
        kind = 'text'
        caption_for = None

    return kind, caption_for, caption_text

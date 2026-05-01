# Docling integration: high-fidelity PDF ingestion for noted Knowledge Bases

## Purpose

Bring PDF (and later DOCX, PPTX) documents into noted's Knowledge Bases with the same retrieval quality the existing markdown pipeline provides, while preserving full provenance from each chunk back to its source page and bounding box. This unlocks "click a citation in the chat answer to open the source PDF at the exact paragraph that supports the claim."

This document assumes the KB consolidation effort (P1 unified ingestion + P2 per-doc add/delete + P3 multi-KB abstraction + P4 multi-active query fan-out) has landed.

## Where Docling fits

The post-consolidation ingestion pipeline already dispatches per-doc add/delete through a format-agnostic adapter layer. Docling slots in as the PDF adapter:

| File type | Adapter | Output |
|---|---|---|
| `.md` | `md_scanner` (existing) | `MdChunk` with `{doc_path, chunk_index, section_path, text, token_count}` |
| `.pdf` | `pdf_scanner` (new, Docling-backed) | Same `MdChunk` shape **plus** `prov: {page_no, bbox, section_level}` |
| `.docx`, `.pptx`, `.html` | same `pdf_scanner` (Docling supports them all) | Same shape |

No schema break. Existing markdown chunks stay as they are; PDF-derived chunks carry additional provenance fields. ChromaDB metadata and ArcadeDB `markdown_chunk` Entity properties both gain optional `page_no` + `bbox` + `section_level` fields, defaulted null for markdown.

## Provenance schema

Per-chunk metadata stored in both stores:

| Field | Type | Source | Used by |
|---|---|---|---|
| `doc_path` | string | adapter | both DBs (existing) |
| `chunk_index` | int | adapter | both DBs (existing) |
| `section_path` | string | adapter | both DBs (existing) |
| `text` | string | adapter | both DBs (existing) |
| `token_count` | int | adapter | both DBs (existing) |
| `page_no` | int \| null | Docling `prov[0].page_no` | citation link; PDF viewer scroll target |
| `bbox` | `[x0, y0, x1, y1]` \| null | Docling `prov[0].bbox` (PDF coordinate space) | PDF viewer highlight overlay |
| `section_level` | int \| null | Docling structural depth | richer rendering of citation context |

ChromaDB collection metadata is indexed for filter on `doc_path` and `page_no` so the UI can ask "all chunks for this PDF on page 12" without a scan.

## Pipeline

```
PDF file in KB corpus
        |
        v
+----------------------------+
| pdf_scanner (Docling)      |
|  DocumentConverter         |
|   .convert(path)           |
|     -> DoclingDocument     |
|  HybridChunker             |
|   .chunk(doc)              |
|     -> chunks w/ prov      |
+----------------------------+
        |
        v
List[MdChunk] with prov fields
        |
        +---> noted-rag: embed + upsert into <kb_id>__corpus  (immediate)
        |
        +---> noted-graph: extract entities (P2 per-doc),
                           upsert into ArcadeDB project_id=<kb_id>,
                           mark KB pending_recluster
```

The dispatch happens in the unified `POST /api/kb/{kb_id}/documents` endpoint (shipped in P1). The adapter is selected by file extension with a `Content-Type` fallback for ambiguous uploads.

## Reference implementation (Docling 2.x current API)

```python
# graph/app/scanners/pdf_scanner.py (and mirrored in noted-rag)
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat

from app.scanners.md_scanner import MdChunk

# Converter and chunker are expensive to construct (model loads).
# Build once at process start, reuse across files.
_converter = DocumentConverter(
    allowed_formats=[InputFormat.PDF, InputFormat.DOCX,
                     InputFormat.PPTX, InputFormat.HTML],
)
_chunker = HybridChunker(
    tokenizer="BAAI/bge-m3",  # match noted-rag's embedder so token counts align
    max_tokens=600,           # mirrors EXTRACT_CHUNK_TARGET_TOKENS
    merge_peers=True,
)

def scan_pdf(file_path: str, kb_id: str) -> list[MdChunk]:
    """Convert one PDF (or DOCX / PPTX / HTML) to provenance-bearing chunks."""
    result = _converter.convert(file_path)
    doc = result.document  # DoclingDocument

    chunks: list[MdChunk] = []
    for i, raw in enumerate(_chunker.chunk(doc)):
        # raw.meta.doc_items list each carry .prov[] with page_no + bbox.
        # Take the first prov as the "anchor" for the chunk; full list is
        # also persistable if multi-page chunks need richer provenance.
        first_item = raw.meta.doc_items[0] if raw.meta.doc_items else None
        prov = first_item.prov[0] if first_item and first_item.prov else None
        section_path = " > ".join(raw.meta.headings or []) or "(root)"

        chunks.append(MdChunk(
            doc_path=file_path,
            chunk_index=i,
            section_path=section_path,
            text=raw.text,
            token_count=len(_chunker.tokenizer.encode(raw.text)),
            page_no=prov.page_no if prov else None,
            bbox=list(prov.bbox.as_tuple()) if prov else None,
            section_level=raw.meta.headings_level if hasattr(raw.meta, "headings_level") else None,
        ))
    return chunks
```

Notes on the API:
- `HybridChunker` is the canonical RAG entry point in Docling 2.x. It produces token-aware chunks that preserve document structure (won't split across heading boundaries unnecessarily) and keeps the provenance trail through `meta.doc_items[].prov[]`.
- Each `prov` carries `page_no` (1-indexed) and `bbox` in PDF coordinate space (origin bottom-left for PDFs by default).
- The tokenizer should match the embedding model used by noted-rag (currently bge-m3) so chunk-size budgets match what gets embedded.
- For very large PDFs the chunker can stream; for noted's scale (single-doc up to a few hundred pages) the all-at-once form is fine.

## noted environment changes

### Container dependencies

`noted-rag/Dockerfile` and `graph/Dockerfile` (if PDF extraction also runs graph-side; otherwise just noted-rag) gain:

```dockerfile
RUN pip install --no-cache-dir \
    "docling>=2.0,<3.0" \
    "docling-core>=2.0"
```

Docling pulls in TableFormer (transformer, ~500 MB) and a layout model (~100 MB) on first use.

### Model cache as a bind mount

So model weights aren't re-downloaded on every container rebuild:

```yaml
# services/docker-compose.yml -- noted-rag service
volumes:
  - ../data/docling_cache:/root/.cache/docling
```

Cache directory survives `docker compose up --build` and lives next to `data/graph_state/` and other persistent state.

### Configuration env vars

Added to `services/.env` under a new `# Docling` block:

```
# Docling (PDF / DOCX / PPTX ingestion)
DOCLING_GPU_ENABLED=auto       # auto | true | false
DOCLING_TABLE_MODE=accurate    # accurate | fast
DOCLING_MAX_PAGES=2000         # safety cap for runaway uploads
```

Wired in `noted-rag/app/config.py` (and `graph/app/config.py` if used graph-side).

### GPU is optional

Docling runs entirely on CPU. A T4 / L4 / similar GPU speeds up TableFormer (the transformer that recovers structured tables from scanned regions); typical end-to-end speedup for table-heavy PDFs is 2-4x. For prose-heavy PDFs (papers without complex tables), the CPU path is acceptable.

## Frontend: PDF viewer with bbox highlight

noted's frontend is vanilla ES6 (no React). The viewer uses Mozilla's PDF.js (already vendored elsewhere in the noted UI for other PDF surfaces).

The `[markdown_chunk:...]` citation tag in chat answers is augmented at render time: when a chunk's metadata carries `page_no`, the citation becomes a clickable link that opens the existing `MediaViewer` panel pointed at the source PDF, scrolls to `page_no`, and overlays a translucent rectangle at the `bbox` coordinates. Click outside the rectangle dismisses the highlight; the user can scroll to other pages without losing the source-PDF context.

The annotation layer is a thin wrapper:

```js
// frontend/js/knowledge-graph/PdfHighlight.js
function showPdfHighlight(viewerEl, pageNo, bbox) {
    const pageEl = viewerEl.querySelector(`[data-page-number="${pageNo}"]`);
    if (!pageEl) return;
    pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const overlay = document.createElement('div');
    const [x0, y0, x1, y1] = bbox;
    // PDF.js renders pages with CSS transforms; convert PDF coords to CSS.
    // page.getViewport({ scale }) gives the conversion factor.
    overlay.className = 'pdf-bbox-highlight';
    overlay.style.cssText = `
        position: absolute;
        left: ${x0 * scale}px;
        top: ${(pageHeight - y1) * scale}px;
        width: ${(x1 - x0) * scale}px;
        height: ${(y1 - y0) * scale}px;
        background: rgba(255, 220, 0, 0.35);
        border: 1px solid rgba(255, 165, 0, 0.6);
        pointer-events: none;
    `;
    pageEl.appendChild(overlay);
}
```

CSS in `media-viewer.css` adds the `.pdf-bbox-highlight` class and a fade-in/fade-out animation.

## Knowledge Base Monitor surface

The Knowledge Base Monitor (shipped in P1) gains a per-format breakdown in the Vector RAG block: total chunks, count by format (`md`, `pdf`, `docx`, `pptx`, `html`), and an ingest-time histogram per format so operators can see when PDF ingestion is dominating throughput.

When a PDF ingest is in flight the monitor shows the Docling pipeline stage (parsing, table extraction, chunking) so the user understands a 30-second pause is normal for a 200-page table-heavy report.

## Multi-KB interaction (P3 / P4)

Docling-derived chunks live in their KB's collections exactly like markdown chunks: ChromaDB at `<kb_id>__corpus`, ArcadeDB at `project_id=<kb_id>`. The format-adapter dispatch is per-KB but the adapter itself is stateless and shared across KBs.

When the user activates multiple KBs and asks a question, fan-out aggregates chunks from all active KBs. PDF chunks and markdown chunks merge by reranker score in the same pool; the citation tag carries the originating KB id so the UI can render KB attribution.

## Failure modes and mitigations

| Risk | Mitigation |
|---|---|
| Docling model download fails (offline / firewall) | Cache directory bind-mount; pre-warm models in the Dockerfile build step |
| Very large PDF stalls the ingest worker | `DOCLING_MAX_PAGES` cap; reject upload with a clear error if exceeded |
| Scanned PDF (no text layer) | Docling supports OCR via Tesseract/EasyOCR; opt-in via `DOCLING_OCR=true` (default off, since OCR is slow) |
| Coordinate mismatch between Docling bbox space and PDF.js viewport | The viewer adapter normalizes via `page.getViewport({ scale })` and accounts for PDF's bottom-left origin |
| TableFormer mis-recovers a complex table | Per-chunk `format_quality_score` (Docling exposes this); chunks below threshold get flagged in the monitor for manual review |

## Open questions to settle before implementation

- Does graph-side entity extraction also run on PDF chunks, or only on the Markdown projection from Docling? (Recommend: same path as markdown, since `text` is identical in shape - the only difference is the metadata trail.)
- Should `bbox` be persisted as a normalized `(x0, y0, x1, y1)` in the original PDF coordinate space, or pre-transformed to CSS pixels for the viewer? (Recommend: PDF space - viewport-aware transformation belongs in the frontend, not the store.)
- For DOCX / PPTX the concept of "page" is fluid; what fills `page_no` for those formats? (Recommend: leave `page_no` null and rely on `section_path` for in-doc navigation; viewer falls back to scrolling to the matching heading.)

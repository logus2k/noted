# Docling integration — implementation handover

Status: P2.5 of the KB consolidation plan. Scanner + dispatch + symmetric remove + Monitor breakdown + viewer infrastructure SHIPPED 2026-04-26 against the post-P3.1 data layout (`data/kb_sources/`, basename entity ids). Citation-click wiring DEFERRED, see open items.

## Architecture: Plan B (graph-only Docling)

Docling runs ONLY in `noted-graph`. `noted-rag` stays Docling-free.

| | Decision | Why |
|---|---|---|
| Where Docling parses | `noted-graph` only | `chromadb==0.5.23` pins `tokenizers<=0.20.3`; Docling's layout model `rt_detr_v2` needs `transformers>=4.49`, which needs `tokenizers>=0.21`. Mutually exclusive. Plan A (bump chromadb to 1.x) would require API-breaking migration of noted-rag. Plan B avoided it entirely. |
| How chunks reach noted-rag | `noted-graph` ships pre-chunked text + provenance to a new `POST /upsert_chunks` endpoint on noted-rag | One parse per doc, single source of truth for chunk text. noted-rag stays a pure embedding/retrieval service. |
| Failure of `/upsert_chunks` from inside `add_doc_pdf` | logged + recorded in response, does NOT roll back the graph commit | Entity extraction already happened; Recluster will reflect it. Vector mismatch is recoverable (re-add reuses content_hash idempotency). |

## Per-doc add flow (PDF)

```
POST /research/doc/add  {path: "tutorial1_report.pdf"}
        |
        v
[graph/app/routers/research.py] file-extension dispatch
        |  (.pdf|.docx|.pptx|.html|.htm)
        v
[research_builder.py] add_doc_pdf(rel_path)
        |
        +--> pdf_scanner.scan_pdf(abs_path)            -> list[MdChunk] with page_no/bbox/section_level
        +--> build markdown_doc Entity (mirrors md_scanner shape)
        +--> _add_doc_from_chunks(rel_path, doc_entity, chunks)
        |       (extract entities + ArcadeDB merge + cache refresh + pending_recluster)
        +--> RagClient.upsert_chunks(...)              -> noted-rag embeds + upserts to ChromaDB
                                                         (best-effort, response carries result.rag)
```

Markdown path is unchanged: `add_doc(rel_path)` -> `_scan_one_file` (md_scanner) -> `_add_doc_from_chunks(...)`. No vector call from inside (kb.py owns markdown vector ingest via the existing /ingest path).

## Per-doc remove flow (any format)

`POST /research/doc/remove` is now atomic for both DBs (was graph-only):
- `_storage.remove_doc_cleanup(...)` -> graph cleanup
- `RagClient.delete_source(rel_path)` -> noted-rag DELETE `/index/sources/{b64}` (idempotent; 404 -> `{deleted_chunks: 0}`)

Verified: re-add then remove on a PDF goes 18 vector chunks -> 0; `rag.deleted_chunks: 18` in the response.

## New endpoints

| Service | Method | Path | Body / params | Notes |
|---|---|---|---|---|
| noted-rag | POST | `/upsert_chunks` | `{source_path, tags[], last_modified, format, chunks: [{chunk_index, section_path, text, page_no?, bbox?, section_level?}]}` | Idempotent on `content_hash`. `bbox` flattened to `bbox_x0/y0/x1/y1` (Chroma metadata is flat). Stale ids for the same source are deleted. |
| noted-rag | GET | `/index/format_breakdown` | — | Returns `{total, by_format: {md: N, pdf: M, ...}}`. Chunks without an explicit `format` field bucket under `md`. |
| noted-backend | GET | `/api/rag/index/format_breakdown` | — | Thin proxy to the above. |

## File-by-file changes

| File | Change |
|---|---|
| `graph/app/scanners/pdf_scanner.py` | NEW. `scan_pdf(abs_path, repo_root=None) -> list[MdChunk]`. Lazy-init `DocumentConverter` + `HybridChunker` (singleton). `PdfPipelineOptions(do_ocr=DOCLING_OCR)` (default off; without this, RapidOCR loads ~40 MB into site-packages). `HuggingFaceTokenizer.count_tokens(text)` (Docling 2.91 dropped `.encode()`). Defaults `repo_root` to `KB_SOURCES_DIR`. |
| `graph/app/scanners/md_scanner.py` | `MdChunk` dataclass gains optional `page_no`, `bbox`, `section_level` (default None). Markdown chunks ignore them. |
| `graph/app/research_builder.py` | `add_doc(rel_path)` becomes a thin markdown wrapper. NEW `add_doc_pdf(rel_path)` and private `_add_doc_from_chunks(rel_path, doc_entity, chunks)` shared post-scan helper. NEW symmetric vector cleanup inside `remove_doc`. |
| `graph/app/routers/research.py` | `/doc/add` dispatches by file extension. `_PDF_LIKE_EXTS = ('.pdf', '.docx', '.pptx', '.html', '.htm')`. Same `_rebuild_lock`. |
| `graph/app/rag_client.py` | NEW `RagClient.upsert_chunks(source_path, tags, last_modified, chunks, format)` (300 s timeout). NEW `RagClient.delete_source(source_path)` (404 -> empty result). |
| `graph/app/config.py` | Reads `DOCLING_GPU_ENABLED` / `DOCLING_TABLE_MODE` / `DOCLING_MAX_PAGES` / `DOCLING_OCR`. |
| `graph/Dockerfile` | apt-get adds `libgl1 libglib2.0-0 libxcb1 libxext6 libxrender1 libsm6` (cv2 / TableFormer runtime deps; missing from CUDA base). |
| `graph/requirements.txt` | `docling>=2.0,<3.0`, `docling-core>=2.0`. |
| `noted-rag/app/main.py` | NEW `POST /upsert_chunks`, NEW `GET /index/format_breakdown`. |
| `noted-rag/Dockerfile` | UNTOUCHED (no Docling here). |
| `noted-rag/requirements.txt` | UNTOUCHED. |
| `noted-rag/app/pdf_ingest.py` | Was created in Plan A, then deleted in Plan B. Should not exist. |
| `backend/app/managers/rag_manager.py` | NEW `format_breakdown()` async method (graceful 'unavailable' on transport failure). |
| `backend/app/routers/rag.py` | NEW `GET /api/rag/index/format_breakdown` thin proxy. |
| `backend/app/routers/kb.py` | UNTOUCHED. The unified ingest endpoint still calls `/research/doc/add` exactly as before; format dispatch happens entirely inside noted-graph. |
| `backend/app/routers/graph_proxy.py` | UNTOUCHED. Per-path read timeouts (`research/rebuild` 4h, `research/recluster` 1h, `research/doc/add` 30m, `research/doc/remove` 10m) cover the new dispatch automatically since they key on suffix. |
| `frontend/js/MediaViewer.js` | NEW `showBboxHighlight(pageNo, bbox)` + `clearBboxHighlight()`. Force-renders the target page when lazy-loaded hasn't fired. ResizeObserver extended to rescale `.pdf-bbox-highlight-layer` alongside `.pdf-annotation-layer`. |
| `frontend/css/media-viewer.css` | NEW `.pdf-bbox-highlight-layer` + `.pdf-bbox-highlight` (translucent yellow with orange border + soft glow + 200 ms fade-in). |
| `frontend/js/knowledge-graph/KnowledgeBaseMonitorPanel.js` | New "by format" row in Vector RAG block. `_tick()` parallel-fetches status + breakdown. New `_applyFormatBreakdown` renders chips sorted desc by count. |
| `frontend/css/graph-rebuild-monitor-panel.css` | NEW `.grm-fmt-chips` row + `.grm-fmt-chip` styling, color variants per format (md=blue, pdf=red, docx=blue, pptx=orange, html=gray). |
| `services/.env` | NEW `# Docling` block: `DOCLING_GPU_ENABLED`, `DOCLING_TABLE_MODE`, `DOCLING_MAX_PAGES`, `DOCLING_OCR`. |
| `services/docker-compose.yml` | `noted-graph` env + `data/models:/data/models` mount. `DOCLING_CACHE_DIR=/data/models/docling` so Docling weights live alongside bge-m3 / bge-reranker. noted-rag block has NO Docling vars. |

## Provenance schema

`MdChunk` (graph-side) and ChromaDB metadata both gain optional fields. Markdown chunks default to None / absent.

| Field | Type | Storage |
|---|---|---|
| `page_no` | `int \| null` | `MdChunk.page_no` (graph) + `metadata.page_no` (Chroma); 1-indexed; null for paginate-less formats |
| `bbox` | `[x0, y0, x1, y1] \| null` | `MdChunk.bbox` (graph) + `metadata.bbox_x0..bbox_y1` flat floats (Chroma) — Chroma metadata is flat, so the list is split |
| `section_level` | `int \| null` | both stores |
| `format` | `str` | `metadata.format` only (Chroma); not on `MdChunk`. Set by `pdf_ingest` via `/upsert_chunks`. |

Chunk id format (PDF / DOCX / PPTX): `<source_path>#<slug(section_path)>#<chunk_index>`. The `#<chunk_index>` suffix avoids collisions when long sections split into multiple HybridChunker chunks sharing a section_path.

## Container + model state

| Item | Location | Size |
|---|---|---|
| `docling-project/docling-layout-heron` | `data/models/docling/models/docling-project--docling-layout-heron/` | 164 MB |
| `docling-project/docling-models` (TableFormer v1, both `accurate` + `fast`) | `data/models/docling/models/docling-project--docling-models/` | 342 MB |
| `docling-project/DocumentFigureClassifier-v2.5` | `data/models/docling/models/docling-project--DocumentFigureClassifier-v2.5/` | 33 MB |
| `docling-project/CodeFormulaV2` | `data/models/docling/models/docling-project--CodeFormulaV2/` | 611 MB |
| **Total cache footprint** | | **1.15 GB** |

Pre-stage either way works:
```bash
# Inside the container (Docling does the work):
docker exec noted-graph python3.12 -m docling.utils.model_downloader \
    --output-dir /data/models/docling/models

# Or from host with huggingface-cli:
HF_DIR="$HOME/env/assets/noted/data/models/docling/models"
huggingface-cli download docling-project/docling-layout-heron \
    --local-dir "$HF_DIR/docling-project--docling-layout-heron"
# ... etc per repo
```

## Verified behavior

End-to-end test on `tutorial1_report.pdf` (8 pages, 365 KB) staged at `data/kb_sources/tutorial1_report.pdf`:

```
POST /research/doc/add  -> {chunks: 18, entities_written: 78-90, rag: {indexed: 18, ...}, duration: ~50-56 s}
POST /research/doc/add  -> (re-add) {rag: {indexed: 0, skipped_unchanged: 18}}      (idempotency works)
POST /research/doc/remove -> {chunks_deleted: 18, entities_deleted: ~50, rag: {deleted_chunks: 18}}
GET  /index/format_breakdown -> {total: 429, by_format: {md: 411, pdf: 18}}
```

Chunk metadata in ChromaDB after add (sample):
```json
{
  "format": "pdf",
  "page_no": 1,
  "bbox_x0": 65.25, "bbox_y0": 704.43, "bbox_x1": 110.59, "bbox_y1": 711.01,
  "content_hash": "2156958a247e",
  "section_path": "noted - Tutorial #1 Report: ..."
}
```

## What the consolidation thread should know going into P3.2 / P3.3 / P4

| Topic | Status |
|---|---|
| `kb.py` (`POST /api/kb/{kb_id}/documents`, `DELETE`) | UNTOUCHED. PDF flow works through it unchanged because dispatch is internal to `/research/doc/add`. When P3.2 introduces per-KB collections, `/upsert_chunks` will need to learn the target KB id (currently always writes to `noted_corpus`). |
| ChromaDB collection naming | `/upsert_chunks` writes to `COLLECTION_NAME` (the legacy `noted_corpus`). When P3.2 prefixes per KB, this needs `<kb_id>__corpus`. |
| `MdChunk.doc_path` | Now relative to `KB_SOURCES_DIR` (P3.1 convention; basename for top-level files). Both md_scanner and pdf_scanner mirror this. Entity ids land as `markdown_doc:<basename>`. |
| `pending_recluster` marker | `add_doc_pdf` and (extended) `remove_doc` set it on the `noted` KB. Same code path as markdown. P4 needs this to be per-KB based on the active KB id. |
| `tags` on PDF-ingested chunks | Currently always `[]` because the dispatch doesn't yet know the KB-derived tag set. When P3.2 wires per-KB tag policy, populate the `tags` arg in `add_doc_pdf -> rag_client.upsert_chunks(...)`. |

## Open items deferred for the consolidation thread to choose

| Item | Why deferred | Options |
|---|---|---|
| Citation-click wiring (chat answer -> MediaViewer + bbox highlight) | `noted_graph_answer` SSE pipeline uses `CitationTagFilter` which currently STRIPS `[markdown_chunk:...]` tags from output. Main `ChatPanel` has no Sources surface for RAG chunks. | (1) Modify `CitationTagFilter` to rewrite `[markdown_chunk:...]` as clickable HTML superscripts. (2) Add a "Sources" section below the answer pane. (3) Both. |
| `KnowledgeBaseMonitorPanel` chip click | None today. | Chips could filter the (P3.2) per-format Sources tree. Or open a "format-only" Explorer view. |
| Per-format ingest histogram (originally proposed in design doc) | Out of scope for the breakdown chip. Needs ingestion timing telemetry first. | Defer until ingest jobs gain timing instrumentation. |

## Reference

Original design doc (assumed full consolidation, then narrowed by Plan B): `documents/docling/docling_integration.md`. Useful background but partially stale on the dual-container assumption — this handover doc supersedes it for the deployed shape.

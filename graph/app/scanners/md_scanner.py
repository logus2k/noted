"""Markdown scanner for GraphRAG.

Walks the prose corpus (documents/**, data/documents/**) and produces
extraction-scale chunks (TARGET=600, MIN=200, MAX=800 tokens, heading-aware
at level >=3) that feed Gemma's entity extractor.

Key separations (resolved Q C):
  - Embedding chunks are produced by noted-rag's own ingest.py (untouched).
    This scanner does NOT produce embedding chunks.
  - Extraction chunks live in ArcadeDB with purpose='extraction' and a
    parent_embedding_chunk_id foreign-key pointer. Phase 1C writes the
    chunks; Phase 1D computes the parent pointer via hash-of-section match.
    For now parent_embedding_chunk_id is left as None; noted-rag's chunk
    ids are derived from `source_path#slug` so we can backfill later.

Ignored paths (resolved Q F):
  - data/testing/       (harness run artifacts)
  - data/environments/  (package-manager caches)
  - data/projects/      (hydra_scanner already covers these)
  - data/.renv-cache/
  - node_modules/
  - .git/
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass

from app.config import (
    EXTRACT_CHUNK_MAX_TOKENS,
    EXTRACT_CHUNK_MIN_TOKENS,
    EXTRACT_CHUNK_TARGET_TOKENS,
)
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


# Directories to skip anywhere in the tree.
_IGNORE_DIRS = {
    'testing', 'environments', 'projects', '.renv-cache',
    'node_modules', '.git', '__pycache__',
}

# Corpus list lives in the per-Domain manifest at
# /app/data/domains/<domain_id>/manifest.json (managed by app.corpus).
# Paths are relative to that Domain's sources/ folder.
from app.corpus import list_paths as _corpus_paths
from app.corpus import sources_dir as _sources_dir

# Very rough token estimate: ArcadeDB has no tokenizer dependency, and
# bge-m3's tokenizer isn't worth importing here just for chunking. Empirically
# ~4 chars per token for English prose; ~3.5 for our dense technical docs.
_CHARS_PER_TOKEN = 3.8


@dataclass
class MdChunk:
    doc_path: str            # rel path from noted repo root
    chunk_index: int         # 0-based within the doc
    section_path: str        # e.g. "Architecture > Data Flow"
    text: str
    token_count: int
    # Optional provenance for non-markdown sources (Docling-derived PDF /
    # DOCX / PPTX / HTML chunks). Markdown chunks leave these as None.
    page_no: int | None = None              # 1-indexed page; None for paginate-less formats
    bbox: list[float] | None = None         # [x0, y0, x1, y1] in PDF coord space (bottom-left origin)
    section_level: int | None = None        # structural depth from the source document
    # A Docling chunk can span multiple pages (HybridChunker(merge_peers=True)
    # merges adjacent doc_items across page breaks). `regions` lists one
    # bbox per page the chunk touches so the deep-jump highlight can paint
    # rectangles on each page. `page_no`/`bbox` mirror regions[0] for
    # back-compat with code that still reads the single-region fields.
    regions: list[dict] | None = None       # [{'page_no': int, 'bbox': [x0,y0,x1,y1]}, ...]
    # Caption-chunk marker. 'text' for normal prose / table chunks
    # produced by the chunker; 'picture_caption' / 'table_caption' for
    # chunks that carry an LLM-generated description of a Docling
    # PictureItem or TableItem at this provenance. Used by:
    #   - the citation icon-family branching in ChatPanel.js
    #   - the backfill idempotency check (skip items already captioned)
    kind: str = 'text'
    # When kind is a caption, this points to the source Docling item's
    # self_ref string (e.g. '#/pictures/3'). Lets backfill detect that a
    # given picture/table has already been captioned in a previous pass.
    caption_for: str | None = None


class MdScanner:
    """Produces markdown_doc + markdown_chunk entities + chunked_into edges."""

    def __init__(self, repo_root: str | None = None, kb_id: str | None = None):
        # `kb_id` selects which Domain's manifest to read. Sources resolve
        # relative to data/domains/<kb_id>/sources/. Tests can override
        # the directory via `repo_root`.
        self._kb_id = kb_id or 'noted'
        self._root = repo_root or _sources_dir(self._kb_id)

    def scan(self, progress_writer=None) -> tuple[list[Entity], list[Relationship], list[MdChunk]]:
        """Walk the corpus. Returns (entities, relationships, chunks).

        Chunks are returned separately because the caller (the rebuild
        orchestrator) needs chunk text to feed the extractor. The graph
        only stores chunk metadata + text; the text field is kept for
        prompt assembly later.

        `progress_writer` is an optional callable that merges its dict
        argument into the caller's progress dict. Forwarded into
        `scan_pdf` so the picture/table captioning sub-phase + counters
        surface in the KB Monitor during full rebuilds.
        """
        entities: list[Entity] = []
        rels: list[Relationship] = []
        all_chunks: list[MdChunk] = []

        # Extensions Docling handles via pdf_scanner; everything else
        # routes through markdown _process_file. Mirrors corpus.py +
        # routers/research.py:doc_add dispatch tables.
        _PDF_LIKE = {'.pdf', '.docx', '.pptx', '.html', '.htm'}

        def _ingest_path(abs_path: str, rel_path: str):
            ext = os.path.splitext(rel_path)[1].lower()
            try:
                if ext in _PDF_LIKE:
                    # Docling path. scan_pdf returns MdChunks; we build the
                    # markdown_doc entity inline (mirrors add_doc_pdf).
                    from app.scanners.pdf_scanner import scan_pdf
                    chunks = scan_pdf(
                        abs_path,
                        repo_root=self._root,
                        progress_writer=progress_writer,
                    )
                    try:
                        stat = os.stat(abs_path)
                        mtime = stat.st_mtime
                        size = stat.st_size
                    except OSError:
                        mtime = 0
                        size = 0
                    doc_entity = Entity(
                        id=f'markdown_doc:{rel_path}',
                        type='markdown_doc',
                        label=rel_path,
                        properties={
                            'path': rel_path,
                            'last_modified': mtime,
                            'size': size,
                            'chunk_count': len(chunks),
                        },
                    )
                else:
                    doc_entity, chunks = _process_file(abs_path, self._root)
            except Exception as e:
                logger.warning('scan failed for %s: %s', rel_path, e)
                return
            entities.append(doc_entity)
            for c in chunks:
                chunk_id = _chunk_id(c.doc_path, c.chunk_index)
                entities.append(Entity(
                    id=chunk_id,
                    type='markdown_chunk',
                    label=f'{c.doc_path}#{c.chunk_index}',
                    properties={
                        'doc_path': c.doc_path,
                        'chunk_index': c.chunk_index,
                        'section_path': c.section_path,
                        'text': c.text,
                        'token_count': c.token_count,
                        'page_no': c.page_no,
                        'bbox': c.bbox,
                        'regions': c.regions,
                        'section_level': c.section_level,
                        # Caption-chunk markers. Default 'text' / None for
                        # ordinary prose; 'picture_caption' / 'table_caption'
                        # plus a self_ref tag for chunks where the LLM
                        # described a Docling PictureItem / TableItem at
                        # this provenance. Used by the chat-side citation
                        # icon family + the backfill idempotency check.
                        'kind': c.kind,
                        'caption_for': c.caption_for,
                        'purpose': 'extraction',
                        'parent_embedding_chunk_id': None,
                        'embedding_id': None,
                    },
                ))
                rels.append(Relationship(
                    source=doc_entity.id,
                    target=chunk_id,
                    type='chunked_into',
                ))
            all_chunks.extend(chunks)

        # Read the corpus list from this KB's manifest.
        corpus_paths = _corpus_paths(self._kb_id)
        for rel_path in corpus_paths:
            abs_path = os.path.join(self._root, rel_path)
            if not os.path.isfile(abs_path):
                logger.warning('Corpus entry missing on disk: %s', rel_path)
                continue
            _ingest_path(abs_path, rel_path)

        logger.info(
            'md scan: %d docs, %d extraction chunks',
            sum(1 for e in entities if e.type == 'markdown_doc'),
            len(all_chunks),
        )
        return entities, rels, all_chunks


# ── File walking ────────────────────────────────────────────────────

def _walk_markdown(root: str):
    """Yield absolute paths to .md files under root, excluding ignore dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for f in filenames:
            if f.endswith('.md'):
                yield os.path.join(dirpath, f)


# ── Doc + chunks ────────────────────────────────────────────────────

def _process_file(abs_path: str, repo_root: str) -> tuple[Entity, list[MdChunk]]:
    with open(abs_path, 'r', encoding='utf-8') as f:
        text = f.read()

    rel_path = os.path.relpath(abs_path, repo_root)
    try:
        stat = os.stat(abs_path)
        mtime = stat.st_mtime
        size = stat.st_size
    except OSError:
        mtime = 0
        size = len(text)

    chunks = _chunk_markdown(text, rel_path)

    doc_id = f'markdown_doc:{rel_path}'
    doc_entity = Entity(
        id=doc_id,
        type='markdown_doc',
        label=rel_path,
        properties={
            'path': rel_path,
            'last_modified': mtime,
            'size': size,
            'chunk_count': len(chunks),
        },
    )
    return doc_entity, chunks


# ── Chunking (heading-aware level >=3 per Q C) ──────────────────────

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)


def _chunk_markdown(text: str, rel_path: str) -> list[MdChunk]:
    """Heading-aware split at level >= 3, with token-budget packing."""
    sections = _split_on_headings(text, min_level=3)
    packed: list[MdChunk] = []
    buffer_sections: list[tuple[str, str]] = []
    buffer_tokens = 0
    next_index = 0

    def flush():
        nonlocal buffer_sections, buffer_tokens, next_index
        if not buffer_sections:
            return
        section_path = buffer_sections[0][0] or '(root)'
        body = '\n\n'.join(s[1] for s in buffer_sections).strip()
        if not body:
            buffer_sections = []
            buffer_tokens = 0
            return
        # If a single section is already over MAX, window-slide it.
        if buffer_tokens > EXTRACT_CHUNK_MAX_TOKENS:
            for i, slice_text in enumerate(_window_slide(body)):
                packed.append(MdChunk(
                    doc_path=rel_path,
                    chunk_index=next_index,
                    section_path=section_path,
                    text=slice_text,
                    token_count=_approx_tokens(slice_text),
                ))
                next_index += 1
        else:
            packed.append(MdChunk(
                doc_path=rel_path,
                chunk_index=next_index,
                section_path=section_path,
                text=body,
                token_count=buffer_tokens,
            ))
            next_index += 1
        buffer_sections = []
        buffer_tokens = 0

    for section_path, body in sections:
        tokens = _approx_tokens(body)
        # Skip empty / trivial sections
        if tokens < 5:
            continue
        # If adding this section would overflow AND we already have enough
        # tokens to be above MIN, flush first.
        if buffer_tokens + tokens > EXTRACT_CHUNK_TARGET_TOKENS and buffer_tokens >= EXTRACT_CHUNK_MIN_TOKENS:
            flush()
        buffer_sections.append((section_path, body))
        buffer_tokens += tokens
        # If a single section is huge, flush it alone so the window slider kicks in.
        if tokens > EXTRACT_CHUNK_MAX_TOKENS:
            flush()
    flush()
    return packed


def _split_on_headings(text: str, min_level: int) -> list[tuple[str, str]]:
    """Split into (section_path, body) pairs at headings >= min_level.

    section_path is "ParentH2 > H3 > H4" built from the heading trail.
    Text above the first qualifying heading goes under section_path = ''.
    """
    sections: list[tuple[str, str]] = []
    current_trail: list[tuple[int, str]] = []  # [(level, title), ...]
    lines = text.splitlines()
    buf: list[str] = []

    def emit():
        path = ' > '.join(t for _, t in current_trail) if current_trail else ''
        body = '\n'.join(buf).strip()
        if body:
            sections.append((path, body))

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if level >= min_level:
                emit()
                buf = []
                # Update trail: drop anything >= this level, then append
                current_trail = [(lvl, t) for (lvl, t) in current_trail if lvl < level]
                current_trail.append((level, title))
                continue
            if level < min_level:
                # H1/H2 boundary: update trail but keep accumulating text under
                # their umbrella
                emit()
                buf = []
                current_trail = [(lvl, t) for (lvl, t) in current_trail if lvl < level]
                current_trail.append((level, title))
                continue
        buf.append(line)
    emit()
    return sections


def _window_slide(body: str) -> list[str]:
    """Sliding window for oversized sections. TARGET chars, 10% overlap."""
    win = int(EXTRACT_CHUNK_TARGET_TOKENS * _CHARS_PER_TOKEN)
    overlap = max(1, int(win * 0.10))
    chunks: list[str] = []
    start = 0
    n = len(body)
    while start < n:
        end = min(start + win, n)
        chunks.append(body[start:end])
        if end == n:
            break
        start = end - overlap
    return chunks


def _approx_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _chunk_id(doc_path: str, chunk_index: int) -> str:
    # Stable id: hash the (path, index) pair so indexing is deterministic.
    h = hashlib.sha1(f'{doc_path}#{chunk_index}'.encode()).hexdigest()[:12]
    return f'markdown_chunk:{h}'

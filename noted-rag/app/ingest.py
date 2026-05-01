"""Ingest pipeline: read the persisted source list, chunk markdown, embed,
upsert.

All content goes into a single `noted_corpus` collection. Per-chunk metadata
carries a comma-joined `tags` list (user-authored) plus the legacy
`doc_type` field set to the first tag for backward compatibility with the
`search_docs` `tags=['doc_type:...']` filter syntax.

Idempotent:
  - stable ID per chunk (source_path#slug)
  - content_hash skips re-embedding unchanged chunks
  - cleanup pass deletes IDs that no longer belong to the current source set

Source list lives at `config.SOURCES_JSON` (under DOC_ROOT, bind-mounted
read-only into noted-rag). The noted side owns the file: it adds and
removes entries, then calls /ingest. noted-rag here is read-only over both
the inventory file and the source documents themselves; it only writes to
the Chroma collection (which lives on a writable volume).

If the JSON file is missing entirely, an in-memory seed list is used so a
fresh environment still produces a populated index. The seed is never
written to disk from this side.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "noted_corpus"


# ── Seed source inventory (in-memory fallback only) ────────────────────
# Each entry describes one markdown file plus the set of user-authored
# tags it carries. Used when SOURCES_JSON is missing (fresh environment).
# The noted side is responsible for writing the JSON on first user action.

_SEED_SOURCES: list[dict] = [
    {"source_path": "documents/architecture/noted_technical_architecture.md",      "tags": ["architecture"]},
    {"source_path": "documents/developer/noted_platform_developer_manual.md",      "tags": ["developer-manual"]},
    {"source_path": "documents/developer/noted_project_notebook_companion.md",     "tags": ["developer-manual"]},
    {"source_path": "documents/noted_architecture_principles.md",                  "tags": ["principles"]},
    {"source_path": "documents/noted_vision.md",                                   "tags": ["vision"]},
    {"source_path": "data/documents/files/noted_platform_user_manual.md",          "tags": ["user-manual"]},
    {"source_path": "README.md",                                                   "tags": ["readme"]},
    {"source_path": "NOTED_SETUP.md",                                              "tags": ["setup-guide"]},
    {"source_path": "jena_weather_report/FINAL/noted_platform_final_delivery_project_report.md", "tags": ["project-report"]},
]


def load_sources() -> list[dict]:
    """Read the persisted source list. Falls back to the in-memory seed
    if the JSON is missing or unreadable. Never writes."""
    path = config.SOURCES_JSON
    if not path.exists():
        logger.info("%s not found; using in-memory seed (%d sources)",
                    path, len(_SEED_SOURCES))
        return list(_SEED_SOURCES)
    try:
        data = json.loads(path.read_text())
        sources = data.get("sources") or []
        return sources
    except Exception as e:
        logger.warning("could not parse %s (%s); falling back to in-memory seed", path, e)
        return list(_SEED_SOURCES)


# ── Chunking ──────────────────────────────────────────────────────────

MAX_CHUNK_TOKENS = 1000
MIN_CHUNK_TOKENS = 150
TARGET_CHUNK_TOKENS = 700
OVERLAP_TOKENS = 80
CHARS_PER_TOKEN = 4  # rough approximation


def _approx_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "-", s)
    return s.strip("-") or "root"


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _split_on_headings(text: str, min_level: int) -> list[tuple[str, str]]:
    """Split markdown at headings of level >= min_level. Returns list of
    (heading_path, body_text). Heading path is a ' > '-joined trail."""
    lines = text.splitlines(keepends=True)
    sections: list[tuple[str, str]] = []
    current_body: list[str] = []
    stack: list[tuple[int, str]] = []  # (level, title)

    def flush() -> None:
        if not current_body:
            return
        path = " > ".join(t for _, t in stack) or "root"
        body = "".join(current_body).strip()
        if body:
            sections.append((path, body))

    for line in lines:
        m = re.match(r"^(#+)\s+(.*)\s*$", line)
        if m and len(m.group(1)) >= min_level:
            level = len(m.group(1))
            flush()
            current_body = [line]
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2).strip()))
        else:
            current_body.append(line)

    flush()
    return sections


def _sliding_window(text: str) -> list[str]:
    """Fall back for oversized sections with no subheadings."""
    win = TARGET_CHUNK_TOKENS * CHARS_PER_TOKEN
    overlap = OVERLAP_TOKENS * CHARS_PER_TOKEN
    step = max(1, win - overlap)
    chunks: list[str] = []
    for start in range(0, len(text), step):
        chunks.append(text[start:start + win])
        if start + win >= len(text):
            break
    return chunks


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Apply chunking rules. Returns [(section_path, chunk_text), ...]."""
    sections = _split_on_headings(text, min_level=2)
    if not sections:
        # No ## headings - treat whole file as one section
        whole = text.strip()
        if _approx_tokens(whole) > MAX_CHUNK_TOKENS:
            return [(f"root[{i}]", w) for i, w in enumerate(_sliding_window(whole))]
        return [("root", whole)]

    out: list[tuple[str, str]] = []
    for section_path, body in sections:
        tokens = _approx_tokens(body)
        if tokens > MAX_CHUNK_TOKENS:
            subs = _split_on_headings(body, min_level=3)
            if len(subs) > 1:
                for sub_path, sub_body in subs:
                    out.append((f"{section_path} > {sub_path}", sub_body))
            else:
                for i, piece in enumerate(_sliding_window(body)):
                    out.append((f"{section_path}[{i}]", piece))
        elif tokens < MIN_CHUNK_TOKENS and out:
            prev_path, prev_body = out[-1]
            out[-1] = (prev_path, prev_body + "\n\n" + body)
        else:
            out.append((section_path, body))
    return out


# ── Walk + build records ──────────────────────────────────────────────

@dataclass
class ChunkRecord:
    id: str
    document: str
    metadata: dict


def _build_records(doc_root: Path, rel_path: str, tags: list[str]) -> list[ChunkRecord]:
    path = doc_root / rel_path
    if not path.is_file():
        logger.warning("source file missing, skipping: %s", path)
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("skip %s: %s", path, e)
        return []

    chunks = _chunk_markdown(text)
    last_modified = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    ).isoformat()
    # Chroma metadata is flat (str / int / float / bool), so the multi-tag
    # list lives as a comma-joined string. `doc_type` is kept as the first
    # tag for backward compatibility with the existing search filter that
    # accepts `tags=['doc_type:user-manual']`.
    tags_csv = ",".join(tags)
    primary_tag = tags[0] if tags else ""

    records: list[ChunkRecord] = []
    for section_path, chunk_text in chunks:
        if not chunk_text.strip():
            continue
        chunk_id = f"{rel_path}#{_slug(section_path)}"
        title = section_path.split(" > ")[-1]
        records.append(ChunkRecord(
            id=chunk_id,
            document=chunk_text,
            metadata={
                "source_path": rel_path,
                "section_path": section_path,
                "title": title,
                "doc_type": primary_tag,
                "tags": tags_csv,
                "content_hash": _content_hash(chunk_text),
                "last_modified": last_modified,
            },
        ))
    return records


def walk(doc_root: Path) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    seen_ids: set[str] = set()
    for entry in load_sources():
        rel_path = entry.get("source_path") or ""
        tags = entry.get("tags") or []
        if not rel_path:
            continue
        for rec in _build_records(doc_root, rel_path, tags):
            if rec.id in seen_ids:
                logger.warning("duplicate chunk id %s - skipping", rec.id)
                continue
            seen_ids.add(rec.id)
            records.append(rec)
    return records


def delete_source_chunks(rag_service, source_path: str, collection: str | None = None) -> int:
    """Drop every chunk for a source from the collection. Returns the
    number of chunks removed. Idempotent (zero is a valid result).

    P3.2: `collection` selects the per-KB ChromaDB collection name;
    defaults to legacy `COLLECTION_NAME`."""
    client = rag_service._get_client()
    try:
        coll = client.get_collection(collection or COLLECTION_NAME)
    except Exception:
        return 0
    got = coll.get(where={"source_path": source_path}, include=[])
    ids = got.get("ids") or []
    if not ids:
        return 0
    coll.delete(ids=ids)
    return len(ids)


# ── Upsert orchestration ──────────────────────────────────────────────

def run_ingest(rag_service, collection: str | None = None) -> dict:
    """Walk, chunk, embed-changed, upsert, cleanup. Returns a summary dict.

    Idempotent: re-running with the same corpus is a no-op (everything
    short-circuits on content_hash).

    P3.2: `collection` targets a per-KB ChromaDB collection; defaults to
    legacy `COLLECTION_NAME`."""
    doc_root = config.DOC_ROOT
    if not doc_root.exists():
        return {"error": f"DOC_ROOT {doc_root} does not exist", "indexed": 0}

    records = walk(doc_root)
    if not records:
        return {"indexed": 0, "skipped_unchanged": 0, "deleted_stale": 0,
                "final_count": 0, "warning": "no source files matched"}

    client = rag_service._get_client()
    coll = client.get_or_create_collection(
        name=collection or COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Existing state
    existing_ids: set[str] = set()
    existing_hashes: dict[str, str] = {}
    if coll.count() > 0:
        existing = coll.get(include=["metadatas"])
        existing_ids = set(existing["ids"])
        for id_, meta in zip(existing["ids"], existing["metadatas"] or []):
            existing_hashes[id_] = (meta or {}).get("content_hash", "")

    # Which chunks need (re)embedding?
    to_embed = [
        c for c in records
        if existing_hashes.get(c.id) != c.metadata["content_hash"]
    ]
    skipped = len(records) - len(to_embed)

    if to_embed:
        logger.info("embedding %d chunks (skipping %d unchanged)", len(to_embed), skipped)
        embeddings = rag_service.embed([c.document for c in to_embed])
        coll.upsert(
            ids=[c.id for c in to_embed],
            documents=[c.document for c in to_embed],
            embeddings=embeddings,
            metadatas=[c.metadata for c in to_embed],
        )
    else:
        logger.info("nothing to embed (%d chunks unchanged)", skipped)

    # Cleanup: any existing ID that wasn't produced this run is stale.
    produced_ids = {c.id for c in records}
    stale_ids = list(existing_ids - produced_ids)
    if stale_ids:
        coll.delete(ids=stale_ids)
        logger.info("deleted %d stale chunks", len(stale_ids))

    return {
        "indexed": len(to_embed),
        "skipped_unchanged": skipped,
        "deleted_stale": len(stale_ids),
        "final_count": coll.count(),
    }

"""Runtime configuration for noted-rag.

All knobs are env-driven. Defaults match the compose mounts so a fresh
container works out of the box.
"""

from __future__ import annotations

import os
from pathlib import Path


CHROMA_DIR: Path = Path(os.environ.get("CHROMA_DIR", "/data/chroma"))
MODEL_CACHE: Path = Path(os.environ.get("MODEL_CACHE", "/data/rag_models"))
DOC_ROOT: Path = Path(os.environ.get("DOC_ROOT", "/docs"))

# Persistent source inventory (lives under DOC_ROOT so it bind-mounts with
# the noted repo and survives container rebuilds). Each entry describes one
# indexed file with its user-authored tag list.
SOURCES_JSON: Path = Path(os.environ.get(
    "RAG_SOURCES_JSON",
    str(DOC_ROOT / "data/documents/rag_sources.json"),
))

# Destination for user-uploaded markdown files. noted writes here via the
# upload endpoint; noted-rag reads via the ingest walk. Sibling of the
# existing Knowledge Base files/ folder.
UPLOAD_DIR: Path = Path(os.environ.get(
    "RAG_UPLOAD_DIR",
    str(DOC_ROOT / "data/documents/rag_sources"),
))

DEVICE: str = os.environ.get("DEVICE", "cuda")  # "cuda" | "cpu"

EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL: str = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

DENSE_TOP_K: int = int(os.environ.get("DENSE_TOP_K", "20"))
FINAL_TOP_K: int = int(os.environ.get("FINAL_TOP_K", "5"))

# Cross-encoder reranker scores below this are treated as noise. If the top
# hit for a query is under this, /search returns no chunks - the tool layer
# then tells the LLM to decline rather than fabricate. Tune if recall suffers.
RERANK_MIN_SCORE: float = float(os.environ.get("RERANK_MIN_SCORE", "0.15"))


def ensure_dirs() -> None:
    """Create only the dirs noted-rag is allowed to write to.

    DOC_ROOT (and everything under it - SOURCES_JSON, UPLOAD_DIR) is
    bind-mounted read-only so noted-rag cannot mkdir there. Those paths
    are owned by the noted side.
    """
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)

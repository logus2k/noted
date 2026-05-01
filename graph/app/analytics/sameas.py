"""Identity-matching for thematic entities.

This module emits TWO edge types from the same input set:

  sameAs    -> TRUE IDENTITY (different spelling of the same thing).
               Computed via string normalization + Levenshtein. Cosine NOT
               used here because cosine measures topical similarity, not
               identity (e.g. "MLflow tracking" has high cosine to "MLflow"
               but is NOT the same entity - it's a feature OF MLflow).

  similar_to -> TOPICAL RELATEDNESS (semantically close, distinct identities).
               Computed via bge-m3 cosine on `name + description` with three
               confidence bands. This is what the previous "sameAs" was
               actually measuring; renamed for accurate semantics.

Both relationships:
  - Same entity type only (no cross-type pairs).
  - Skip pairs already linked via sameAs in the similar_to pass.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Iterable

import numpy as np

from app.models import Entity, Relationship
from app.rag_client import RagClient, RagClientError

logger = logging.getLogger(__name__)


# CuPy probe (same lazy detection as before; numpy fallback is fine).
_cp = None
try:
    import cupy as cp  # type: ignore
    cp.zeros(1, dtype=cp.float32)
    _cp = cp
    logger.info('similar_to cosine pass will use CuPy (GPU).')
except Exception as e:  # noqa: BLE001
    logger.info('CuPy unavailable (%s); similar_to cosine pass will use numpy CPU.', e)


_THEMATIC_TYPES = {'concept', 'person', 'organization', 'term'}

# sameAs (Levenshtein ratio on normalized names). 1.0 = identical after
# normalization; the threshold is high because we want IDENTITY, not
# similarity. Catches "MLflow" vs "ML flow" vs "MLFlow" but NOT
# "MLflow" vs "MLflow tracking".
_LEVENSHTEIN_SAMEAS_THRESHOLD = 0.92

# similar_to (cosine bands on bge-m3 embeddings of name + description).
# Topical relatedness, NOT identity.
_COSINE_HIGH = 0.90
_COSINE_MEDIUM = 0.80
_COSINE_LOW = 0.70
_SHORT_NAME_BUMP = 0.05


# ── Normalization helpers ───────────────────────────────────────────

_PUNCT_RE = re.compile(r'[\W_]+', re.UNICODE)


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not s:
        return ''
    cleaned = _PUNCT_RE.sub(' ', s.lower())
    return ' '.join(cleaned.split())


def _is_short(entity: Entity) -> bool:
    name = entity.properties.get('canonical_name') or entity.label
    if len((name or '').split()) >= 2:
        return False
    return not entity.properties.get('description')


def _embed_text(e: Entity) -> str:
    name = e.properties.get('canonical_name') or e.label
    desc = e.properties.get('description') or ''
    return f'{name}. {desc}' if desc else name


# ── sameAs (identity) ───────────────────────────────────────────────

def compute_sameas_edges(entities: Iterable[Entity]) -> list[Relationship]:
    """Emit sameAs edges for true-identity pairs ONLY.

    Two passes:
      1. Same normalized form -> confidence 1.0.
      2. Levenshtein ratio >= _LEVENSHTEIN_SAMEAS_THRESHOLD -> ratio as confidence.

    Cosine similarity is NOT used here. See module docstring.
    Returns [] if no thematic entities.
    """
    thematic = [e for e in entities if e.type in _THEMATIC_TYPES]
    if len(thematic) < 2:
        return []

    rels: list[Relationship] = []

    # Group by type; sameAs cannot cross types (we relax this in a later
    # iteration if cases like noted-organization vs noted-concept warrant it).
    by_type: dict[str, list[Entity]] = {}
    for e in thematic:
        by_type.setdefault(e.type, []).append(e)

    for type_, group in by_type.items():
        if len(group) < 2:
            continue
        rels.extend(_sameas_within_type(group))

    logger.info(
        'sameAs (identity) pass: %d thematic entities -> %d edges across %d type groups',
        len(thematic), len(rels), len(by_type),
    )
    return rels


def _sameas_within_type(group: list[Entity]) -> list[Relationship]:
    rels: list[Relationship] = []

    # Pre-compute normalized name per entity ONCE.
    norm: list[tuple[Entity, str]] = [
        (e, _normalize(e.properties.get('canonical_name') or e.label))
        for e in group
    ]

    # Pass 1: bucket by exact normalized form (fast).
    buckets: dict[str, list[Entity]] = {}
    for e, n in norm:
        if not n:
            continue
        buckets.setdefault(n, []).append(e)
    paired = set()  # (sorted-pair-of-ids) already linked
    for bucket in buckets.values():
        if len(bucket) > 1:
            for i in range(len(bucket)):
                for j in range(i + 1, len(bucket)):
                    rels.append(_sameas_edge(bucket[i].id, bucket[j].id, 1.0, 'identical_normalized'))
                    paired.add(_pair_key(bucket[i].id, bucket[j].id))

    # Pass 2: Levenshtein within type (skip already-paired).
    # O(n^2) per type; acceptable at our scale (<= ~1000 per type).
    for i in range(len(norm)):
        ei, ni = norm[i]
        if not ni:
            continue
        for j in range(i + 1, len(norm)):
            ej, nj = norm[j]
            if not nj or ni == nj:
                continue  # exact-norm handled in pass 1
            key = _pair_key(ei.id, ej.id)
            if key in paired:
                continue
            ratio = difflib.SequenceMatcher(None, ni, nj).ratio()
            if ratio >= _LEVENSHTEIN_SAMEAS_THRESHOLD:
                rels.append(_sameas_edge(ei.id, ej.id, ratio, 'levenshtein'))
                paired.add(key)

    return rels


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _sameas_edge(source: str, target: str, score: float, method: str) -> Relationship:
    return Relationship(
        source=source,
        target=target,
        type='sameAs',
        properties={'score': round(float(score), 4), 'method': method},
    )


# ── similar_to (topical relatedness) ────────────────────────────────

def compute_similar_to_edges(
    entities: Iterable[Entity],
    rag_client: RagClient | None = None,
    sameas_pairs: Iterable[tuple[str, str]] = (),
) -> list[Relationship]:
    """Emit similar_to edges for thematic entities that are topically close
    but NOT the same identity.

    Cosine bands on bge-m3 embeddings of `name + description`:
      >= 0.90  -> confidence=high
      0.80-0.90 -> confidence=medium
      0.70-0.80 -> confidence=low
      < 0.70   -> no edge

    Skip pairs already linked via sameAs (passed in `sameas_pairs`).
    """
    thematic = [e for e in entities if e.type in _THEMATIC_TYPES]
    if len(thematic) < 2:
        return []

    client = rag_client or RagClient()
    skip_pairs = {(_pair_key(a, b)) for a, b in sameas_pairs}
    rels: list[Relationship] = []

    by_type: dict[str, list[Entity]] = {}
    for e in thematic:
        by_type.setdefault(e.type, []).append(e)

    for type_, group in by_type.items():
        if len(group) < 2:
            continue
        rels.extend(_similar_within_type(group, client, skip_pairs))

    logger.info(
        'similar_to pass: %d thematic entities -> %d edges across %d type groups (backend=%s)',
        len(thematic), len(rels), len(by_type),
        'cupy' if _cp is not None else 'numpy',
    )
    return rels


def _similar_within_type(
    group: list[Entity],
    client: RagClient,
    skip_pairs: set,
) -> list[Relationship]:
    rels: list[Relationship] = []
    texts = [_embed_text(e) for e in group]
    try:
        vectors = client.embed(texts)
    except RagClientError as e:
        logger.warning('Skipping similar_to embedding pass: %s', e)
        return rels
    if len(vectors) != len(group):
        logger.warning('embed returned %d vectors for %d entities', len(vectors), len(group))
        return rels

    sims = _pairwise_cosine_matrix(vectors)
    if sims is None:
        return rels

    short_flags = [_is_short(e) for e in group]
    n = len(group)
    for i in range(n):
        a_id = group[i].id
        a_short = short_flags[i]
        row = sims[i]
        for j in range(i + 1, n):
            if _pair_key(a_id, group[j].id) in skip_pairs:
                continue
            cos_val = float(row[j])
            floor = _COSINE_LOW + (_SHORT_NAME_BUMP if (a_short or short_flags[j]) else 0.0)
            if cos_val < floor:
                continue
            rels.append(_similar_edge(a_id, group[j].id, cos_val, _band(cos_val)))
    return rels


def _band(cos: float) -> str:
    if cos >= _COSINE_HIGH:
        return 'high'
    if cos >= _COSINE_MEDIUM:
        return 'medium'
    return 'low'


def _similar_edge(source: str, target: str, cos: float, band: str) -> Relationship:
    return Relationship(
        source=source,
        target=target,
        type='similar_to',
        properties={'confidence': band, 'cosine': round(cos, 4)},
    )


# ── Pairwise cosine (CuPy GPU / numpy CPU) ──────────────────────────

def _pairwise_cosine_matrix(vectors: list[list[float]]):
    try:
        v_np = np.asarray(vectors, dtype=np.float32)
        if _cp is not None:
            v_gpu = _cp.asarray(v_np)
            sims_gpu = v_gpu @ v_gpu.T
            sims = _cp.asnumpy(sims_gpu)
            del v_gpu, sims_gpu
            _cp.get_default_memory_pool().free_all_blocks()
            return sims
        return v_np @ v_np.T
    except Exception as e:  # noqa: BLE001
        logger.exception('Pairwise cosine compute failed: %s', e)
        return None

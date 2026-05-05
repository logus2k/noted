"""Preflight scan for KB document ingestion.

Runs a battery of cheap (5-15s total) checks BEFORE committing to the long
ingestion. Catches problems that today only surface 30-60 minutes later:
corrupt PDF, LLM-output regression (chat-template-swap-style think-tag
leak into JSON), ArcadeDB schema drift, embedding service down, manifest
collision (doc already exists in this domain).

Two entry points:
- `run_preflight_for_doc(domain_id, path)` — for `/api/graph/research/<id>/doc/add`
- `run_preflight_for_notedoc(domain_id, archive_bytes)` — for the (future)
  `.notedoc` import endpoint. Adds compatibility checks (schema_rev,
  producer.embedding_model, checksum) against the archive's manifest.

Both return a `PreflightReport` with per-check status; the orchestrator
short-circuits on the first hard failure unless `fail_fast=False`.

See documents/kb/kb_import_export.md Phase 0a for the design rationale.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app import corpus
from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
from app.llm_client import LLMClient, LLMError
from app.rag_client import RagClient, RagClientError

logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    """Outcome of a single preflight check.

    `status`:
      - 'ok'    : passed cleanly, ingestion can proceed
      - 'warn'  : non-blocking concern (e.g. extraction model differs);
                  ingestion proceeds but UI surfaces the warning
      - 'error' : blocking; ingestion must abort with this reason
    """
    name: str
    status: str
    elapsed_ms: int
    detail: str = ''
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            'name': self.name,
            'status': self.status,
            'elapsed_ms': self.elapsed_ms,
        }
        if self.detail:
            d['detail'] = self.detail
        d.update(self.extra)
        return d


@dataclass
class PreflightReport:
    ok: bool                                # True iff no 'error' checks
    checks: list[CheckResult] = field(default_factory=list)
    estimate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'checks': [c.to_dict() for c in self.checks],
            'estimate': self.estimate,
        }


# ── Individual checks (each <5s in the typical case) ─────────────────────


def _docling_first_page_probe(abs_path: str) -> CheckResult:
    """Parse only the first page of the source via Docling. Catches
    corrupt / encrypted / unsupported PDFs before the full ~30-90s parse
    that the ingestion would do anyway."""
    t0 = time.perf_counter()
    name = 'docling.first_page'
    try:
        # Lazy import — Docling pulls PyTorch and OCR deps; only load
        # when actually probing.
        from app.scanners.pdf_scanner import scan_pdf
    except Exception as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'pdf_scanner import failed: {type(e).__name__}: {e}',
        )

    if not os.path.isfile(abs_path):
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'file not found: {abs_path}',
        )

    try:
        # `scan_pdf` doesn't currently expose a page-range knob; we run
        # the full scan but cap with DOCLING_MAX_PAGES — for the probe we
        # accept paying the cost since it's the same parse the full
        # ingestion would do, and we WANT to know if it fails. If a future
        # `scan_pdf(max_pages=1)` lands, swap to that.
        chunks = scan_pdf(abs_path, repo_root=os.path.dirname(abs_path))
    except Exception as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'parse failed: {type(e).__name__}: {e}',
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=f'{len(chunks)} chunks',
        extra={'chunks_estimate': len(chunks)},
    )


def _gemma_json_smoke() -> CheckResult:
    """Send a tiny entity-extraction prompt to the configured LLM and
    verify the response is parseable JSON with the expected `entities`
    field, AND that no `<think>` text leaks into the content. Catches
    today's chat-template-swap-style regressions in seconds."""
    t0 = time.perf_counter()
    name = 'gemma.json_smoke'
    try:
        client = LLMClient()
        result = client.chat_json(
            system_prompt=(
                "You extract named entities. Return ONLY a JSON object "
                "with one field `entities`, a list of items each with "
                "`type`, `name`, `description`, `confidence`."
            ),
            user_prompt='Extract entities from: "Linear regression is a method developed by Galton."',
            temperature=0.1,
            max_tokens=512,
        )
    except LLMError as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'LLM call failed: {e}',
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # Even though chat_json filters out <think>, we double-check the
    # parsed dict shape so a model returning {"thought": "..."} or
    # {"reasoning": "..."} keys is flagged.
    if not isinstance(result, dict):
        return CheckResult(
            name=name, status='error', elapsed_ms=elapsed_ms,
            detail=f'unexpected response shape: {type(result).__name__}',
        )
    has_entities = 'entities' in result
    has_reasoning_keys = any(k in result for k in ('thought', 'reasoning', 'think'))
    if not has_entities or has_reasoning_keys:
        return CheckResult(
            name=name, status='warn', elapsed_ms=elapsed_ms,
            detail=(f'response keys: {list(result.keys())} '
                    f'(expected `entities`); possible model regression'),
        )
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=f'{len(result.get("entities") or [])} entities in smoke output',
    )


def _arcadedb_write_probe(database: str) -> CheckResult:
    """Insert 10 vertices + 20 edges via the same GraphBatch HTTP
    endpoint we use in production, then delete them. Verifies server
    reachable, auth correct, schema present, and CREATE EDGE works.
    Total cost: <100ms in healthy state."""
    t0 = time.perf_counter()
    name = 'arcadedb.write_probe'
    client = ArcadeDBClient(database=database)
    try:
        # Build 10 vertex + 20 edge payload
        lines = []
        for i in range(10):
            lines.append(json.dumps({
                '@type': 'vertex', '@class': 'Entity',
                '@id': f'__preflight__:v{i}', 'id': f'__preflight__:v{i}',
                'type': 'concept', 'label': f'preflight_v{i}',
            }))
        for i in range(20):
            a = f'__preflight__:v{i % 10}'
            b = f'__preflight__:v{(i + 1) % 10}'
            lines.append(json.dumps({
                '@type': 'edge', '@class': 'RELATES',
                '@from': a, '@to': b, 'type': 'preflight',
            }))
        result = client.graphbatch_post(lines, light_edges=False)
    except ArcadeDBError as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'GraphBatch probe failed: {e}',
        )
    finally:
        # Always attempt cleanup, even on partial failure.
        try:
            client.command_sql(
                "DELETE FROM Entity WHERE id LIKE '__preflight__%'",
            )
        except Exception:
            pass

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if (result.get('verticesCreated') or 0) < 10 or (result.get('edgesCreated') or 0) < 20:
        return CheckResult(
            name=name, status='error', elapsed_ms=elapsed_ms,
            detail=f'GraphBatch returned partial counts: {result}',
        )
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=f'10v + 20e in {result.get("elapsedMs")}ms server time',
    )


def _schema_indexes_check(database: str) -> CheckResult:
    """Verify the indexes the retriever depends on are present. Catches
    schema drift after manual ops or incomplete bootstrap."""
    t0 = time.perf_counter()
    name = 'arcadedb.schema_indexes'
    client = ArcadeDBClient(database=database)
    try:
        rows = client.command_sql('SELECT FROM schema:indexes')
    except ArcadeDBError as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'index list query failed: {e}',
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    required = {
        ('Entity', 'id', True),       # type, prop, unique
        ('Entity', 'type', False),
        ('RELATES', 'type', False),
    }
    found: set[tuple[str, str, bool]] = set()
    for ix in rows:
        type_name = ix.get('typeName', '')
        props = ix.get('properties') or []
        flat = [p[0] if isinstance(p, list) else p for p in props]
        for p in flat:
            found.add((type_name, p, bool(ix.get('unique'))))

    missing = required - found
    if missing:
        return CheckResult(
            name=name, status='error', elapsed_ms=elapsed_ms,
            detail=f'missing indexes: {sorted(missing)}',
        )
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=f'{len(rows)} indexes; required indexes present',
    )


def _rag_embedding_probe() -> CheckResult:
    """Round-trip a tiny string through noted-rag's `embed` endpoint.
    Verifies the embedding service is up + model loaded + GPU available.
    Embedding-model-name match for .notedoc archives is enforced by
    `_notedoc_compatibility_check` instead (the rag client has no
    /health endpoint that exposes the model name today)."""
    t0 = time.perf_counter()
    name = 'noted_rag.embedding'
    client = RagClient()
    try:
        vecs = client.embed(['preflight smoke test'])
    except RagClientError as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'noted-rag embed failed: {e}',
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not vecs or not isinstance(vecs[0], list):
        return CheckResult(
            name=name, status='error', elapsed_ms=elapsed_ms,
            detail=f'unexpected embed response shape: {type(vecs).__name__}',
        )
    dim = len(vecs[0])
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=f'embedder ready, dim={dim}',
        extra={'embedding_dim': dim},
    )


def _manifest_collision_check(domain_id: str, path: str) -> CheckResult:
    """Check whether a doc with this path is already in the domain's
    manifest. If yes, mark as 'warn' so the UI can prompt the user with
    Replace / Skip / Cancel before committing."""
    t0 = time.perf_counter()
    name = 'manifest.collision'
    try:
        manifest = corpus.get_manifest(domain_id)
    except Exception as e:
        return CheckResult(
            name=name, status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'manifest read failed: {type(e).__name__}: {e}',
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    included = manifest.get('included_files') or []
    for entry in included:
        if entry.get('path') == path:
            return CheckResult(
                name=name, status='warn', elapsed_ms=elapsed_ms,
                detail=f'doc already in domain: {path}',
                extra={'collision': True, 'existing_entry': entry},
            )
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail='no collision',
    )


def _disk_space_estimate(abs_path: str) -> CheckResult:
    """Coarse sanity check on free disk vs estimated growth. PDF size ×
    ~10 = rough projection for chunks + entities + edge rows + vector
    embeddings storage. Refuse if free space < projection × 2."""
    t0 = time.perf_counter()
    name = 'disk.space'
    try:
        file_size = os.path.getsize(abs_path)
        free = shutil.disk_usage(os.path.dirname(abs_path)).free
    except OSError as e:
        return CheckResult(
            name=name, status='warn',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'stat failed: {e}',
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    projected = file_size * 10
    if free < projected * 2:
        return CheckResult(
            name=name, status='error', elapsed_ms=elapsed_ms,
            detail=(f'free={free // (1024*1024)} MB, projected '
                    f'={projected // (1024*1024)} MB. <2x headroom.'),
        )
    return CheckResult(
        name=name, status='ok', elapsed_ms=elapsed_ms,
        detail=(f'free={free // (1024*1024)} MB, '
                f'projected={projected // (1024*1024)} MB'),
        extra={'file_size_bytes': file_size, 'free_bytes': free},
    )


def _notedoc_compatibility_check(
    archive_manifest: dict,
    target_embedding_model: str,
    importer_schema_rev: int,
) -> list[CheckResult]:
    """Three checks for `.notedoc` archives:
      1. schema_rev <= importer's
      2. producer.embedding_model == target's (HARD requirement)
      3. checksum integrity (caller does this against the archive bytes)
    """
    out: list[CheckResult] = []

    t0 = time.perf_counter()
    archive_rev = archive_manifest.get('schema_rev')
    if not isinstance(archive_rev, int) or archive_rev > importer_schema_rev:
        out.append(CheckResult(
            name='notedoc.schema_rev', status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=(f'archive schema_rev={archive_rev} > '
                    f'importer={importer_schema_rev}; upgrade noted-graph'),
        ))
    else:
        out.append(CheckResult(
            name='notedoc.schema_rev', status='ok',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'archive_rev={archive_rev} <= importer_rev={importer_schema_rev}',
        ))

    t0 = time.perf_counter()
    producer = archive_manifest.get('producer', {}) or {}
    archive_emb = producer.get('embedding_model', '')
    if archive_emb and archive_emb != target_embedding_model:
        out.append(CheckResult(
            name='notedoc.embedding_model', status='error',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=(f'archive embedding_model={archive_emb!r} vs target='
                    f'{target_embedding_model!r}; vectors not transferable'),
        ))
    else:
        out.append(CheckResult(
            name='notedoc.embedding_model', status='ok',
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            detail=f'embedding_model match: {archive_emb}',
        ))

    archive_extr = producer.get('extraction_model', '')
    if archive_extr:
        # Warn-only: different extraction model means different entity
        # quality but the graph remains valid.
        # (We don't have a clean way to read the running extraction
        # model from inside the importer; just expose the archive's value.)
        out.append(CheckResult(
            name='notedoc.extraction_model', status='ok',
            elapsed_ms=0,
            detail=f'archive extraction_model: {archive_extr}',
        ))

    return out


# ── Orchestrators ────────────────────────────────────────────────────────


def run_preflight_for_doc(
    domain_id: str,
    path: str | None = None,
    *,
    skip_docling: bool = False,
) -> PreflightReport:
    """Preflight orchestrator. Runs in two modes:

    1. **System-health mode** (`path=None`): skips Docling, manifest
       collision, disk-space (file-specific checks). Use for "is the
       domain's pipeline healthy?" diagnostics from the KB Manager.
       Total wall ~3-5s.

    2. **Doc-targeted mode** (`path=<rel_path>`): full battery,
       including Docling first-page parse + manifest collision + disk
       estimate. Use as the first step of `add_doc_pdf` to fail fast
       before committing 30-60 minutes to a doomed run. Total wall
       ~5-15s (or up to ~90s for very large PDF cold-starts).

    `skip_docling=True` lets callers in mode 2 opt out of the Docling
    probe (e.g. a future endpoint that takes pre-parsed chunks)."""
    checks: list[CheckResult] = []

    # 1. Cheap, blocking checks first — fail fast.
    checks.append(_schema_indexes_check(database=domain_id))
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    checks.append(_arcadedb_write_probe(database=domain_id))
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    checks.append(_rag_embedding_probe())
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    checks.append(_gemma_json_smoke())
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    # 2. File-specific checks (only when a path is supplied).
    estimate: dict[str, Any] = {}
    if path:
        abs_path = os.path.join(corpus.sources_dir(domain_id), path)

        checks.append(_disk_space_estimate(abs_path))
        if checks[-1].status == 'error':
            return PreflightReport(ok=False, checks=checks)

        checks.append(_manifest_collision_check(domain_id, path))
        # collision is warn-only — keep going.

        # Docling probe is the most expensive (30-90s on large PDFs).
        if not skip_docling and not abs_path.lower().endswith('.md'):
            checks.append(_docling_first_page_probe(abs_path))
            if checks[-1].status == 'error':
                return PreflightReport(ok=False, checks=checks)

        # Estimate from Docling output if present.
        for c in checks:
            if c.name == 'docling.first_page' and c.extra.get('chunks_estimate'):
                n_chunks = c.extra['chunks_estimate']
                estimate = {
                    'chunks': n_chunks,
                    # ~3.5 entities per chunk based on historical add_doc runs
                    'entities': int(n_chunks * 3.5),
                    # ~7 mention edges per chunk
                    'mentions': int(n_chunks * 7),
                }
                break

    ok = not any(c.status == 'error' for c in checks)
    return PreflightReport(ok=ok, checks=checks, estimate=estimate)


def run_preflight_for_notedoc(
    domain_id: str,
    archive_manifest: dict,
    target_embedding_model: str = 'bge-m3-q8',
    importer_schema_rev: int = 1,
) -> PreflightReport:
    """Preflight for `.notedoc` import. Skips Docling (the archive
    already has parsed chunks); skips Gemma (we won't run extraction);
    runs ArcadeDB + schema + RAG + manifest checks PLUS the
    archive-compatibility checks (schema_rev, embedding_model)."""
    checks: list[CheckResult] = []

    checks.extend(_notedoc_compatibility_check(
        archive_manifest, target_embedding_model, importer_schema_rev,
    ))
    if any(c.status == 'error' for c in checks):
        return PreflightReport(ok=False, checks=checks)

    checks.append(_schema_indexes_check(database=domain_id))
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    checks.append(_arcadedb_write_probe(database=domain_id))
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    # For .notedoc the embedding model match is enforced by the
    # compatibility check above; the rag probe just verifies the
    # service is reachable (don't re-validate model name).
    checks.append(_rag_embedding_probe())
    if checks[-1].status == 'error':
        return PreflightReport(ok=False, checks=checks)

    # Manifest collision — caller passes the doc path from the archive's
    # manifest; we look for it in the target domain.
    archive_path = archive_manifest.get('filename')
    if archive_path:
        checks.append(_manifest_collision_check(domain_id, archive_path))

    counts = archive_manifest.get('counts', {}) or {}
    estimate = {
        'chunks': counts.get('chunks', 0),
        'entities': counts.get('entities', 0),
        'mentions': counts.get('mentions', 0),
    }

    ok = not any(c.status == 'error' for c in checks)
    return PreflightReport(ok=ok, checks=checks, estimate=estimate)

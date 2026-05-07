"""GraphRAG research endpoints (P3.2: per-KB).

Every endpoint takes a `{domain_id}` path segment and dispatches via the
KBRegistry. Per-KB state (rebuild lock, last_build, ResearchBuilder/
Retriever/GraphStorage instances) lives on the matching DomainContext.

Endpoint shape:
  POST /research/{domain_id}/rebuild              full re-extraction
  POST /research/{domain_id}/recluster            analytics-only
  POST /research/{domain_id}/doc/add              per-doc add (.md or Docling)
  POST /research/{domain_id}/doc/remove           per-doc remove (any format)
  POST /research/{domain_id}/query                synthesized answer
  POST /research/{domain_id}/retrieve             raw subgraph
  POST /research/{domain_id}/query/stream         SSE answer stream
  POST /research/{domain_id}/synthesize/stream    SSE answer from pre-loaded subgraph
  GET  /research/{domain_id}/status               progress + counts + pending markers
  GET  /research/{domain_id}/corpus               doc list
  POST /research/{domain_id}/corpus/upload        add a file to kb_sources/
  DELETE /research/{domain_id}/corpus             drop a doc from manifest
  GET  /research/{domain_id}/communities          community list
  GET  /research/{domain_id}/communities/{cid}    one community detail
  GET  /research/{domain_id}/entities/search      entity search by label
  GET  /research/{domain_id}/entity/{eid:path}/neighborhood   BFS subgraph
  POST /research/{domain_id}/recluster/pending    set marker
  DELETE /research/{domain_id}/recluster/pending  clear marker

Cross-KB endpoint (no domain_id in path):
  GET  /research/recluster/pending            map of every KB's pending marker
"""

from __future__ import annotations

import json as _json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from pydantic import BaseModel, Field

from app import corpus, state as domain_state
from app.arcadedb_client import ArcadeDBError
from app.domain_registry import DomainContext, registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/research', tags=['research'])


# ── KB lookup helper ──────────────────────────────────────────────

def _get_domain(domain_id: str) -> DomainContext:
    """Look up a DomainContext by id. Raises HTTPException(404) if unknown."""
    try:
        return registry().get(domain_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f'unknown Domain: {domain_id!r}')


def _empty_knowledge_response(payload_key: str = 'results'):
    """Standard empty response for knowledge-half endpoints called against
    a capability-only Domain (e.g. `general`). Returns 200 with an empty
    payload so frontends render a clean empty state instead of seeing 500s."""
    return {payload_key: [], 'has_knowledge': False}


def _require_knowledge(kb: DomainContext) -> None:
    """For mutation endpoints (rebuild, doc/add, doc/remove, recluster):
    raise 409 if the Domain has no knowledge half. The op semantically
    cannot run; clear error is friendlier than silent no-op."""
    if not kb.has_knowledge():
        raise HTTPException(
            status_code=409,
            detail=f'Domain {kb.domain_id!r} is capability-only (no knowledge half)',
        )


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = Field(default='auto', description='global | local | auto')


class RetrieveRequest(BaseModel):
    """For /research/retrieve. Either `question` (for the legacy embed-here
    path) OR `query_vector` (skip embed - the caller already embedded).
    Vector takes precedence if both are provided. mode is 'local' only
    here; auto/global still need the synthesizing /query endpoint."""
    question: str | None = Field(default=None)
    query_vector: list[float] | None = Field(default=None)
    mode: str = Field(default='local')


class DocPathRequest(BaseModel):
    path: str = Field(..., min_length=1, description='Path relative to kb_sources/')


class SynthesizeRequest(BaseModel):
    """Body for /synthesize/stream. The frontend caches the /retrieve
    payload after a typed question and posts it back here when the user
    clicks 'Ask the assistant', so the LLM gets the same subgraph the
    panel is rendering without a duplicate BFS."""
    question: str = Field(..., min_length=1)
    entities: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    chunk_excerpts: list[dict] = Field(default_factory=list)


# File extensions routed to pdf_scanner (Docling). Everything else goes
# through the markdown path. Kept narrow on purpose - adding a new format
# means verifying Docling handles it AND the chunking behavior is sane.
_PDF_LIKE_EXTS = ('.pdf', '.docx', '.pptx', '.html', '.htm')


# ── Lifecycle: rebuild / recluster / per-doc ─────────────────────

@router.post('/{domain_id}/rebuild')
def rebuild(
    domain_id: str,
    dry_run: bool = Query(False, description='Skip Gemma extraction; just scan markdown + commit doc/chunk nodes.'),
    limit_chunks: int | None = Query(None, description='Cap the number of chunks fed to the extractor (dev/testing).'),
    skip_analytics: bool = Query(False, description='Skip sameAs + Leiden + PageRank.'),
    skip_community_summaries: bool = Query(False, description='Skip the Gemma community-summary pass.'),
):
    """Full rebuild: re-extract every doc in the KB. ~25 min for the noted
    corpus. Serialized: a concurrent call returns HTTP 409."""
    kb = _get_domain(domain_id)
    _require_knowledge(kb)
    if not kb.rebuild_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='Rebuild or per-doc op in progress')
    try:
        kb.last_build = kb.builder.build(
            dry_run=dry_run,
            limit_chunks=limit_chunks,
            skip_analytics=skip_analytics,
            skip_community_summaries=skip_community_summaries,
        )
        # Successful rebuild = community structure refreshed. Clear the
        # KB's pending-recluster marker.
        if not skip_analytics and not skip_community_summaries:
            domain_state.clear_recluster_pending(kb.domain_id)
        return kb.last_build.to_dict()
    except ArcadeDBError as e:
        logger.exception('Research rebuild failed: ArcadeDB error')
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    except Exception as e:
        logger.exception('Research rebuild failed')
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    finally:
        kb.rebuild_lock.release()


@router.post('/{domain_id}/doc/add', status_code=202)
def doc_add(domain_id: str, req: DocPathRequest):
    """Queue a single doc for incremental graph extraction. Returns 202
    immediately with the post-enqueue queue depth.

    A per-Domain background worker drains the queue serially under
    rebuild_lock, then auto-reclusters once the queue settles - so the
    caller never has to fire Recluster manually and concurrent uploads
    can't drop on lock contention (the prior 409-on-busy fast-path
    silently lost any doc that arrived while another was extracting).
    """
    kb = _get_domain(domain_id)
    _require_knowledge(kb)
    abs_path = os.path.join(corpus.sources_dir(domain_id), req.path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f'Doc not found: {req.path}')
    depth = kb.enqueue_doc_add(req.path)
    return {'status': 'queued', 'queue_depth': depth, 'path': req.path}


class PreflightRequest(BaseModel):
    path: str | None = Field(
        default=None,
        description=('Doc path relative to sources/. Omit for system-health '
                     'mode (skip Docling, manifest, disk-space file checks).'),
    )


@router.post('/{domain_id}/preflight')
def preflight(domain_id: str, req: PreflightRequest = PreflightRequest()):
    """Run the preflight scan for a per-doc add OR as a system-health
    diagnostic (when path is omitted).

    Doc-targeted mode (path supplied): cheap (~5-15s) battery — Docling
    probe, Gemma JSON smoke, ArcadeDB write probe, schema sanity,
    embedding probe, manifest collision, disk-space estimate. Catches
    problems BEFORE committing to the long ingestion.

    System-health mode (path omitted): runs only the non-file checks
    (~3-5s). Surfaces in the KB Manager as "Run Diagnostics".

    Returns a structured report. `ok=true` means safe to proceed;
    `ok=false` means at least one blocking error was hit. See
    documents/kb/kb_import_export.md Phase 0a."""
    from app.preflight import run_preflight_for_doc
    kb = _get_domain(domain_id)
    _require_knowledge(kb)
    report = run_preflight_for_doc(domain_id, req.path)
    return report.to_dict()


@router.post('/{domain_id}/doc/remove')
def doc_remove(domain_id: str, req: DocPathRequest):
    """Incremental remove of a single doc from the KB's graph (and its
    vector chunks). Sets pending_recluster on this KB."""
    kb = _get_domain(domain_id)
    _require_knowledge(kb)
    if not kb.rebuild_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='Rebuild or per-doc op in progress')
    try:
        return kb.builder.remove_doc(req.path)
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    except Exception as e:
        logger.exception('doc/remove failed')
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    finally:
        kb.rebuild_lock.release()


@router.post('/{domain_id}/recluster')
def recluster(domain_id: str):
    """Re-run analytics + community summaries over the KB's CURRENT graph
    (no entity re-extraction). Drops old communities/summaries/sameAs/
    similar_to and writes new ones. Clears pending_recluster on success."""
    kb = _get_domain(domain_id)
    _require_knowledge(kb)
    if not kb.rebuild_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='Rebuild or recluster in progress')
    try:
        return kb.builder.recluster()
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    except Exception as e:
        logger.exception('recluster failed')
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    finally:
        kb.rebuild_lock.release()


# ── Query / retrieve ──────────────────────────────────────────────

@router.post('/{domain_id}/query')
def query(domain_id: str, req: QueryRequest):
    """Answer a research question via GraphRAG retrieval over this KB."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        return {
            'question': req.question, 'mode': req.mode,
            'entry_entities': [], 'entities': [], 'edges': [],
            'chunk_excerpts': [], 'answer': '', 'has_knowledge': False,
            'rebuild_in_progress': False,
        }
    try:
        envelope = kb.retriever.query(req.question, mode=req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    except Exception as e:
        logger.exception('research query failed')
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    envelope.rebuild_in_progress = kb.rebuild_lock.locked()
    return envelope.to_dict()


@router.post('/{domain_id}/retrieve')
def retrieve(domain_id: str, req: RetrieveRequest):
    """Retrieval-only endpoint (no Gemma synthesis). Returns the raw
    subgraph the chat-side parallel graph+vector tool fuses with vector
    chunks. See pre-P3.2 docstring for two input modes."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        return {
            'entry_entities': [], 'entities': [], 'edges': [],
            'chunk_excerpts': [], 'has_knowledge': False,
            'rebuild_in_progress': False,
        }
    try:
        mode = (req.mode or 'local').strip()
        if mode != 'local':
            if not req.question:
                raise HTTPException(status_code=400, detail='question required for non-local mode')
            envelope = kb.retriever.query(req.question, mode=mode)
            env_dict = envelope.to_dict()
            env_dict['rebuild_in_progress'] = kb.rebuild_lock.locked()
            return env_dict
        if req.query_vector:
            bundle = kb.retriever.local_mode_retrieve_by_vector(req.query_vector)
        elif req.question:
            bundle = kb.retriever.local_mode_retrieve(req.question)
        else:
            raise HTTPException(status_code=400, detail='either question or query_vector is required')
        bundle['rebuild_in_progress'] = kb.rebuild_lock.locked()
        return bundle
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    except Exception as e:
        logger.exception('research retrieve failed')
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')


@router.post('/{domain_id}/query/stream')
def query_stream(domain_id: str, req: QueryRequest):
    """Streaming variant of /query for the local mode. SSE events:
    retrieval_done / token / done / error."""
    kb = _get_domain(domain_id)

    def gen():
        if not kb.has_knowledge():
            yield (
                "event: done\n"
                f"data: {_json.dumps({'has_knowledge': False, 'envelope': {}})}\n\n"
            )
            return
        try:
            mode = (req.mode or 'auto').strip()
            if mode == 'global':
                stream_iter = kb.retriever.global_mode_stream(req.question)
            elif mode == 'local':
                stream_iter = kb.retriever.local_mode_stream(req.question)
            else:
                # auto / unknown: fall back to non-streaming envelope build,
                # emit single done event. (auto today picks between local
                # and global based on citation count - not stream-friendly.)
                envelope = kb.retriever.query(req.question, mode=mode)
                env_dict = envelope.to_dict()
                env_dict['rebuild_in_progress'] = kb.rebuild_lock.locked()
                yield f"event: done\ndata: {_json.dumps(env_dict)}\n\n"
                return
            for ev_name, payload in stream_iter:
                if ev_name == 'token' and isinstance(payload, str):
                    payload = {'text': payload}
                if ev_name == 'done' and isinstance(payload, dict) and 'envelope' in payload:
                    payload['envelope']['rebuild_in_progress'] = kb.rebuild_lock.locked()
                yield f"event: {ev_name}\ndata: {_json.dumps(payload)}\n\n"
        except ValueError as e:
            yield f"event: error\ndata: {_json.dumps({'detail': str(e)})}\n\n"
        except ArcadeDBError as e:
            yield f"event: error\ndata: {_json.dumps({'detail': f'ArcadeDB error: {e}'})}\n\n"
        except Exception as e:
            logger.exception('research query/stream failed')
            yield f"event: error\ndata: {_json.dumps({'detail': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(gen(), media_type='text/event-stream')


@router.post('/{domain_id}/synthesize/stream')
def synthesize_stream(domain_id: str, req: SynthesizeRequest):
    """Stream an LLM answer from a pre-loaded subgraph. Skips retrieve."""
    kb = _get_domain(domain_id)

    def gen():
        if not kb.has_knowledge():
            yield (
                "event: done\n"
                f"data: {_json.dumps({'has_knowledge': False, 'text': ''})}\n\n"
            )
            return
        try:
            for ev_name, payload in kb.retriever.synthesize_stream(
                req.question, req.entities, req.edges, req.chunk_excerpts,
            ):
                if ev_name == 'token':
                    yield f"event: token\ndata: {_json.dumps({'text': payload})}\n\n"
                elif ev_name == 'done':
                    yield f"event: done\ndata: {_json.dumps(payload)}\n\n"
                else:
                    yield f"event: {ev_name}\ndata: {_json.dumps(payload if isinstance(payload, dict) else {'text': str(payload)})}\n\n"
        except Exception as e:
            logger.exception('research synthesize/stream failed')
            yield f"event: error\ndata: {_json.dumps({'detail': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(
        gen(),
        media_type='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )


# ── Status ────────────────────────────────────────────────────────

@router.get('/{domain_id}/status')
def status(domain_id: str):
    """Inspect the KB's rebuild progress, last build, and ArcadeDB counts.
    `pending_recluster` is the cross-KB map (so the UI can see other KBs'
    markers too) rather than just this KB's marker."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        return {
            'domain_id': kb.domain_id,
            'has_knowledge': False,
            'rebuild_in_progress': False,
            'progress': {'phase': 'n/a'},
            'last_build': None,
            'global_counts': {'entities': 0, 'relationships': 0},
            'pending_recluster': domain_state.list_recluster_pending(),
        }
    try:
        counts = kb.storage.counts()
    except ArcadeDBError as e:
        counts = {'error': str(e)}
    return {
        'domain_id': kb.domain_id,
        'has_knowledge': True,
        'rebuild_in_progress': kb.rebuild_lock.locked(),
        'progress': kb.builder.progress,
        'last_build': kb.last_build.to_dict() if kb.last_build else None,
        'global_counts': counts,
        'pending_recluster': domain_state.list_recluster_pending(),
        'add_queue_depth': kb.add_queue_depth(),
    }


# ── Recluster-pending markers ─────────────────────────────────────

@router.post('/{domain_id}/recluster/pending')
def set_recluster_pending(domain_id: str, reason: str = Query('')):
    """Mark <domain_id> as needing a recluster."""
    _get_domain(domain_id)  # 404 if unknown
    domain_state.set_recluster_pending(domain_id, reason=reason)
    return {'domain_id': domain_id, 'pending': True}


@router.delete('/{domain_id}/recluster/pending')
def clear_recluster_pending(domain_id: str):
    """Clear the marker for <domain_id>."""
    _get_domain(domain_id)
    domain_state.clear_recluster_pending(domain_id)
    return {'domain_id': domain_id, 'pending': False}


@router.get('/recluster/pending')
def list_recluster_pending():
    """Cross-KB: every KB currently flagged as needing a recluster."""
    return {'pending': domain_state.list_recluster_pending()}


# ── Corpus management ────────────────────────────────────────────

@router.get('/{domain_id}/corpus')
def list_corpus(domain_id: str):
    """Return the KB's corpus. Reads from data/kb/<domain_id>/manifest.json."""
    _get_domain(domain_id)
    return {'documents': corpus.list_documents(domain_id)}


@router.post('/{domain_id}/corpus/upload')
async def upload_corpus_doc(
    domain_id: str,
    file: UploadFile = File(...),
    mode: str = Query(
        'read_store',
        description="read_store: indexed in vector + graph (default). "
                    "read_only: file on disk + visible in tree, no DB ingestion.",
    ),
    category: str = Query(
        '',
        description="Optional free-text category for tree grouping. "
                    "Empty = uncategorized.",
    ),
):
    """Add a file to the Domain. The file is saved under
    data/domains/<domain_id>/sources/. Sets pending_recluster on the
    Domain when mode=read_store; read_only files don't touch the graph."""
    _get_domain(domain_id)
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename required')
    if mode not in ('read_only', 'read_store'):
        raise HTTPException(
            status_code=400,
            detail=f"invalid mode {mode!r}; must be 'read_only' or 'read_store'",
        )
    content = await file.read()
    try:
        result = corpus.add_uploaded_file(
            file.filename, content,
            domain_id=domain_id, mode=mode, category=category,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if mode == 'read_store':
        domain_state.set_recluster_pending(
            domain_id, reason=f'corpus add: {file.filename}',
        )
    return result


@router.patch('/{domain_id}/corpus/category')
def set_corpus_category(
    domain_id: str,
    path: str = Query(..., description='Doc path (Domain sources/-relative)'),
    category: str = Query('', description='New category. Empty = uncategorized.'),
):
    """Update the category of an existing document in the manifest. Pure
    metadata change - does not re-index, doesn't touch the source file or
    any database. UI groups files in the Documents tree by category."""
    _get_domain(domain_id)
    result = corpus.set_category(path, category, domain_id=domain_id)
    if not result.get('updated'):
        raise HTTPException(status_code=404, detail=f'doc not found in manifest: {path}')
    return result


@router.patch('/{domain_id}/corpus/display_name')
def set_corpus_display_name(
    domain_id: str,
    path: str = Query(..., description='Doc path (Domain sources/-relative)'),
    display_name: str = Query('', description='User-friendly title for the tree. Empty = use basename(path).'),
):
    """Update the display_name of an existing document in the manifest.
    Pure metadata change - does not re-index, doesn't rename the file
    on disk, doesn't touch any database. The Explorer tree title falls
    back to basename(path) when display_name is empty."""
    _get_domain(domain_id)
    result = corpus.set_display_name(path, display_name, domain_id=domain_id)
    if not result.get('updated'):
        raise HTTPException(status_code=404, detail=f'doc not found in manifest: {path}')
    return result


@router.delete('/{domain_id}/corpus')
def delete_corpus_doc(
    domain_id: str,
    path: str = Query(..., description='Path of the doc to remove from the corpus'),
):
    """Drop a doc path from the Domain's manifest AND delete the file
    from data/domains/<domain_id>/sources/ (no cross-Domain sharing -
    each Domain owns its copy). Sets pending_recluster only when the
    removed entry was indexed (mode=read_store)."""
    _get_domain(domain_id)
    prior_mode = corpus.get_mode(domain_id, path)
    result = corpus.remove_document(path, domain_id=domain_id)
    if prior_mode == 'read_store':
        domain_state.set_recluster_pending(
            domain_id, reason=f'corpus remove: {path}',
        )
    return result


# ── Communities (UI tree exposure) ───────────────────────────────

@router.get('/{domain_id}/communities')
def list_communities(domain_id: str):
    """Return the KB's communities sorted by member_count desc. Used by
    the Explorer Graph tree."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        return _empty_knowledge_response('communities')
    # Avoid `MATCH (c:Entity {type: "community"})` — Entity.type's index
    # goes stale after large DETACH DELETEs (full rebuild) and points at
    # records that no longer exist, surfacing as `Record #X:Y not found`
    # at query time. Community entity ids are deterministic
    # `community:<cid>`, so the id-prefix filter is both correct and
    # immune to the stale index. Same pattern repeats below.
    try:
        rows = kb.storage._c.query(
            '''MATCH (c:Entity)
               WHERE c.id STARTS WITH "community:"
                 AND $pid IN c.project_ids
               RETURN c.community_id AS cid, c.properties_json AS props''',
            {'pid': kb.project_id},
        )
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    out = []
    for row in rows:
        try:
            props = _json.loads(row.get('props') or '{}')
        except Exception:
            props = {}
        out.append({
            'community_id': row.get('cid'),
            'member_count': props.get('member_count', 0),
            'dominant_entity_types': props.get('dominant_entity_types', []),
        })
    out.sort(key=lambda c: -(c.get('member_count') or 0))
    return {'communities': out}


@router.get('/{domain_id}/communities/{cid}')
def community_detail(domain_id: str, cid: int, top_n: int = 15):
    """One community's detail: summary + top-N members by PageRank."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        raise HTTPException(
            status_code=404, detail=f'Community {cid} not found',
        )
    # The three queries below are independent: community node, summary,
    # and top-N members. Run them concurrently rather than serially.
    # Use exact-id MATCH instead of `{type: "..."}` for the same reason
    # documented in list_communities above (stale Entity.type index).
    cnid = f'community:{cid}'
    sid = f'community_summary:{cid}'

    def _fetch_community() -> list[dict]:
        return kb.storage._c.query(
            '''MATCH (c:Entity {id: $cnid})
               WHERE $pid IN c.project_ids
               RETURN c.properties_json AS props''',
            {'cnid': cnid, 'pid': kb.project_id},
        )

    def _fetch_summary() -> list[dict]:
        return kb.storage._c.query(
            '''MATCH (s:Entity {id: $sid})
               WHERE $pid IN s.project_ids
               RETURN s.properties_json AS props''',
            {'sid': sid, 'pid': kb.project_id},
        )

    def _fetch_members() -> list[dict]:
        return kb.storage._c.query(
            '''MATCH (e:Entity)-[r:RELATES]->(c:Entity {id: $cnid})
               WHERE r.type = "member_of"
               RETURN e.id AS id, e.label AS label, e.type AS type, e.rank AS rank, e.properties_json AS props
               ORDER BY e.rank DESC
               LIMIT $n''',
            {'cnid': cnid, 'n': top_n},
        )

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_community = ex.submit(_fetch_community)
        f_summary = ex.submit(_fetch_summary)
        f_members = ex.submit(_fetch_members)

        # Community: hard error if missing (404 expected by GraphPanel).
        try:
            c_rows = f_community.result()
        except ArcadeDBError as e:
            raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
        if not c_rows:
            raise HTTPException(status_code=404, detail=f'Community {cid} not found')
        try:
            c_props = _json.loads(c_rows[0].get('props') or '{}')
        except Exception:
            c_props = {}

        # Summary: soft-fail (preserves existing semantics where missing
        # summary is acceptable).
        summary_text = None
        try:
            s_rows = f_summary.result()
            if s_rows:
                sp = _json.loads(s_rows[0].get('props') or '{}')
                summary_text = sp.get('text')
        except ArcadeDBError:
            pass

        # Members: hard error.
        try:
            m_rows = f_members.result()
        except ArcadeDBError as e:
            raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    members = []
    for row in m_rows:
        try:
            mp = _json.loads(row.get('props') or '{}')
        except Exception:
            mp = {}
        members.append({
            'id': row.get('id'),
            'label': row.get('label'),
            'type': row.get('type'),
            'rank': row.get('rank'),
            'description': mp.get('description', ''),
        })
    return {
        'community_id': cid,
        'member_count': c_props.get('member_count', 0),
        'dominant_entity_types': c_props.get('dominant_entity_types', []),
        'summary': summary_text,
        'top_members': members,
    }


@router.get('/{domain_id}/entities/search')
def search_entities(
    domain_id: str,
    q: str = Query(..., min_length=1),
    limit: int = 20,
):
    """Substring (case-insensitive) match on entity label, sorted by PageRank.
    ArcadeDB lacks toLowerCase, so we filter in Python (a few hundred rows).
    """
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        return _empty_knowledge_response('results')
    try:
        rows = kb.storage._c.query(
            '''MATCH (e:Entity)
               WHERE $pid IN e.project_ids
                 AND e.type IN ["concept", "person", "organization", "term"]
               RETURN e.id AS id, e.label AS label, e.type AS type, e.rank AS rank''',
            {'pid': kb.project_id},
        )
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')

    needle = q.lower()
    matches = [r for r in rows if needle in (r.get('label') or '').lower()]
    matches.sort(key=lambda r: -(r.get('rank') or 0))
    return {
        'results': [
            {'id': r.get('id'), 'label': r.get('label'),
             'type': r.get('type'), 'rank': r.get('rank')}
            for r in matches[:int(limit)]
        ],
    }


@router.get('/{domain_id}/entity/{entity_id:path}/neighborhood')
def entity_neighborhood(
    domain_id: str,
    entity_id: str,
    hops: int = Query(2, ge=1, le=3),
    limit: int = Query(80, ge=5, le=1000),
):
    """BFS subgraph rooted at `entity_id`, expanded `hops` levels via
    sameAs / similar_to / member_of edges."""
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        raise HTTPException(
            status_code=404, detail=f'Entity {entity_id} not found',
        )
    TRAVERSAL_EDGE_TYPES = ['sameAs', 'similar_to', 'member_of']
    HOP_FRONTIER_CAP = max(30, int(limit))
    SUBGRAPH_CAP = int(limit)

    try:
        seed_rows = kb.storage._c.query(
            '''MATCH (e:Entity)
               WHERE $pid IN e.project_ids AND e.id = $id
               RETURN e.id AS id''',
            {'id': entity_id, 'pid': kb.project_id},
        )
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    if not seed_rows:
        raise HTTPException(status_code=404, detail=f'Entity {entity_id} not found')

    reached: set[str] = {entity_id}
    frontier: list[str] = [entity_id]
    for _hop in range(int(hops)):
        if not frontier:
            break
        try:
            hop_rows = kb.storage._c.query(
                '''MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                   WHERE a.id IN $front
                     AND r.type IN $rtypes
                     AND NOT b.id IN $seen
                   RETURN DISTINCT b.id AS id, b.rank AS rank
                   ORDER BY b.rank DESC
                   LIMIT $cap''',
                {'front': frontier, 'rtypes': TRAVERSAL_EDGE_TYPES,
                 'seen': list(reached), 'cap': HOP_FRONTIER_CAP},
            )
        except ArcadeDBError as e:
            raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
        new_ids = [row['id'] for row in hop_rows if row.get('id')]
        if not new_ids:
            break
        reached.update(new_ids)
        frontier = new_ids
        if len(reached) >= SUBGRAPH_CAP:
            break

    ids_list = list(reached)

    def _fetch_nodes() -> list[dict]:
        return kb.storage._c.query(
            '''MATCH (n:Entity)
               WHERE n.id IN $ids
               RETURN n.id AS id, n.label AS label, n.type AS type,
                      n.community_id AS community_id, n.rank AS rank,
                      n.properties_json AS props''',
            {'ids': ids_list},
        )

    def _fetch_edges() -> list[dict]:
        # Node-centric pattern: 3.4x faster than the global form because
        # the first MATCH locks in the Entity.id index, then traverses
        # outgoing RELATES edges from there.
        return kb.storage._c.query(
            '''MATCH (n:Entity) WHERE n.id IN $ids
               MATCH (n)-[r:RELATES]->(m:Entity) WHERE m.id IN $ids AND r.type IN $rtypes
               RETURN n.id AS source, m.id AS target, r.type AS type''',
            {'ids': ids_list, 'rtypes': TRAVERSAL_EDGE_TYPES},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_nodes = ex.submit(_fetch_nodes)
            f_edges = ex.submit(_fetch_edges)
            node_rows = f_nodes.result()
            edge_rows = f_edges.result()
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')

    entities = []
    for r in node_rows:
        try:
            props = _json.loads(r.get('props') or '{}')
        except Exception:
            props = {}
        if r.get('community_id') is not None and 'community_id' not in props:
            props['community_id'] = r.get('community_id')
        if r.get('rank') is not None and 'rank' not in props:
            props['rank'] = r.get('rank')
        entities.append({
            'id': r.get('id'), 'label': r.get('label'),
            'type': r.get('type'), 'rank': r.get('rank'),
            'properties': props,
        })
    edges = [
        {'source': r.get('source'), 'target': r.get('target'), 'type': r.get('type')}
        for r in edge_rows
    ]
    return {
        'seed_entity_id': entity_id,
        'hops': int(hops),
        'entities': entities,
        'edges': edges,
        'entity_count': len(entities),
        'relationship_count': len(edges),
    }


@router.get('/{domain_id}/chunk/{chunk_id:path}')
def chunk_lookup(domain_id: str, chunk_id: str):
    """Resolve a markdown_chunk entity id to its provenance.

    Returns the document path + section path + (when ingested with PDF
    provenance) page_no + bbox so the frontend can open the source
    document and jump to the cited region. 404 if the chunk doesn't
    exist in this Domain.
    """
    kb = _get_domain(domain_id)
    if not kb.has_knowledge():
        raise HTTPException(status_code=404, detail=f'Domain {domain_id!r} has no knowledge')
    try:
        # Drop the `n.type = "markdown_chunk"` filter: ArcadeDB's
        # Entity.type index goes stale after the rebuild's DETACH DELETE
        # pass and produces "Record not found" 500s. The id is already
        # `markdown_chunk:<hex>` (sha1[:12]), unique enough on its own.
        # Same defensive pattern as graph_storage.add_doc_merge and
        # retriever._chunk_excerpts.
        rows = kb.storage._c.query(
            '''MATCH (n:Entity)
               WHERE $pid IN n.project_ids
                 AND n.id = $id
               RETURN n.properties_json AS props''',
            {'id': chunk_id, 'pid': kb.project_id},
        )
    except ArcadeDBError as e:
        raise HTTPException(status_code=500, detail=f'ArcadeDB error: {e}')
    if not rows:
        raise HTTPException(status_code=404, detail=f'chunk {chunk_id!r} not found in {domain_id!r}')
    try:
        props = _json.loads(rows[0].get('props') or '{}')
    except Exception:
        props = {}
    # `regions` is the per-page bbox list for chunks that span page breaks.
    # Pre-multi-region chunks have it as None; fall back to a single-entry
    # list synthesized from page_no/bbox so the frontend can treat regions
    # as the source of truth without two code paths.
    regions = props.get('regions')
    if not regions and props.get('page_no') is not None and props.get('bbox') is not None:
        regions = [{'page_no': props['page_no'], 'bbox': props['bbox']}]
    return {
        'type': 'chunk',
        'domain_id': domain_id,
        'chunk_id': chunk_id,
        'source_path': props.get('doc_path') or '',
        'section_path': props.get('section_path') or '',
        'page_no': props.get('page_no'),
        'bbox': props.get('bbox'),
        'regions': regions or [],
        'snippet': (props.get('text') or '')[:200],
    }

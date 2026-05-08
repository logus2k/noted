"""Domain registry + per-Domain context.

A "Domain" is the unit of activation in noted's Knowledge Base + Assistant
architecture. It bundles three things:
  - Knowledge: documents, vector cache, graph (this side of the bundle)
  - Skills: per-Domain skill files (loaded from data/domains/<id>/skills/)
  - Tools: per-Domain tool definitions (loaded from data/domains/<id>/tools/)

Each Domain is fully self-contained on disk:
  /app/data/domains/<domain_id>/manifest.json
  /app/data/domains/<domain_id>/sources/      user content
  /app/data/domains/<domain_id>/state/        per-Domain persistent markers
  /app/data/domains/<domain_id>/skills/       per-Domain skills
  /app/data/domains/<domain_id>/tools/        per-Domain tool definitions

At runtime each Domain has:
  - one ArcadeDB project_id (entities + edges live there)
  - three ChromaDB collections (corpus / gr_entities / gr_summaries)
  - one ResearchBuilder + Retriever + GraphStorage instance, parameterized
    with the Domain's project_id and collection names

Heavyweight clients (LLMClient, RagClient, ArcadeDBClient) are SHARED -
they're stateless HTTP wrappers, no per-Domain allocation needed. Only the
config (project_id + collection names) varies per Domain.

Manifest schema:
  {
    "domain_id": "noted",
    "name": "noted",                           # display name
    "description": "...",
    "created_at": "...",
    "embeddings_model": "bge-m3",
    "pinned": false,                           # true = cannot be deactivated
    "arcadedb_project_id": "noted",            # null/missing for capability-only Domains
    "corpus_collection": "noted__corpus",      # null/missing if no knowledge half
    "entity_cache_collection": "noted__gr_entities",
    "summary_cache_collection": "noted__gr_summaries",
    "included_files": [
      {"path": "user_manual.md", "mode": "read_store", "added_at": "..."},
      {"path": "blog_post.md", "mode": "read_only", "added_at": "..."}
    ]
  }

Convention for collection / project names: <domain_id> for ArcadeDB,
<domain_id>__corpus / <domain_id>__gr_entities / <domain_id>__gr_summaries
for ChromaDB. No legacy soft-mapping - the Domain migration (P-Domain in
app.migration) normalizes the noted Domain's names from the old layout
('__global__' / 'noted_corpus' / 'gr_entities' / 'gr_summaries') to the
convention ('noted' / 'noted__corpus' / etc.) on first boot.

The pinned `general` Domain is capability-only - no documents, no graph,
no vector cache. Its manifest omits the project_id and collection fields.
It exists to host universal Assistant behavior (fairness, honesty, voice
format, citation conventions, tool-call discipline) plus general-purpose
tools that aren't tied to any other Domain. Cannot be deleted or
deactivated.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from queue import Empty

from app.config import DOMAIN_HOME_DIR, GENERAL_DOMAIN_ID

logger = logging.getLogger(__name__)

# File extensions routed through Docling (PDF-like). Mirrors the constant
# in routers/research.py - duplicated here so the worker can route
# without importing the router module (circular).
_PDF_LIKE_EXTS = ('.pdf', '.docx', '.pptx', '.html', '.htm')

# Idle timeout for the per-Domain doc-add worker. After draining the
# queue, the worker waits this long for new arrivals before triggering
# auto-recluster. Short enough that single-doc uploads recluster
# quickly; long enough that a tight burst of N uploads drains as one
# batch (sequential frontend uploads complete in <1s each).
_QUEUE_SETTLE_SECONDS = 2


def _convention(domain_id: str, kind: str) -> str:
    """Convention-based default for a per-Domain resource name.

    kind: 'arcadedb_database' | 'corpus_collection' |
          'entity_cache_collection' | 'summary_cache_collection'
    """
    if kind == 'arcadedb_database':
        return domain_id
    if kind == 'corpus_collection':
        return f'{domain_id}__corpus'
    if kind == 'entity_cache_collection':
        return f'{domain_id}__gr_entities'
    if kind == 'summary_cache_collection':
        return f'{domain_id}__gr_summaries'
    raise ValueError(f'unknown resource kind: {kind!r}')


def _doc_add_worker(ctx: 'DomainContext') -> None:
    """Per-Domain background worker: drain ctx.add_queue serially under
    rebuild_lock, auto-recluster once the queue settles, then exit.

    Drain phase: pull paths off the queue with a 2-second idle timeout.
    Each path is processed under rebuild_lock so concurrent /rebuild
    or /recluster calls return 409 cleanly instead of corrupting state.

    Settle phase: when the queue has been empty for the idle timeout,
    if the Domain has a pending_recluster marker, run recluster()
    (which clears the marker on success). This is the auto-recovery
    that removes the "Knowledge Graph is behind the corpus" prompt -
    the user never has to fire Recluster manually after uploads.

    Exit phase: re-check the queue under add_worker_lock to win the
    race against a /doc/add that's enqueueing right now. If new items
    arrived, loop back to drain instead of exiting; otherwise clear
    add_worker and return so the next /doc/add spawns a fresh thread.
    """
    from app import state as domain_state  # avoid import cycle at module load

    while True:
        # Drain phase. Track whether ANY doc-add in this drain failed -
        # if so, we skip the auto-recluster (clustering against a graph
        # that didn't get the new entities is wasteful AND will leave the
        # pending_recluster marker set forever, since recluster() only
        # clears the marker on success).
        any_failure = False
        any_success = False
        # Doc counter for the Monitor's "Document N / M" indicator.
        # Updated per-doc; cleared at end of drain. doc_total grows
        # dynamically as new uploads land in the queue mid-drain
        # (current + remaining_queue), so the user sees a live
        # picture of what's left.
        doc_done_in_drain = 0
        while True:
            try:
                rel_path = ctx.add_queue.get(timeout=_QUEUE_SETTLE_SECONDS)
            except Empty:
                break
            doc_done_in_drain += 1
            try:
                # Surface the doc counter on the builder's progress
                # before extraction starts so the Monitor renders it
                # alongside `current_source`. Total = the doc we're
                # about to process + everything still queued behind it.
                try:
                    ctx.builder.progress['doc_index'] = doc_done_in_drain
                    ctx.builder.progress['doc_total'] = doc_done_in_drain + ctx.add_queue.qsize()
                except Exception:
                    pass
                with ctx.rebuild_lock:
                    ext = os.path.splitext(rel_path)[1].lower()
                    if ext in _PDF_LIKE_EXTS:
                        ctx.builder.add_doc_pdf(rel_path)
                    else:
                        ctx.builder.add_doc(rel_path)
                any_success = True
                logger.info('doc-add-worker[%s]: extracted %s (doc %d, %d remaining)',
                            ctx.domain_id, rel_path, doc_done_in_drain, ctx.add_queue.qsize())
            except Exception as e:
                any_failure = True
                logger.exception('doc-add-worker[%s]: extraction failed for %s',
                                 ctx.domain_id, rel_path)
                # Mark phase as 'failed' (NOT 'idle' - 'idle' lies to the
                # Monitor about whether work happened). Preserves any
                # existing progress keys (started_at, current_doc, etc.)
                # so the UI can show "failed at <last phase>".
                try:
                    ctx.builder._set_phase(
                        'failed',
                        failed_at=datetime.now(timezone.utc).isoformat(),
                        failed_op='doc_add',
                        failed_doc=rel_path,
                        error=f'{type(e).__name__}: {str(e)[:200]}',
                    )
                except Exception:
                    pass
            finally:
                ctx.add_queue.task_done()

        # Drain just finished — clear the doc counter so the Monitor
        # doesn't show stale "Document N / N" during the recluster /
        # idle phases that follow.
        try:
            ctx.builder.progress.pop('doc_index', None)
            ctx.builder.progress.pop('doc_total', None)
        except Exception:
            pass

        # Settle phase: queue has been empty for the idle timeout.
        # Auto-recluster only if (a) at least one doc actually succeeded
        # AND (b) no doc failed AND (c) the marker is set. Skipping when
        # any doc failed prevents the marker from being permanently stuck
        # (recluster would also fail and never clear it).
        if any_success and not any_failure and domain_state.get_recluster_pending(ctx.domain_id):
            try:
                with ctx.rebuild_lock:
                    logger.info('doc-add-worker[%s]: auto-recluster after queue drain',
                                ctx.domain_id)
                    ctx.builder.recluster()
            except Exception as e:
                logger.exception('doc-add-worker[%s]: auto-recluster failed',
                                 ctx.domain_id)
                # Mark phase as 'failed' (not 'idle' - see doc_add path above).
                try:
                    ctx.builder._set_phase(
                        'failed',
                        failed_at=datetime.now(timezone.utc).isoformat(),
                        failed_op='auto_recluster',
                        error=f'{type(e).__name__}: {str(e)[:200]}',
                    )
                except Exception:
                    pass
        elif any_failure:
            logger.warning('doc-add-worker[%s]: skipping auto-recluster '
                           '(at least one doc-add failed in this batch)',
                           ctx.domain_id)

        # Exit phase: check the queue under the worker lock so that any
        # /doc/add racing with us either (a) sees us alive and skips spawn,
        # in which case we'll see its enqueued item and loop back; or
        # (b) sees us cleared and spawns a fresh worker.
        with ctx.add_worker_lock:
            if not ctx.add_queue.empty():
                continue
            ctx.add_worker = None
            return


class DomainContext:
    """Per-Domain bundle of stateful objects + config.

    Construction is cheap (just storing a few strings + a lock). The
    Retriever / ResearchBuilder / GraphStorage instances are constructed
    lazily on first access so that listing Domains doesn't pay the cost.

    Capability-only Domains (no knowledge half) have project_id=None and
    collection names=None. Trying to access .builder / .retriever /
    .storage on such a Domain raises - callers must check has_knowledge().
    """

    def __init__(self, manifest: dict):
        domain_id = manifest.get('domain_id')
        if not domain_id:
            raise ValueError(f'manifest missing domain_id: {manifest!r}')
        self.domain_id: str = domain_id
        self.name: str = manifest.get('name') or domain_id
        self.description: str = manifest.get('description') or ''
        self.created_at: str = manifest.get('created_at') or ''
        self.embeddings_model: str = manifest.get('embeddings_model') or 'bge-m3'
        self.pinned: bool = bool(manifest.get('pinned', False))
        # `deletable` is independent from `pinned`. The noted platform Domain
        # is deletable=False (can't be deleted) but pinned=False (can be
        # deactivated). General is both pinned AND not deletable.
        # User-created Domains default to deletable=True.
        self.deletable: bool = bool(manifest.get('deletable', True))

        # Knowledge-half resource names. Manifest may explicitly set them
        # (preferred), or omit them entirely (capability-only Domain), or
        # leave them blank (treated as "use convention").
        # `arcadedb_database` (preferred) names the per-Domain ArcadeDB
        # database. Old manifests used `arcadedb_project_id` for the same
        # value (when entities lived in a shared DB tagged by project_ids);
        # both keys are accepted for backward compat.
        db = manifest.get('arcadedb_database')
        if db is None:
            db = manifest.get('arcadedb_project_id')
        if db is None:
            self.arcadedb_database: str | None = None
        elif db == '':
            self.arcadedb_database = _convention(domain_id, 'arcadedb_database')
        else:
            self.arcadedb_database = db
        # Back-compat alias - some callers still read `.project_id`.
        # Same value as arcadedb_database under the new architecture.
        self.project_id: str | None = self.arcadedb_database

        self.corpus_collection: str | None = self._resolve_collection(
            manifest, 'corpus_collection')
        self.entity_cache_collection: str | None = self._resolve_collection(
            manifest, 'entity_cache_collection')
        self.summary_cache_collection: str | None = self._resolve_collection(
            manifest, 'summary_cache_collection')

        # Per-Domain lifecycle state
        self.rebuild_lock = threading.Lock()
        # last_build is persisted to data/domains/<id>/state/last_build.json
        # so the field survives noted-graph container restarts. Pre-fix
        # behavior: in-memory only, every restart wiped it and /status
        # reported `last_build: None` for every domain regardless of
        # whether a build had ever run.
        self.last_build = self._load_last_build()

        # Per-Domain doc-add queue + worker thread. Sequential uploads land
        # here; the worker drains them one-at-a-time under rebuild_lock and
        # auto-reclusters once the queue settles. Replaces the prior
        # 409-on-contention behavior that silently dropped concurrent adds.
        self.add_queue: queue.Queue[str] = queue.Queue()
        self.add_worker: threading.Thread | None = None
        self.add_worker_lock = threading.Lock()

        # Lazily-constructed heavyweight objects (one per Domain).
        # The init_lock guards the lazy constructors below: without it,
        # two near-simultaneous callers (e.g. /rebuild handler thread +
        # Monitor /status poll thread) can each see `_builder is None`,
        # each construct an instance, and the last write to self._builder
        # wins — leaving the first thread holding an orphan instance whose
        # progress updates are never visible to the rest of the process.
        # Symptom: Monitor shows IDLE while logs show extraction running.
        # MUST be RLock (re-entrant): builder lazy-init reads self.storage
        # which also acquires this lock on the same thread; a non-reentrant
        # Lock would self-deadlock and freeze every status / build request.
        self._init_lock = threading.RLock()
        self._builder = None
        self._retriever = None
        self._storage = None

    def _resolve_collection(self, manifest: dict, kind: str) -> str | None:
        """Knowledge collections: explicit field > convention > None.

        None means this Domain has no knowledge half (e.g. `general`).
        """
        v = manifest.get(kind)
        if v is None:
            return None
        if v == '':
            return _convention(self.domain_id, kind)
        return v

    @property
    def state_dir(self) -> str:
        return os.path.join(DOMAIN_HOME_DIR, self.domain_id, 'state')

    def _last_build_path(self) -> str:
        return os.path.join(self.state_dir, 'last_build.json')

    def _load_last_build(self):
        """Read the persisted last_build stats from disk. Returns a
        ResearchBuildStats-shaped object via dict mimic, or None when no
        file exists / parse fails. Defensive: bad JSON should never
        prevent a Domain from loading."""
        path = self._last_build_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning('Domain %s: cannot load last_build.json: %s',
                           self.domain_id, e)
            return None
        # The status endpoint calls .to_dict() on this; expose a tiny
        # shim so a persisted-from-disk dict round-trips identically.
        from types import SimpleNamespace
        ns = SimpleNamespace(**data)
        ns.to_dict = lambda: dict(data)  # closure over the loaded dict
        return ns

    def record_last_build(self, stats) -> None:
        """Persist a ResearchBuildStats to disk + update the in-memory
        attribute. Called after every successful build / recluster /
        add_doc cycle that produces fresh stats. Failures here log but
        don't raise - the build itself already succeeded; persistence
        is observability, not correctness."""
        self.last_build = stats
        try:
            os.makedirs(self.state_dir, exist_ok=True)
            payload = stats.to_dict() if hasattr(stats, 'to_dict') else dict(stats)
            with open(self._last_build_path(), 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, sort_keys=True)
        except (OSError, ValueError) as e:
            logger.warning('Domain %s: failed to persist last_build: %s',
                           self.domain_id, e)

    def has_knowledge(self) -> bool:
        """True when this Domain has the knowledge half (arcadedb_database
        + collections set). False for capability-only Domains like
        `general`."""
        return (
            self.arcadedb_database is not None
            and self.corpus_collection is not None
            and self.entity_cache_collection is not None
            and self.summary_cache_collection is not None
        )

    def _require_knowledge(self, what: str) -> None:
        if not self.has_knowledge():
            raise ValueError(
                f'Domain {self.domain_id!r} is capability-only (no knowledge half); '
                f'cannot access {what}'
            )

    # -- Lazy instances ------------------------------------------------
    # Each property uses double-checked locking under self._init_lock to
    # guarantee a single instance per Domain across concurrent threads.
    @property
    def storage(self):
        self._require_knowledge('storage')
        if self._storage is None:
            with self._init_lock:
                if self._storage is None:
                    from app.graph_storage import GraphStorage
                    self._storage = GraphStorage(arcadedb_database=self.arcadedb_database)
        return self._storage

    @property
    def builder(self):
        self._require_knowledge('builder')
        if self._builder is None:
            with self._init_lock:
                if self._builder is None:
                    from app.research_builder import ResearchBuilder
                    self._builder = ResearchBuilder(
                        kb_id=self.domain_id,
                        arcadedb_database=self.arcadedb_database,
                        corpus_collection=self.corpus_collection,
                        entity_cache_collection=self.entity_cache_collection,
                        summary_cache_collection=self.summary_cache_collection,
                        storage=self.storage,
                    )
        return self._builder

    @property
    def retriever(self):
        self._require_knowledge('retriever')
        if self._retriever is None:
            with self._init_lock:
                if self._retriever is None:
                    from app.retrieval.retriever import Retriever
                    self._retriever = Retriever(
                        kb_id=self.domain_id,
                        arcadedb_database=self.arcadedb_database,
                        entity_cache_collection=self.entity_cache_collection,
                        summary_cache_collection=self.summary_cache_collection,
                    )
        return self._retriever

    # -- Doc-add queue -------------------------------------------------
    def enqueue_doc_add(self, rel_path: str) -> int:
        """Queue a single doc for incremental graph extraction. Spawns
        a per-Domain worker thread on demand. Returns the queue depth
        right after enqueue (1 means "this is the only queued item").

        Concurrent uploads stack here serially instead of being dropped
        by the prior `acquire(blocking=False) -> 409` fast-path.
        """
        self._require_knowledge('enqueue_doc_add')
        with self.add_worker_lock:
            self.add_queue.put(rel_path)
            depth = self.add_queue.qsize()
            if self.add_worker is None or not self.add_worker.is_alive():
                t = threading.Thread(
                    target=_doc_add_worker, args=(self,), daemon=True,
                    name=f'doc-add-{self.domain_id}',
                )
                self.add_worker = t
                t.start()
        return depth

    def add_queue_depth(self) -> int:
        """Approximate queue depth, for the Monitor UI."""
        return self.add_queue.qsize()

    # -- Serialization -------------------------------------------------
    def to_dict(self) -> dict:
        """Public-facing snapshot for /api/domains endpoints."""
        out: dict = {
            'domain_id': self.domain_id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'embeddings_model': self.embeddings_model,
            'pinned': self.pinned,
            'deletable': self.deletable,
            'has_knowledge': self.has_knowledge(),
        }
        if self.has_knowledge():
            out['arcadedb_project_id'] = self.project_id
            out['corpus_collection'] = self.corpus_collection
            out['entity_cache_collection'] = self.entity_cache_collection
            out['summary_cache_collection'] = self.summary_cache_collection
        return out


class DomainRegistry:
    """In-process registry of DomainContext objects keyed by domain_id.

    Loads from disk on first access (walks /app/data/domains/*/manifest.json).
    create() / delete() update both the in-memory dict AND disk.
    """

    def __init__(self):
        self._domains: dict[str, DomainContext] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self) -> None:
        if not os.path.isdir(DOMAIN_HOME_DIR):
            logger.info('Domain home dir does not exist yet: %s', DOMAIN_HOME_DIR)
            return
        for entry in sorted(os.listdir(DOMAIN_HOME_DIR)):
            d_dir = os.path.join(DOMAIN_HOME_DIR, entry)
            manifest_path = os.path.join(d_dir, 'manifest.json')
            if not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except (OSError, ValueError) as e:
                logger.warning('Skipping Domain %s: cannot load manifest: %s', entry, e)
                continue
            try:
                ctx = DomainContext(manifest)
            except ValueError as e:
                logger.warning('Skipping Domain %s: invalid manifest: %s', entry, e)
                continue
            self._domains[ctx.domain_id] = ctx
            if ctx.has_knowledge():
                logger.info('Loaded Domain %r (project_id=%s, corpus=%s)',
                            ctx.domain_id, ctx.project_id, ctx.corpus_collection)
            else:
                logger.info('Loaded Domain %r (capability-only)', ctx.domain_id)

    # -- Public API ----------------------------------------------------
    def list(self) -> list[DomainContext]:
        self._ensure_loaded()
        return list(self._domains.values())

    def list_ids(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._domains.keys())

    def get(self, domain_id: str) -> DomainContext:
        """Return the DomainContext for `domain_id`. Raises KeyError if unknown."""
        self._ensure_loaded()
        if domain_id not in self._domains:
            raise KeyError(f'unknown Domain: {domain_id!r}')
        return self._domains[domain_id]

    def has(self, domain_id: str) -> bool:
        self._ensure_loaded()
        return domain_id in self._domains

    def create(
        self,
        domain_id: str,
        name: str | None = None,
        description: str = '',
        embeddings_model: str = 'bge-m3',
        pinned: bool = False,
        capability_only: bool = False,
    ) -> DomainContext:
        """Create a new Domain (manifest on disk + in-memory context).

        New Domains follow the naming convention `<domain_id>__corpus` etc.;
        the manifest stores those names so they're stable. ChromaDB
        collections + ArcadeDB project for the new Domain are created
        lazily on first write by the existing per-Domain code paths
        (ChromaDB get_or_create, ArcadeDB MERGE).

        capability_only=True creates a Domain without the knowledge half
        (no project_id, no collections). For Domains that only host
        skills/tools.
        """
        self._ensure_loaded()
        if not _is_valid_domain_id(domain_id):
            raise ValueError(
                f'invalid domain_id {domain_id!r}: must be lowercase ASCII letters/digits/underscore, '
                f'1-32 chars, must start with a letter'
            )
        with self._lock:
            if domain_id in self._domains:
                raise ValueError(f'Domain {domain_id!r} already exists')
            manifest: dict = {
                'domain_id': domain_id,
                'name': name or domain_id,
                'description': description,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'embeddings_model': embeddings_model,
                'pinned': pinned,
                'included_files': [],
            }
            if not capability_only:
                manifest['arcadedb_database'] = _convention(domain_id, 'arcadedb_database')
                manifest['corpus_collection'] = _convention(domain_id, 'corpus_collection')
                manifest['entity_cache_collection'] = _convention(
                    domain_id, 'entity_cache_collection')
                manifest['summary_cache_collection'] = _convention(
                    domain_id, 'summary_cache_collection')
            _write_manifest(domain_id, manifest)
            ctx = DomainContext(manifest)
            self._domains[domain_id] = ctx
        # Bootstrap the per-Domain ArcadeDB database + schema NOW so that
        # the first doc-upload doesn't hit "Database 'X' is not available"
        # (startup migration only runs at boot - new Domains created via
        # the API skip it). Chroma collections autocreate on first write,
        # so they don't need the same explicit bootstrap.
        if not capability_only:
            try:
                from app.migration import _ensure_arcadedb_for_domain
                _ensure_arcadedb_for_domain(ctx.arcadedb_database)
            except Exception as e:
                logger.warning(
                    'Created Domain %r but ArcadeDB bootstrap failed: %s',
                    domain_id, e,
                )
        logger.info('Created Domain %r (capability_only=%s)', domain_id, capability_only)
        return ctx

    def update(
        self,
        domain_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> DomainContext:
        """Update editable fields on an existing Domain. Currently only
        `name` and `description` can be changed; `arcadedb_database`,
        `pinned`, and the collection names are fixed at creation time
        (changing them would require data migration).

        Both args are optional; pass only the fields you want to change.
        Returns the updated DomainContext."""
        self._ensure_loaded()
        with self._lock:
            ctx = self._domains.get(domain_id)
            if ctx is None:
                raise KeyError(f'unknown Domain: {domain_id!r}')
            manifest_path = os.path.join(DOMAIN_HOME_DIR, domain_id, 'manifest.json')
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except (OSError, ValueError) as e:
                raise RuntimeError(f'cannot read manifest: {e}') from e
            if name is not None:
                manifest['name'] = name
                ctx.name = name
            if description is not None:
                manifest['description'] = description
                ctx.description = description
            _write_manifest(domain_id, manifest)
        logger.info('Updated Domain %r', domain_id)
        return ctx

    def delete(self, domain_id: str) -> dict:
        """Drop a Domain: remove its in-memory context, drop its ChromaDB
        collections, drop its ArcadeDB project, delete its on-disk
        directory (manifest + state + sources + skills + tools).

        Cannot delete a Domain whose manifest has `deletable: false`
        (general - pinned, noted - platform default)."""
        self._ensure_loaded()
        with self._lock:
            ctx = self._domains.get(domain_id)
            if ctx is None:
                raise KeyError(f'unknown Domain: {domain_id!r}')
            if not ctx.deletable:
                raise ValueError(
                    f'Domain {domain_id!r} is not deletable'
                )
            self._domains.pop(domain_id, None)

        result: dict = {'domain_id': domain_id}

        # ChromaDB: drop the three caches (best-effort - log + continue).
        if ctx.has_knowledge():
            from app.rag_client import RagClient, RagClientError
            rag = RagClient()
            for kind, name in [
                ('corpus', ctx.corpus_collection),
                ('entities', ctx.entity_cache_collection),
                ('summaries', ctx.summary_cache_collection),
            ]:
                try:
                    rag.cache_drop(name)
                    result[f'chroma_{kind}_dropped'] = True
                except (RagClientError, Exception) as e:
                    logger.warning('delete Domain %s: cache_drop(%s) failed: %s',
                                   domain_id, name, e)
                    result[f'chroma_{kind}_dropped'] = False
                    result[f'chroma_{kind}_error'] = str(e)

            # ArcadeDB: drop the entire per-Domain database. Each Domain
            # owns its own DB inside the shared noted-arcadedb container,
            # so DROP DATABASE removes everything atomically.
            from app.arcadedb_client import ArcadeDBClient
            try:
                c = ArcadeDBClient()
                ok = c.drop_database(ctx.arcadedb_database)
                result['arcadedb_dropped'] = ok
                if not ok:
                    result['arcadedb_error'] = 'drop_database returned False'
            except Exception as e:
                logger.warning('delete Domain %s: ArcadeDB drop failed: %s', domain_id, e)
                result['arcadedb_dropped'] = False
                result['arcadedb_error'] = str(e)

        # Domain dir (manifest + state + sources + skills + tools).
        import shutil
        d_dir = os.path.join(DOMAIN_HOME_DIR, domain_id)
        try:
            shutil.rmtree(d_dir)
            result['dir_deleted'] = True
        except OSError as e:
            logger.warning('delete Domain %s: cannot rmtree %s: %s', domain_id, d_dir, e)
            result['dir_deleted'] = False
            result['dir_error'] = str(e)

        logger.info('Deleted Domain %r: %s', domain_id, result)
        return result


# -- Module-level singleton ------------------------------------------
_registry: DomainRegistry | None = None


def registry() -> DomainRegistry:
    """Get-or-create the global DomainRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = DomainRegistry()
    return _registry


# -- Helpers ---------------------------------------------------------

def _is_valid_domain_id(domain_id: str) -> bool:
    """domain_ids are used as URL path segments + ArcadeDB project ids +
    ChromaDB collection prefixes - keep them strict."""
    if not domain_id:
        return False
    if len(domain_id) > 32:
        return False
    if not domain_id[0].isalpha():
        return False
    return all(c.isalnum() or c == '_' for c in domain_id) and domain_id == domain_id.lower()


def _write_manifest(domain_id: str, manifest: dict) -> None:
    d_dir = os.path.join(DOMAIN_HOME_DIR, domain_id)
    os.makedirs(d_dir, exist_ok=True)
    os.makedirs(os.path.join(d_dir, 'state'), exist_ok=True)
    os.makedirs(os.path.join(d_dir, 'sources'), exist_ok=True)
    os.makedirs(os.path.join(d_dir, 'skills'), exist_ok=True)
    os.makedirs(os.path.join(d_dir, 'tools'), exist_ok=True)
    path = os.path.join(d_dir, 'manifest.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp, path)

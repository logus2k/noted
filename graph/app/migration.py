"""On-startup data migration.

Two layered migrations run sequentially. Both are idempotent.

Step 1: P1 (graph_corpus.json) -> P3.1 (data/kb/<id>/manifest.json)
  Reads legacy /app/data/graph_corpus.json and writes a per-KB manifest
  for the seeded `noted` KB. Copies basenames into /app/data/kb_sources/.
  Skipped if data/kb/noted/manifest.json already exists.

Step 2: P3.1 (data/kb/) -> Domain layout (data/domains/<id>/manifest.json
        with mode-aware included_files + per-Domain sources/ folder)
  - Walks every kb_id under data/kb/.
  - For each, creates data/domains/<id>/ with sources/, state/, skills/,
    tools/ subfolders.
  - Copies that KB's referenced source files from the SHARED
    data/kb_sources/ pool into the Domain's own sources/ folder (the
    Domain layout doesn't share source files between Domains).
  - Rewrites manifest in the new schema:
      * `kb_id` -> `domain_id`
      * `included_files: ["x.md", ...]` -> `[{"path": "x.md", "mode": "read_store", "added_at": ""}, ...]`
      * Drops legacy soft-mapping for the noted KB - normalizes its
        ArcadeDB project_id ('__global__' -> 'noted') and its three
        ChromaDB collection names ('noted_corpus' -> 'noted__corpus',
        'gr_entities' -> 'noted__gr_entities', 'gr_summaries' -> 'noted__gr_summaries').
      * Adds `pinned: false`.
  - Moves data/kb/<id>/state/* into data/domains/<id>/state/.
  - The old data/kb/ tree is LEFT IN PLACE as a safety net; can be
    removed manually after verification.

Step 3: ensure the pinned `general` Domain exists (creates an empty
        capability-only manifest if missing).

Step 4: best-effort ArcadeDB project_ids rename for entities that still
        carry the legacy '__global__' marker. Walks Entity rows where
        '__global__' IN project_ids and replaces the marker with 'noted'.
        Best-effort: failure is logged but does not abort startup.

Step 5: ChromaDB rename of the three legacy noted collections. Requires
        a noted-rag /admin/rename_collection endpoint which is added in
        the same patch series; if absent, this step is logged as TODO and
        the queries will resolve through the new convention name once the
        next full rebuild lands.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone

from app.config import (
    DOMAIN_HOME_DIR,
    GENERAL_DOMAIN_ID,
    _LEGACY_KB_HOME_DIR,
    _LEGACY_KB_SOURCES_DIR,
    _LEGACY_GRAPH_STATE_DIR,
    _LEGACY_GLOBAL_PROJECT_ID,
    _LEGACY_NOTED_CORPUS_COLLECTION,
    _LEGACY_NOTED_ENTITIES_COLLECTION,
    _LEGACY_NOTED_SUMMARIES_COLLECTION,
)

logger = logging.getLogger(__name__)

# Legacy P1 paths
_LEGACY_CORPUS_JSON = '/app/data/graph_corpus.json'
_LEGACY_UPLOAD_DIR = '/app/data/graph_corpus_uploads'
_REPO_ROOT = '/app'

# `noted` is the well-known platform Domain id - the only one that pre-
# exists across the layout migrations and needs collection-name normalization.
_NOTED_DOMAIN_ID = 'noted'


# ── Public entrypoint ──────────────────────────────────────────────

def run_migration_if_needed() -> None:
    """Idempotent migration entry point. Called from main.py at startup.

    Legacy P1->P3.1 and P3.1->Domain steps are disabled now that the
    Domain layout is universal. They were one-time conversions; leaving
    them on every boot caused re-import of stale state from the
    git-tracked `data/kb/` tree, undoing user wipes (see
    feedback_data_kb_git_tracked.md). If a fresh install ever needs
    them again, re-enable selectively.
    """
    # _migrate_p1_to_p31()
    # _migrate_p31_to_domain()
    _ensure_general_domain()
    _ensure_noted_domain()
    _normalize_noted_arcadedb()
    _split_per_domain_arcadedb_dbs()
    _log_chromadb_rename_status()


# ── Step 1: P1 -> P3.1 (kept defensively) ──────────────────────────

def _migrate_p1_to_p31() -> None:
    """Legacy P1 (graph_corpus.json) -> P3.1 (data/kb/noted/manifest.json).

    Skipped if data/kb/noted/manifest.json already exists OR if the
    legacy graph_corpus.json doesn't exist. Both branches are common
    on production today; this stays in place as a defensive net for any
    install still on P1.
    """
    target = os.path.join(_LEGACY_KB_HOME_DIR, _NOTED_DOMAIN_ID, 'manifest.json')
    if os.path.isfile(target):
        return
    if not os.path.isfile(_LEGACY_CORPUS_JSON):
        return

    logger.info('Migrating legacy P1 layout -> P3.1 KB layout')
    os.makedirs(os.path.join(_LEGACY_KB_HOME_DIR, _NOTED_DOMAIN_ID), exist_ok=True)
    os.makedirs(os.path.join(_LEGACY_KB_HOME_DIR, _NOTED_DOMAIN_ID, 'state'), exist_ok=True)
    os.makedirs(_LEGACY_KB_SOURCES_DIR, exist_ok=True)

    try:
        with open(_LEGACY_CORPUS_JSON, 'r', encoding='utf-8') as f:
            legacy = json.load(f)
    except (OSError, ValueError) as e:
        logger.error('Migration P1: cannot read %s: %s', _LEGACY_CORPUS_JSON, e)
        return

    included: list[str] = []
    for entry in legacy.get('documents', []):
        rel_path = entry.get('path')
        if not rel_path:
            continue
        src = os.path.join(_REPO_ROOT, rel_path)
        if not os.path.isfile(src):
            continue
        basename = os.path.basename(rel_path)
        dst = os.path.join(_LEGACY_KB_SOURCES_DIR, basename)
        if not os.path.isfile(dst):
            try:
                shutil.copy2(src, dst)
            except OSError as e:
                logger.warning('Migration P1: cannot copy %s: %s', src, e)
                continue
        included.append(basename)

    manifest = {
        'kb_id': _NOTED_DOMAIN_ID,
        'name': 'noted',
        'description': 'Default knowledge base shipped with the platform.',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'embeddings_model': 'bge-m3',
        'included_files': included,
    }
    _write_json(target, manifest)
    logger.info('Migration P1: wrote %s with %d files', target, len(included))

    _migrate_recluster_markers_p1()


def _migrate_recluster_markers_p1() -> None:
    """Move pending_recluster markers from /app/data/graph_state/ to
    /app/data/kb/<id>/state/."""
    src_dir = os.path.join(_LEGACY_GRAPH_STATE_DIR, 'pending_recluster')
    if not os.path.isdir(src_dir):
        return
    for name in os.listdir(src_dir):
        if not name.endswith('.json'):
            continue
        kb_id = name[:-5]
        state_dir = os.path.join(_LEGACY_KB_HOME_DIR, kb_id, 'state')
        os.makedirs(state_dir, exist_ok=True)
        try:
            shutil.copy2(os.path.join(src_dir, name),
                         os.path.join(state_dir, 'pending_recluster.json'))
        except OSError as e:
            logger.warning('Migration P1: marker copy failed for %s: %s', kb_id, e)


# ── Step 2: P3.1 -> Domain layout ──────────────────────────────────

def _migrate_p31_to_domain() -> None:
    """For each KB under data/kb/, produce a Domain at data/domains/.

    Idempotent per-Domain: skips kb_ids whose data/domains/<id>/manifest.json
    already exists. Leaves data/kb/ in place after migrating (safety net).
    """
    if not os.path.isdir(_LEGACY_KB_HOME_DIR):
        return

    for kb_id in sorted(os.listdir(_LEGACY_KB_HOME_DIR)):
        old_dir = os.path.join(_LEGACY_KB_HOME_DIR, kb_id)
        if not os.path.isdir(old_dir):
            continue
        old_manifest_path = os.path.join(old_dir, 'manifest.json')
        if not os.path.isfile(old_manifest_path):
            continue
        new_manifest_path = os.path.join(DOMAIN_HOME_DIR, kb_id, 'manifest.json')
        if os.path.isfile(new_manifest_path):
            continue

        try:
            with open(old_manifest_path, 'r', encoding='utf-8') as f:
                old_manifest = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning('Migration Domain: cannot read %s: %s', old_manifest_path, e)
            continue

        _migrate_single_kb_to_domain(kb_id, old_manifest, old_dir)


def _migrate_single_kb_to_domain(kb_id: str, old_manifest: dict, old_dir: str) -> None:
    """Produce data/domains/<kb_id>/ from a single legacy data/kb/<kb_id>/."""
    domain_dir = os.path.join(DOMAIN_HOME_DIR, kb_id)
    sources_dir = os.path.join(domain_dir, 'sources')
    state_dir = os.path.join(domain_dir, 'state')
    skills_dir = os.path.join(domain_dir, 'skills')
    tools_dir = os.path.join(domain_dir, 'tools')
    for d in (domain_dir, sources_dir, state_dir, skills_dir, tools_dir):
        os.makedirs(d, exist_ok=True)

    # Copy referenced source files from the SHARED kb_sources/ pool into
    # the Domain's own sources/ folder. Each Domain owns its copy.
    copied = 0
    skipped = 0
    legacy_files = old_manifest.get('included_files', [])
    for raw in legacy_files:
        rel_path = raw if isinstance(raw, str) else (raw or {}).get('path')
        if not rel_path:
            continue
        basename = os.path.basename(rel_path)
        src = os.path.join(_LEGACY_KB_SOURCES_DIR, basename)
        if not os.path.isfile(src):
            logger.warning('Migration Domain: %s/%s missing in kb_sources/, skipping',
                           kb_id, basename)
            skipped += 1
            continue
        dst = os.path.join(sources_dir, basename)
        if not os.path.isfile(dst):
            try:
                shutil.copy2(src, dst)
                copied += 1
            except OSError as e:
                logger.warning('Migration Domain: %s/%s copy failed: %s', kb_id, basename, e)
                skipped += 1
                continue

    # Move state markers (recluster pending, etc.)
    legacy_state = os.path.join(old_dir, 'state')
    if os.path.isdir(legacy_state):
        for name in os.listdir(legacy_state):
            src = os.path.join(legacy_state, name)
            dst = os.path.join(state_dir, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError as e:
                    logger.warning('Migration Domain: %s state %s: %s', kb_id, name, e)

    # Build the new manifest. For the noted KB, drop the legacy soft-mapping
    # and normalize collection names to convention.
    new_files = []
    for raw in legacy_files:
        if isinstance(raw, str):
            if raw:
                new_files.append({
                    'path': raw,
                    'mode': 'read_store',
                    'added_at': '',
                })
        elif isinstance(raw, dict):
            path = raw.get('path')
            if not path:
                continue
            new_files.append({
                'path': path,
                'mode': raw.get('mode') or 'read_store',
                'added_at': raw.get('added_at') or '',
            })

    new_manifest: dict = {
        'domain_id': kb_id,
        'name': old_manifest.get('name') or kb_id,
        'description': old_manifest.get('description') or '',
        'created_at': old_manifest.get('created_at') or datetime.now(timezone.utc).isoformat(),
        'embeddings_model': old_manifest.get('embeddings_model') or 'bge-m3',
        'pinned': False,
        'arcadedb_database': kb_id,
        'corpus_collection': f'{kb_id}__corpus',
        'entity_cache_collection': f'{kb_id}__gr_entities',
        'summary_cache_collection': f'{kb_id}__gr_summaries',
        'included_files': new_files,
    }

    new_manifest_path = os.path.join(domain_dir, 'manifest.json')
    _write_json(new_manifest_path, new_manifest)
    logger.info(
        'Migration Domain: %s -> %s (copied %d/%d source files, %d skipped)',
        kb_id, new_manifest_path, copied, len(legacy_files), skipped,
    )


# ── Step 3: ensure General Domain ──────────────────────────────────

def _ensure_general_domain() -> None:
    """Seed the pinned `general` Domain (capability-only) if missing.

    The skill content under data/domains/general/skills/ is shipped with
    the repo - we just make sure the manifest exists so the registry
    discovers the Domain.
    """
    target = os.path.join(DOMAIN_HOME_DIR, GENERAL_DOMAIN_ID, 'manifest.json')
    if os.path.isfile(target):
        return
    domain_dir = os.path.join(DOMAIN_HOME_DIR, GENERAL_DOMAIN_ID)
    for sub in ('sources', 'state', 'skills', 'tools'):
        os.makedirs(os.path.join(domain_dir, sub), exist_ok=True)

    manifest = {
        'domain_id': GENERAL_DOMAIN_ID,
        'name': 'General',
        'description': (
            "Universal Assistant behavior: fairness, honesty, voice format, "
            "citation conventions, tool-call discipline, multi-Domain awareness. "
            "Pinned-active; cannot be deactivated. Holds general-purpose tools "
            "that aren't tied to any other Domain."
        ),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'embeddings_model': 'bge-m3',
        'pinned': True,
        'deletable': False,
        'included_files': [],
    }
    _write_json(target, manifest)
    logger.info('Seeded pinned General Domain at %s', target)


# ── Step 3.5: ensure noted Domain (platform-default) ─────────────

def _ensure_noted_domain() -> None:
    """Seed the platform `noted` Domain manifest if missing.

    Unlike General (capability-only, pinned), noted is a regular knowledge
    Domain with the platform's MLOps skills. It ships with the platform
    so its skills (airflow-*, dvc-*, hydra-*, mlflow-*, noted-*) are
    always reachable. Empty `included_files` until the user uploads.

    The user can deactivate noted (drop MLOps context for a clean general
    Assistant) but cannot delete it via the UI - the Manager hides Delete
    only on pinned Domains. We don't pin noted (deactivating is fine), but
    we do auto-recreate it here on every startup so that if it gets
    deleted via API, the next restart brings it back.
    """
    target = os.path.join(DOMAIN_HOME_DIR, 'noted', 'manifest.json')
    if os.path.isfile(target):
        return
    domain_dir = os.path.join(DOMAIN_HOME_DIR, 'noted')
    for sub in ('sources', 'state', 'skills', 'tools'):
        os.makedirs(os.path.join(domain_dir, sub), exist_ok=True)

    manifest = {
        'domain_id': 'noted',
        'name': 'noted',
        'description': (
            "The noted MLOps platform. Holds platform-specific skills "
            "(airflow, dvc, hydra, mlflow, evidently) plus your noted-related "
            "documents. Activate to bring MLOps context into the Assistant; "
            "deactivate for a clean general-purpose Assistant."
        ),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'embeddings_model': 'bge-m3',
        'pinned': False,
        'deletable': False,
        'arcadedb_database': 'noted',
        'corpus_collection': 'noted__corpus',
        'entity_cache_collection': 'noted__gr_entities',
        'summary_cache_collection': 'noted__gr_summaries',
        'included_files': [],
    }
    _write_json(target, manifest)
    logger.info('Seeded platform `noted` Domain at %s', target)


# ── Step 4: ArcadeDB project_ids normalization ─────────────────────

def _normalize_noted_arcadedb() -> None:
    """Replace '__global__' with 'noted' in every Entity.project_ids[]
    entry. Best-effort: failure is logged but does not abort startup."""
    try:
        from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
    except ImportError:
        logger.info('ArcadeDB client not importable; skipping project_ids normalization')
        return

    try:
        client = ArcadeDBClient()
    except Exception as e:
        logger.info('ArcadeDB unavailable; skipping project_ids normalization: %s', e)
        return

    try:
        rows = client.command_sql(
            "SELECT @rid as rid, project_ids FROM Entity WHERE project_ids CONTAINS :pid",
            {'pid': _LEGACY_GLOBAL_PROJECT_ID},
        )
    except ArcadeDBError as e:
        logger.warning('ArcadeDB normalization: query failed: %s', e)
        return
    except Exception as e:
        logger.warning('ArcadeDB normalization: query unavailable: %s', e)
        return

    if not rows:
        return

    logger.info('ArcadeDB normalization: rewriting project_ids for %d entities (%s -> %s)',
                len(rows), _LEGACY_GLOBAL_PROJECT_ID, _NOTED_DOMAIN_ID)

    fixed = 0
    failed = 0
    for row in rows:
        rid = row.get('rid') or row.get('@rid')
        pids = row.get('project_ids') or []
        new_pids = sorted(set(
            (_NOTED_DOMAIN_ID if p == _LEGACY_GLOBAL_PROJECT_ID else p) for p in pids
        ))
        try:
            client.command_sql(
                f"UPDATE {rid} SET project_ids = :pids",
                {'pids': new_pids},
            )
            fixed += 1
        except ArcadeDBError as e:
            failed += 1
            logger.warning('ArcadeDB normalization: rid=%s failed: %s', rid, e)

    logger.info('ArcadeDB normalization: %d updated, %d failed', fixed, failed)


# ── Step 5: per-Domain ArcadeDB database split ─────────────────────

def _split_per_domain_arcadedb_dbs() -> None:
    """Each Domain owns its own ArcadeDB database inside the shared
    noted-arcadedb container. Idempotent:

    1. Walks data/domains/*/manifest.json. For each Domain that has a
       knowledge half (manifest declares an arcadedb_database), ensures
       that ArcadeDB database exists and has the schema bootstrapped.
    2. Cleans up the legacy shared `noted` database: drops entities
       exclusive to non-noted Domains (project_ids has no `noted` entry)
       and drops corrupt cross-tagged community / community_summary nodes
       (size(project_ids) > 1 - they collided across Domains under the
       old shared-DB model).

    After this migration, non-noted Domains' ArcadeDB databases START
    EMPTY. The user re-extracts them (uploaded sources still on disk
    under data/domains/<id>/sources/) into their own DB. Noted's data
    stays in the `noted` DB - it only loses entities that weren't its
    own to begin with, plus the polluted communities (recluster will
    rebuild them clean).
    """
    try:
        from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
        from app.graph_storage import GraphStorage
    except ImportError as e:
        logger.info('Per-Domain DB split: ArcadeDB modules not importable; skipping: %s', e)
        return

    if not os.path.isdir(DOMAIN_HOME_DIR):
        return

    # Walk manifests directly (the registry isn't loaded yet at startup).
    for entry in sorted(os.listdir(DOMAIN_HOME_DIR)):
        manifest_path = os.path.join(DOMAIN_HOME_DIR, entry, 'manifest.json')
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning('Per-Domain DB split: cannot read %s: %s',
                           manifest_path, e)
            continue
        db_name = manifest.get('arcadedb_database') or manifest.get('arcadedb_project_id')
        if not db_name:
            # Capability-only Domain (e.g. general) - no DB needed.
            continue
        _ensure_arcadedb_for_domain(db_name)

    _clean_legacy_shared_noted_db()


def _ensure_arcadedb_for_domain(db_name: str) -> None:
    """Create the per-Domain ArcadeDB database if missing, and bootstrap
    its Entity / RELATES schema. Idempotent."""
    from app.arcadedb_client import ArcadeDBClient, ArcadeDBError
    from app.graph_storage import GraphStorage

    try:
        probe = ArcadeDBClient()  # any DB - this call goes to /server
        if probe.database_exists(db_name):
            logger.info('Per-Domain DB %s already exists', db_name)
        else:
            ok = probe.create_database(db_name)
            if not ok:
                logger.warning('Per-Domain DB %s: CREATE DATABASE failed', db_name)
                return
            logger.info('Per-Domain DB %s: created', db_name)
    except Exception as e:
        logger.warning('Per-Domain DB %s: ensure failed: %s', db_name, e)
        return

    # Bootstrap schema by constructing a GraphStorage against this DB.
    try:
        storage = GraphStorage(arcadedb_database=db_name)
        storage.ensure_ready()
        logger.info('Per-Domain DB %s: schema bootstrapped', db_name)
    except Exception as e:
        logger.warning('Per-Domain DB %s: schema bootstrap failed: %s', db_name, e)


def _clean_legacy_shared_noted_db() -> None:
    """In the shared `noted` ArcadeDB database, drop:
      a) entities exclusive to non-noted Domains (no `noted` in project_ids)
      b) cross-tagged community + community_summary nodes (corrupt by
         id-collision under the old shared-DB model)

    Runs against the legacy shared `noted` database. Safe to re-run."""
    from app.arcadedb_client import ArcadeDBClient, ArcadeDBError

    try:
        client = ArcadeDBClient()  # default = legacy `noted` DB
    except Exception as e:
        logger.info('Cleanup shared `noted` DB skipped (ArcadeDB unavailable): %s', e)
        return

    # (a) Entities tagged exclusively with non-noted Domains.
    try:
        rows_a = client.command_sql(
            "SELECT count(*) AS c FROM Entity WHERE NOT (project_ids CONTAINS :pid)",
            {'pid': _NOTED_DOMAIN_ID},
        )
        n_other_only = int((rows_a[0] or {}).get('c', 0)) if rows_a else 0
    except (ArcadeDBError, Exception) as e:
        logger.info('Cleanup shared `noted` DB: count query failed: %s', e)
        return

    if n_other_only:
        try:
            client.command(
                "MATCH (n:Entity) WHERE NOT 'noted' IN n.project_ids DETACH DELETE n",
            )
            logger.info(
                'Cleanup shared `noted` DB: detach-deleted %d entities exclusive to '
                'non-noted Domains (their data lives in their own per-Domain DB now)',
                n_other_only,
            )
        except ArcadeDBError as e:
            logger.warning('Cleanup shared `noted` DB: delete failed: %s', e)

    # (b) Cross-tagged community / community_summary nodes - corrupt.
    # Idempotent Cypher DETACH DELETE; no pre-count (SQL `size()` doesn't
    # exist in ArcadeDB; Cypher's `size()` does). The delete is safe to
    # run when nothing matches.
    try:
        client.command(
            "MATCH (n:Entity) WHERE size(n.project_ids) > 1 "
            "AND n.type IN ['community', 'community_summary'] DETACH DELETE n",
        )
        logger.info(
            'Cleanup shared `noted` DB: detach-deleted any cross-tagged '
            'community/community_summary nodes (recluster noted to rebuild)',
        )
    except ArcadeDBError as e:
        logger.warning('Cleanup shared `noted` DB: community delete failed: %s', e)


# ── Step 6: ChromaDB collection rename status log ──────────────────

def _log_chromadb_rename_status() -> None:
    """ChromaDB collection rename ('noted_corpus' -> 'noted__corpus' etc.)
    needs a noted-rag /admin/rename_collection endpoint. When that lands,
    swap this log for an actual call. Until then, the noted Domain's data
    lives under the legacy collection names; queries will return empty
    until a full rebuild repopulates the new convention names."""
    logger.info(
        'ChromaDB rename TODO: %s -> %s__corpus, %s -> %s__gr_entities, '
        '%s -> %s__gr_summaries (waiting on noted-rag /admin/rename_collection)',
        _LEGACY_NOTED_CORPUS_COLLECTION, _NOTED_DOMAIN_ID,
        _LEGACY_NOTED_ENTITIES_COLLECTION, _NOTED_DOMAIN_ID,
        _LEGACY_NOTED_SUMMARIES_COLLECTION, _NOTED_DOMAIN_ID,
    )


# ── Helpers ─────────────────────────────────────────────────────────

def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

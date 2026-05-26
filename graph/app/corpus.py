"""Per-Domain corpus management.

Each Domain has its own manifest at /app/data/domains/<domain_id>/manifest.json.
Source files live INSIDE the Domain at /app/data/domains/<domain_id>/sources/.
No cross-Domain sharing of source files - if the same file is wanted in two
Domains, it's uploaded twice (one copy per Domain).

`included_files` is a list of entries shaped:
    {"path": "user_manual.md", "mode": "read_store", "added_at": "2026-04-27T..."}

Modes:
  - "read_only"  : visible in the Domain's Documents tree, openable via
                   MediaViewer, NOT indexed in vector or graph.
  - "read_store" : visible in the Documents tree AND indexed in vector +
                   graph. Default for new uploads.

For backward compat, bare-string entries (legacy P3.x layout) are treated as
mode='read_store'. New writes always use the dict shape.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

from app.config import DOMAIN_HOME_DIR

logger = logging.getLogger(__name__)


_lock = threading.Lock()

MODE_READ_ONLY = 'read_only'
MODE_READ_STORE = 'read_store'
_VALID_MODES = {MODE_READ_ONLY, MODE_READ_STORE}


# -- Path helpers ----------------------------------------------------

def manifest_path(domain_id: str) -> str:
    return os.path.join(DOMAIN_HOME_DIR, domain_id, 'manifest.json')


def sources_dir(domain_id: str) -> str:
    return os.path.join(DOMAIN_HOME_DIR, domain_id, 'sources')


def source_abs_path(domain_id: str, rel_path: str) -> str:
    """Resolve a manifest-relative path to an absolute path on disk."""
    return os.path.join(sources_dir(domain_id), rel_path)


def _ensure_dirs(domain_id: str) -> None:
    os.makedirs(sources_dir(domain_id), exist_ok=True)
    os.makedirs(os.path.join(DOMAIN_HOME_DIR, domain_id), exist_ok=True)


# -- Manifest read/write ---------------------------------------------

def _load_manifest(domain_id: str) -> dict:
    """Load the Domain manifest. Raises FileNotFoundError if missing."""
    with open(manifest_path(domain_id), 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_manifest(domain_id: str, manifest: dict) -> None:
    path = manifest_path(domain_id)
    _ensure_dirs(domain_id)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp, path)


def _normalize_entry(raw) -> dict | None:
    """Coerce a raw `included_files` entry into the canonical dict shape.
    Returns None for invalid entries (caller should skip them).

    Accepts either:
      - bare string  -> {path, mode='read_store', added_at='', category='', display_name=''}  (legacy)
      - dict         -> validated; path required; mode/added_at/category/
                        display_name preserved when present (all optional;
                        '' = unset). `display_name` is the user-friendly
                        title shown in the Explorer tree; '' falls back to
                        basename(path) at render time.
    """
    if isinstance(raw, str):
        if not raw:
            return None
        return {'path': raw, 'mode': MODE_READ_STORE, 'added_at': '',
                'category': '', 'display_name': ''}
    if isinstance(raw, dict):
        path = raw.get('path')
        if not path:
            return None
        mode = raw.get('mode') or MODE_READ_STORE
        if mode not in _VALID_MODES:
            logger.warning('included_files entry %r has invalid mode %r; coercing to %s',
                           path, mode, MODE_READ_STORE)
            mode = MODE_READ_STORE
        normalized = {
            'path': path,
            'mode': mode,
            'added_at': raw.get('added_at') or '',
            'category': (raw.get('category') or '').strip(),
            'display_name': (raw.get('display_name') or '').strip(),
        }
        # Preserve chunking_profile_id when present. Omitted on entries
        # that predate the field (and on entries uploaded without an
        # explicit profile) so downstream code can `.get()`-check it.
        cpid = raw.get('chunking_profile_id')
        if isinstance(cpid, str) and cpid:
            normalized['chunking_profile_id'] = cpid
        return normalized
    return None


# -- Public API ------------------------------------------------------

def list_documents(domain_id: str) -> list[dict]:
    """Return the Domain's documents as
    [{path, mode, added_at, category, display_name, exists, basename}, ...].

    `path` is relative to /app/data/domains/<domain_id>/sources/.
    `exists` is computed against the filesystem at call time.
    `category` is '' when uncategorized.
    `display_name` is '' when the user hasn't renamed the doc; the
    frontend falls back to `basename` for the tree title in that case.
    """
    with _lock:
        manifest = _load_manifest(domain_id)
    out = []
    for raw in manifest.get('included_files', []):
        entry = _normalize_entry(raw)
        if entry is None:
            continue
        abs_path = source_abs_path(domain_id, entry['path'])
        out.append({
            'path': entry['path'],
            'mode': entry['mode'],
            'added_at': entry['added_at'],
            'category': entry.get('category', ''),
            'display_name': entry.get('display_name', ''),
            'exists': os.path.isfile(abs_path),
            'basename': os.path.basename(entry['path']),
        })
    return out


def chunking_profile_for(domain_id: str, rel_path: str) -> str | None:
    """Return the chunking_profile_id recorded in the manifest entry
    for `rel_path`, or None when the entry is absent / the field is not
    present (legacy entries, or uploads without an explicit profile
    choice). Called from _doc_add_worker to re-apply the user's per-doc
    chunking choice on background re-chunks."""
    with _lock:
        manifest = _load_manifest(domain_id)
    for raw in manifest.get('included_files', []):
        entry = _normalize_entry(raw)
        if entry is None:
            continue
        if entry['path'] == rel_path:
            return entry.get('chunking_profile_id') or None
    return None


def list_paths(domain_id: str, mode_filter: str | None = MODE_READ_STORE) -> list[str]:
    """Just the manifest-relative paths, in order. md_scanner /
    research_builder consume this.

    Defaults to mode_filter='read_store' so callers that ingest into
    vector/graph see only indexable files. Pass mode_filter=None to get
    every file regardless of mode.
    """
    docs = list_documents(domain_id)
    if mode_filter is None:
        return [d['path'] for d in docs]
    return [d['path'] for d in docs if d['mode'] == mode_filter]


def get_mode(domain_id: str, path: str) -> str | None:
    """Return the mode for `path` in this Domain, or None if not present."""
    for d in list_documents(domain_id):
        if d['path'] == path:
            return d['mode']
    return None


def add_uploaded_file(
    filename: str,
    content_bytes: bytes,
    domain_id: str,
    mode: str = MODE_READ_STORE,
    category: str = '',
    chunking_profile_id: str | None = None,
) -> dict:
    """Save uploaded file to this Domain's sources/ and append (or update)
    the manifest entry.

    The file lands at data/domains/<domain_id>/sources/<basename>. If a
    file with the same name exists already, it is OVERWRITTEN (per the
    user's "override = replace" semantic). The manifest entry is
    de-duplicated by path; a re-upload with a different mode/category
    UPDATES them in place. Returns {path, replaced, mode, category}.

    `category` is an optional free-text taxonomy label used by the
    Documents tree to group files within a Domain. Empty = uncategorized.

    `chunking_profile_id` is the named profile (see
    chunking_profiles.json) chosen at upload time. Persisted in the
    manifest entry so the _doc_add_worker (and any future bulk
    rebuild) can re-apply the same profile when re-chunking this
    document. None = use the catalog default at chunk time.

    Accepted formats: .md plus the Docling-handled set
    (.pdf, .docx, .pptx, .html, .htm).
    """
    if mode not in _VALID_MODES:
        raise ValueError(f'invalid mode {mode!r}; must be one of {sorted(_VALID_MODES)}')
    safe_name = os.path.basename(filename)
    _ext = os.path.splitext(safe_name)[1].lower()
    if _ext not in ('.md', '.pdf', '.docx', '.pptx', '.html', '.htm'):
        raise ValueError(
            f'Unsupported file extension {_ext!r}. '
            'Accepted: .md, .pdf, .docx, .pptx, .html, .htm'
        )
    _ensure_dirs(domain_id)
    target = os.path.join(sources_dir(domain_id), safe_name)
    relative_path = os.path.relpath(target, sources_dir(domain_id))
    replaced = os.path.isfile(target)
    with open(target, 'wb') as f:
        f.write(content_bytes)
    cat = (category or '').strip()
    with _lock:
        manifest = _load_manifest(domain_id)
        files = [_normalize_entry(e) for e in manifest.get('included_files', [])]
        files = [e for e in files if e is not None and e['path'] != relative_path]
        entry = {
            'path': relative_path,
            'mode': mode,
            'added_at': datetime.now(timezone.utc).isoformat(),
            'category': cat,
        }
        if chunking_profile_id:
            entry['chunking_profile_id'] = chunking_profile_id
        files.append(entry)
        manifest['included_files'] = files
        _save_manifest(domain_id, manifest)
    out = {
        'path': relative_path,
        'replaced': replaced,
        'mode': mode,
        'category': cat,
        'domain_id': domain_id,
    }
    if chunking_profile_id:
        out['chunking_profile_id'] = chunking_profile_id
    return out


def remove_document(path: str, domain_id: str) -> dict:
    """Drop a path from this Domain's manifest AND delete the source file
    on disk (no cross-Domain sharing - the file is owned by this Domain).
    Returns {path, removed_from_list, file_deleted}.
    """
    file_deleted = False
    with _lock:
        manifest = _load_manifest(domain_id)
        files = [_normalize_entry(e) for e in manifest.get('included_files', [])]
        files = [e for e in files if e is not None]
        before = len(files)
        files = [e for e in files if e['path'] != path]
        removed_from_list = len(files) < before
        if removed_from_list:
            manifest['included_files'] = files
            _save_manifest(domain_id, manifest)
            try:
                os.remove(source_abs_path(domain_id, path))
                file_deleted = True
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning('remove_document(%s, %s): cannot delete file: %s',
                               domain_id, path, e)
    return {
        'path': path,
        'removed_from_list': removed_from_list,
        'file_deleted': file_deleted,
        'domain_id': domain_id,
    }


def set_category(path: str, category: str, domain_id: str) -> dict:
    """Update the category of an existing manifest entry. Returns
    {path, updated, category} - updated=False if path not present.
    No-op on a missing entry rather than raising; the caller can decide
    whether 'not found' is a 404."""
    cat = (category or '').strip()
    with _lock:
        manifest = _load_manifest(domain_id)
        files = [_normalize_entry(e) for e in manifest.get('included_files', [])]
        files = [e for e in files if e is not None]
        updated = False
        for e in files:
            if e['path'] == path:
                e['category'] = cat
                updated = True
                break
        if updated:
            manifest['included_files'] = files
            _save_manifest(domain_id, manifest)
    return {'path': path, 'updated': updated, 'category': cat, 'domain_id': domain_id}


def set_display_name(path: str, display_name: str, domain_id: str) -> dict:
    """Update the user-friendly display name of an existing manifest entry.
    Returns {path, updated, display_name}; updated=False if path not present.
    Empty string clears the override (tree falls back to basename(path))."""
    name = (display_name or '').strip()
    with _lock:
        manifest = _load_manifest(domain_id)
        files = [_normalize_entry(e) for e in manifest.get('included_files', [])]
        files = [e for e in files if e is not None]
        updated = False
        for e in files:
            if e['path'] == path:
                e['display_name'] = name
                updated = True
                break
        if updated:
            manifest['included_files'] = files
            _save_manifest(domain_id, manifest)
    return {'path': path, 'updated': updated, 'display_name': name,
            'domain_id': domain_id}


def get_manifest(domain_id: str) -> dict:
    """Return the full Domain manifest."""
    with _lock:
        return _load_manifest(domain_id)

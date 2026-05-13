"""Per-tenant secret store (Phase H1 of the auth workstream).

File-backed JSON KV at `data/tenants/<tenant_id>/vault/<NAME>.json`.

Design decisions (2026-05-12, perm fix 2026-05-13):
  - **Plain JSON.** Single-host T1; anyone with host root has the
    bind-mount either way. Encryption at this tier is theatre.
    Fernet/KMS layer arrives when we move multi-host (project memory:
    feedback_dont_assume_single_user_local).
  - **File perms 0644, dir 0755.** Originally 0600/0700, but noted backend
    runs as uid 0 (root) inside its container and noted-tools runs as
    uid 1000 — strict owner-only perms broke the cross-service bridge
    (noted-tools' secret_resolver got PermissionError on the bind-mount).
    Since the trust boundary on T1 is the host filesystem (anyone with
    `docker exec` is already root either way), readable-to-the-host is
    fine; the chmod was theatre that didn't add real security.
  - **Per-tenant scope** (not per-tool). One place to set; per-tool
    declares which secrets it reads via `tool.json._meta.allowed_secrets`.
    The executor enforces the allowlist at injection time (Phase H3).
  - **Audit log** at `data/tenants/<tenant>/vault/_audit.jsonl` — append-
    only, one JSON object per line. Records every set/get/delete with
    timestamp + actor_id + secret name (never the value). Reading the log
    is how operators trace "who saw secret X when".
  - **Name validation**: UPPERCASE + digits + underscore, max 64 chars,
    starts with a letter. Avoids path-traversal + matches the
    `SECRET_<NAME>` env-var convention used by tool_author.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

logger = logging.getLogger(__name__)


class VaultError(RuntimeError):
    """Any failure interacting with the vault."""


class VaultNotFound(VaultError):
    """Requested secret does not exist for this tenant."""


_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')

# Module-level lock map: one RLock per tenant. The lock serializes
# concurrent writes to the same tenant's vault dir (otherwise two
# set_secret() calls could race on the atomic-rename). RLock so a
# manager's own helpers can re-enter under the same lock.
_TENANT_LOCKS: dict[str, threading.RLock] = {}
_TENANT_LOCKS_GUARD = threading.Lock()


def _tenant_lock(tenant_id: str) -> threading.RLock:
    with _TENANT_LOCKS_GUARD:
        lk = _TENANT_LOCKS.get(tenant_id)
        if lk is None:
            lk = threading.RLock()
            _TENANT_LOCKS[tenant_id] = lk
        return lk


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise VaultError(
            f'invalid secret name {name!r}: must match {_NAME_RE.pattern} '
            '(UPPERCASE, digits, underscores; first char a letter; max 64)'
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VaultManager:
    """Per-tenant vault. Instantiate once per tenant_id; methods are
    thread-safe via a per-tenant RLock."""

    def __init__(self, tenant_id: str):
        if not isinstance(tenant_id, str) or not tenant_id:
            raise VaultError('tenant_id must be a non-empty string')
        self.tenant_id = tenant_id
        self._dir = Path(DATA_DIR) / 'tenants' / tenant_id / 'vault'
        self._audit = self._dir / '_audit.jsonl'
        self._lock = _tenant_lock(tenant_id)

    # ── path helpers ───────────────────────────────────────────────
    def _path(self, name: str) -> Path:
        _validate_name(name)
        return self._dir / f'{name}.json'

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        # 0755 so noted-tools (uid 1000) can traverse the bind mount even
        # when noted backend writes as uid 0. See module docstring for
        # the trust-boundary discussion.
        try:
            os.chmod(self._dir, 0o755)
        except OSError:  # platform may not support; non-fatal
            pass

    # ── audit ──────────────────────────────────────────────────────
    def _audit_log(self, op: str, name: str, actor_id: str,
                   ok: bool, detail: str = '') -> None:
        self._ensure_dir()
        record = {
            'ts': _now_iso(),
            'tenant': self.tenant_id,
            'actor': actor_id,
            'op': op,
            'name': name,
            'ok': ok,
        }
        if detail:
            record['detail'] = detail
        try:
            with self._audit.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(record) + '\n')
            try:
                os.chmod(self._audit, 0o644)
            except OSError:
                pass
        except OSError as e:
            # Audit logging is best-effort; do not let a disk-full event
            # mask a successful set. Just warn.
            logger.warning('vault audit-log write failed (tenant=%s op=%s name=%s): %s',
                           self.tenant_id, op, name, e)

    # ── operations ─────────────────────────────────────────────────
    def set_secret(self, name: str, value: str, *, actor_id: str) -> None:
        """Write a secret. Atomic via temp+rename so concurrent reads
        never see a half-written file."""
        if not isinstance(value, str):
            raise VaultError('secret value must be a string')
        path = self._path(name)
        with self._lock:
            self._ensure_dir()
            existing_ts = None
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding='utf-8'))
                    existing_ts = existing.get('created_at')
                except (OSError, json.JSONDecodeError):
                    existing_ts = None
            now = _now_iso()
            payload = {
                'name': name,
                'value': value,
                'created_at': existing_ts or now,
                'updated_at': now,
            }
            tmp = path.with_suffix(path.suffix + '.tmp')
            try:
                tmp.write_text(json.dumps(payload), encoding='utf-8')
                try:
                    os.chmod(tmp, 0o644)
                except OSError:
                    pass
                os.replace(tmp, path)  # atomic on POSIX
                try:
                    os.chmod(path, 0o644)
                except OSError:
                    pass
            except OSError as e:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                self._audit_log('set', name, actor_id, ok=False, detail=str(e))
                raise VaultError(f'failed to write secret {name}: {e}') from e
            self._audit_log('set', name, actor_id, ok=True)

    def get_secret(self, name: str, *, actor_id: str) -> str:
        """Read a secret. Raises VaultNotFound if absent."""
        path = self._path(name)
        with self._lock:
            if not path.exists():
                self._audit_log('get', name, actor_id, ok=False, detail='not_found')
                raise VaultNotFound(f'secret {name!r} not set for tenant {self.tenant_id!r}')
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as e:
                self._audit_log('get', name, actor_id, ok=False, detail=f'parse:{e}')
                raise VaultError(f'failed to read secret {name}: {e}') from e
            self._audit_log('get', name, actor_id, ok=True)
            return data.get('value', '')

    def delete_secret(self, name: str, *, actor_id: str) -> bool:
        """Remove a secret. Returns True if it existed, False if absent."""
        path = self._path(name)
        with self._lock:
            if not path.exists():
                self._audit_log('delete', name, actor_id, ok=False, detail='not_found')
                return False
            try:
                path.unlink()
            except OSError as e:
                self._audit_log('delete', name, actor_id, ok=False, detail=str(e))
                raise VaultError(f'failed to delete secret {name}: {e}') from e
            self._audit_log('delete', name, actor_id, ok=True)
            return True

    def list_secrets(self) -> list[dict[str, Any]]:
        """List secret NAMES + timestamps (never values). Used by the
        UI to show "which secrets does this tenant have set"."""
        with self._lock:
            if not self._dir.exists():
                return []
            out: list[dict[str, Any]] = []
            for entry in sorted(self._dir.iterdir()):
                if entry.name.startswith('_') or entry.suffix != '.json':
                    continue
                try:
                    data = json.loads(entry.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    continue
                out.append({
                    'name': data.get('name', entry.stem),
                    'created_at': data.get('created_at'),
                    'updated_at': data.get('updated_at'),
                })
            return out

    def resolve_allowed_secrets(self, allowed: list[str], *, actor_id: str) -> dict[str, str]:
        """Resolve a tool's `_meta.allowed_secrets` list into a dict of
        SECRET_<NAME>=value pairs the executor injects as env vars.
        Raises VaultNotFound for any missing secret; the executor surfaces
        that as a clean tool-launch error so the operator knows to
        set the missing secret."""
        out: dict[str, str] = {}
        for name in allowed:
            value = self.get_secret(name, actor_id=actor_id)
            out[f'SECRET_{name}'] = value
        return out

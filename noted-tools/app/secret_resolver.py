"""Resolve `tool.json._meta.allowed_secrets` to env-var values at tool
launch (Phase H3 of the auth workstream).

Reads the per-tenant JSON-backed vault written by noted's
`VaultManager` (see `noted/backend/app/managers/vault_manager.py`).
The vault directory is bind-mounted into noted-tools via the
docker-compose stanza (`../data/tenants:/app/data/tenants`); no HTTP
round-trip is needed.

Tenant scope:
  - Today single-tenant; uses the `default` tenant to match
    `USER_TOOLS_DIR=/app/data/tenants/default/user_tools` in the
    noted-tools service env.
  - Multi-tenant lookup will plumb a tenant_id from the request
    context when noted's auth plan adds X-Forwarded-User.

Failure mode:
  - Missing secret -> raise SecretNotFound. The caller (executor)
    surfaces a clear ExecResult to the model so the operator knows
    which name to `set_secret`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Vault root inside the noted-tools container. Matches the
# docker-compose bind: ../data/tenants:/app/data/tenants
_VAULT_ROOT = Path(os.environ.get('VAULT_ROOT', '/app/data/tenants'))
_TENANT_DEFAULT = os.environ.get('VAULT_TENANT_ID', 'default')
_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')


class SecretNotFound(RuntimeError):
    """Raised when a tool's allowed_secrets references an unset secret."""


def _path(tenant_id: str, name: str) -> Path:
    if not _NAME_RE.match(name):
        raise SecretNotFound(
            f'invalid secret name {name!r}: must match {_NAME_RE.pattern}'
        )
    return _VAULT_ROOT / tenant_id / 'vault' / f'{name}.json'


def _read_value(tenant_id: str, name: str) -> str:
    path = _path(tenant_id, name)
    if not path.exists():
        raise SecretNotFound(
            f'secret {name!r} not set for tenant {tenant_id!r}; '
            f'paste a value via the set_secret tool'
        )
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        raise SecretNotFound(
            f'secret {name!r} could not be read for tenant {tenant_id!r}: {e}'
        ) from e
    value = data.get('value')
    if not isinstance(value, str):
        raise SecretNotFound(
            f'secret {name!r} payload is malformed for tenant {tenant_id!r}'
        )
    return value


def resolve(allowed: list[str], tenant_id: str | None = None) -> dict[str, str]:
    """Resolve an allowlist into a dict of SECRET_<NAME> = value pairs
    suitable for subprocess env injection. Returns an empty dict for an
    empty allowlist. Raises SecretNotFound on the FIRST missing secret —
    the executor surfaces that to the caller without spawning the
    subprocess."""
    if not allowed:
        return {}
    tid = tenant_id or _TENANT_DEFAULT
    out: dict[str, str] = {}
    for name in allowed:
        out[f'SECRET_{name}'] = _read_value(tid, name)
    return out

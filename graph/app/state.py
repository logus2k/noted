"""Per-Domain persistent state that must survive container restarts.

So far: pending-recluster markers per Domain. Set when a per-doc op
leaves community structure (PageRank / Leiden / community summaries)
stale; cleared when a recluster (or full rebuild) finishes.

Layout: /app/data/domains/<domain_id>/state/pending_recluster.json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.config import DOMAIN_HOME_DIR

logger = logging.getLogger(__name__)


def _state_dir(domain_id: str) -> str:
    return os.path.join(DOMAIN_HOME_DIR, domain_id, 'state')


def _path_for(domain_id: str) -> str:
    return os.path.join(_state_dir(domain_id), 'pending_recluster.json')


def set_recluster_pending(domain_id: str, reason: str = '') -> None:
    """Mark <domain_id> as needing a recluster. Idempotent: re-setting just
    updates the timestamp + reason. Survives restart."""
    try:
        os.makedirs(_state_dir(domain_id), exist_ok=True)
        payload = {
            'domain_id': domain_id,
            'set_at': datetime.now(timezone.utc).isoformat(),
            'reason': reason or '',
        }
        with open(_path_for(domain_id), 'w') as f:
            json.dump(payload, f, indent=2)
    except OSError as e:
        logger.warning('Failed to persist recluster-pending marker for %s: %s', domain_id, e)


def clear_recluster_pending(domain_id: str) -> None:
    """Drop the marker (no-op if it doesn't exist)."""
    try:
        os.remove(_path_for(domain_id))
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning('Failed to clear recluster-pending marker for %s: %s', domain_id, e)


def get_recluster_pending(domain_id: str) -> dict | None:
    """Return the marker payload (set_at, reason) or None if not set."""
    try:
        with open(_path_for(domain_id)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning('Failed to read recluster-pending marker for %s: %s', domain_id, e)
        return None


def list_recluster_pending() -> dict[str, dict]:
    """Map of domain_id -> marker payload, for the UI to render at startup.

    Walks every Domain directory under DOMAIN_HOME_DIR and reads its
    state/pending_recluster.json if present.
    """
    out: dict[str, dict] = {}
    if not os.path.isdir(DOMAIN_HOME_DIR):
        return out
    for domain_id in os.listdir(DOMAIN_HOME_DIR):
        d_dir = os.path.join(DOMAIN_HOME_DIR, domain_id)
        if not os.path.isdir(d_dir):
            continue
        payload = get_recluster_pending(domain_id)
        if payload:
            out[domain_id] = payload
    return out

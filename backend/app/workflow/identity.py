"""Identity threading from oauth2-proxy headers into the workflow context.

When the outer nginx's `auth_request /oauth2/auth` block extends to `/noted/`
(see `reference_oauth2_proxy_google_idp.md`), oauth2-proxy injects:

  X-Forwarded-User       - the OIDC `sub` claim (canonical user id)
  X-Forwarded-Email      - email
  X-Forwarded-Preferred-Username - display name (best-effort)

This module reads those headers, falling back to a constant `"default"` tenant
and actor when absent. The fallback path is what runs in dev today; the same
code activates real identity once the auth plan lands without any change here.

Callers (workflow trigger endpoints) call `extract_identity(request)` and
pass `tenant_id` + `actor_id` to `run_workflow`. The framework itself takes
those as parameters; it never reads request state directly so it stays
testable without a request scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_TENANT_ID = "default"
DEFAULT_ACTOR_ID = "default"


@dataclass
class Identity:
    tenant_id: str
    actor_id: str
    email: str | None = None
    display_name: str | None = None


def extract_identity(headers: Any) -> Identity:
    """Read identity from a request's headers (any case-insensitive Mapping).

    Designed to accept FastAPI's `request.headers` (CIMultiDict) or a plain
    dict; only `.get(name, default)` is required.
    """
    user = (headers.get("X-Forwarded-User") or "").strip()
    email = (headers.get("X-Forwarded-Email") or "").strip() or None
    display = (headers.get("X-Forwarded-Preferred-Username") or "").strip() or None
    if not user:
        return Identity(
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=DEFAULT_ACTOR_ID,
            email=email,
            display_name=display,
        )
    # In V1, tenant == actor (single-user-per-tenant). When team / org
    # tenancy lands, the auth plan will inject an X-Forwarded-Group or
    # similar and tenant_id will derive from that instead.
    return Identity(
        tenant_id=user,
        actor_id=user,
        email=email,
        display_name=display,
    )

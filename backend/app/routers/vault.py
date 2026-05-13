"""Per-tenant secret-store HTTP endpoints (Phase H2 of the auth workstream).

CRUD for the values backing `tool.json._meta.allowed_secrets`. Frontend
calls these from the `set_secret` MCP tool's masked-input flow (Phase K)
and from any future "Manage secrets" panel in the UI.

Security model:
  - All writes are audited (see VaultManager._audit_log).
  - Plain JSON at rest, perms 0600 (single-host T1; KMS later).
  - This router does NOT return secret VALUES via GET. The only way a
    secret value leaves the vault is through the executor's
    `resolve_allowed_secrets()` path, which injects into a tool's
    subprocess env after checking the tool's declared allowlist.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.managers.vault_manager import VaultError, VaultManager, VaultNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vault", tags=["vault"])


def _vault_for(tenant_id: str) -> VaultManager:
    """Resolve a VaultManager for the requesting tenant. Today we
    default the single-user single-tenant 'default' assignment; once
    auth lands in noted proper, the tenant_id will come from the
    request context (Authorization header or session cookie)."""
    return VaultManager(tenant_id or "default")


class SecretSetRequest(BaseModel):
    name: str = Field(..., description="UPPERCASE secret name, [A-Z][A-Z0-9_]{0,63}")
    value: str = Field(..., description="Secret value; not echoed back from any endpoint")
    tenant_id: str = Field("default", description="Tenant scope (single-tenant default for now)")
    actor_id: str = Field("user", description="Who is setting the secret (audit only)")


class SecretDeleteRequest(BaseModel):
    tenant_id: str = Field("default")
    actor_id: str = Field("user")


@router.get("/secrets")
async def list_secrets(tenant_id: str = "default") -> dict:
    """List secret NAMES set for this tenant. Values are never returned.
    Used by the UI to render "secrets you've set" without exposing them."""
    try:
        items = _vault_for(tenant_id).list_secrets()
    except VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"tenant_id": tenant_id, "secrets": items}


@router.post("/secrets")
async def set_secret(req: SecretSetRequest) -> dict:
    """Create or overwrite a secret. Atomic write; audit-logged.
    The value is never echoed back."""
    try:
        _vault_for(req.tenant_id).set_secret(
            req.name, req.value, actor_id=req.actor_id,
        )
    except VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"tenant_id": req.tenant_id, "name": req.name, "ok": True}


@router.delete("/secrets/{name}")
async def delete_secret(name: str, tenant_id: str = "default", actor_id: str = "user") -> dict:
    """Remove a secret. 404 if the secret was not set."""
    try:
        existed = _vault_for(tenant_id).delete_secret(name, actor_id=actor_id)
    except VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not existed:
        raise HTTPException(status_code=404, detail=f"secret {name!r} not set for tenant {tenant_id!r}")
    return {"tenant_id": tenant_id, "name": name, "deleted": True}


@router.get("/secrets/{name}/exists")
async def secret_exists(name: str, tenant_id: str = "default") -> dict:
    """Probe-only endpoint: does this secret exist? Returns boolean,
    never the value. Useful for the UI to show "needs to be set" hints
    on tools that declare allowed_secrets the tenant hasn't filled."""
    try:
        items = _vault_for(tenant_id).list_secrets()
    except VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    names = {item["name"] for item in items}
    return {"tenant_id": tenant_id, "name": name, "exists": name in names}

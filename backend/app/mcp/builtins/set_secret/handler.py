"""`set_secret` MCP tool handler (Phase K1 of the auth workstream).

In-process call to VaultManager — same code path as the
POST /api/vault/secrets HTTP endpoint, just without the HTTP hop.
The value never leaves the process via this handler; the response
string explicitly does NOT include it.

Frontend rendering: `tool.json.inputSchema.properties.value` carries
`format: "password"` + `writeOnly: true` — the noted chat UI uses
these to render the input box masked when the model invokes this tool.

Audit: every set is logged by VaultManager to
`data/tenants/<tenant>/vault/_audit.jsonl` (tenant + actor + op +
name + ok + timestamp; never the value).
"""

from __future__ import annotations

import logging
from typing import Any

from app.managers.vault_manager import VaultError, VaultManager

logger = logging.getLogger(__name__)


async def handler(
    args: dict,
    managers: dict | None = None,
    ctx: dict | None = None,
) -> str:
    name = (args.get("name") or "").strip()
    value = args.get("value")
    tenant_id = (args.get("tenant_id") or "default").strip() or "default"

    if not name:
        return "Error: 'name' is required (UPPERCASE secret identifier)."
    if not isinstance(value, str) or not value:
        return "Error: 'value' is required (the secret value the user pasted)."

    # actor_id comes from the chat request context when the dispatcher
    # passes it; otherwise audit logs the literal "user".
    actor_id = "user"
    if isinstance(ctx, dict):
        actor_id = str(ctx.get("actor_id") or actor_id)

    try:
        VaultManager(tenant_id).set_secret(name, value, actor_id=actor_id)
    except VaultError as e:
        logger.warning("set_secret tenant=%s name=%s failed: %s", tenant_id, name, e)
        return f"Error: could not store secret {name}: {e}"

    # Response intentionally does NOT include the value. The model and
    # the chat history both see only the confirmation, never the secret.
    return (
        f"Stored secret {name} for tenant {tenant_id}. "
        f"Tools that declare it in `_meta.allowed_secrets` will read "
        f"the value at runtime via the env var SECRET_{name}."
    )

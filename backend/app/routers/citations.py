"""Citation resolver: turn a chat citation tag into navigable provenance.

Tag forms supported (Phase 1A + Phase 2):
  `[markdown_chunk:hex]` - chunk citation. Returns source_path + page_no/bbox
                            for click-to-open + deep-jump in the PDF/MD viewer.
  `[E:entity_id]`        - entity citation. Returns entity props +
                            neighborhood for click-to-open in GraphPanel
                            (trace mode).
  `[R:src>type>tgt]`     - relationship citation. Returns parsed src/type/tgt
                            and the union neighborhood of both endpoints.
  `[Cn]`                 - community summary citation. Returns the community
                            summary text + member entities.

The model emits tags WITHOUT a domain prefix (it doesn't know the
active-Domain set), so the resolver fans out across the active Domain
set and returns the first hit.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from fastapi import APIRouter, HTTPException

from app.routers.kb import NOTED_GRAPH_BASE, get_active_domains

# Shared keepalive client for all citation lookups. Lazy-init on first use
# so the client is created inside an event loop. Same per-call timeout
# overrides as before via client.X(..., timeout=...).
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient()
    return _shared_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/citations", tags=["citations"])

_COMMUNITY_RE = re.compile(r"^C(\d+)$")


@router.get("/{tag:path}")
async def resolve_citation(tag: str):
    """Resolve a citation tag to provenance metadata."""
    tag = (tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="empty tag")

    active = get_active_domains() or []
    if not active:
        raise HTTPException(status_code=404, detail="no active Domains")

    # Dispatch by tag form
    if tag.startswith("markdown_chunk:"):
        return await _resolve_chunk(tag, active)
    if tag.startswith("E:"):
        return await _resolve_entity(tag[len("E:"):], active)
    if tag.startswith("R:"):
        return await _resolve_relationship(tag[len("R:"):], active)
    m = _COMMUNITY_RE.match(tag)
    if m:
        return await _resolve_community(int(m.group(1)), active)

    raise HTTPException(status_code=404, detail=f"unknown citation form: {tag}")


# ── Chunk ─────────────────────────────────────────────────────────────────

async def _resolve_chunk(tag: str, active: list[str]) -> dict:
    """Fan out to noted-graph's per-Domain chunk lookup. First hit wins."""
    client = _get_client()

    async def _try(domain_id: str):
        try:
            r = await client.get(
                f"{NOTED_GRAPH_BASE}/research/{domain_id}/chunk/{tag}",
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            return None
        return None

    results = await asyncio.gather(*[_try(d) for d in active])

    for hit in results:
        if hit:
            return hit

    raise HTTPException(status_code=404, detail=f"chunk not found in active Domains: {tag}")


# ── Entity ────────────────────────────────────────────────────────────────

async def _resolve_entity(entity_id: str, active: list[str]) -> dict:
    """Fan out to neighborhood lookup. Returns the first Domain that has it
    plus its 2-hop subgraph for the GraphPanel trace view."""
    client = _get_client()

    async def _try(domain_id: str):
        try:
            r = await client.get(
                f"{NOTED_GRAPH_BASE}/research/{domain_id}/entity/{entity_id}/neighborhood",
                params={"hops": 2, "limit": 80},
                timeout=8,
            )
            if r.status_code == 200:
                payload = r.json()
                payload["domain_id"] = domain_id
                return payload
        except httpx.HTTPError:
            return None
        return None

    results = await asyncio.gather(*[_try(d) for d in active])

    for hit in results:
        if hit:
            return {
                "type": "entity",
                "domain_id": hit.get("domain_id"),
                "entity_id": entity_id,
                # Subgraph payload shape compatible with GraphPanel trace mode
                "trace": {
                    "seed_entity_id": hit.get("seed_entity_id") or entity_id,
                    "entities": hit.get("entities") or [],
                    "edges": hit.get("edges") or [],
                },
            }

    raise HTTPException(status_code=404, detail=f"entity not found: {entity_id}")


# ── Relationship ──────────────────────────────────────────────────────────

async def _resolve_relationship(body: str, active: list[str]) -> dict:
    """Tag form: `R:source>type>target`. Parse, then fetch the union of
    both endpoints' neighborhoods so the GraphPanel can show the edge in
    context."""
    parts = body.split(">")
    if len(parts) != 3:
        raise HTTPException(
            status_code=400,
            detail=f"malformed relationship tag (expected R:src>type>tgt): {body}",
        )
    src_id, edge_type, tgt_id = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if not src_id or not tgt_id:
        raise HTTPException(status_code=400, detail="src/tgt empty")

    # Resolve each endpoint via the entity branch and merge subgraphs.
    # Both lookups are independent — fan out concurrently. (src_id and
    # tgt_id are both validated non-empty above, so no None-guard needed.)
    src, tgt = await asyncio.gather(
        _resolve_entity(src_id, active),
        _resolve_entity(tgt_id, active),
    )

    # Union the entities + edges from both lookups (dedup by id)
    ents_by_id: dict = {}
    edges: list = []
    edge_keys: set = set()
    for side in (src, tgt):
        if not side:
            continue
        for e in (side.get("trace") or {}).get("entities") or []:
            if e.get("id") and e["id"] not in ents_by_id:
                ents_by_id[e["id"]] = e
        for r in (side.get("trace") or {}).get("edges") or []:
            key = (r.get("source"), r.get("type"), r.get("target"))
            if all(key) and key not in edge_keys:
                edge_keys.add(key)
                edges.append(r)

    if not ents_by_id:
        raise HTTPException(status_code=404, detail=f"relationship endpoints not found: {body}")

    return {
        "type": "relationship",
        "domain_id": (src or tgt or {}).get("domain_id"),
        "edge": {"source": src_id, "type": edge_type, "target": tgt_id},
        "trace": {
            "seed_entity_id": src_id,
            "entities": list(ents_by_id.values()),
            "edges": edges,
        },
    }


# ── Community ─────────────────────────────────────────────────────────────

async def _resolve_community(cid: int, active: list[str]) -> dict:
    """Fan out to community detail. First hit wins."""
    client = _get_client()

    async def _try(domain_id: str):
        try:
            r = await client.get(
                f"{NOTED_GRAPH_BASE}/research/{domain_id}/communities/{cid}",
                timeout=8,
            )
            if r.status_code == 200:
                payload = r.json()
                payload["domain_id"] = domain_id
                return payload
        except httpx.HTTPError:
            return None
        return None

    results = await asyncio.gather(*[_try(d) for d in active])

    for hit in results:
        if hit:
            members = hit.get("members") or hit.get("top_members") or []
            return {
                "type": "community",
                "domain_id": hit.get("domain_id"),
                "community_id": cid,
                "summary": hit.get("summary") or hit.get("summary_text") or "",
                "members": members[:30],
            }

    raise HTTPException(status_code=404, detail=f"community {cid} not found")

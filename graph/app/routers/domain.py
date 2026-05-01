"""Domain lifecycle endpoints (graph-side).

Exposes the DomainRegistry CRUD surface so the noted backend can mirror
it. The actual per-Domain operations (rebuild, recluster, doc/add, ...)
live in routers/research.py under `/research/{domain_id}/...`.

Endpoints:
  GET    /domains              - list every Domain known to the registry
  POST   /domains              - create a new Domain (capability-only optional)
  DELETE /domains/{domain_id}  - drop a Domain (manifest + ChromaDB collections + ArcadeDB project)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.domain_registry import registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/domains', tags=['domains'])


class CreateDomainRequest(BaseModel):
    domain_id: str = Field(..., min_length=1, max_length=32)
    name: str | None = Field(default=None)
    description: str = Field(default='')
    capability_only: bool = Field(
        default=False,
        description=(
            'When true, the Domain has no knowledge half (no ArcadeDB '
            'project, no ChromaDB collections) - useful for Domains that '
            'only host skills/tools.'
        ),
    )


class UpdateDomainRequest(BaseModel):
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)


@router.get('')
def list_domains() -> dict:
    """Return every Domain known to the registry, in stable order."""
    domains = [ctx.to_dict() for ctx in sorted(registry().list(), key=lambda c: c.domain_id)]
    return {'domains': domains}


@router.post('')
def create_domain(req: CreateDomainRequest) -> dict:
    """Mint a new Domain: writes its manifest + state dir on disk and adds
    a DomainContext to the in-memory registry. ChromaDB collections + the
    ArcadeDB project are created lazily on first write by the per-Domain
    code paths (no eager allocation needed).
    """
    try:
        ctx = registry().create(
            domain_id=req.domain_id,
            name=req.name,
            description=req.description,
            capability_only=req.capability_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ctx.to_dict()


@router.patch('/{domain_id}')
def update_domain(domain_id: str, req: UpdateDomainRequest) -> dict:
    """Update name + description of an existing Domain. arcadedb_database,
    pinned, and collection names are fixed at creation time."""
    try:
        ctx = registry().update(
            domain_id, name=req.name, description=req.description,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f'unknown Domain: {domain_id!r}')
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ctx.to_dict()


@router.delete('/{domain_id}')
def delete_domain(domain_id: str) -> dict:
    """Drop a Domain. Cannot delete a pinned Domain."""
    try:
        return registry().delete(domain_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f'unknown Domain: {domain_id!r}')
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

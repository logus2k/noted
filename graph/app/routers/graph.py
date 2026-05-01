"""Graph API - full graph, neighborhood, and entity endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Query

from app.graph_builder import GraphBuilder
from app.graph_cache import GraphCache
from app.graph_storage import GraphStorage
from app.arcadedb_client import ArcadeDBError
from app.config import CACHE_TTL_SECONDS, ARCADEDB_SYNC_ENABLED

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])

_builder = GraphBuilder()
_cache = GraphCache(ttl_seconds=CACHE_TTL_SECONDS)
# Per-project graph syncing is independent of the GraphRAG/KB layer:
# project scanners (Hydra, MLflow, Airflow, ...) write into ArcadeDB
# under the project's own project_id, NOT under a KB project_id. P3.2:
# `GraphStorage` is parameterized at construction with one project_id,
# so this router constructs a fresh storage per call instead of sharing
# one mutable instance.

def _sync_to_arcadedb(graph) -> None:
    """Write a freshly built graph to ArcadeDB. Swallows errors so the
    in-memory path (the existing UI) keeps working even if ArcadeDB is down."""
    if not ARCADEDB_SYNC_ENABLED:
        return
    try:
        storage = GraphStorage(project_id=graph.project_id)
        storage.replace_project_graph(graph.entities, graph.relationships)
    except ArcadeDBError as e:
        logger.warning('ArcadeDB sync failed for %s: %s', graph.project_id, e)
    except Exception:
        logger.exception('Unexpected ArcadeDB sync failure for %s', graph.project_id)


def _get_graph(project_id: str, max_age: int | None = None):
    """Get or build the graph for a project."""
    graph = _cache.get(project_id)
    if graph:
        return graph
    graph = _builder.build(project_id)
    _cache.set(project_id, graph)
    _sync_to_arcadedb(graph)
    return graph


@router.get("/graph/{project_id}")
def get_graph(project_id: str, max_age: int = Query(default=300)):
    """Get the full entity-relationship graph for a project."""
    try:
        graph = _get_graph(project_id, max_age)
        return graph.model_dump()
    except Exception as e:
        logger.exception("Failed to build graph")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/graph/{project_id}/neighborhood/{entity_id:path}")
def get_neighborhood(project_id: str, entity_id: str, hops: int = Query(default=2)):
    """Get the N-hop neighborhood around an entity."""
    try:
        graph = _get_graph(project_id)

        # Find center entity
        center = None
        for e in graph.entities:
            if e.id == entity_id:
                center = e
                break
        if not center:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

        # BFS to find N-hop neighbors
        visited = {entity_id}
        frontier = {entity_id}
        included_rels = []

        for _ in range(hops):
            next_frontier = set()
            for rel in graph.relationships:
                if rel.source in frontier:
                    next_frontier.add(rel.target)
                    included_rels.append(rel)
                if rel.target in frontier:
                    next_frontier.add(rel.source)
                    included_rels.append(rel)
            next_frontier -= visited
            visited |= next_frontier
            frontier = next_frontier

        # Collect entities
        neighbor_entities = [e for e in graph.entities if e.id in visited]
        # Deduplicate relationships
        seen = set()
        unique_rels = []
        for r in included_rels:
            key = (r.source, r.target, r.type)
            if key not in seen and r.source in visited and r.target in visited:
                seen.add(key)
                unique_rels.append(r)

        return {
            'center': center.model_dump(),
            'entities': [e.model_dump() for e in neighbor_entities],
            'relationships': [r.model_dump() for r in unique_rels],
            'hops': hops,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get neighborhood")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/graph/{project_id}/entity/{entity_id:path}")
def get_entity(project_id: str, entity_id: str):
    """Get a single entity with its direct relationships."""
    try:
        graph = _get_graph(project_id)

        entity = None
        for e in graph.entities:
            if e.id == entity_id:
                entity = e
                break
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

        # Direct relationships
        rels = [r for r in graph.relationships if r.source == entity_id or r.target == entity_id]

        return {
            'entity': entity.model_dump(),
            'relationships': [r.model_dump() for r in rels],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get entity")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/graph/{project_id}/invalidate")
def invalidate_cache(project_id: str):
    """Force rebuild of the graph on next request."""
    _cache.invalidate(project_id)
    return {'invalidated': True, 'project_id': project_id}


@router.get("/graph/_arcadedb/status")
def arcadedb_status(project_id: str | None = None):
    """Inspect ArcadeDB connectivity + entity/relationship counts.

    Diagnostic-only. Useful to confirm sync is working without opening
    Studio. `project_id` is required (cross-project counts removed in P3.2
    because `GraphStorage` is now scoped to one project per instance).
    """
    if not ARCADEDB_SYNC_ENABLED:
        return {'enabled': False}
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail='project_id is required (P3.2: counts are per-project)',
        )
    try:
        storage = GraphStorage(project_id=project_id)
        storage.ensure_ready()
        counts = storage.counts()
        return {'enabled': True, 'ready': True, 'counts': counts, 'project_id': project_id}
    except ArcadeDBError as e:
        return {'enabled': True, 'ready': False, 'error': str(e)}

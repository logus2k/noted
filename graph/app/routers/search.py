"""Search API - full-text search across graph entities."""

import logging
from fastapi import APIRouter, HTTPException, Query

from app.routers.graph import _get_graph
from app.search_index import SearchIndex

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

_index_cache: dict[str, SearchIndex] = {}


def _get_index(project_id: str) -> SearchIndex:
    """Get or build the search index for a project."""
    graph = _get_graph(project_id)
    # Rebuild index if graph changed
    cache_key = f"{project_id}:{graph.built_at}"
    if cache_key not in _index_cache:
        index = SearchIndex()
        index.build(graph.entities)
        _index_cache.clear()  # Only cache one project at a time
        _index_cache[cache_key] = index
    return _index_cache[cache_key]


@router.get("/search/{project_id}")
def search(project_id: str,
           q: str = Query(description="Search query"),
           type: str = Query(default=None, description="Filter by entity type"),
           limit: int = Query(default=20, description="Max results")):
    """Search across all entities in a project's graph.

    Query types:
    - Text: "GRU" matches labels, properties, IDs
    - Metric threshold: "val_loss < 0.1"
    - Tag: "#experiment-batch-1"
    """
    try:
        index = _get_index(project_id)
        results = index.search(q, entity_type=type, limit=limit)
        return {
            'query': q,
            'type_filter': type,
            'results': [r.model_dump() for r in results],
            'total': len(results),
        }
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=f"{type.__name__ if isinstance(type, type) else 'Error'}: {e}")

"""In-memory graph cache with TTL-based invalidation."""

import time
import logging
from app.models import Graph

logger = logging.getLogger(__name__)


class GraphCache:
    """Caches built graphs per project with configurable TTL."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[Graph, float]] = {}
        self._ttl = ttl_seconds

    def get(self, project_id: str) -> Graph | None:
        """Get cached graph if fresh, None if stale or missing."""
        entry = self._cache.get(project_id)
        if not entry:
            return None
        graph, timestamp = entry
        if time.time() - timestamp > self._ttl:
            del self._cache[project_id]
            return None
        return graph

    def set(self, project_id: str, graph: Graph):
        """Cache a graph for a project."""
        self._cache[project_id] = (graph, time.time())

    def invalidate(self, project_id: str):
        """Remove a project's cached graph."""
        self._cache.pop(project_id, None)

    def invalidate_all(self):
        """Clear entire cache."""
        self._cache.clear()

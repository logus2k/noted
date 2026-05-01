"""Pydantic models for the Knowledge Graph."""

from __future__ import annotations
from pydantic import BaseModel


class Entity(BaseModel):
    """A node in the knowledge graph."""
    id: str                      # Unique: "{type}:{source_id}" e.g. "run:abc123"
    type: str                    # Entity type: project, run, data_file, model, etc.
    label: str                   # Human-readable display name
    properties: dict = {}        # Type-specific metadata
    tags: list[dict] = []        # User and auto-generated tags [{key, value}]


class Relationship(BaseModel):
    """A directed edge between two entities."""
    source: str                  # Source entity ID
    target: str                  # Target entity ID
    type: str                    # Relationship type: contains, produces, uses_data, etc.
    properties: dict = {}        # Edge metadata


class Graph(BaseModel):
    """Complete entity-relationship graph for a project."""
    project_id: str
    entities: list[Entity] = []
    relationships: list[Relationship] = []
    entity_count: int = 0
    relationship_count: int = 0
    built_at: str = ''           # ISO timestamp


class Neighborhood(BaseModel):
    """N-hop neighborhood around a center entity."""
    center: Entity
    entities: list[Entity] = []
    relationships: list[Relationship] = []
    hops: int = 2


class ViewDefinition(BaseModel):
    """A perspective view that filters and shapes the graph."""
    name: str
    description: str = ''
    is_builtin: bool = False
    primary_entities: list[str] = []      # Entity types to emphasize (large nodes)
    secondary_entities: list[str] = []    # Entity types to show smaller
    hidden_entities: list[str] = []       # Entity types to hide
    emphasized_relationships: list[str] = []  # Relationship types to highlight
    layout: str = 'force'                 # force, hierarchical, radial, timeline
    color_by: str = 'entity_type'         # entity_type, status, metric, recency, tag
    size_by: str | None = None            # metric, file_size, run_count, version_count


class SearchResult(BaseModel):
    """A search result with relevance score."""
    entity: Entity
    score: float = 0.0
    matches: list[str] = []      # Which fields matched

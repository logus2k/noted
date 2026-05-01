"""Full-text search index across all graph entities.

Builds an in-memory inverted index from entity labels, properties, and tags.
Supports text matching, type filtering, and metric threshold queries.
"""

import logging
import re
from app.models import Entity, SearchResult

logger = logging.getLogger(__name__)


class SearchIndex:
    """In-memory search index built from graph entities."""

    def __init__(self):
        self._entities: list[Entity] = []
        self._tokens: dict[str, list[int]] = {}  # token -> [entity indices]

    def build(self, entities: list[Entity]):
        """Build the search index from a list of entities."""
        self._entities = list(entities)
        self._tokens = {}

        for i, entity in enumerate(self._entities):
            tokens = self._extract_tokens(entity)
            for token in tokens:
                self._tokens.setdefault(token, []).append(i)

    def search(self, query: str, entity_type: str | None = None,
               limit: int = 20) -> list[SearchResult]:
        """Search entities by text query.

        Supports:
        - Text matching: "GRU" matches labels, property values, tags
        - Type filter: type=run narrows to run entities
        - Metric threshold: "val_loss < 0.1" (basic numeric comparison)
        - Tag search: "#tag_name" matches tag keys/values
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        # Check for metric threshold query (e.g., "val_loss < 0.1")
        threshold_match = re.match(r'^(\w+)\s*([<>=!]+)\s*([\d.]+)$', query)
        if threshold_match:
            return self._metric_search(
                threshold_match.group(1),
                threshold_match.group(2),
                float(threshold_match.group(3)),
                entity_type, limit,
            )

        # Check for tag search (e.g., "#experiment-batch-1")
        if query.startswith('#'):
            return self._tag_search(query[1:], entity_type, limit)

        # Standard text search
        query_tokens = self._tokenize(query.lower())
        if not query_tokens:
            return []

        # Score entities by token match count
        scores: dict[int, float] = {}
        matched_fields: dict[int, list[str]] = {}

        for token in query_tokens:
            # Exact match
            if token in self._tokens:
                for idx in self._tokens[token]:
                    scores[idx] = scores.get(idx, 0) + 1.0
                    matched_fields.setdefault(idx, []).append(f'exact:{token}')

            # Prefix match (for partial queries)
            for indexed_token, indices in self._tokens.items():
                if indexed_token.startswith(token) and indexed_token != token:
                    for idx in indices:
                        scores[idx] = scores.get(idx, 0) + 0.5
                        matched_fields.setdefault(idx, []).append(f'prefix:{token}')

        # Filter by type
        if entity_type:
            scores = {idx: score for idx, score in scores.items()
                      if self._entities[idx].type == entity_type}

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        return [
            SearchResult(
                entity=self._entities[idx],
                score=score,
                matches=list(set(matched_fields.get(idx, []))),
            )
            for idx, score in ranked
        ]

    def _metric_search(self, metric_key: str, operator: str, threshold: float,
                       entity_type: str | None, limit: int) -> list[SearchResult]:
        """Search entities by metric threshold."""
        results = []
        for entity in self._entities:
            if entity_type and entity.type != entity_type:
                continue
            metrics = entity.properties.get('metrics', {})
            if metric_key not in metrics:
                continue
            value = metrics[metric_key]
            if not isinstance(value, (int, float)):
                continue

            match = False
            if operator == '<':
                match = value < threshold
            elif operator == '<=':
                match = value <= threshold
            elif operator == '>':
                match = value > threshold
            elif operator == '>=':
                match = value >= threshold
            elif operator in ('==', '='):
                match = abs(value - threshold) < 1e-9
            elif operator == '!=':
                match = abs(value - threshold) >= 1e-9

            if match:
                results.append(SearchResult(
                    entity=entity,
                    score=1.0,
                    matches=[f'{metric_key} {operator} {threshold} (actual: {value})'],
                ))

        results.sort(key=lambda r: r.entity.properties.get('metrics', {}).get(metric_key, 0))
        return results[:limit]

    def _tag_search(self, tag_query: str, entity_type: str | None,
                    limit: int) -> list[SearchResult]:
        """Search entities by tag key or value."""
        tag_query_lower = tag_query.lower()
        results = []
        for entity in self._entities:
            if entity_type and entity.type != entity_type:
                continue
            for tag in entity.tags:
                key = str(tag.get('key', '')).lower()
                value = str(tag.get('value', '')).lower()
                if tag_query_lower in key or tag_query_lower in value:
                    results.append(SearchResult(
                        entity=entity,
                        score=1.0 if tag_query_lower == key else 0.7,
                        matches=[f'tag:{tag.get("key")}={tag.get("value")}'],
                    ))
                    break

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _extract_tokens(self, entity: Entity) -> set[str]:
        """Extract searchable tokens from an entity."""
        tokens = set()

        # Label
        tokens.update(self._tokenize(entity.label.lower()))

        # Type
        tokens.add(entity.type)

        # ID components
        tokens.update(self._tokenize(entity.id.lower()))

        # Properties (flatten values to strings)
        for key, value in entity.properties.items():
            tokens.add(key.lower())
            if isinstance(value, str):
                tokens.update(self._tokenize(value.lower()))
            elif isinstance(value, (int, float)):
                tokens.add(str(value))
            elif isinstance(value, dict):
                for k, v in value.items():
                    tokens.add(k.lower())
                    if isinstance(v, str):
                        tokens.update(self._tokenize(v.lower()))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        tokens.update(self._tokenize(item.lower()))

        # Tags
        for tag in entity.tags:
            tokens.add(str(tag.get('key', '')).lower())
            tokens.add(str(tag.get('value', '')).lower())

        # Remove empty tokens
        tokens.discard('')
        return tokens

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text into searchable tokens."""
        return [t for t in re.split(r'[^a-z0-9_.]+', text) if t and len(t) > 1]

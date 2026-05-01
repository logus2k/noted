"""Graph Builder - orchestrates entity scanning and relationship resolution.

Scans all data sources (MLflow, DVC, Hydra, Airflow, filesystem) and builds
a unified entity-relationship graph for a project.
"""

import json
import logging
import os
from datetime import datetime, timezone

from app.models import Graph, Entity, Relationship
from app.config import PROJECTS_DIR, MOUNTS_DIR
from app.scanners.mlflow_scanner import MlflowScanner
from app.scanners.dvc_scanner import DvcScanner
from app.scanners.hydra_scanner import HydraScanner
from app.scanners.airflow_scanner import AirflowScanner
from app.scanners.filesystem_scanner import FilesystemScanner
from app.relationship_resolver import RelationshipResolver

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds the Knowledge Graph by scanning all data sources."""

    def __init__(self):
        self._mlflow = MlflowScanner()
        self._dvc = DvcScanner()
        self._hydra = HydraScanner()
        self._airflow = AirflowScanner()
        self._filesystem = FilesystemScanner()
        self._resolver = RelationshipResolver()

    def build(self, project_id: str) -> Graph:
        """Build the complete graph for a project.

        Scans all sources, collects entities and relationships,
        then resolves cross-source relationships.
        """
        all_entities: list[Entity] = []
        all_relationships: list[Relationship] = []

        # Filesystem (projects, notebooks, files)
        try:
            entities, rels = self._filesystem.scan(project_id)
            all_entities.extend(entities)
            all_relationships.extend(rels)
            logger.info("Filesystem scan: %d entities, %d rels", len(entities), len(rels))
        except Exception as e:
            logger.warning("Filesystem scan failed: %s", e)

        # MLflow (experiments, runs, snapshots, models)
        try:
            entities, rels = self._mlflow.scan(project_id)
            all_entities.extend(entities)
            all_relationships.extend(rels)
            logger.info("MLflow scan: %d entities, %d rels", len(entities), len(rels))
        except Exception as e:
            logger.warning("MLflow scan failed: %s", e)

        # DVC (tracked data files, versions)
        try:
            entities, rels = self._dvc.scan(project_id)
            all_entities.extend(entities)
            all_relationships.extend(rels)
            logger.info("DVC scan: %d entities, %d rels", len(entities), len(rels))
        except Exception as e:
            logger.warning("DVC scan failed: %s", e)

        # Hydra (config dirs, groups, options)
        try:
            entities, rels = self._hydra.scan(project_id)
            all_entities.extend(entities)
            all_relationships.extend(rels)
            logger.info("Hydra scan: %d entities, %d rels", len(entities), len(rels))
        except Exception as e:
            logger.warning("Hydra scan failed: %s", e)

        # Airflow (DAGs, tasks, runs)
        try:
            entities, rels = self._airflow.scan(project_id)
            all_entities.extend(entities)
            all_relationships.extend(rels)
            logger.info("Airflow scan: %d entities, %d rels", len(entities), len(rels))
        except Exception as e:
            logger.warning("Airflow scan failed: %s", e)

        # Resolve cross-source relationships
        try:
            cross_rels = self._resolver.resolve(all_entities)
            all_relationships.extend(cross_rels)
            logger.info("Resolved %d cross-source relationships", len(cross_rels))
        except Exception as e:
            logger.warning("Relationship resolution failed: %s", e)

        # Deduplicate entities by ID
        seen_ids = set()
        unique_entities = []
        for e in all_entities:
            if e.id not in seen_ids:
                seen_ids.add(e.id)
                unique_entities.append(e)

        # Deduplicate relationships
        seen_rels = set()
        unique_rels = []
        for r in all_relationships:
            key = (r.source, r.target, r.type)
            if key not in seen_rels:
                seen_rels.add(key)
                unique_rels.append(r)

        # Load user tags into entities
        self._load_tags(project_id, unique_entities)

        # Remove relationships with missing endpoints
        entity_ids = {e.id for e in unique_entities}
        valid_rels = [r for r in unique_rels if r.source in entity_ids and r.target in entity_ids]

        return Graph(
            project_id=project_id,
            entities=unique_entities,
            relationships=valid_rels,
            entity_count=len(unique_entities),
            relationship_count=len(valid_rels),
            built_at=datetime.now(timezone.utc).isoformat(),
        )

    def _load_tags(self, project_id: str, entities: list[Entity]):
        """Load user-defined tags from .noted/tags/ into entity objects."""
        if project_id.startswith('__mount__:'):
            name = project_id[len('__mount__:'):]
            base = os.path.join(MOUNTS_DIR, name)
        else:
            base = os.path.join(PROJECTS_DIR, project_id)

        tags_dir = os.path.join(base, '.noted', 'tags')
        if not os.path.isdir(tags_dir):
            return

        # Build entity lookup by safe ID
        entity_by_safe_id = {}
        for e in entities:
            safe_id = e.id.replace(':', '_').replace('/', '_')
            entity_by_safe_id[safe_id] = e

        for f in os.listdir(tags_dir):
            if not f.endswith('.json'):
                continue
            safe_id = f[:-5]  # Strip .json
            entity = entity_by_safe_id.get(safe_id)
            if not entity:
                continue
            try:
                with open(os.path.join(tags_dir, f)) as fh:
                    tags = json.load(fh)
                entity.tags = tags
            except Exception:
                pass

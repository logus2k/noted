"""Tags API - add, remove, and list tags on entities.

Tags are stored as JSON files in .noted/tags/ within each project directory.
Each entity's tags are in a file named by the entity ID (with : replaced by _).
"""

import json
import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import PROJECTS_DIR, MOUNTS_DIR
from app.routers.graph import _get_graph, _cache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tags"])


class TagRequest(BaseModel):
    key: str
    value: str = ''


def _tags_dir(project_id: str) -> str:
    """Get the tags directory for a project, creating if needed."""
    if project_id.startswith('__mount__:'):
        name = project_id[len('__mount__:'):]
        base = os.path.join(MOUNTS_DIR, name)
    else:
        base = os.path.join(PROJECTS_DIR, project_id)

    tags_dir = os.path.join(base, '.noted', 'tags')
    os.makedirs(tags_dir, exist_ok=True)
    return tags_dir


def _entity_tags_file(project_id: str, entity_id: str) -> str:
    """Get the path to an entity's tag file."""
    safe_id = entity_id.replace(':', '_').replace('/', '_')
    return os.path.join(_tags_dir(project_id), f'{safe_id}.json')


def _load_entity_tags(project_id: str, entity_id: str) -> list[dict]:
    """Load tags for an entity."""
    path = _entity_tags_file(project_id, entity_id)
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _save_entity_tags(project_id: str, entity_id: str, tags: list[dict]):
    """Save tags for an entity."""
    path = _entity_tags_file(project_id, entity_id)
    if not tags:
        # Remove empty tag file
        if os.path.isfile(path):
            os.remove(path)
        return
    with open(path, 'w') as f:
        json.dump(tags, f, indent=2)


@router.get("/tags/{project_id}")
def list_all_tags(project_id: str):
    """List all unique tags across all entities in a project."""
    tags_dir_path = _tags_dir(project_id)
    tag_counts: dict[str, int] = {}

    if os.path.isdir(tags_dir_path):
        for f in os.listdir(tags_dir_path):
            if not f.endswith('.json'):
                continue
            try:
                with open(os.path.join(tags_dir_path, f)) as fh:
                    tags = json.load(fh)
                for tag in tags:
                    key = f"{tag.get('key', '')}={tag.get('value', '')}"
                    tag_counts[key] = tag_counts.get(key, 0) + 1
            except Exception:
                pass

    return {
        'tags': [
            {'key': k.split('=')[0], 'value': k.split('=', 1)[1] if '=' in k else '', 'entity_count': count}
            for k, count in sorted(tag_counts.items())
        ],
    }


@router.get("/tags/{project_id}/entity/{entity_id:path}")
def get_entity_tags(project_id: str, entity_id: str):
    """Get all tags for a specific entity."""
    return {'entity_id': entity_id, 'tags': _load_entity_tags(project_id, entity_id)}


@router.post("/tags/{project_id}/entity/{entity_id:path}")
def add_tag(project_id: str, entity_id: str, body: TagRequest):
    """Add a tag to an entity."""
    if not body.key or not body.key.strip():
        raise HTTPException(status_code=400, detail="Tag key is required")

    tags = _load_entity_tags(project_id, entity_id)

    # Remove existing tag with same key (update)
    tags = [t for t in tags if t.get('key') != body.key.strip()]
    tags.append({'key': body.key.strip(), 'value': body.value.strip()})

    _save_entity_tags(project_id, entity_id, tags)

    # Invalidate graph cache so tags appear in next graph build
    _cache.invalidate(project_id)

    return {'added': True, 'entity_id': entity_id, 'key': body.key.strip(), 'value': body.value.strip()}


@router.delete("/tags/{project_id}/entity/{entity_id:path}/{key}")
def remove_tag(project_id: str, entity_id: str, key: str):
    """Remove a tag from an entity."""
    tags = _load_entity_tags(project_id, entity_id)
    original_len = len(tags)
    tags = [t for t in tags if t.get('key') != key]

    if len(tags) == original_len:
        raise HTTPException(status_code=404, detail=f"Tag '{key}' not found on entity")

    _save_entity_tags(project_id, entity_id, tags)
    _cache.invalidate(project_id)

    return {'removed': True, 'entity_id': entity_id, 'key': key}

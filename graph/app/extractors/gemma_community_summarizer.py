"""Gemma-powered community summarizer.

For each community produced by Leiden, synthesizes a short, retrieval-
oriented summary from the member entity names + descriptions. The summary
is indexed (via bge-m3) at query time so global-mode retrieval can pick
the relevant communities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.llm_client import LLMClient, LLMError
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are a technical writer summarizing a cluster of related concepts "
    "from an MLOps platform's documentation. Return ONLY a JSON object "
    "with one field `summary`: a single dense paragraph of 3-5 sentences "
    "that captures the theme of this cluster, names 3-5 of the most "
    "important concepts in it, and explains how they relate. "
    "Do not pad with generic language; grounded, specific, useful."
)


def _user_prompt(members: list[Entity]) -> str:
    lines = [f'Cluster of {len(members)} related entities:', '']
    # Cap the prompt at the most-information-dense slice to keep the
    # context window reasonable even for huge communities.
    for m in members[:60]:
        name = m.properties.get('canonical_name') or m.label
        desc = m.properties.get('description') or ''
        if desc:
            lines.append(f'- {m.type}: {name} -- {desc}')
        else:
            lines.append(f'- {m.type}: {name}')
    if len(members) > 60:
        lines.append(f'... and {len(members) - 60} more.')
    lines.append('')
    lines.append('Write the JSON summary.')
    return '\n'.join(lines)


def summarize_communities(
    community_entities: list[Entity],
    community_memberships: dict[str, int],
    entity_by_id: dict[str, Entity],
    client: LLMClient | None = None,
) -> tuple[list[Entity], list[Relationship]]:
    """Generate one community_summary entity per community.

    Returns the new summary entities plus :summarizes edges.
    """
    if not community_entities:
        return [], []

    llm = client or LLMClient()
    # Invert memberships: community_id -> [member_ids]
    by_cid: dict[int, list[str]] = {}
    for eid, cid in community_memberships.items():
        by_cid.setdefault(cid, []).append(eid)

    summary_entities: list[Entity] = []
    rels: list[Relationship] = []

    for ce in community_entities:
        cid = ce.properties.get('community_id')
        if cid is None:
            continue
        members = [entity_by_id[mid] for mid in by_cid.get(cid, []) if mid in entity_by_id]
        # Skip communities with no thematic members (they'd summarize nothing useful)
        thematic = [m for m in members if m.type in {'concept', 'person', 'organization', 'term'}]
        if len(thematic) < 2:
            continue
        try:
            parsed = llm.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=_user_prompt(thematic),
                temperature=0.2,
                max_tokens=1024,
            )
        except LLMError as e:
            logger.warning('Community %s summarization failed: %s', cid, e)
            continue
        text = (parsed.get('summary') or '').strip()
        if not text:
            continue
        summary_id = f'community_summary:{cid}'
        summary_entities.append(Entity(
            id=summary_id,
            type='community_summary',
            label=f'Summary for community {cid}',
            properties={
                'community_id': cid,
                'text': text,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'token_count': max(1, int(len(text) / 3.8)),
            },
        ))
        rels.append(Relationship(
            source=summary_id,
            target=ce.id,
            type='summarizes',
        ))

    logger.info('Community summaries: generated %d', len(summary_entities))
    return summary_entities, rels

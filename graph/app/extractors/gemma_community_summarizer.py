"""Gemma-powered community summarizer.

For each community produced by Leiden, synthesizes a short, retrieval-
oriented summary from the member entity names + descriptions. The summary
is indexed (via bge-m3) at query time so global-mode retrieval can pick
the relevant communities.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.config import COMMUNITY_SUMMARY_PARALLELISM
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


# JSON schema passed to llama.cpp's json_schema-constrained sampling.
# The sampler enforces this at token level — including proper backslash
# escaping inside string values. Without this, LaTeX content like
# `$\lambda$` or `$\partial b$` produced ~1% malformed-JSON failures
# (bare `\l`, `\p` rejected by json.loads). With this, the sampler
# physically cannot emit invalid escapes. See llm_client.chat_json
# docstring for the failure-mode history.
_SUMMARY_SCHEMA: dict = {
    'type': 'object',
    'required': ['summary'],
    'properties': {
        'summary': {'type': 'string', 'minLength': 1},
    },
    'additionalProperties': False,
}


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


def _summarize_one(
    ce: Entity,
    by_cid: dict[int, list[str]],
    entity_by_id: dict[str, Entity],
    llm: LLMClient,
) -> tuple[str, Entity | None, Relationship | None]:
    """Build one community summary. Returns a tagged result:
      ('ok', entity, rel)     - summary generated successfully
      ('skipped', None, None) - intentional skip (no community_id,
                                fewer than 2 thematic members, or
                                empty LLM response). NOT a gap.
      ('failed', None, None)  - LLM error during generation. This IS
                                a real gap the user should see.
    Pure function over its inputs — safe to call from worker threads
    sharing the same LLMClient."""
    cid = ce.properties.get('community_id')
    if cid is None:
        return ('skipped', None, None)
    members = [entity_by_id[mid] for mid in by_cid.get(cid, []) if mid in entity_by_id]
    thematic = [m for m in members if m.type in {'concept', 'person', 'organization', 'term'}]
    if len(thematic) < 2:
        return ('skipped', None, None)
    try:
        parsed = llm.chat_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_user_prompt(thematic),
            temperature=0.2,
            max_tokens=1024,
            json_schema=_SUMMARY_SCHEMA,
        )
    except LLMError as e:
        logger.warning('Community %s summarization failed: %s', cid, e)
        return ('failed', None, None)
    text = (parsed.get('summary') or '').strip()
    if not text:
        # Empty LLM response: not a hard failure, treat as skip so the
        # community doesn't generate a useless empty summary entity and
        # doesn't keep flipping the recluster banner forever.
        return ('skipped', None, None)
    summary_id = f'community_summary:{cid}'
    summary_entity = Entity(
        id=summary_id,
        type='community_summary',
        label=f'Summary for community {cid}',
        properties={
            'community_id': cid,
            'text': text,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'token_count': max(1, int(len(text) / 3.8)),
        },
    )
    rel = Relationship(
        source=summary_id,
        target=ce.id,
        type='summarizes',
    )
    return ('ok', summary_entity, rel)


def summarize_communities(
    community_entities: list[Entity],
    community_memberships: dict[str, int],
    entity_by_id: dict[str, Entity],
    client: LLMClient | None = None,
) -> tuple[list[Entity], list[Relationship], int, int]:
    """Generate one community_summary entity per community.

    Returns `(summary_entities, summarizes_edges, n_attempted, n_failed)`:
      - summary_entities / summarizes_edges: the produced graph objects.
      - n_attempted: communities the summarizer ACTUALLY tried to summarize
        (i.e. those with >=2 thematic members; eligibility-skipped ones
        excluded). Use this for "real" denominators - comparing
        len(summary_entities) against this tells you the true coverage.
      - n_failed: of those attempted, how many failed due to LLM errors.
        This is the signal for a gap that's worth surfacing to the user
        (recluster banner). Intentional skips are not a gap.

    The per-community Gemma calls run in parallel up to
    COMMUNITY_SUMMARY_PARALLELISM workers; the same llama-server slot
    constraint as entity extraction applies (raising past the slot count
    just queues server-side). Output order matches input order so
    downstream consumers see deterministic results.
    """
    if not community_entities:
        return [], [], 0, 0

    llm = client or LLMClient()
    # Invert memberships: community_id -> [member_ids]
    by_cid: dict[int, list[str]] = {}
    for eid, cid in community_memberships.items():
        by_cid.setdefault(cid, []).append(eid)

    workers = max(1, COMMUNITY_SUMMARY_PARALLELISM)
    summary_entities: list[Entity] = []
    rels: list[Relationship] = []
    n_attempted = 0
    n_failed = 0

    # ThreadPoolExecutor.map preserves input order. _summarize_one is a
    # pure function of (ce, by_cid, entity_by_id, llm) — by_cid and
    # entity_by_id are read-only here; LLMClient is already used
    # concurrently from extraction's 4-way pool so it's thread-safe.
    if workers == 1:
        results = (_summarize_one(ce, by_cid, entity_by_id, llm) for ce in community_entities)
    else:
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='gemma-summary')
        results = pool.map(lambda ce: _summarize_one(ce, by_cid, entity_by_id, llm), community_entities)

    try:
        for status, ent, rel in results:
            if status == 'ok':
                n_attempted += 1
                summary_entities.append(ent)
                rels.append(rel)
            elif status == 'failed':
                n_attempted += 1
                n_failed += 1
            # 'skipped' contributes to neither counter (intentional).
    finally:
        if workers > 1:
            pool.shutdown(wait=True)

    logger.info(
        'Community summaries: generated %d / %d attempted (failed=%d, parallelism=%d)',
        len(summary_entities), n_attempted, n_failed, workers,
    )
    return summary_entities, rels, n_attempted, n_failed

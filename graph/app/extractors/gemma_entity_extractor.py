"""Gemma-powered entity extractor for markdown chunks.

Given a chunk of prose, asks Gemma to return a JSON list of entities found
in the text: concepts, persons, organizations, terms. Each entity carries
a confidence score; entries below the configured floor are dropped.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import ENTITY_CONFIDENCE_FLOOR
from app.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)


_VALID_TYPES = {'concept', 'person', 'organization', 'term'}


_SYSTEM_PROMPT = (
    "You extract named entities from technical documentation. "
    "Return ONLY a JSON object with one field `entities`, a list of items. "
    "Each item has: "
    "`type` (one of: concept, person, organization, term), "
    "`name` (the canonical form as it appears or a cleaned-up version), "
    "`description` (a 1-sentence description grounded in the text), "
    "`confidence` (0.0 to 1.0). "
    "Rules: "
    "- concept = an abstract idea, feature, or capability (e.g. 'knowledge graph', 'RAG'). "
    "- person = an individual's name. "
    "- organization = a company, team, or project name. "
    "- term = a technical acronym or jargon word with a specific meaning (e.g. 'DVC', 'MLflow'). "
    "- Skip generic words ('system', 'platform', 'data'). "
    "- Skip file paths, URLs, code snippets, variable names. "
    "- Prefer canonical names over possessive/pronominal forms. "
    "- confidence reflects how clearly the entity is introduced or defined in THIS chunk."
)


def _format_user_prompt(chunk_text: str) -> str:
    return (
        "Extract entities from this chunk of a noted MLOps platform "
        "documentation:\n\n---\n"
        + chunk_text.strip()
        + "\n---"
    )


class GemmaEntityExtractor:
    """Wraps LLMClient with the extraction prompt + post-filtering."""

    def __init__(self, client: LLMClient | None = None,
                 confidence_floor: float = ENTITY_CONFIDENCE_FLOOR):
        self._llm = client or LLMClient()
        self._floor = confidence_floor
        # Below-floor entities are logged, not stored (per Q D decision).
        self._below_floor_log: list[dict] = []

    def extract(self, chunk_text: str) -> list[dict[str, Any]]:
        """Return a list of accepted entity dicts for this chunk.

        Each dict: {type, name, description, confidence}.
        Below-floor entries are captured in self._below_floor_log but not
        returned.
        """
        if not chunk_text or not chunk_text.strip():
            return []
        try:
            parsed = self._llm.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=_format_user_prompt(chunk_text),
                temperature=0.1,
                max_tokens=2048,
            )
        except LLMError as e:
            logger.warning('Entity extraction LLM call failed: %s', e)
            return []

        # Gemma occasionally returns a top-level list `[...]` instead of
        # the requested `{"entities": [...]}` wrapper. The system prompt
        # asks for the wrapper but `response_format={"type":"json_object"}`
        # in llama-cpp-python is a soft hint (no grammar enforcement);
        # chunks whose content is already list-shaped (bullet enumerations,
        # glossaries) bias the model toward emitting the list directly.
        # Accept both shapes here; deeper fix is a json_schema constraint
        # in agent_server (see noted_entity_extraction memory).
        if isinstance(parsed, list):
            raw = parsed
        elif isinstance(parsed, dict):
            raw = parsed.get('entities')
        else:
            raw = None
        if not isinstance(raw, list):
            logger.warning('Extraction response missing entities list: %s', parsed)
            return []

        accepted: list[dict[str, Any]] = []
        for item in raw:
            clean = _normalize_entity(item)
            if clean is None:
                continue
            if clean['confidence'] < self._floor:
                self._below_floor_log.append(clean)
                continue
            accepted.append(clean)
        return accepted

    def drain_below_floor(self) -> list[dict]:
        """Return and clear the below-floor log. Callers can persist it for review."""
        out, self._below_floor_log = self._below_floor_log, []
        return out


def _normalize_entity(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    t = (item.get('type') or '').lower().strip()
    if t not in _VALID_TYPES:
        return None
    name = (item.get('name') or '').strip()
    if not name:
        return None
    try:
        conf = float(item.get('confidence', 0))
    except (TypeError, ValueError):
        return None
    if conf < 0:
        conf = 0.0
    if conf > 1:
        conf = 1.0
    desc = (item.get('description') or '').strip()
    return {
        'type': t,
        'name': name,
        'description': desc,
        'confidence': conf,
    }

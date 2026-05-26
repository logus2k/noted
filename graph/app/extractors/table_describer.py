"""Table-caption helper for the ingest pipeline (Path A).

For each Docling `TableItem` found during a scan, send the table's
markdown rendering plus a slice of surrounding context to agent_server's
`table_describer` preset and return a short retrieval-friendly summary.
The summary is injected into the chunk stream just before the table so
both the prose framing AND the raw cells flow through embedding + entity
extraction. See `pdf_scanner.py` for the wiring.

Designed to be cheap to skip:
    cap = describe_table(table_md, section='Methods', preceding=intro_para)
    if cap:
        ...inject as text item with the table's provenance...
A None return means "could not summarise — proceed without". Callers
must NOT abort on a None; one bad table per doc is normal.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from app.config import LLM_BASE_URL, LLM_TIMEOUT


# The `table_describer` preset may route to a thinking-enabled LLM
# whose response includes a `<think>...</think>` chain-of-thought
# block before the actual caption. If we store that raw output as
# the chunk text, downstream RAG queries return the CoT to the
# answering LLM, whose own `<think>` protocol collides with it and
# emits malformed output (no `<voice>` block, unclosed `</think>`,
# etc.) — the user sees "Diana hangs". Strip the CoT here so only
# the caption survives. Both closed `<think>...</think>` and
# unclosed-trailing variants are handled.
_THINK_BLOCK_RE = re.compile(r'<think>[\s\S]*?</think>\s*', re.IGNORECASE)
_THINK_OPEN_TRAILING_RE = re.compile(r'<think>[\s\S]*$', re.IGNORECASE)


def _strip_think(text: str) -> str:
    text = _THINK_BLOCK_RE.sub('', text or '')
    text = _THINK_OPEN_TRAILING_RE.sub('', text)
    return text.strip()


logger = logging.getLogger(__name__)


_MODEL = 'table_describer'


def _build_user_prompt(
    table_markdown: str,
    *,
    section: str | None,
    preceding: str | None,
    following: str | None,
) -> str:
    """Compose the user-message body the preset receives. The preset's
    system prompt carries the instructions; this body just supplies the
    structured inputs."""
    parts: list[str] = []
    if section:
        parts.append(f'Section: {section.strip()}')
    if preceding:
        parts.append(f'Preceding context:\n{preceding.strip()}')
    if following:
        parts.append(f'Following context:\n{following.strip()}')
    parts.append(f'Table:\n{table_markdown.strip()}')
    return '\n\n'.join(parts)


def describe_table(
    table_markdown: str,
    *,
    section: str | None = None,
    preceding: str | None = None,
    following: str | None = None,
    timeout: float | None = None,
) -> str | None:
    """Return a short retrieval-friendly caption for the given table, or
    None on failure. All context fields are optional; the prompt is built
    from whatever is available."""
    if not table_markdown or not table_markdown.strip():
        return None

    user_prompt = _build_user_prompt(
        table_markdown,
        section=section,
        preceding=preceding,
        following=following,
    )

    payload: dict[str, Any] = {
        'model': _MODEL,
        'stream': False,
        'messages': [
            {'role': 'user', 'content': user_prompt},
        ],
    }

    try:
        r = requests.post(
            f'{LLM_BASE_URL.rstrip("/")}/v1/chat/completions',
            json=payload,
            timeout=timeout if timeout is not None else LLM_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning('table caption request failed: %s', e)
        return None
    if not r.ok:
        logger.warning(
            'table caption HTTP %d: %s',
            r.status_code, r.text[:300],
        )
        return None

    try:
        data = r.json()
    except ValueError:
        logger.warning('table caption: non-JSON response')
        return None
    content = (
        (data.get('choices') or [{}])[0]
        .get('message', {})
        .get('content', '')
    )
    text = _strip_think(content)
    if not text:
        return None
    return text

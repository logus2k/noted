"""Picture-caption helper for the ingest pipeline (Path A).

For each Docling `PictureItem` found during a scan, send the image bytes
to agent_server's `picture_describer` preset (which routes through
`llama-vision` with the Gemma 4 mmproj loaded) and return a short
factual caption. The caption is then injected into the chunk stream at
the picture's position so it flows through embedding + entity extraction
identically to native text — see `pdf_scanner.py` for the wiring.

Designed to be cheap to skip:
    cap = describe_picture(image_bytes, mime='image/png')
    if cap:
        ...inject as text item with the picture's provenance...
A None return means "could not caption — proceed without". Callers must
NOT abort on a None; one bad picture per doc is normal.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import requests

from app.config import LLM_BASE_URL, LLM_TIMEOUT


# See the matching block in table_describer.py for why we strip
# `<think>...</think>` from the LLM response before storing the
# caption. tldr: the preset's underlying model can emit raw CoT,
# which then poisons RAG evidence and breaks the answering LLM's
# own `<think>` protocol.
_THINK_BLOCK_RE = re.compile(r'<think>[\s\S]*?</think>\s*', re.IGNORECASE)
_THINK_OPEN_TRAILING_RE = re.compile(r'<think>[\s\S]*$', re.IGNORECASE)


def _strip_think(text: str) -> str:
    text = _THINK_BLOCK_RE.sub('', text or '')
    text = _THINK_OPEN_TRAILING_RE.sub('', text)
    return text.strip()


logger = logging.getLogger(__name__)


# agent_server preset name. The preset file at
# `agent_server/data/agents/picture_describer.agent.json` selects the
# system prompt + sampling overrides; we just route to it via `model`.
_MODEL = 'picture_describer'

# User-side prompt: minimal nudge that instructs the model what to do
# with the attached image. The PRESET's system prompt carries the real
# instruction; this user message exists because some chat templates need
# at least one non-system user turn to dispatch.
_USER_PROMPT = 'Describe this image for a search index.'


def describe_picture(
    image_bytes: bytes,
    *,
    mime: str = 'image/png',
    timeout: float | None = None,
) -> str | None:
    """Return a short factual caption for `image_bytes`, or None on failure.

    `mime` is the image MIME type (image/png, image/jpeg, image/webp).
    Defaults to PNG since Docling exports PictureItem images that way.
    `timeout` overrides LLM_TIMEOUT for this single call; defaults to the
    global LLM_TIMEOUT which already accounts for vision-encoder latency.
    """
    if not image_bytes:
        return None

    b64 = base64.b64encode(image_bytes).decode('ascii')
    data_url = f'data:{mime};base64,{b64}'

    payload: dict[str, Any] = {
        'model': _MODEL,
        'stream': False,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': _USER_PROMPT},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ],
        }],
    }

    try:
        r = requests.post(
            f'{LLM_BASE_URL.rstrip("/")}/v1/chat/completions',
            json=payload,
            timeout=timeout if timeout is not None else LLM_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning('picture caption request failed: %s', e)
        return None
    if not r.ok:
        logger.warning(
            'picture caption HTTP %d: %s',
            r.status_code, r.text[:300],
        )
        return None

    try:
        data = r.json()
    except ValueError:
        logger.warning('picture caption: non-JSON response')
        return None
    choice = (data.get('choices') or [{}])[0]
    content = (choice.get('message') or {}).get('content', '') or ''
    text = _strip_think(content)
    if not text:
        logger.warning(
            'picture caption: empty after stripping <think> '
            '(finish_reason=%s, raw_len=%d, contains_think_open=%s) — '
            'returning None',
            choice.get('finish_reason'),
            len(content),
            '<think>' in content,
        )
        return None
    return text

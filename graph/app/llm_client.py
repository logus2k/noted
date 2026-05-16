"""Synchronous client for agent_server's OpenAI-compatible chat API.

noted-graph uses this from inside long rebuild loops, one chunk at a time,
so we stay synchronous (the shared Gemma pool serializes calls anyway).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

from app.config import LLM_BASE_URL, LLM_MODEL_ID, LLM_TIMEOUT

logger = logging.getLogger(__name__)


_FAILURE_DUMP_DIR = '/tmp/summarizer_failures'


def _dump_chat_json_failure(raw_text: str, reason: str) -> str:
    """Persist the full raw model response when chat_json parsing fails.

    The default LLMError message only carries a 200-char snippet; for
    diagnosing structural issues (think-tag leakage, LaTeX backslash
    escapes, truncation) we need the WHOLE text. Returns the dump path
    so it can be referenced in the raised error."""
    try:
        os.makedirs(_FAILURE_DUMP_DIR, exist_ok=True)
        ts = time.strftime('%Y%m%dT%H%M%S') + f'_{int(time.time() * 1000) % 1000:03d}'
        path = f'{_FAILURE_DUMP_DIR}/{ts}_{reason}.txt'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(raw_text)
        logger.warning('chat_json failure (%s) — full response dumped to %s (%d chars)',
                       reason, path, len(raw_text))
        return path
    except OSError as e:
        logger.warning('chat_json failure (%s) — dump skipped: %s', reason, e)
        return ''


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Thin wrapper around /v1/chat/completions (non-streaming)."""

    def __init__(self):
        self._base = LLM_BASE_URL.rstrip('/')
        self._model = LLM_MODEL_ID
        self._timeout = LLM_TIMEOUT

    def chat_text(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Ask the model for free-form text and return the raw content.

        Used by the synthesis step where we want markdown, not JSON. Avoids
        the JSON-extraction wrapping that mangles plain answers.

        `system_prompt` is optional. When omitted, only the user message is
        sent and the agent_server preset's own system prompt (loaded server-
        side from the agent's prompt file) is the single source of truth -
        avoids the dual-system-message conflict where two prompts give
        contradictory citation/output rules.
        """
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': user_prompt})
        payload: dict[str, Any] = {
            'model': self._model,
            'messages': messages,
            'stream': False,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        try:
            r = requests.post(
                f'{self._base}/v1/chat/completions',
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise LLMError(f'LLM request failed: {e}') from e
        if not r.ok:
            raise LLMError(f'LLM HTTP {r.status_code}: {r.text[:500]}')
        data = r.json()
        content = (
            (data.get('choices') or [{}])[0]
            .get('message', {})
            .get('content', '')
        )
        return (content or '').strip()

    def chat_text_stream(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        model: str | None = None,
    ):
        """Streaming variant of chat_text. Yields content delta strings as
        they arrive. Used by /research/query/stream so the user sees
        synthesis tokens flowing rather than waiting for the full answer.

        `system_prompt` is optional - see `chat_text` docstring for why.
        `model` overrides the default LLM_MODEL_ID for this single call -
        synthesize_stream uses it to route through the noted_graph_answer
        preset (prose) while the chat tool flow keeps using the
        analyst-style noted_graph preset.
        """
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': user_prompt})
        payload: dict[str, Any] = {
            'model': model or self._model,
            'messages': messages,
            'stream': True,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        try:
            r = requests.post(
                f'{self._base}/v1/chat/completions',
                json=payload,
                timeout=self._timeout,
                stream=True,
            )
        except requests.RequestException as e:
            raise LLMError(f'LLM request failed: {e}') from e
        if not r.ok:
            raise LLMError(f'LLM HTTP {r.status_code}: {r.text[:500]}')
        # Iterate SSE lines from the agent_server
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith('data:'):
                continue
            data = raw[5:].strip()
            if data == '[DONE]':
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = obj.get('choices') or []
            if not choices:
                continue
            delta = choices[0].get('delta') or {}
            content = delta.get('content')
            if content:
                yield content

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_schema: dict | None = None,
    ) -> dict:
        """Ask the model for a JSON object. Returns parsed dict.

        When `json_schema` is provided, uses llama.cpp's strict
        json_schema-constrained sampling. The sampler physically cannot
        emit a token that would invalidate the schema — including bare
        backslashes inside string values (the bug that ate ~1% of
        community summaries on LaTeX-heavy academic content: `\\lambda`,
        `\\partial`, etc. needed to be JSON-escaped as `\\\\lambda` but
        the unconstrained model emitted them raw, breaking json.loads).
        With json_schema, the sampler forces proper `\\\\` escapes at
        token-level. Validated 2026-05-15: gemma-4 returns valid JSON
        carrying LaTeX content reliably.

        Without `json_schema`, uses the loose `{"type": "json_object"}`
        hint — encourages JSON shape but does NOT constrain escapes.

        Falls back to extracting the first balanced {...} span from raw
        content if the server ignores the format hint.
        """
        if json_schema is not None:
            rf = {
                'type': 'json_schema',
                'json_schema': {'name': 'response', 'schema': json_schema},
            }
        else:
            rf = {'type': 'json_object'}
        payload: dict[str, Any] = {
            'model': self._model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'stream': False,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'response_format': rf,
            # Disable thinking for structured-output calls. With the global
            # `reasoning = on` in llama-router-models.ini, Gemma 4 emits a
            # `<think>...</think>` block that agent_server's _ThinkingSplice
            # folds into the response content. _extract_json then finds the
            # first `{` inside the think block (often part of an example the
            # model wrote in its reasoning) and fails to balance, dumping
            # the response to /tmp/summarizer_failures/. Forwarding
            # chat_template_kwargs through to llama-server suppresses the
            # think channel for THIS payload only — entity extractor +
            # community summarizer get clean JSON, other consumers (chat
            # stream) keep their reasoning channel.
            'chat_template_kwargs': {'enable_thinking': False},
        }
        try:
            r = requests.post(
                f'{self._base}/v1/chat/completions',
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise LLMError(f'LLM request failed: {e}') from e
        if not r.ok:
            raise LLMError(f'LLM HTTP {r.status_code}: {r.text[:500]}')

        data = r.json()
        content = (
            (data.get('choices') or [{}])[0]
            .get('message', {})
            .get('content', '')
        )
        if not content:
            raise LLMError(f'Empty LLM response: {data}')
        return _extract_json(content)


def _extract_json(text: str) -> dict:
    """Try direct parse, then fall back to first balanced {...} span."""
    raw = text
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find('{')
    if start < 0:
        dump = _dump_chat_json_failure(raw, 'no_object')
        raise LLMError(f'No JSON object in response (dump={dump}): {text[:200]}')
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as e:
                    dump = _dump_chat_json_failure(raw, 'malformed_span')
                    raise LLMError(f'Malformed JSON span (dump={dump}): {e}') from e
    dump = _dump_chat_json_failure(raw, 'unbalanced')
    raise LLMError(f'Unbalanced JSON in response (dump={dump}): {text[:200]}')

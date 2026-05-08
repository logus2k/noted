"""Service-health monitor.

Runs concurrent probes against the platform's hard dependencies on a
fixed cadence and pushes state changes to connected clients via
Socket.IO. Designed to surface upstream failures (bge-m3 zombie,
noted-rag down, ArcadeDB unreachable) before a multi-hour build is
attempted, not after.

State shape per service:
    {
        "status": "ok" | "fail" | "unknown",
        "latency_ms": int | None,
        "last_error": str | None,
        "last_ok_at": ISO timestamp | None,
        "last_checked_at": ISO timestamp,
    }

Top-level state:
    {
        "services": {<id>: <state>, ...},
        "checked_at": ISO timestamp,
    }

Push semantics:
- On every probe cycle, compare new statuses to prior. If ANY service's
  status field changed, emit `services:health` to all clients.
- On client connect (handled in main.py), send the current cached state
  immediately so the LED strip paints on first frame without polling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# Service IDs and how to probe them. Each entry: (id, label, prober).
# Probers return (status, error_or_none) and run with their own timeout.
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Where to find each service. Keep these tied to env so dev / prod
# overrides land naturally; default to the in-network hostnames.
NOTED_GRAPH_URL = os.environ.get('NOTED_GRAPH_URL', 'http://noted-graph:5523')
NOTED_RAG_URL = os.environ.get('NOTED_RAG_URL', 'http://noted-rag:8200')
LLAMA_VISION_URL = os.environ.get('LLAMA_VISION_URL', 'http://llama-vision:8500')
AGENT_SERVER_URL = os.environ.get('AGENT_SERVER_URL', 'http://agent_server:7701')


PROBE_TIMEOUT_SECONDS = 5.0
DEFAULT_INTERVAL_SECONDS = 30.0


async def _probe_get(client: httpx.AsyncClient, url: str) -> tuple[str, Optional[str], Optional[int]]:
    """GET probe. Returns (status, error, latency_ms)."""
    import time
    t0 = time.perf_counter()
    try:
        r = await client.get(url, timeout=PROBE_TIMEOUT_SECONDS)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code == 200:
            return 'ok', None, latency_ms
        return 'fail', f'HTTP {r.status_code}: {r.text[:120]}', latency_ms
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return 'fail', f'{type(e).__name__}: {e}'[:160], latency_ms


async def _probe_noted_graph(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    return await _probe_get(client, f'{NOTED_GRAPH_URL}/health')


async def _probe_noted_rag(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    return await _probe_get(client, f'{NOTED_RAG_URL}/health')


async def _probe_llama_vision_proxy(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    return await _probe_get(client, f'{LLAMA_VISION_URL}/health')


async def _probe_bge_m3(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    """Real embed call against bge-m3. The most important probe — the
    proxy returning /health=ok while bge-m3's child process is a zombie
    is the EXACT failure mode that took down ml's import for 2 days."""
    import time
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f'{LLAMA_VISION_URL}/v1/embeddings',
            json={'input': 'probe', 'model': 'bge-m3'},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return 'fail', f'HTTP {r.status_code}: {r.text[:120]}', latency_ms
        body = r.json()
        data = body.get('data') or []
        if data and data[0].get('embedding') and len(data[0]['embedding']) > 0:
            return 'ok', None, latency_ms
        return 'fail', f'malformed embedding response: {str(body)[:120]}', latency_ms
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return 'fail', f'{type(e).__name__}: {e}'[:160], latency_ms


async def _probe_graph_db(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    """Graph Database probe — hits noted-graph's /domains endpoint
    which reads through to ArcadeDB. If ArcadeDB is wedged the call
    errors or hangs, so this probe covers BOTH the graph service AND
    the underlying database in one shot."""
    return await _probe_get(client, f'{NOTED_GRAPH_URL}/domains')


async def _probe_gemma4(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    """Real chat-completion call against gemma-4. Conceptually redundant
    with the LLM Proxy probe — ideally the proxy's `/health` would
    itself verify all child models are responsive. But upstream
    `llama-server` doesn't probe its children, so a green proxy
    doesn't prove gemma-4 hasn't zombied (same failure mode bge-m3
    hit). Cost: one tiny generation per cycle (~50-200ms GPU).
    Captioning + chat both depend on this; without an active probe
    a zombied gemma-4 would silently break image/table descriptions
    AND every chat response while the LLM Proxy LED stayed green."""
    import time
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f'{LLAMA_VISION_URL}/v1/chat/completions',
            json={
                'model': 'gemma-4',
                'messages': [{'role': 'user', 'content': 'ok'}],
                'max_tokens': 1,
                'temperature': 0,
            },
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return 'fail', f'HTTP {r.status_code}: {r.text[:120]}', latency_ms
        body = r.json()
        choices = body.get('choices') or []
        if choices and 'message' in choices[0]:
            return 'ok', None, latency_ms
        return 'fail', f'malformed completion response: {str(body)[:120]}', latency_ms
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return 'fail', f'{type(e).__name__}: {e}'[:160], latency_ms


async def _probe_bge_reranker(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    """Real rerank call against bge-reranker. Same model-zombie scenario
    that took down bge-m3 could happen here; the proxy /health doesn't
    catch a child-process death."""
    import time
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f'{LLAMA_VISION_URL}/v1/rerank',
            json={'model': 'bge-reranker', 'query': 'probe', 'documents': ['a']},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return 'fail', f'HTTP {r.status_code}: {r.text[:120]}', latency_ms
        body = r.json()
        results = body.get('results') or []
        if results and 'relevance_score' in results[0]:
            return 'ok', None, latency_ms
        return 'fail', f'malformed rerank response: {str(body)[:120]}', latency_ms
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return 'fail', f'{type(e).__name__}: {e}'[:160], latency_ms


async def _probe_agent_server(client: httpx.AsyncClient) -> tuple[str, Optional[str], Optional[int]]:
    """agent_server doesn't expose /health. Probe / and accept any
    HTTP response < 500 as 'process is up' since the chat router lives
    here. A 404 is fine; a connection refusal is not."""
    import time
    t0 = time.perf_counter()
    try:
        r = await client.get(AGENT_SERVER_URL, timeout=PROBE_TIMEOUT_SECONDS)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code < 500:
            return 'ok', None, latency_ms
        return 'fail', f'HTTP {r.status_code}', latency_ms
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return 'fail', f'{type(e).__name__}: {e}'[:160], latency_ms


PROBES = [
    ('noted_rag',       'Vector Database',     _probe_noted_rag),
    ('noted_graph',     'Graph Database',      _probe_graph_db),
    ('llama_vision',    'LLM Proxy',           _probe_llama_vision_proxy),
    ('agent_server',    'Agent Server',        _probe_agent_server),
    ('bge_m3',          'Embeddings Service',  _probe_bge_m3),
    ('bge_reranker',    'Reranker Service',    _probe_bge_reranker),
    ('gemma_4',         'Generation Service',  _probe_gemma4),
]


class HealthMonitor:
    """Singleton. Run by the FastAPI lifespan. Probes services on a
    fixed cadence; pushes state changes to all Socket.IO clients on the
    `services:health` event."""

    def __init__(self, sio, interval_seconds: float = DEFAULT_INTERVAL_SECONDS):
        self._sio = sio
        self._interval = interval_seconds
        self._state: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # Pulse so a manual `force_refresh()` can interrupt the sleep
        # and run a probe NOW without waiting for the next cadence tick.
        self._wake_event = asyncio.Event()
        self._lock = asyncio.Lock()

    def get_state(self) -> dict:
        """Return a snapshot of the current state (safe to serialize)."""
        return {
            'services': dict(self._state),
            'checked_at': self._state.get('__last_checked_at__', None),
            'interval_seconds': self._interval,
        }

    async def force_refresh(self) -> dict:
        """Trigger an immediate probe cycle, wait for it to finish,
        and return the resulting state."""
        self._wake_event.set()
        # Wait for the loop to consume the wake. The loop clears
        # the event when it starts a probe, so polling for it being
        # cleared is enough to know a probe is running.
        deadline = asyncio.get_event_loop().time() + 10.0
        while self._wake_event.is_set():
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.05)
        # Now wait for the probe to finish (grab the lock).
        async with self._lock:
            return self.get_state()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info('HealthMonitor started (interval=%.0fs, %d probes)',
                    self._interval, len(PROBES))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._wake_event.set()  # wake from sleep so it can exit
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        self._task = None
        logger.info('HealthMonitor stopped')

    async def _run(self) -> None:
        # First probe immediately so the state is non-empty as soon as
        # the server starts; clients connecting in the first 30s see
        # real data, not 'unknown'.
        async with httpx.AsyncClient() as client:
            await self._probe_once(client)
            while not self._stop_event.is_set():
                # Sleep for the interval but allow `force_refresh()` to
                # wake us early.
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=self._interval,
                    )
                except asyncio.TimeoutError:
                    pass
                if self._stop_event.is_set():
                    break
                self._wake_event.clear()
                await self._probe_once(client)

    async def _probe_once(self, client: httpx.AsyncClient) -> None:
        async with self._lock:
            checked_at = _now_iso()
            tasks = [prober(client) for _id, _label, prober in PROBES]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            new_state: dict[str, dict] = {}
            any_changed = False
            for (svc_id, label, _), res in zip(PROBES, results):
                if isinstance(res, Exception):
                    status, err, latency = 'fail', f'probe raised: {type(res).__name__}: {res}'[:160], None
                else:
                    status, err, latency = res

                prior = self._state.get(svc_id, {})
                last_ok = checked_at if status == 'ok' else prior.get('last_ok_at')
                new_state[svc_id] = {
                    'label': label,
                    'status': status,
                    'latency_ms': latency,
                    'last_error': err,
                    'last_ok_at': last_ok,
                    'last_checked_at': checked_at,
                }
                if prior.get('status') != status:
                    any_changed = True
                    logger.info(
                        'HealthMonitor: %s status %s -> %s%s',
                        svc_id, prior.get('status', 'unknown'), status,
                        f' ({err})' if err else '',
                    )
            new_state['__last_checked_at__'] = checked_at
            self._state = new_state

            # Emit on first probe (any_changed will be True since prior
            # is empty for all) AND on subsequent state changes only.
            if any_changed:
                try:
                    await self._sio.emit('services:health', self.get_state())
                except Exception as e:
                    logger.warning('HealthMonitor: emit failed: %s', e)


# Module-level singleton; initialized in main.py's lifespan.
_monitor: HealthMonitor | None = None


def get_monitor() -> HealthMonitor | None:
    return _monitor


def set_monitor(m: HealthMonitor) -> None:
    global _monitor
    _monitor = m

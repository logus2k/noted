"""Serving Proxy API - proxies requests to the model serving container.

Provides a single endpoint surface for the frontend to interact with
the serving container without exposing it directly.
"""

import json
import os
import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import requests

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/serving", tags=["serving"])

SERVING_URL = os.environ.get('SERVING_URL', 'http://noted-serving:5522')


class LoadRequest(BaseModel):
    model_name: str
    version: str | None = None
    alias: str | None = None


class PredictRequest(BaseModel):
    data: Any


def _proxy_get(path: str) -> dict:
    """Proxy a GET request to the serving container."""
    try:
        resp = requests.get(f'{SERVING_URL}{path}', timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="Serving container is not reachable")
    except requests.HTTPError as e:
        detail = ''
        try:
            detail = e.response.json().get('detail', str(e))
        except Exception:
            detail = str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)


def _proxy_post(path: str, json_data: dict, timeout: int = 60) -> dict:
    """Proxy a POST request to the serving container."""
    try:
        resp = requests.post(f'{SERVING_URL}{path}', json=json_data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="Serving container is not reachable")
    except requests.HTTPError as e:
        detail = ''
        try:
            detail = e.response.json().get('detail', str(e))
        except Exception:
            detail = str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)


@router.get("/health")
def health():
    """Get serving container status and loaded model info."""
    return _proxy_get('/health')


@router.post("/load")
async def load_model(body: LoadRequest):
    """Publish a model: load it into the serving container.

    Streams progress events back to the client as NDJSON, one JSON line
    per phase change. Terminal events are {"phase": "ready", "result": ...}
    on success or {"phase": "error", "error": "..."} on failure.

    Implemented as an async streaming proxy with httpx so the FastAPI
    event loop stays free during the 60+ second publishing window. A
    previous sync (requests + iterate_in_threadpool) implementation
    starved python-socketio's ping task and caused the Assistant
    socket.io connection to drop mid-publish.
    """
    async def _gen():
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    'POST',
                    f'{SERVING_URL}/load',
                    json=body.model_dump(),
                ) as resp:
                    if resp.status_code >= 400:
                        body_bytes = await resp.aread()
                        body_text = body_bytes.decode('utf-8', 'replace')[:500]
                        yield (json.dumps({
                            'phase': 'error',
                            'error': f'Upstream HTTP {resp.status_code}: {body_text}',
                        }) + '\n').encode('utf-8')
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield (line + '\n').encode('utf-8')
        except httpx.ConnectError:
            yield (json.dumps({
                'phase': 'error',
                'error': 'Serving container is not reachable',
            }) + '\n').encode('utf-8')
        except Exception as e:
            logger.exception("Publish stream proxy failed")
            yield (json.dumps({
                'phase': 'error',
                'error': f'{type(e).__name__}: {e}',
            }) + '\n').encode('utf-8')

    return StreamingResponse(_gen(), media_type='application/x-ndjson')


@router.post("/unload")
def unload_model():
    """Unload the current model from the serving container."""
    return _proxy_post('/unload', {})


@router.get("/schema")
def get_schema():
    """Get input/output schema for the loaded model."""
    return _proxy_get('/schema')


@router.post("/predict")
def predict(body: PredictRequest):
    """Run prediction on the loaded model."""
    return _proxy_post('/predict', body.model_dump())

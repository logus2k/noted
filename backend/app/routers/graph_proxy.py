"""Knowledge Graph Proxy - forwards requests to the graph service container."""

import os
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])

GRAPH_URL = os.environ.get('GRAPH_URL', 'http://noted-graph:5523')

# Per-path read timeout overrides for noted-graph endpoints that legitimately
# run long. Match the operation suffix only (everything after `/research/`)
# so the same matchers work for the P3.2 per-KB shape `/research/{kb_id}/op`
# AND any future flat shape.
_LONG_OP_TIMEOUTS = (
    ('/rebuild',    14400),  # 4h cap (typical full rebuild ~25 min)
    ('/recluster',  3600),   # 1h cap (typical recluster minutes)
    ('/doc/add',    1800),   # 30m cap (typical 1-5 min per doc)
    ('/doc/remove', 600),    # 10m cap (no extraction, just storage)
)


def _timeout_for(path: str) -> float:
    for suffix, t in _LONG_OP_TIMEOUTS:
        if path.endswith(suffix):
            return t
    return 30


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_graph(path: str, request: Request):
    """Proxy all graph requests to the Knowledge Graph service.

    Streaming endpoints (path ends in `/stream`) are pass-through: the
    upstream byte stream is forwarded chunk-by-chunk so SSE events reach
    the browser as they arrive. Non-streaming endpoints are buffered and
    JSON-parsed as before.
    """
    url = f'{GRAPH_URL}/{path}'
    if request.query_params:
        url += f'?{request.query_params}'

    if path.endswith('/stream'):
        body = await request.body()
        headers = {'Content-Type': request.headers.get('content-type', 'application/json')}

        async def stream_upstream():
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream(request.method, url, content=body, headers=headers) as resp:
                        async for chunk in resp.aiter_raw():
                            if chunk:
                                yield chunk
            except httpx.RequestError as e:
                logger.exception("Graph proxy stream error")
                yield f"event: error\ndata: {{\"detail\": \"upstream unreachable: {e}\"}}\n\n".encode()

        return StreamingResponse(
            stream_upstream(),
            media_type='text/event-stream',
            headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
        )

    # CRITICAL: must use httpx.AsyncClient (async) here, not requests
    # (sync). graph_proxy is `async def` and any sync I/O blocks uvicorn's
    # event loop for the full duration of the upstream call. With long
    # endpoints like /research/rebuild (~25 min), that freezes the entire
    # platform - no API, no static files, no WebSockets. See
    # feedback_never_block_noted_api.md.
    try:
        timeout = _timeout_for(path)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if request.method == 'GET':
                resp = await client.get(url)
            else:
                body = await request.body()
                headers = {'Content-Type': request.headers.get('content-type', 'application/json')}
                resp = await client.request(request.method, url, content=body, headers=headers)
        if resp.status_code >= 400:
            detail = ''
            try:
                detail = resp.json().get('detail', resp.text[:300])
            except Exception:
                detail = resp.text[:300]
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Knowledge Graph service is not reachable")
    except httpx.RequestError as e:
        logger.exception("Graph proxy request error")
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Graph proxy error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

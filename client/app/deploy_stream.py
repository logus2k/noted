"""Streaming deploy endpoint helper.

Encapsulates the asyncio plumbing that converts the synchronous
ModelLoader.load() call into an NDJSON stream of progress events for the
/load endpoint. Kept in its own module so main.py stays small and the
streaming concerns are isolated from the route wiring.

"Deploy" here matches MLflow's own terminology (mlflow deployments
create / mlflow models serve) - the user-facing action of loading a
registered model into a serving process so it can answer predictions.
"""

import asyncio
import json
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class DeployEventStream:
    """Bridges ModelLoader's synchronous phase callbacks to an async event
    queue suitable for FastAPI StreamingResponse.

    Usage:
        stream = DeployEventStream(loader)
        return StreamingResponse(
            stream.run(model_name, version, alias),
            media_type='application/x-ndjson',
        )

    Event shape (one JSON object per newline-terminated line):
        {"phase": "<name>", "detail": "<free text>"}
        ...
        {"phase": "ready", "result": {<full health payload>}}
        # or
        {"phase": "error", "error": "<message>"}
    """

    def __init__(self, loader):
        self._loader = loader

    async def run(
        self,
        model_name: str,
        version: str | None,
        alias: str | None,
        on_ready=None,
    ) -> AsyncIterator[bytes]:
        """Start a load in a worker thread, yield NDJSON events as they
        arrive on the phase callback, finish with a terminal 'ready' or
        'error' event.

        Args:
            model_name, version, alias: passed to loader.load()
            on_ready: optional sync callback invoked with the final health
                dict once the load succeeds (before the 'ready' event is
                yielded). Used by the route to refresh cached schema.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_phase(phase: str, detail: str):
            # Called from the loader thread. Schedule the put on the loop.
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {'phase': phase, 'detail': detail},
                )
            except RuntimeError:
                # Loop already closed (client disconnected) - silently drop.
                pass

        self._loader.set_phase_callback(on_phase)
        load_future = loop.run_in_executor(
            None, self._loader.load, model_name, version, alias,
        )

        try:
            # Stream events as they come in. A completion future is
            # awaited alongside the queue so we exit the moment the load
            # finishes, without needing any timeout-based wake-ups.
            completion = asyncio.ensure_future(self._awaited(load_future))
            while True:
                get_task = asyncio.ensure_future(queue.get())
                done, _pending = await asyncio.wait(
                    {get_task, completion},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if get_task in done:
                    event = get_task.result()
                    yield self._encode(event)
                else:
                    get_task.cancel()

                if completion in done:
                    # Drain any remaining events already queued before
                    # breaking out.
                    while not queue.empty():
                        yield self._encode(queue.get_nowait())
                    break

            # Terminal event
            try:
                result = completion.result()
                if on_ready is not None:
                    try:
                        on_ready(result)
                    except Exception:
                        logger.exception("on_ready callback failed")
                yield self._encode({'phase': 'ready', 'result': result})
            except Exception as e:
                logger.exception("Model deploy failed")
                yield self._encode({
                    'phase': 'error',
                    'error': f'{type(e).__name__}: {e}',
                })
        finally:
            self._loader.set_phase_callback(None)

    @staticmethod
    async def _awaited(future):
        """Wrap a concurrent.futures.Future so asyncio.wait can wait on it."""
        return await future

    @staticmethod
    def _encode(event: dict) -> bytes:
        return (json.dumps(event) + '\n').encode('utf-8')

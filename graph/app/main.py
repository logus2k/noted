"""Knowledge Graph Service - entity discovery, relationship mapping, and search.

A lightweight service that scans MLflow, DVC, Hydra, Airflow, and the filesystem
to build a navigable graph of all noted entities and their relationships.
"""

import logging
import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.migration import run_migration_if_needed
from app.progress_events import sio, set_loop
from app.routers import graph as graph_router
from app.routers import domain as domain_router
from app.routers import research as research_router
from app.routers import search as search_router
from app.routers import tags as tags_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Layered idempotent migration: P1 -> P3.1 -> Domain layout, plus seed
# of the pinned `general` Domain and ArcadeDB project_ids normalization.
# Runs at import time (before routes serve) so corpus.py / state.py never
# read missing paths during startup probes.
run_migration_if_needed()

app = FastAPI(title="noted Knowledge Graph", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph_router.router)
app.include_router(domain_router.router)
app.include_router(research_router.router)
app.include_router(search_router.router)
app.include_router(tags_router.router)


@app.get("/health")
def health():
    """Service health check."""
    return {'status': 'ok', 'service': 'knowledge-graph'}


@app.on_event("startup")
async def _capture_event_loop():
    """Hand the running ASGI loop to the progress channel so the build's worker
    threads can schedule Socket.IO emits onto it."""
    import asyncio
    set_loop(asyncio.get_running_loop())


# Serve the REST API and the Socket.IO live-progress channel on the same port.
# Clients connect at /socket.io and subscribe to a domain's progress room.
# The container CMD runs `app.main:asgi_app`.
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="socket.io")


if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run(asgi_app, host=HOST, port=PORT)

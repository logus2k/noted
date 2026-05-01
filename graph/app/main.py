"""Knowledge Graph Service - entity discovery, relationship mapping, and search.

A lightweight service that scans MLflow, DVC, Hydra, Airflow, and the filesystem
to build a navigable graph of all noted entities and their relationships.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.migration import run_migration_if_needed
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


if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run(app, host=HOST, port=PORT)

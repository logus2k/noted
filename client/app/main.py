"""Model Serving API - loads models from MLflow Registry and serves predictions.

Endpoints:
    POST /load       - Load a model by name + version or alias
    POST /unload     - Unload the current model
    POST /predict    - Run prediction on the loaded model
    GET  /health     - Current serving status
    GET  /schema     - Input/output schema for the loaded model
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.model_loader import ModelLoader
from app.schema_builder import build_schema
from app.predict import run_prediction
from app.deploy_stream import DeployEventStream

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s UTC [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

app = FastAPI(title="noted Model Serving", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

loader = ModelLoader()
_cached_schema = None


# ── Request Models ────────────────────────────────────────────

class LoadRequest(BaseModel):
    model_name: str
    version: str | None = None
    alias: str | None = None


from typing import Any

class PredictRequest(BaseModel):
    data: Any


# ── Endpoints ─────────────────────────────────────────────────

@app.get("/health")
def health():
    """Current serving status and loaded model info."""
    return loader.get_health()


@app.post("/load")
async def load_model(body: LoadRequest):
    """Deploy a model from MLflow Registry into the serving process.

    Returns an NDJSON streaming response: one JSON line per progress event
    while the deploy runs, terminated by a 'ready' event carrying the full
    health payload, or an 'error' event with the failure message. See
    deploy_stream.DeployEventStream for the event shape.
    """
    def _on_ready(_result):
        global _cached_schema
        _cached_schema = build_schema(loader.model_info, loader.model)
        logger.info("Schema cached after deploy: %s", _cached_schema)

    stream = DeployEventStream(loader)
    return StreamingResponse(
        stream.run(body.model_name, body.version, body.alias, on_ready=_on_ready),
        media_type='application/x-ndjson',
    )


@app.post("/unload")
def unload_model():
    """Unload the current model and free memory."""
    global _cached_schema
    _cached_schema = None
    return loader.unload()


@app.get("/schema")
def get_schema():
    """Input/output schema for the loaded model.

    Used by the frontend to dynamically generate input forms
    and choose the appropriate output renderer.
    """
    if not loader.is_ready():
        raise HTTPException(status_code=404, detail="No model loaded")
    if _cached_schema:
        return _cached_schema
    return build_schema(loader.model_info, loader.model)


@app.post("/predict")
def predict(body: PredictRequest):
    """Run prediction on the loaded model.

    Input format depends on the model:
    - DataFrame models: {"data": {"col1": val1, "col2": val2, ...}}
    - Tensor models: {"data": {"data": [[1.0, 2.0, ...]]}}
    - Columnar: {"data": {"columns": [...], "data": [[...]]}}
    """
    if not loader.is_ready():
        raise HTTPException(status_code=400, detail="No model loaded. Call /load first.")

    schema = _cached_schema or build_schema(loader.model_info, loader.model)

    try:
        result = run_prediction(loader.model, body.data, schema)
        result['model_name'] = loader.model_info.get('model_name')
        result['model_version'] = loader.model_info.get('version')
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run(app, host=HOST, port=PORT)

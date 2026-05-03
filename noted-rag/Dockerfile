# syntax=docker/dockerfile:1
#
# noted-rag image (forwarding mode, post-Phase 9):
# - dense embeddings + cross-encoder rerank are HTTP-forwarded to a
#   llama-server router (typically `llama-vision` from agent_server,
#   reachable on noted-network).
# - This image carries no model weights, no CUDA, no llama-cpp-python.
#   ChromaDB + the FastAPI surface are the only heavyweights now.
#
# For the in-process / pre-router rollback, use the reference Dockerfile
# kept in agent_server (Dockerfile.fat) as a template — same multi-stage
# CUDA + llama-cpp-python build noted-rag had before.

FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

COPY app/ ./app/
COPY scripts/ ./scripts/

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]

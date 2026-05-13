# syntax=docker/dockerfile:1
#
# noted-tools image: MCP server hosting self-authored tools.
#
# Bundles Python 3.12 + Node.js 22 LTS so generated tools can be either
# language. Per-tool venvs / node_modules are created at runtime under
# /app/data/user_tools/<name>/ via uv (Python) or npm (JS). No model
# weights, no CUDA.

FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app

RUN pip install --upgrade pip uv

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

COPY app/ ./app/
# Vendored _auth helper. Copied into every user-tool venv's
# site-packages at venv-build time by app/venv_manager.py
# (`_vendor_auth_helper`).
COPY data/auth_lib/ ./data/auth_lib/

# Run as a non-root UID so per-tool venvs created on the bind-mounted
# data/user_tools/ are owned by the host user (UID 1000) instead of root.
# Compose pins user: "1000:1000" so we don't need to create a host-user
# entry inside the image.
RUN chown -R 1000:1000 /app

EXPOSE 7702

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7702"]

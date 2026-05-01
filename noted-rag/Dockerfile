# syntax=docker/dockerfile:1
#
# noted-rag image: dense embeddings (bge-m3 GGUF) + cross-encoder rerank
# (bge-reranker-v2-m3 GGUF) via llama-cpp-python with CUDA. Mirrors the
# agent_server build pattern (multi-stage CUDA builder + slim runtime) but
# is fully self-contained — no cross-project image dep.

#############################
# Builder: CUDA + toolchain #
#############################
FROM nvidia/cuda:12.9.0-devel-ubuntu22.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive

# System deps + Python 3.10
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        build-essential cmake git curl ca-certificates \
        gcc-12 g++-12 \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

# --- Build backend / helpers (no-build-isolation) ---
RUN pip install --no-cache-dir \
        scikit-build-core>=0.10 \
        ninja \
        setuptools \
        wheel \
        packaging

# --- Build llama-cpp-python with CUDA ---
ENV CC=/usr/bin/gcc-12 \
    CXX=/usr/bin/g++-12 \
    CUDAHOSTCXX=/usr/bin/g++-12

ENV CMAKE_ARGS="-DGGML_CUDA=on -DLLAMA_BUILD_TOOLS=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF" \
    FORCE_CMAKE=1

# CUDA driver stub for link-time (real driver is provided at runtime).
ENV LIBRARY_PATH=/usr/local/cuda/lib64/stubs:${LIBRARY_PATH} \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH} \
    LDFLAGS="-L/usr/local/cuda/lib64/stubs -Wl,-rpath-link,/usr/local/cuda/lib64/stubs"
RUN ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/libcuda.so \
 && ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/libcuda.so.1 \
 && ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1

RUN pip install --no-cache-dir --no-build-isolation --force-reinstall llama-cpp-python

# --- App-level Python deps (read from requirements.txt so the source of
# truth stays one file). Cached separately from the slow llama-cpp build,
# so app-dep changes don't trigger a CUDA rebuild.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

###########################
# Runtime: CUDA + Python  #
###########################
FROM nvidia/cuda:12.9.0-runtime-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Bring in the venv from the builder.
COPY --from=builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

WORKDIR /app

COPY app/ ./app/
COPY scripts/ ./scripts/

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]

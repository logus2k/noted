# Ubuntu 22.04 + CUDA 13.2.1 runtime - matches host driver 13.2,
# in CuPy's tested OS matrix. Provides cuBLAS / cuRAND / etc. so plain
# `pip install cupy-cuda13x` (no [ctk] extra) works.
FROM nvidia/cuda:13.2.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.12 via deadsnakes (Ubuntu 22.04 default is 3.10).
# git: used by future git_scanner.
# build-essential: source-build fallback for any dep without manylinux wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common ca-certificates curl gnupg \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update && apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3.12-dev \
      git build-essential \
      libgl1 libglib2.0-0 libxcb1 libxext6 libxrender1 libsm6 \
 && rm -rf /var/lib/apt/lists/* \
 && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Bootstrap pip for Python 3.12 specifically (Ubuntu's `python3-pip` package
# binds pip to the system Python 3.10, which fails under 3.12 because it
# references the removed `distutils` module). `ensurepip` is in the stdlib
# and installs a 3.12-native pip.
RUN python3.12 -m ensurepip --upgrade \
 && python3.12 -m pip install --no-cache-dir --upgrade \
      'pip>=24.0' 'setuptools>=68' wheel

WORKDIR /app

COPY requirements.txt .
RUN python3.12 -m pip install --no-cache-dir -r requirements.txt

COPY app/ app/

EXPOSE 5523

CMD ["python3.12", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5523"]

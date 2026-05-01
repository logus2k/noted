FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY app/ app/

EXPOSE 5522

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5522"]

FROM python:3.12-slim

# System deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git && rm -rf /var/lib/apt/lists/*

WORKDIR /tests

# Python test dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy test code
COPY . .

# Default: run all tests
ENTRYPOINT ["pytest"]
CMD ["-v", "--tb=short", "-x", "--junitxml=/tests/results/results.xml"]

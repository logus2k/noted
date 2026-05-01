#!/usr/bin/env bash
# Entrypoint: generate runtime configs for installed languages, then start the app.
set -euo pipefail

# Generate runtime.json files into data/runtimes/ (the volume mount)
# Runs every startup so new image builds with new runtimes are auto-detected.
/app/scripts/create_runtime_configs.sh /app/data/runtimes
/app/scripts/create_js_runtime_configs.sh /app/data/runtimes

exec "$@"

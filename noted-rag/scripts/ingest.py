"""CLI wrapper: trigger an ingest without going through HTTP.

Usage (inside the noted-rag container):
    python3 scripts/ingest.py

Also useful for one-shot runs on a fresh container without waiting for an
HTTP client to call /ingest.
"""

from __future__ import annotations

import json
import sys

# Make `app` importable when running as a script from /app
sys.path.insert(0, "/app")

from app import ingest  # noqa: E402
from app.rag_service import RagService  # noqa: E402


def main() -> int:
    rag = RagService()
    result = ingest.run_ingest(rag)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

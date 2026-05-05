"""ArcadeDB HTTP client.

Thin wrapper around ArcadeDB's REST API. Sends Cypher / openCypher commands,
returns parsed JSON results. Connection config comes from environment via
app.config.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import requests

from app.config import (
    ARCADEDB_URL,
    ARCADEDB_DATABASE,
    ARCADEDB_USER,
    ARCADEDB_PASSWORD,
    ARCADEDB_TIMEOUT,
)

logger = logging.getLogger(__name__)


class ArcadeDBError(RuntimeError):
    """Any failure talking to ArcadeDB."""


# Retry policy for transient page-level optimistic-lock collisions. ArcadeDB
# uses LSM page versioning for write isolation; when two writers touch the
# same bucket page concurrently the slower one gets:
#   HTTP 503 ConcurrentModificationException
#   "Concurrent modification on page PageId(...) (current v.X <> database v.Y)
#    Please retry the operation"
# Hot edge buckets (e.g. Entity_*_in_edges.* during a heavy mention-edge
# write) are the typical trigger. A bounded retry with jittered backoff is
# safe because the failed batch did not commit; the next attempt sees the
# new page version and proceeds.
_RETRYABLE_EXCEPTIONS = ('ConcurrentModificationException',)
_MAX_RETRIES = int(os.environ.get('ARCADEDB_MAX_RETRIES', '5'))
_RETRY_BACKOFF_BASE = float(os.environ.get('ARCADEDB_RETRY_BACKOFF_BASE', '0.25'))


def _is_retryable_arcadedb_error(status_code: int, body: str) -> bool:
    """Match ArcadeDB's documented retryable failures by exception class
    in the response body. Other 5xx are surfaced unchanged."""
    if status_code != 503:
        return False
    return any(exc in body for exc in _RETRYABLE_EXCEPTIONS)


class ArcadeDBClient:
    """Stateless HTTP client for ArcadeDB.

    Two endpoints are used:
      POST /api/v1/command/<db>   - mutating statements (CREATE, MERGE, DELETE)
      POST /api/v1/query/<db>     - read-only SELECT/MATCH queries
    Both accept {"language": "cypher", "command": "..."}.

    Per-Domain isolation: each Domain owns its own ArcadeDB database
    (named after its domain_id) inside the single noted-arcadedb container.
    Pass `database=<domain_id>` to the constructor for Domain-scoped ops;
    omit for the default `noted` database.
    """

    def __init__(self, database: str | None = None):
        self._base = ARCADEDB_URL.rstrip('/')
        self._db = database or ARCADEDB_DATABASE
        self._auth = (ARCADEDB_USER, ARCADEDB_PASSWORD)
        self._timeout = ARCADEDB_TIMEOUT
        # Connection pool with HTTP keepalive: avoids paying TCP handshake
        # on every Cypher query. Auth is set once and never mutated, so
        # cross-thread use of the session for stateless POSTs is safe.
        self._session = requests.Session()

    @property
    def database(self) -> str:
        """The database name this client targets."""
        return self._db

    # ── Basic health / probe ─────────────────────────────────────────
    def ready(self) -> bool:
        """True if the server responds to /api/v1/ready with HTTP 2xx."""
        try:
            r = self._session.get(f'{self._base}/api/v1/ready', timeout=self._timeout)
            return r.ok
        except requests.RequestException:
            return False

    def databases(self) -> list[str]:
        r = self._session.get(
            f'{self._base}/api/v1/databases',
            auth=self._auth,
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json().get('result', []) or []

    def database_exists(self, name: str) -> bool:
        """True if the named ArcadeDB database exists on the server."""
        try:
            return name in self.databases()
        except (requests.RequestException, ValueError):
            return False

    def create_database(self, name: str) -> bool:
        """Create a new ArcadeDB database via the server-level command.
        Returns True if created (or already existed), False on failure.

        The command runs against the special `_system` namespace - any
        existing database name is fine for the URL, the SQL targets the
        server. Idempotent: if the database already exists, returns True
        without error."""
        if self.database_exists(name):
            return True
        url = f'{self._base}/api/v1/server'
        payload = {'language': 'sql', 'command': f'CREATE DATABASE {name}'}
        try:
            r = self._session.post(
                url, json=payload, auth=self._auth, timeout=self._timeout,
            )
        except requests.RequestException as e:
            logger.warning('ArcadeDB CREATE DATABASE %s: transport error: %s',
                           name, e)
            return False
        if not r.ok:
            logger.warning('ArcadeDB CREATE DATABASE %s: HTTP %d: %s',
                           name, r.status_code, r.text[:300])
            return False
        return True

    def drop_database(self, name: str) -> bool:
        """Drop an ArcadeDB database via the server-level command.
        Idempotent: returns True if the database is gone (or never existed)."""
        if not self.database_exists(name):
            return True
        url = f'{self._base}/api/v1/server'
        payload = {'language': 'sql', 'command': f'DROP DATABASE {name}'}
        try:
            r = self._session.post(
                url, json=payload, auth=self._auth, timeout=self._timeout,
            )
        except requests.RequestException as e:
            logger.warning('ArcadeDB DROP DATABASE %s: transport error: %s',
                           name, e)
            return False
        if not r.ok:
            logger.warning('ArcadeDB DROP DATABASE %s: HTTP %d: %s',
                           name, r.status_code, r.text[:300])
            return False
        return True

    # ── Command / query ──────────────────────────────────────────────
    def command(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run a Cypher statement that may mutate state. Returns result rows."""
        return self._send('command', cypher, params)

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run a read-only Cypher query. Returns result rows."""
        return self._send('query', cypher, params)

    def _send(self, kind: str, cypher: str, params: dict[str, Any] | None) -> list[dict]:
        url = f'{self._base}/api/v1/{kind}/{self._db}'
        payload: dict[str, Any] = {'language': 'cypher', 'command': cypher}
        if params:
            payload['params'] = params
        return self._post_with_retry(url, payload, kind=kind, expect_result=True)

    def _post_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        kind: str,
        expect_result: bool,
    ) -> list[dict]:
        """POST + retry on transient ArcadeDB ConcurrentModificationException.

        Retries _MAX_RETRIES times with jittered exponential backoff. Network
        errors and non-retryable HTTP errors raise immediately. The failed
        batch did not commit (ArcadeDB's optimistic locking aborts cleanly
        on conflict), so retry is safe."""
        last_body = ''
        for attempt in range(_MAX_RETRIES + 1):
            try:
                r = self._session.post(url, json=payload, auth=self._auth, timeout=self._timeout)
            except requests.RequestException as e:
                raise ArcadeDBError(f'ArcadeDB request failed: {e}') from e
            if r.ok:
                if not expect_result:
                    return r.json().get('result', [])
                data = r.json()
                result = data.get('result')
                if result is None:
                    raise ArcadeDBError(f'ArcadeDB response missing result: {data}')
                return result
            last_body = r.text[:500]
            if attempt < _MAX_RETRIES and _is_retryable_arcadedb_error(r.status_code, last_body):
                # Jittered exponential backoff: 0.25, 0.5, 1.0, 2.0, 4.0 ish.
                # Jitter prevents synchronized retries from colliding again
                # if multiple worker threads got the same conflict.
                backoff = _RETRY_BACKOFF_BASE * (2 ** attempt) * (0.5 + random.random())
                logger.warning(
                    'ArcadeDB %s HTTP %d (retryable, attempt %d/%d, backoff %.2fs): %s',
                    kind, r.status_code, attempt + 1, _MAX_RETRIES, backoff, last_body[:200],
                )
                time.sleep(backoff)
                continue
            raise ArcadeDBError(
                f'ArcadeDB {kind} HTTP {r.status_code}: {last_body}'
            )
        # Exhausted retries — last response was retryable but never succeeded.
        raise ArcadeDBError(
            f'ArcadeDB {kind} exhausted {_MAX_RETRIES} retries on retryable error: {last_body}'
        )

    # ── Schema bootstrap ─────────────────────────────────────────────
    def ensure_schema(self) -> None:
        """Create vertex/edge types, declare hot properties, and build the
        indexes the retriever depends on.

        - `Entity.id` UNIQUE: vertex lookup by id (every MERGE/MATCH-by-id).
        - `Entity.type`: every retrieval filters by type (community_summary,
          markdown_chunk, concept/term/...). Non-unique LSM_TREE.
        - `Entity.community_id`: global-mode retrieval looks up entities by
          community membership. Promoted out of properties_json to a
          first-class indexed property. Non-unique LSM_TREE.
        - `RELATES.type`: every traversal filters edges by the relationship
          kind (member_of / mentions / domain-specific RTYPES). Without
          this index, `(a)-[r:RELATES {type: "X"}]->(b)` scans every
          outgoing RELATES from `a` and filters in memory; popular
          concepts accumulate many edges and the BFS walks become O(degree)
          per hop. Non-unique LSM_TREE.
        """
        for stmt in [
            'CREATE VERTEX TYPE Entity IF NOT EXISTS',
            'CREATE EDGE TYPE RELATES IF NOT EXISTS',
            # Property declarations - required before CREATE INDEX
            'CREATE PROPERTY Entity.id IF NOT EXISTS STRING',
            'CREATE PROPERTY Entity.type IF NOT EXISTS STRING',
            'CREATE PROPERTY Entity.community_id IF NOT EXISTS INTEGER',
            'CREATE PROPERTY RELATES.type IF NOT EXISTS STRING',
            # Indexes
            'CREATE INDEX IF NOT EXISTS ON Entity (id) UNIQUE',
            'CREATE INDEX IF NOT EXISTS ON Entity (type) NOTUNIQUE',
            'CREATE INDEX IF NOT EXISTS ON Entity (community_id) NOTUNIQUE',
            'CREATE INDEX IF NOT EXISTS ON RELATES (type) NOTUNIQUE',
        ]:
            self._send_sql(stmt)

    def command_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run an ArcadeDB SQL statement (not Cypher). Used when Cypher
        lacks a feature (e.g. list comprehension / array REMOVE)."""
        return self._send_sql(sql, params)

    def graphbatch_post(
        self,
        ndjson_lines: list[str],
        *,
        light_edges: bool = False,
    ) -> dict[str, Any]:
        """POST a GraphBatch payload to /api/v1/batch/<db>.

        Each line in `ndjson_lines` is an already-serialized JSON dict
        (vertex or edge per the ArcadeDB GraphBatch HTTP schema).
        Vertices: `{"@type":"vertex","@class":"Entity","@id":"...", ...props}`.
        Edges:    `{"@type":"edge","@class":"RELATES","@from":"...","@to":"...", ...props}`.

        `@from`/`@to` may be either:
          - a `@id` declared earlier in THIS batch (vertex must precede the edge), or
          - an existing-vertex RID string like `"#1:967834"` (caller is
            responsible for fetching the RID via a prior SELECT).

        The endpoint is CREATE-only — duplicate `@id` raises
        DuplicatedKeyException (HTTP 503). Vertex MERGE must be handled
        by the caller (pre-fetch + partition new vs existing).

        Returns the server response: `{verticesCreated, edgesCreated,
        elapsedMs, idMapping: {<@id>: <RID>, ...}}`.
        """
        url = f'{self._base}/api/v1/batch/{self._db}?lightEdges={"true" if light_edges else "false"}'
        body = ('\n'.join(ndjson_lines)).encode('utf-8')
        headers = {'Content-Type': 'application/x-ndjson'}
        # GraphBatch is the hot path; retry on the same transient errors
        # the regular command path retries on (ConcurrentModificationException
        # is theoretically possible if another writer hits the same edge
        # bucket page concurrently with our batch).
        last_body = ''
        for attempt in range(_MAX_RETRIES + 1):
            try:
                r = self._session.post(
                    url, data=body, headers=headers, auth=self._auth, timeout=self._timeout,
                )
            except requests.RequestException as e:
                raise ArcadeDBError(f'GraphBatch request failed: {e}') from e
            if r.ok:
                return r.json()
            last_body = r.text[:500]
            if attempt < _MAX_RETRIES and _is_retryable_arcadedb_error(r.status_code, last_body):
                backoff = _RETRY_BACKOFF_BASE * (2 ** attempt) * (0.5 + random.random())
                logger.warning(
                    'GraphBatch HTTP %d (retryable, attempt %d/%d, backoff %.2fs): %s',
                    r.status_code, attempt + 1, _MAX_RETRIES, backoff, last_body[:200],
                )
                time.sleep(backoff)
                continue
            raise ArcadeDBError(
                f'GraphBatch HTTP {r.status_code}: {last_body}'
            )
        raise ArcadeDBError(
            f'GraphBatch exhausted {_MAX_RETRIES} retries on retryable error: {last_body}'
        )

    def _send_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run an ArcadeDB SQL statement (not Cypher)."""
        url = f'{self._base}/api/v1/command/{self._db}'
        payload: dict[str, Any] = {'language': 'sql', 'command': sql}
        if params:
            payload['params'] = params
        try:
            r = self._session.post(url, json=payload, auth=self._auth, timeout=self._timeout)
        except requests.RequestException as e:
            raise ArcadeDBError(f'ArcadeDB SQL request failed: {e}') from e
        if not r.ok:
            raise ArcadeDBError(
                f'ArcadeDB SQL HTTP {r.status_code}: {r.text[:500]}'
            )
        return r.json().get('result', [])

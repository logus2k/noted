"""Auth helper for user tools (Phase I1 of the auth workstream).

Vendored verbatim into every new user-tool's site-packages at venv
build time by `venv_manager.py` (Phase I2). Tools `import _auth` and
call one of three session factories that return a configured
`httpx.Client`:

    anonymous_session()                                # no auth
    api_key_session(secret_name, header_name, prefix)  # single-header key
    oauth2_client_credentials_session(token_url, client_id_secret,
                                      client_secret_secret, scope)

The factory:
  - reads the actual secret VALUES from env vars named `SECRET_<NAME>`
    (the noted-tools executor injects these per the tool's declared
    `_meta.allowed_secrets`);
  - configures retries on transient 5xx with bounded backoff;
  - sets a default User-Agent (overridable);
  - for OAuth2: fetches a bearer token on first request, caches it in
    memory for the lifetime of the client, and re-fetches transparently
    on 401.

Tools should NEVER hand-roll the OAuth2 token dance or wire api-key
headers manually. The helper is the contract; the framework keeps it
correct.

This file is intentionally STDLIB + httpx only. No requests-oauthlib,
no authlib — those would each need to be vendored too, and httpx is
already the canonical transport.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Generator

import httpx

DEFAULT_USER_AGENT = (
    'noted-user-tool/1.0 (+published-by-noted-workflow-framework)'
)
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_RETRIES = 3


class AuthHelperError(RuntimeError):
    """Any failure in the auth helper. Tool code should let this
    propagate to stderr + exit non-zero."""


# ── Secret env-var reader ────────────────────────────────────────


def _read_secret_env(secret_name: str) -> str:
    """Read SECRET_<NAME> from the environment. Raises if absent so
    the tool fails loudly rather than calling the upstream with an
    empty credential."""
    env_key = f'SECRET_{secret_name}'
    value = os.environ.get(env_key)
    if not value:
        raise AuthHelperError(
            f'env var {env_key} not set; the executor did not inject '
            f'the secret {secret_name!r}. Did the tool declare it in '
            f'_meta.allowed_secrets? Has the user run set_secret for it?'
        )
    return value


# ── Retry transport (used by every factory) ──────────────────────


class _RetryTransport(httpx.HTTPTransport):
    """Retry on 5xx + connect / read timeouts. Cap = max_retries. Sleep
    between attempts: exponential, 0.25s * 2**n, max 4s."""

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES, **kwargs):
        super().__init__(**kwargs)
        self._max_retries = max_retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = super().handle_request(request)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                if attempt < self._max_retries:
                    time.sleep(min(4.0, 0.25 * (2 ** attempt)))
                    continue
                raise
            if response.status_code >= 500 and attempt < self._max_retries:
                time.sleep(min(4.0, 0.25 * (2 ** attempt)))
                continue
            return response
        # unreachable, but mypy:
        if last_exc:
            raise last_exc
        raise AuthHelperError('retry loop exhausted without response')


def _base_client(*, headers: dict[str, str] | None = None,
                 auth: httpx.Auth | None = None,
                 timeout: float = DEFAULT_TIMEOUT_S,
                 max_retries: int = DEFAULT_MAX_RETRIES) -> httpx.Client:
    merged_headers = {'User-Agent': DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)
    return httpx.Client(
        transport=_RetryTransport(max_retries=max_retries),
        headers=merged_headers,
        timeout=timeout,
        auth=auth,
    )


# ── 1. Anonymous ──────────────────────────────────────────────────


def anonymous_session(*, timeout: float = DEFAULT_TIMEOUT_S,
                      max_retries: int = DEFAULT_MAX_RETRIES) -> httpx.Client:
    """Public-endpoint session. Default UA + retry on 5xx. Use this
    even for unauthenticated tools — the retry transport is worth
    having."""
    return _base_client(timeout=timeout, max_retries=max_retries)


# ── 2. API key (single-header) ───────────────────────────────────


def api_key_session(*, secret_name: str, header_name: str = 'Authorization',
                    prefix: str = 'Bearer ',
                    timeout: float = DEFAULT_TIMEOUT_S,
                    max_retries: int = DEFAULT_MAX_RETRIES) -> httpx.Client:
    """API-key session. Reads the key from `SECRET_<secret_name>` and
    sets `header_name: <prefix><key>` on every outgoing request.

    Common patterns:
      - Bearer-style: `api_key_session(secret_name='X', header_name='Authorization', prefix='Bearer ')`
      - Custom-header: `api_key_session(secret_name='X', header_name='X-API-Key', prefix='')`
    """
    key = _read_secret_env(secret_name)
    return _base_client(
        headers={header_name: f'{prefix}{key}'},
        timeout=timeout, max_retries=max_retries,
    )


# ── 3. OAuth2 client_credentials ─────────────────────────────────


class _OAuth2ClientCredentialsAuth(httpx.Auth):
    """httpx.Auth that fetches + caches a bearer token via the
    client_credentials grant; refreshes on 401."""

    requires_response_body = False

    def __init__(self, token_url: str, client_id: str, client_secret: str,
                 scope: str = ''):
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        """Synchronous token-endpoint POST. Standard OAuth2 RFC 6749
        Section 4.4: client_credentials grant, basic-auth the client
        identifier, form-encoded body."""
        with self._lock:
            data = {'grant_type': 'client_credentials'}
            if self._scope:
                data['scope'] = self._scope
            # Use a SEPARATE httpx.Client (no auth, no retry) so we
            # don't recurse into ourselves on token-endpoint errors.
            with httpx.Client(timeout=DEFAULT_TIMEOUT_S) as fetch:
                resp = fetch.post(
                    self._token_url,
                    data=data,
                    auth=(self._client_id, self._client_secret),
                    headers={'User-Agent': DEFAULT_USER_AGENT,
                             'Accept': 'application/json'},
                )
            if resp.status_code != 200:
                raise AuthHelperError(
                    f'OAuth2 token endpoint returned {resp.status_code}: '
                    f'{resp.text[:300]}'
                )
            try:
                payload = resp.json()
            except ValueError as e:
                raise AuthHelperError(
                    f'OAuth2 token endpoint returned non-JSON: {resp.text[:200]}'
                ) from e
            token = payload.get('access_token')
            if not isinstance(token, str) or not token:
                raise AuthHelperError(
                    f'OAuth2 token endpoint payload missing access_token: '
                    f'{list(payload.keys())}'
                )
            expires_in = payload.get('expires_in')
            self._token = token
            # Treat token as fresh for (expires_in - 30s) to avoid using
            # a token in the last-second of its lifetime. If expires_in
            # absent, refresh on every 401 only.
            if isinstance(expires_in, (int, float)) and expires_in > 60:
                self._expires_at = time.time() + float(expires_in) - 30.0
            else:
                self._expires_at = float('inf')  # only refresh on 401

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        if self._token is None or time.time() >= self._expires_at:
            self._refresh()
        request.headers['Authorization'] = f'Bearer {self._token}'
        response = yield request
        if response.status_code == 401:
            # Force refresh + retry once.
            self._token = None
            self._expires_at = 0.0
            self._refresh()
            request.headers['Authorization'] = f'Bearer {self._token}'
            yield request


def oauth2_client_credentials_session(
    *, token_url: str,
    client_id_secret: str,
    client_secret_secret: str,
    scope: str = '',
    timeout: float = DEFAULT_TIMEOUT_S,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> httpx.Client:
    """OAuth2 client_credentials session. Reads client_id from
    `SECRET_<client_id_secret>` and client_secret from
    `SECRET_<client_secret_secret>`. Fetches a bearer token on first
    request, caches in memory, refreshes on 401."""
    client_id = _read_secret_env(client_id_secret)
    client_secret_value = _read_secret_env(client_secret_secret)
    auth = _OAuth2ClientCredentialsAuth(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret_value,
        scope=scope,
    )
    return _base_client(auth=auth, timeout=timeout, max_retries=max_retries)

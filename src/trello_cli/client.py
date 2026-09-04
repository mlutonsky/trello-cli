"""Thin httpx wrapper over the Trello REST API.

Three things here are not obvious and are the reason this file exists:

1. **Header auth, everywhere.** Trello accepts `?key=&token=` on most routes, but NOT
   on the attachment download route — that one has required
   `Authorization: OAuth oauth_consumer_key="…", oauth_token="…"` since 2021. Rather
   than carry two auth styles, everything uses the header.
2. **Credentials are host-gated.** An attachment `url` can point at any third-party
   host, and a download can redirect to a presigned URL elsewhere. Credentials are
   attached via an `httpx.Auth` subclass (httpx re-runs the auth flow per request and
   drops the header across hosts) plus an explicit allowlist.
3. **Rate limits without `Retry-After`.** Trello documents 300 req/10s per key and
   100 req/10s per token, returns 429, and sends no `Retry-After`. We steer by the
   `x-rate-limit-api-token-remaining` header and back off with jitter on 429/5xx.
"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import config
from .errors import TrelloApiError

BASE_URL = "https://api.trello.com/1"
DEFAULT_TIMEOUT = 30.0

# Hosts we are willing to send Trello credentials to.
TRELLO_HOSTS = frozenset({"api.trello.com", "trello.com"})

MAX_ATTEMPTS = 4  # total attempts incl. the first
RETRY_BACKOFF_BASE = 0.5  # seconds; doubled per attempt
RETRY_DELAY_CAP = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Slow down before we hit the wall rather than after.
THROTTLE_THRESHOLD = 5  # requests left in the window


def _is_trello_host(url: httpx.URL | str) -> bool:
    host = urlsplit(str(url)).hostname or ""
    return host.lower() in TRELLO_HOSTS


class TrelloAuth(httpx.Auth):
    """Attach Trello's OAuth-style header, but only on Trello's own hosts.

    Using the `auth=` slot rather than `headers=` means httpx re-evaluates this per
    request, including after a redirect — so a redirect to a presigned S3 URL does not
    leak the token.
    """

    def __init__(self, key: str, token: str) -> None:
        self._key = key
        self._token = token

    def auth_flow(self, request: httpx.Request):
        if _is_trello_host(request.url):
            request.headers["Authorization"] = (
                f'OAuth oauth_consumer_key="{self._key}", oauth_token="{self._token}"'
            )
        yield request


def serialise(params: dict[str, Any] | None) -> dict[str, str]:
    """Trello wants `true`/`false` strings and comma-separated lists, never repeated keys."""
    if not params:
        return {}
    out: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, list | tuple | set):
            items = [str(v) for v in value if v is not None]
            out[key] = ",".join(items)
        else:
            out[key] = str(value)
    return out


def _error_from(response: httpx.Response) -> TrelloApiError:
    """Trello returns `{"code","message"}` on some routes and bare text on others."""
    detail: Any
    message: str
    try:
        detail = response.json()
    except ValueError:
        detail = response.text.strip()
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("error") or response.reason_phrase)
    else:
        message = str(detail) or response.reason_phrase
    return TrelloApiError(message, status=response.status_code, details=detail)


class TrelloClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url if base_url is not None else BASE_URL,
            auth=TrelloAuth(config.api_key(), config.token()),
            headers={"Accept": "application/json"},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            transport=transport,
        )
        self._remaining: int | None = None
        self._interval_ms: int | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TrelloClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- rate limiting ------------------------------------------------------

    def _note_limits(self, response: httpx.Response) -> None:
        for header, attr in (
            ("x-rate-limit-api-token-remaining", "_remaining"),
            ("x-rate-limit-api-token-interval-ms", "_interval_ms"),
        ):
            raw = response.headers.get(header)
            if raw is not None:
                try:
                    setattr(self, attr, int(raw))
                except ValueError:
                    pass

    def _throttle(self) -> None:
        """Wait out the window when the token budget is nearly spent."""
        if self._remaining is None or self._remaining > THROTTLE_THRESHOLD:
            return
        wait = (self._interval_ms or 10_000) / 1000.0
        time.sleep(min(wait, RETRY_DELAY_CAP))
        self._remaining = None  # the next response re-establishes the budget

    # --- request plumbing ---------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        query = serialise(params)
        last_error: TrelloApiError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle()
            response = self._http.request(
                method, path, params=query, files=files, json=json_body
            )
            self._note_limits(response)
            if response.status_code < 400:
                return response
            last_error = _error_from(response)
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise last_error
            # No Retry-After is documented; exponential backoff with jitter.
            delay = min(RETRY_BACKOFF_BASE * (2 ** (attempt - 1)), RETRY_DELAY_CAP)
            time.sleep(delay + random.uniform(0, delay / 2))
        assert last_error is not None
        raise last_error

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params).json()

    def post(self, path: str, **params: Any) -> Any:
        return self.request("POST", path, params=params).json()

    def put(self, path: str, **params: Any) -> Any:
        return self.request("PUT", path, params=params).json()

    def put_json(self, path: str, body: Any) -> Any:
        response = self.request("PUT", path, json_body=body)
        try:
            return response.json()
        except ValueError:
            return {}

    def delete(self, path: str, **params: Any) -> Any:
        response = self.request("DELETE", path, params=params)
        try:
            return response.json()
        except ValueError:
            return {}

    def upload(self, path: str, *, files: dict[str, Any], **params: Any) -> Any:
        return self.request("POST", path, params=params, files=files).json()

    def download(self, url: str) -> tuple[bytes, str | None]:
        """Fetch attachment bytes. Absolute non-Trello URLs are fetched without credentials."""
        response = self.request("GET", url) if url.startswith("/") else self._absolute_get(url)
        return response.content, response.headers.get("content-type")

    def _absolute_get(self, url: str) -> httpx.Response:
        response = self._http.get(url)
        self._note_limits(response)
        if response.status_code >= 400:
            raise _error_from(response)
        return response

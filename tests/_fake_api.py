"""A fake Trello API for command-level tests.

Commands reach the network only through `_common.client()`, which resolves
`TrelloClient` from its own module globals at call time — so patching that one name
puts every command under test without touching command code.
"""

from __future__ import annotations

from typing import Any

import httpx

from trello_cli.client import TrelloClient

BOARD_ID = "6a3e6e0463ecebc66c58fb6c"
LIST_TODO = "1" * 24
LIST_DONE = "2" * 24
CARD = "6h3iK2mA"


class FakeApi:
    """Routes are keyed by `"METHOD /path"`; values are payloads or callables."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        self.calls.append((request.method, request.url.path, dict(request.url.params)))
        if key not in self.routes:
            raise AssertionError(f"unmocked route {key} (mocked: {sorted(self.routes)})")
        payload = self.routes[key]
        if callable(payload):
            payload = payload(request)
        return httpx.Response(200, json=payload)

    def params_for(self, method: str, path: str) -> dict[str, str]:
        for m, p, params in self.calls:
            if m == method and p == path:
                return params
        raise AssertionError(f"{method} {path} was never called; calls={self.calls}")

    def called(self, method: str, path: str) -> bool:
        return any(m == method and p == path for m, p, _ in self.calls)


DEFAULT_ROUTES: dict[str, Any] = {
    "GET /1/members/me/boards": [
        {"id": BOARD_ID, "name": "Clusbpire klienti", "shortLink": "6RSm3uu9"}
    ],
    f"GET /1/boards/{BOARD_ID}/lists": [
        {"id": LIST_TODO, "name": "TODO"},
        {"id": LIST_DONE, "name": "Hotovo"},
    ],
    f"GET /1/boards/{BOARD_ID}/labels": [
        {"id": "3" * 24, "name": "bug", "color": "red"},
    ],
    f"GET /1/boards/{BOARD_ID}/members": [
        {"id": "4" * 24, "username": "lutonsky", "fullName": "Martin Lutonsky"},
    ],
    f"GET /1/boards/{BOARD_ID}/customFields": [
        {"id": "5" * 24, "name": "Estimate", "type": "number"},
    ],
}


def install(monkeypatch, extra_routes: dict[str, Any] | None = None) -> FakeApi:
    routes = dict(DEFAULT_ROUTES)
    routes.update(extra_routes or {})
    api = FakeApi(routes)
    monkeypatch.setattr(
        "trello_cli.commands._common.TrelloClient",
        lambda **kw: TrelloClient(transport=httpx.MockTransport(api.handler)),
    )
    monkeypatch.setenv("TRELLO_BOARD_ID", BOARD_ID)
    return api

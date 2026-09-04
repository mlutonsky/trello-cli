from __future__ import annotations

import httpx
import pytest

from trello_cli.client import TrelloClient, serialise
from trello_cli.errors import ConfigError, TrelloApiError


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        TrelloClient()


def test_serialise_booleans_and_lists():
    assert serialise({"a": True, "b": False, "c": ["x", "y"], "d": None, "e": 3}) == {
        "a": "true",
        "b": "false",
        "c": "x,y",
        "e": "3",
    }


def test_auth_header_only_on_trello_hosts():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[str(request.url)] = request.headers.get("Authorization")
        return httpx.Response(200, json={})

    client = TrelloClient(transport=httpx.MockTransport(handler))
    client.get("/members/me")
    client._absolute_get("https://evil.example.com/file.png")
    client.close()

    trello_url = next(u for u in seen if "api.trello.com" in u)
    assert seen[trello_url].startswith('OAuth oauth_consumer_key="test-key"')
    assert seen["https://evil.example.com/file.png"] is None


def test_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("trello_cli.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "API_TOKEN_LIMIT_EXCEEDED"})
        return httpx.Response(200, json={"ok": True})

    client = TrelloClient(transport=httpx.MockTransport(handler))
    assert client.get("/members/me") == {"ok": True}
    assert calls["n"] == 2
    client.close()


def test_does_not_retry_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="invalid id")

    client = TrelloClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TrelloApiError) as excinfo:
        client.get("/cards/nope")
    assert excinfo.value.status == 404
    assert "invalid id" in excinfo.value.message
    client.close()


def test_throttles_when_budget_is_spent(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("trello_cli.client.time.sleep", slept.append)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={},
            headers={
                "x-rate-limit-api-token-remaining": "1",
                "x-rate-limit-api-token-interval-ms": "10000",
            },
        )

    client = TrelloClient(transport=httpx.MockTransport(handler))
    client.get("/members/me")  # learns the budget
    client.get("/members/me")  # must wait it out first
    assert slept == [10.0]
    client.close()

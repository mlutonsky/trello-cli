from __future__ import annotations

import httpx
import pytest

from trello_cli import resolve
from trello_cli.client import TrelloClient
from trello_cli.errors import InputError, ResolutionError

FULL_ID = "5e839f3696a55979a932b3ad"


def make_client(handler) -> TrelloClient:
    return TrelloClient(transport=httpx.MockTransport(handler))


def _no_requests(request: httpx.Request) -> httpx.Response:  # pragma: no cover - guard
    raise AssertionError(f"unexpected request to {request.url}")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (FULL_ID, FULL_ID),
        ("6h3iK2mA", "6h3iK2mA"),
        ("https://trello.com/c/6h3iK2mA/87-broken-export", "6h3iK2mA"),
        ("https://trello.com/c/6h3iK2mA", "6h3iK2mA"),
    ],
)
def test_card_identifiers_need_no_request(given, expected):
    client = make_client(_no_requests)
    assert resolve.card_id(client, given) == expected
    client.close()


def test_card_idshort_is_looked_up_live(monkeypatch):
    monkeypatch.setattr(resolve.state, "board", FULL_ID)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cards"):
            return httpx.Response(
                200, json=[{"idShort": 87, "shortLink": "6h3iK2mA", "name": "Broken export"}]
            )
        raise AssertionError(request.url)

    client = make_client(handler)
    assert resolve.card_id(client, "#87") == "6h3iK2mA"
    client.close()


def test_unrecognised_card_identifier_is_an_input_error():
    client = make_client(_no_requests)
    with pytest.raises(InputError):
        resolve.card_id(client, "not a card")
    client.close()


def test_board_resolves_by_name_and_caches():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json=[
                {"id": FULL_ID, "name": "Office2000 vývoj", "shortLink": "SwIFrRUT"},
                {"id": "a" * 24, "name": "Clusbpire klienti", "shortLink": "6RSm3uu9"},
            ],
        )

    client = make_client(handler)
    assert resolve.board_id(client, "office2000") == FULL_ID
    assert resolve.board_id(client, "Clusbpire klienti") == "a" * 24
    assert calls["n"] == 1  # the second lookup came from the cache
    client.close()


def test_ambiguous_name_is_an_error_not_a_guess():
    candidates = [{"name": "Test one"}, {"name": "Test two"}]
    with pytest.raises(ResolutionError) as excinfo:
        resolve.match_by_name(candidates, "test", kind="list")
    assert "ambiguous" in excinfo.value.message


def test_exact_match_beats_prefix():
    candidates = [{"name": "Done"}, {"name": "Done later"}]
    assert resolve.match_by_name(candidates, "Done", kind="list")["name"] == "Done"


def test_missing_name_lists_what_is_available():
    with pytest.raises(ResolutionError) as excinfo:
        resolve.match_by_name([{"name": "TODO"}], "Nope", kind="list")
    assert excinfo.value.details == {"available": ["TODO"]}


def test_list_name_refetches_once_before_failing():
    """A column renamed since we cached it must resolve on the refetch, not error."""
    responses = [
        [{"id": "1" * 24, "name": "Old name"}],
        [{"id": "2" * 24, "name": "New name"}],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0) if responses else [])

    client = make_client(handler)
    assert resolve.list_id(client, FULL_ID, "New name") == "2" * 24
    client.close()

"""Read commands: what they ask the API for, and what they print."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from trello_cli.cli import app

from ._fake_api import BOARD_ID, CARD, LIST_TODO, install

runner = CliRunner()

FULL_CARD = {
    "id": "a" * 24,
    "idBoard": BOARD_ID,
    "idShort": 87,
    "shortLink": CARD,
    "shortUrl": f"https://trello.com/c/{CARD}",
    "name": "Broken export",
    "desc": "Steps:\n1. open admin",
    "due": "2026-09-10T12:00:00.000Z",
    "labels": [{"name": "bug", "color": "red"}],
    "members": [{"username": "lutonsky"}],
    "badges": {"comments": 12},
    "board": {"name": "Clusbpire klienti"},
    "list": {"name": "TODO"},
    "checklists": [
        {"name": "QA", "checkItems": [{"id": "i1", "name": "reproduce", "state": "incomplete"}]}
    ],
    "attachments": [{"id": "at1", "name": "spec.pdf", "isUpload": True, "bytes": 10}],
    "customFieldItems": [{"idCustomField": "5" * 24, "value": {"number": "4"}}],
    "actions": [
        {
            "id": "c1",
            "type": "commentCard",
            "date": "2026-09-01T10:14:00.000Z",
            "memberCreator": {"username": "lutonsky"},
            "data": {"text": "Reproduced."},
        }
    ],
}


@pytest.fixture
def api(monkeypatch):
    return install(monkeypatch, {f"GET /1/cards/{CARD}": FULL_CARD})


def test_card_fetches_everything_in_one_request(api):
    result = runner.invoke(app, ["card", CARD])
    assert result.exit_code == 0, result.output
    assert len([c for c in api.calls if c[1] == f"/1/cards/{CARD}"]) == 1
    params = api.params_for("GET", f"/1/cards/{CARD}")
    # `checklists` is a string enum in Trello's API, not a boolean — an easy thing to break.
    assert params["checklists"] == "all"
    assert params["attachments"] == "true"
    assert params["customFieldItems"] == "true"
    assert params["actions"] == "commentCard"
    assert params["actions_limit"] == "10"


def test_card_renders_every_section(api):
    out = runner.invoke(app, ["card", CARD]).output
    assert "#87 Broken export [6h3iK2mA]" in out
    assert "Clusbpire klienti › TODO · bug(red) · @lutonsky" in out
    assert "## Description" in out
    assert "## Checklists" in out
    assert "## Custom fields\nEstimate: 4" in out
    assert "## Attachments (1)" in out
    assert "## Comments (1 of 12, newest first)" in out


def test_card_accepts_a_pasted_url_without_extra_requests(api):
    result = runner.invoke(app, ["card", f"https://trello.com/c/{CARD}/87-broken-export"])
    assert result.exit_code == 0, result.output
    assert api.called("GET", f"/1/cards/{CARD}")


def test_no_comments_skips_the_actions_parameter(api):
    runner.invoke(app, ["card", CARD, "--no-comments"])
    assert "actions" not in api.params_for("GET", f"/1/cards/{CARD}")


def test_full_raises_the_comment_limit(api):
    runner.invoke(app, ["card", CARD, "--full"])
    assert api.params_for("GET", f"/1/cards/{CARD}")["actions_limit"] == "1000"


def test_json_flag_emits_the_raw_payload(api):
    out = runner.invoke(app, ["--json", "card", CARD]).output
    assert json.loads(out)["shortLink"] == CARD


def test_markdown_is_much_smaller_than_json(api):
    markdown = runner.invoke(app, ["card", CARD]).output
    as_json = runner.invoke(app, ["--json", "card", CARD]).output
    assert len(markdown) * 3 < len(as_json)


def test_cards_lists_one_column(monkeypatch):
    api = install(
        monkeypatch,
        {
            f"GET /1/lists/{LIST_TODO}/cards": [
                {"idShort": 1, "shortLink": "aaaaaaaa", "name": "First"},
            ]
        },
    )
    out = runner.invoke(app, ["cards", "TODO"]).output
    assert "#1 [aaaaaaaa] First" in out
    assert api.params_for("GET", f"/1/lists/{LIST_TODO}/cards")["filter"] == "open"


def test_cards_archived_switches_the_filter(monkeypatch):
    api = install(monkeypatch, {f"GET /1/lists/{LIST_TODO}/cards": []})
    runner.invoke(app, ["cards", "TODO", "--archived"])
    assert api.params_for("GET", f"/1/lists/{LIST_TODO}/cards")["filter"] == "closed"


def test_snapshot_caps_cards_per_column(monkeypatch):
    install(
        monkeypatch,
        {
            f"GET /1/boards/{BOARD_ID}/lists": [
                {
                    "id": LIST_TODO,
                    "name": "TODO",
                    "cards": [
                        {"idShort": i, "shortLink": f"x{i:07d}", "name": f"Card {i}"}
                        for i in range(1, 6)
                    ],
                }
            ]
        },
    )
    out = runner.invoke(app, ["snapshot", "-n", "2"]).output
    assert "## TODO (5)" in out
    assert "Card 1" in out and "Card 2" in out
    assert "Card 3" not in out
    assert "… 3 more" in out


def test_search_reads_the_object_response_not_an_array(monkeypatch):
    """Trello's own OpenAPI spec claims /search returns an array. It returns an object."""
    api = install(
        monkeypatch,
        {
            "GET /1/search": {
                "cards": [
                    {
                        "idShort": 5,
                        "shortLink": "bbbbbbbb",
                        "name": "Export bug",
                        "board": {"name": "Clusbpire klienti"},
                        "list": {"name": "Hotovo"},
                    }
                ]
            }
        },
    )
    out = runner.invoke(app, ["search", "export"]).output
    assert "Export bug" in out
    assert "Clusbpire klienti › Hotovo" in out
    assert api.params_for("GET", "/1/search")["idBoards"] == BOARD_ID


def test_search_all_boards_drops_the_board_scope(monkeypatch):
    api = install(monkeypatch, {"GET /1/search": {"cards": []}})
    runner.invoke(app, ["search", "export", "--all-boards"])
    assert "idBoards" not in api.params_for("GET", "/1/search")


def test_history_names_the_columns_a_card_moved_between(monkeypatch):
    install(
        monkeypatch,
        {
            f"GET /1/cards/{CARD}/actions": [
                {
                    "type": "updateCard",
                    "date": "2026-06-26T13:46:00.000Z",
                    "memberCreator": {"username": "lutonsky"},
                    "data": {"listBefore": {"name": "TODO"}, "listAfter": {"name": "Hotovo"}},
                }
            ]
        },
    )
    out = runner.invoke(app, ["history", CARD]).output
    assert "lutonsky: moved TODO → Hotovo" in out


def test_history_moves_filters_server_side(monkeypatch):
    api = install(monkeypatch, {f"GET /1/cards/{CARD}/actions": []})
    runner.invoke(app, ["history", CARD, "--moves"])
    assert api.params_for("GET", f"/1/cards/{CARD}/actions")["filter"] == "updateCard:idList"


def test_empty_listings_say_so_rather_than_printing_nothing(monkeypatch):
    install(monkeypatch, {f"GET /1/lists/{LIST_TODO}/cards": []})
    assert "_(no cards)_" in runner.invoke(app, ["cards", "TODO"]).output

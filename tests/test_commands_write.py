"""Write commands: the request that goes out, the audit trail, and --dry-run."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from trello_cli.cli import app
from trello_cli.config import home

from ._fake_api import BOARD_ID, CARD, LIST_DONE, LIST_TODO, install

runner = CliRunner()

CREATED = {"id": "a" * 24, "shortLink": CARD, "shortUrl": f"https://trello.com/c/{CARD}", "name": "New card"}


def audit_lines() -> list[dict]:
    path = home() / "audit.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def api(monkeypatch):
    return install(
        monkeypatch,
        {
            "POST /1/cards": CREATED,
            f"PUT /1/cards/{CARD}": CREATED,
            f"POST /1/cards/{CARD}/idLabels": {},
            f"POST /1/cards/{CARD}/idMembers": {},
            f"DELETE /1/cards/{CARD}/idLabels/{'3' * 24}": {},
            f"POST /1/cards/{CARD}/actions/comments": {"id": "c1"},
        },
    )


def test_create_resolves_names_to_ids(api):
    result = runner.invoke(
        app, ["create", "--name", "New card", "--list", "TODO", "--label", "bug", "--member", "lutonsky"]
    )
    assert result.exit_code == 0, result.output
    params = api.params_for("POST", "/1/cards")
    assert params["idList"] == LIST_TODO
    assert params["idLabels"] == "3" * 24
    assert params["idMembers"] == "4" * 24
    assert "created https://trello.com/c/" in result.output


def test_create_reads_the_description_from_a_file(api, tmp_path):
    body = tmp_path / "desc.md"
    body.write_text("# Heading\n\nWith `backticks` and\nnewlines.", encoding="utf-8")
    runner.invoke(app, ["create", "--name", "x", "--list", "TODO", "--desc", f"@{body}"])
    assert api.params_for("POST", "/1/cards")["desc"] == body.read_text()


def test_dry_run_describes_the_write_and_sends_nothing(api):
    result = runner.invoke(app, ["--dry-run", "create", "--name", "x", "--list", "TODO"])
    assert result.exit_code == 0, result.output
    assert "dry-run · card.create · POST /cards" in result.output
    assert not api.called("POST", "/1/cards")


def test_dry_run_is_recorded_as_such(api):
    runner.invoke(app, ["--dry-run", "create", "--name", "x", "--list", "TODO"])
    entry = audit_lines()[-1]
    assert entry["dryRun"] is True
    assert entry["command"] == "card.create"


def test_every_write_lands_in_the_audit_log(api):
    runner.invoke(app, ["comment", "add", CARD, "hello"])
    entry = audit_lines()[-1]
    assert entry["command"] == "comment.add"
    assert entry["method"] == "POST"
    assert entry["path"] == f"/cards/{CARD}/actions/comments"
    assert entry["dryRun"] is False


def test_move_sends_only_the_list_within_one_board(api):
    result = runner.invoke(app, ["move", CARD, "--list", "Hotovo"])
    assert result.exit_code == 0, result.output
    params = api.params_for("PUT", f"/1/cards/{CARD}")
    assert params["idList"] == LIST_DONE
    assert "idBoard" not in params


def test_cross_board_move_sends_idboard_with_idlist_and_warns(monkeypatch):
    other = "b" * 24
    api = install(
        monkeypatch,
        {
            "GET /1/members/me/boards": [
                {"id": BOARD_ID, "name": "Clusbpire klienti", "shortLink": "6RSm3uu9"},
                {"id": other, "name": "Office2000", "shortLink": "SwIFrRUT"},
            ],
            f"GET /1/boards/{other}/lists": [{"id": "9" * 24, "name": "Inbox"}],
            f"PUT /1/cards/{CARD}": CREATED,
        },
    )
    result = runner.invoke(app, ["move", CARD, "--list", "Inbox", "--to-board", "Office2000"])
    assert result.exit_code == 0, result.output
    params = api.params_for("PUT", f"/1/cards/{CARD}")
    # idBoard alone would leave the card without a valid list on the target board.
    assert params["idBoard"] == other
    assert params["idList"] == "9" * 24
    assert "silently drops labels" in result.output


def test_archive_closes_rather_than_deleting(api):
    runner.invoke(app, ["archive", CARD])
    assert api.params_for("PUT", f"/1/cards/{CARD}")["closed"] == "true"
    assert not any(m == "DELETE" and p == f"/1/cards/{CARD}" for m, p, _ in api.calls)


def test_label_add_uses_idlabels_not_labels(api):
    """POST /cards/{id}/labels would create a NEW board label — a costly slip."""
    runner.invoke(app, ["label", "add", CARD, "bug"])
    assert api.called("POST", f"/1/cards/{CARD}/idLabels")
    assert not api.called("POST", f"/1/cards/{CARD}/labels")


def test_label_rm_deletes_the_link(api):
    result = runner.invoke(app, ["label", "rm", CARD, "bug"])
    assert result.exit_code == 0, result.output
    assert api.called("DELETE", f"/1/cards/{CARD}/idLabels/{'3' * 24}")


def test_member_add_resolves_a_username_to_an_id(api):
    """Trello's card member endpoint rejects usernames — only the 24-hex id works."""
    runner.invoke(app, ["member", "add", CARD, "lutonsky"])
    assert api.params_for("POST", f"/1/cards/{CARD}/idMembers")["value"] == "4" * 24


def test_update_without_any_field_is_an_input_error(api):
    result = runner.invoke(app, ["update", CARD])
    assert result.exit_code != 0
    assert not api.called("PUT", f"/1/cards/{CARD}")


def test_comment_rm_requires_explicit_confirmation(monkeypatch):
    api = install(monkeypatch, {"DELETE /1/actions/c1": {}})
    result = runner.invoke(app, ["comment", "rm", "c1"])
    assert result.exit_code != 0
    assert not api.called("DELETE", "/1/actions/c1")
    assert runner.invoke(app, ["comment", "rm", "c1", "--yes"]).exit_code == 0
    assert api.called("DELETE", "/1/actions/c1")


def test_checklist_tick_uses_the_singular_checkitem_route(monkeypatch):
    api = install(
        monkeypatch,
        {
            f"GET /1/cards/{CARD}/checklists": [
                {"id": "cl1", "name": "QA", "checkItems": [{"id": "i1", "name": "reproduce", "state": "incomplete"}]}
            ],
            f"PUT /1/cards/{CARD}/checkItem/i1": {"name": "reproduce", "state": "complete"},
        },
    )
    result = runner.invoke(app, ["check", "tick", CARD, "reproduce"])
    assert result.exit_code == 0, result.output
    assert api.params_for("PUT", f"/1/cards/{CARD}/checkItem/i1")["state"] == "complete"
    assert "[x] reproduce" in result.output


def test_custom_number_field_is_sent_as_a_string_in_a_json_body(monkeypatch):
    sent = {}

    def capture(request):
        sent.update(json.loads(request.content))
        return {}

    install(
        monkeypatch,
        {f"PUT /1/cards/{CARD}/customField/{'5' * 24}/item": capture},
    )
    result = runner.invoke(app, ["field", "set", CARD, "Estimate", "4"])
    assert result.exit_code == 0, result.output
    assert sent == {"value": {"number": "4"}}


def test_clearing_a_custom_field(monkeypatch):
    sent = {}

    def capture(request):
        sent.update(json.loads(request.content))
        return {}

    install(monkeypatch, {f"PUT /1/cards/{CARD}/customField/{'5' * 24}/item": capture})
    runner.invoke(app, ["field", "set", CARD, "Estimate", "--clear"])
    assert sent == {"value": ""}


def test_attachment_download_uses_the_authenticated_route(monkeypatch):
    """`?key=&token=` does not work on this route; only the OAuth header does."""
    api = install(
        monkeypatch,
        {
            f"GET /1/cards/{CARD}/attachments": [
                {"id": "at1", "name": "spec.pdf", "isUpload": True, "url": "https://attachments.trello.com/x"}
            ],
            f"GET /1/cards/{CARD}/attachments/at1/download/spec.pdf": {},
        },
    )
    result = runner.invoke(app, ["attach", "get", CARD, "spec.pdf", "--out", "-"])
    assert result.exit_code == 0, result.output
    assert api.called("GET", f"/1/cards/{CARD}/attachments/at1/download/spec.pdf")


def test_link_attachment_is_fetched_from_its_own_url(monkeypatch):
    api = install(
        monkeypatch,
        {
            f"GET /1/cards/{CARD}/attachments": [
                {"id": "at2", "name": "issue", "isUpload": False, "url": "https://example.com/issue"}
            ],
            "GET /issue": {},
        },
    )
    result = runner.invoke(app, ["attach", "get", CARD, "issue", "--out", "-"])
    assert result.exit_code == 0, result.output
    assert api.called("GET", "/issue")

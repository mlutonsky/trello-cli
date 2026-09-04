"""Cache and audit log — the two things that live in ~/.trello and are not credentials."""

from __future__ import annotations

import json

from trello_cli import audit, cache
from trello_cli.config import home


def test_boards_cache_round_trips_with_an_age():
    cache.put_boards([{"id": "1", "name": "One"}])
    cache.reset_for_tests()
    boards, age = cache.get_boards()
    assert boards == [{"id": "1", "name": "One"}]
    assert age < 60


def test_missing_cache_reports_infinite_age():
    boards, age = cache.get_boards()
    assert boards == []
    assert age == float("inf")


def test_board_maps_are_kept_per_board():
    cache.put_board_map("b1", "lists", {"items": [{"id": "l1"}]})
    cache.put_board_map("b2", "lists", {"items": [{"id": "l2"}]})
    cache.reset_for_tests()
    assert cache.get_board_map("b1", "lists")["items"][0]["id"] == "l1"
    assert cache.get_board_map("b2", "lists")["items"][0]["id"] == "l2"


def test_clear_drops_the_cache_but_not_the_credentials():
    (home()).mkdir(parents=True, exist_ok=True)
    (home() / "credentials").write_text("TRELLO_API_KEY=x\n", encoding="utf-8")
    cache.put_boards([{"id": "1"}])
    cache.clear()
    assert cache.get_boards() == ([], float("inf"))
    assert (home() / "credentials").exists()


def test_cache_files_are_not_world_readable():
    cache.put_boards([{"id": "1"}])
    assert (home() / "boards.json").stat().st_mode & 0o077 == 0


def test_audit_writes_one_json_object_per_line():
    audit.record(command="card.move", method="PUT", path="/cards/x", body={"idList": "1"})
    audit.record(command="card.archive", method="PUT", path="/cards/x", body=None, dry_run=True)
    lines = (home() / "audit.log").read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["command"] == "card.move"
    assert first["dryRun"] is False
    assert json.loads(lines[1])["dryRun"] is True


def test_audit_never_raises_when_the_log_is_unwritable(monkeypatch):
    monkeypatch.setenv("TRELLO_HOME", "/proc/nonexistent/trello")
    audit.record(command="x", method="GET", path="/y")  # must not raise

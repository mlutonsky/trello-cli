from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """Point TRELLO_HOME at a temp dir so tests never touch the real ~/.trello."""
    monkeypatch.setenv("TRELLO_HOME", str(tmp_path / "trello"))
    monkeypatch.setenv("TRELLO_API_KEY", "test-key")
    monkeypatch.setenv("TRELLO_TOKEN", "test-token")
    from trello_cli import cache, state

    cache.reset_for_tests()
    state.reset_for_tests()
    yield
    cache.reset_for_tests()
    state.reset_for_tests()

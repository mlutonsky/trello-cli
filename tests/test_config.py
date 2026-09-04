from __future__ import annotations

import pytest

from trello_cli import config
from trello_cli.errors import ConfigError


def write_credentials(text: str) -> None:
    home = config.home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "credentials").write_text(text, encoding="utf-8")


def test_reads_shell_style_credentials(monkeypatch):
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)
    write_credentials(
        "# comment\nTRELLO_API_KEY=abc123\nexport TRELLO_TOKEN='tok en'\nTRELLO_BOARD_ID=b1 # default\n"
    )
    assert config.api_key() == "abc123"
    assert config.token() == "tok en"
    assert config.default_board() == "b1"


def test_environment_wins_over_the_file(monkeypatch):
    write_credentials("TRELLO_API_KEY=from-file\n")
    monkeypatch.setenv("TRELLO_API_KEY", "from-env")
    assert config.api_key() == "from-env"


def test_missing_credential_names_the_file(monkeypatch):
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    with pytest.raises(ConfigError) as excinfo:
        config.api_key()
    assert "credentials" in excinfo.value.message


def test_use_writes_the_default_board(monkeypatch):
    monkeypatch.delenv("TRELLO_BOARD_ID", raising=False)
    config.set_default_board("SwIFrRUT")
    assert config.default_board() == "SwIFrRUT"

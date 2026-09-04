"""Argument plumbing shared by every command."""

from __future__ import annotations

import io

import pytest

from trello_cli.commands._common import read_text
from trello_cli.errors import InputError


def test_literal_text_passes_through():
    assert read_text("hello") == "hello"


def test_none_stays_none():
    assert read_text(None) is None


def test_at_prefix_reads_a_file(tmp_path):
    path = tmp_path / "body.md"
    path.write_text("# Title\n\n`code` and\nnewlines\n", encoding="utf-8")
    assert read_text(f"@{path}") == path.read_text()


def test_dash_reads_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("from a pipe"))
    assert read_text("-") == "from a pipe"


def test_missing_file_is_an_input_error_naming_the_path(tmp_path):
    with pytest.raises(InputError) as excinfo:
        read_text(f"@{tmp_path / 'nope.md'}")
    assert "nope.md" in excinfo.value.message

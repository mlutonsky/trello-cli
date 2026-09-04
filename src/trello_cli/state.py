"""Process-wide flags set once by the root Typer callback.

A module-level singleton rather than threading `ctx` through every command: the flags
are global by nature (output format, dry-run, board scope) and this keeps command
signatures about Trello rather than about plumbing.
"""

from __future__ import annotations


class _State:
    json_output: bool = False
    dry_run: bool = False
    board: str | None = None
    refresh: bool = False


state = _State()


def reset_for_tests() -> None:
    state.json_output = False
    state.dry_run = False
    state.board = None
    state.refresh = False

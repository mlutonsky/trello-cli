"""Disk-backed cache under the tool's home directory.

Holds two things, both derived from the API and both refillable at any time:
- `boards.json` — the member's boards (id, shortLink, name), so `--board <name>` works
  without anyone maintaining a list by hand.
- `cache.json`  — per-board name→id maps for lists, labels, members and custom fields.

Neither file is configuration. Deleting either one costs nothing but a refetch.

Design (inherited from tempo-cli): loaded once per process, writes flush under an
`fcntl.flock` so concurrent invocations don't lose each other's updates. Directory
0700 / files 0600 — the board and member names are mildly private.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from .config import home

CACHE_FILE = "cache.json"
BOARDS_FILE = "boards.json"

_state: dict[str, dict[str, Any] | None] = {CACHE_FILE: None, BOARDS_FILE: None}


def _path(name: str) -> Path:
    return home() / name


def _load(name: str) -> dict[str, Any]:
    cached = _state.get(name)
    if cached is not None:
        return cached
    f = _path(name)
    data: dict[str, Any]
    try:
        parsed = json.loads(f.read_text(encoding="utf-8"))
        data = parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    _state[name] = data
    return data


def _flush(name: str) -> None:
    data = _state.get(name)
    assert data is not None
    d = home()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass  # best-effort; non-fatal if the FS doesn't support it
    lock_fd = os.open(str(d / ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        tmp = _path(name).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(_path(name))
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def reset_for_tests() -> None:
    """Drop the in-process copies and force the next access to re-read from disk."""
    for k in _state:
        _state[k] = None


# --- boards.json -------------------------------------------------------------

def get_boards() -> tuple[list[dict[str, Any]], float]:
    """Return (boards, age_seconds). Age is `inf` when nothing is cached yet."""
    data = _load(BOARDS_FILE)
    boards = data.get("boards")
    if not isinstance(boards, list):
        return [], float("inf")
    fetched_at = data.get("fetchedAt")
    age = time.time() - fetched_at if isinstance(fetched_at, int | float) else float("inf")
    return boards, age


def put_boards(boards: list[dict[str, Any]]) -> None:
    _state[BOARDS_FILE] = {"fetchedAt": time.time(), "boards": boards}
    _flush(BOARDS_FILE)


# --- cache.json (per-board name→id maps) -------------------------------------

def get_board_map(board_id: str, kind: str) -> dict[str, Any] | None:
    """`kind` is one of lists / labels / members / fields."""
    board = _load(CACHE_FILE).get(board_id)
    if not isinstance(board, dict):
        return None
    entry = board.get(kind)
    return entry if isinstance(entry, dict) else None


def put_board_map(board_id: str, kind: str, value: dict[str, Any]) -> None:
    data = _load(CACHE_FILE)
    board = data.get(board_id)
    if not isinstance(board, dict):
        board = {}
        data[board_id] = board
    board[kind] = value
    _flush(CACHE_FILE)


def clear() -> None:
    """Drop every cached lookup. Credentials and the default board are untouched."""
    for name in (CACHE_FILE, BOARDS_FILE):
        _state[name] = {}
        f = _path(name)
        if f.exists():
            f.unlink()

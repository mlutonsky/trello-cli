"""Credentials and the tool's home directory.

Design rule (deliberate): the ONLY file a human ever edits is `~/.trello/credentials`.
Everything derivable from the API — the board list above all — is cache the tool fills
in by itself, never configuration someone has to assemble by hand.

`credentials` is a shell-sourceable `KEY=value` file, the same format the older
`~/.config/clubspire-trello/credentials` used, so it can simply be copied over.
Environment variables of the same name win over the file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import ConfigError

DEFAULT_HOME = "~/.trello"
CREDENTIALS_FILE = "credentials"
DEFAULT_BOARD_FILE = "default"

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def home() -> Path:
    """The tool's home directory. `TRELLO_HOME` overrides; default `~/.trello`."""
    raw = os.environ.get("TRELLO_HOME") or DEFAULT_HOME
    return Path(raw).expanduser()


def _strip_quotes(value: str) -> str:
    value = value.strip()
    # Drop a trailing comment only when the value is not quoted — `KEY=abc # note`.
    if value[:1] not in {'"', "'"}:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_credentials_file() -> dict[str, str]:
    """Parse `~/.trello/credentials`. Missing file is not an error — env may supply everything."""
    path = home() / CREDENTIALS_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(1)] = _strip_quotes(m.group(2))
    return out


def _setting(name: str) -> str | None:
    env = os.environ.get(name)
    if env:
        return env
    return read_credentials_file().get(name) or None


def api_key() -> str:
    key = _setting("TRELLO_API_KEY")
    if not key:
        raise ConfigError(
            f"TRELLO_API_KEY is not set (looked in the environment and {home() / CREDENTIALS_FILE})"
        )
    return key


def token() -> str:
    tok = _setting("TRELLO_TOKEN")
    if not tok:
        raise ConfigError(
            f"TRELLO_TOKEN is not set (looked in the environment and {home() / CREDENTIALS_FILE})"
        )
    return tok


def default_board() -> str | None:
    """The board used when `--board` is omitted.

    `~/.trello/default` (written by `trello use`) wins over `TRELLO_BOARD_ID`, so
    switching boards never means editing the credentials file.
    """
    path = home() / DEFAULT_BOARD_FILE
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    return _setting("TRELLO_BOARD_ID")


def set_default_board(value: str) -> Path:
    d = home()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    path = d / DEFAULT_BOARD_FILE
    path.write_text(value + "\n", encoding="utf-8")
    return path

"""Append-only audit log for writes.

Every POST/PUT/DELETE the CLI issues lands in `~/.trello/audit.log`, so a human can
reconstruct what the tool — or the agent driving it — actually did to a board.

Format: one JSON object per line, fields:
  ts       — ISO-8601 UTC timestamp
  command  — logical action, e.g. "card.move" / "comment.add"
  method   — HTTP verb
  path     — Trello API path
  body     — request parameters, or null
  dryRun   — true iff the write was suppressed
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import home

_MAX_BYTES = 5 * 1024 * 1024  # rotate at 5 MiB


def _log_file() -> Path:
    return home() / "audit.log"


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.stat().st_size >= _MAX_BYTES:
            path.rename(path.with_suffix(".log.1"))
    except FileNotFoundError:
        pass


def record(
    *,
    command: str,
    method: str,
    path: str,
    body: Any | None = None,
    dry_run: bool = False,
) -> None:
    """Append one entry. Never raises — an unwritable log must not fail a Trello write."""
    entry = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "command": command,
        "method": method,
        "path": path,
        "body": body,
        "dryRun": dry_run,
    }
    try:
        d = home()
        d.mkdir(parents=True, exist_ok=True)
        f = _log_file()
        _rotate_if_needed(f)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass

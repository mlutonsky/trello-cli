"""Helpers shared by the command modules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .. import audit, resolve
from ..client import TrelloClient, serialise
from ..errors import InputError
from ..output import emit
from ..state import state


def client() -> TrelloClient:
    return TrelloClient()


def board(c: TrelloClient, raw: str | None = None) -> str:
    return resolve.board_id(c, raw)


def read_text(value: str | None) -> str | None:
    """Accept literal text, `@path/to/file`, or `-` for stdin.

    Long Markdown with backticks and newlines is the normal case for card descriptions
    and comments, and quoting it through a shell is where agent calls break.
    """
    if value is None:
        return None
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InputError(f"cannot read {path}: {exc}") from exc
    return value


def write(
    c: TrelloClient,
    *,
    command: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    """Audit, honour `--dry-run`, then perform the write.

    On `--dry-run` nothing is sent: the request is queued for `ok()` to print, and the
    return value is a placeholder whose `id` stands in for the object the request would
    create. Follow-up writes that use that id are planned too.
    """
    body = json_body if json_body is not None else serialise(params)
    audit.record(
        command=command, method=method, path=path, body=body, dry_run=state.dry_run
    )
    if state.dry_run:
        state.planned.append(
            {"dryRun": True, "command": command, "would": {"method": method, "path": path, "body": body}}
        )
        return {"id": f"<{command} id>"}
    response = c.request(method, path, params=params, json_body=json_body, files=files)
    try:
        return response.json()
    except ValueError:
        return {}


def ok(data: Any, message: str) -> None:
    """Emit a write confirmation: one line for humans, the API payload for `--json`.

    On `--dry-run` it prints the planned requests instead: one JSON object for a single
    request, a list for several.
    """
    if state.dry_run:
        planned = state.planned
        emit(
            planned[0] if len(planned) == 1 else planned,
            lambda: "\n".join(
                f"dry-run · {p['command']} · {p['would']['method']} {p['would']['path']}\n{p['would']['body']}"
                for p in planned
            ),
        )
        return
    emit(data, message)

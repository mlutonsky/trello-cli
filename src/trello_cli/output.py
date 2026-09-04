"""The output contract.

- Success on stdout: compact Markdown by default, JSON when `--json` is passed.
  Markdown is the default because Trello content is prose — descriptions, comments,
  checklists — where JSON roughly doubles the token count and reads worse.
- Errors always go to stderr as `{"error": {...}}` with a non-zero exit, whatever the
  output format is, and stdout stays empty. One shape to handle, always.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from .errors import TrelloCliError
from .state import state


def emit_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=_default)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def emit(data: Any, markdown: Callable[[], str] | str | None = None) -> None:
    """Emit `data` as JSON, or its Markdown rendering when that is the active format.

    `markdown` is a callable so a renderer is never run for `--json` output.
    """
    if state.json_output or markdown is None:
        emit_json(data)
        return
    text = markdown() if callable(markdown) else markdown
    sys.stdout.write(text.rstrip("\n") + "\n")
    sys.stdout.flush()


def emit_error(err: TrelloCliError | Exception, *, exit_code: int = 1) -> None:
    if isinstance(err, TrelloCliError):
        payload = {"error": err.to_dict()}
    else:
        payload = {"error": {"code": "internal_error", "message": str(err)}}
    json.dump(payload, sys.stderr, ensure_ascii=False, indent=2, default=_default)
    sys.stderr.write("\n")
    sys.stderr.flush()
    raise SystemExit(exit_code)

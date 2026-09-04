"""Self-documentation and environment checks."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from .. import config, resolve
from ..errors import TrelloCliError
from ..output import emit
from ._common import client


def agent_guide() -> None:
    """Print the agent-facing reference guide bundled with the tool."""
    try:
        bundled = resources.files("trello_cli").joinpath("CLAUDE.md")
        if bundled.is_file():
            emit(
                {"path": str(bundled), "content": bundled.read_text(encoding="utf-8")},
                lambda: bundled.read_text(encoding="utf-8"),
            )
            return
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    # Editable install: fall back to the repo root.
    repo_path = Path(__file__).resolve().parents[3] / "CLAUDE.md"
    text = repo_path.read_text(encoding="utf-8")
    emit({"path": str(repo_path), "content": text}, lambda: text)


def doctor() -> None:
    """Check credentials, token scope and board access."""
    report: dict[str, Any] = {"home": str(config.home()), "checks": []}

    def check(name: str, ok_: bool, detail: str) -> None:
        report["checks"].append({"check": name, "ok": ok_, "detail": detail})

    try:
        config.api_key()
        check("api_key", True, "present")
    except TrelloCliError as exc:
        check("api_key", False, exc.message)
    try:
        token = config.token()
        check("token", True, "present")
    except TrelloCliError as exc:
        check("token", False, exc.message)
        token = None

    if token:
        try:
            with client() as c:
                info = c.get(f"/tokens/{token}", fields="dateExpires,permissions,idMember")
                perms = info.get("permissions") or []
                scopes = ",".join(
                    f"{p.get('modelType')}:{'w' if p.get('write') else 'r'}" for p in perms
                )
                check("token_scope", True, scopes or "no scopes reported")
                check("token_expiry", True, str(info.get("dateExpires") or "never"))

                me = c.get("/members/me", fields="username,fullName")
                check("account", True, f"@{me.get('username')} ({me.get('fullName')})")

                boards = resolve.boards(c)
                check("boards", bool(boards), f"{len(boards)} visible")

                default = config.default_board()
                if default:
                    try:
                        check("default_board", True, resolve.board_id(c, default))
                    except TrelloCliError as exc:
                        check("default_board", False, exc.message)
                else:
                    check(
                        "default_board",
                        False,
                        "not set — run `trello use <board>` or set TRELLO_BOARD_ID",
                    )
                check(
                    "rate_limit",
                    True,
                    f"{c._remaining if c._remaining is not None else '?'} requests left this window",
                )
        except TrelloCliError as exc:
            check("api", False, exc.message)

    report["ok"] = all(c["ok"] for c in report["checks"])

    def md() -> str:
        lines = [f"home: {report['home']}"]
        for item in report["checks"]:
            mark = "ok  " if item["ok"] else "FAIL"
            lines.append(f"[{mark}] {item['check']}: {item['detail']}")
        return "\n".join(lines)

    emit(report, md)

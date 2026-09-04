"""Board reference data — the lookups an agent needs before it can do anything else."""

from __future__ import annotations

import typer

from .. import cache, config, resolve
from ..output import emit
from ..state import state
from ._common import board, client

app = typer.Typer(no_args_is_help=True)


def whoami() -> None:
    """Show the account the current token belongs to."""
    with client() as c:
        me = c.get("/members/me", fields="id,username,fullName,email")
    emit(me, lambda: f"@{me.get('username')} · {me.get('fullName')} · {me.get('id')}")


def boards(
    refresh: bool = typer.Option(False, "--refresh", help="Refetch instead of using the cache."),
) -> None:
    """List the boards this account can see."""
    with client() as c:
        items = resolve.boards(c, refresh=refresh)
    current = config.default_board()

    def md() -> str:
        if not items:
            return "_(no boards)_"
        lines = []
        for b in items:
            mark = " ←default" if current in {b.get("id"), b.get("shortLink"), b.get("name")} else ""
            lines.append(f"[{b.get('shortLink')}] {b.get('name')}{mark}")
        return "\n".join(lines)

    emit(items, md)


def lists() -> None:
    """List the board's columns."""
    with client() as c:
        b = board(c)
        items = resolve.lists(c, b, refresh=state.refresh)
    emit(
        items,
        lambda: "\n".join(
            f"{i.get('name')}" + (" (archived)" if i.get("closed") else "") for i in items
        )
        or "_(no lists)_",
    )


def members() -> None:
    """List the board's members."""
    with client() as c:
        b = board(c)
        items = resolve.members(c, b, refresh=state.refresh)
    emit(
        items,
        lambda: "\n".join(f"@{m.get('username')} · {m.get('fullName')}" for m in items)
        or "_(no members)_",
    )


def labels() -> None:
    """List the board's labels."""
    with client() as c:
        b = board(c)
        items = resolve.labels(c, b, refresh=state.refresh)
    emit(
        items,
        lambda: "\n".join(
            f"{lab.get('name') or '(unnamed)'} · {lab.get('color') or 'no colour'}" for lab in items
        )
        or "_(no labels)_",
    )


def fields() -> None:
    """List the board's custom field definitions."""
    with client() as c:
        b = board(c)
        items = resolve.custom_fields(c, b, refresh=state.refresh)

    def md() -> str:
        if not items:
            return "_(no custom fields)_"
        out = []
        for f in items:
            line = f"{f.get('name')} · {f.get('type')}"
            options = (f.get("options") or []) if f.get("type") == "list" else []
            if options:
                values = ", ".join(str((o.get("value") or {}).get("text")) for o in options)
                line += f" · options: {values}"
            out.append(line)
        return "\n".join(out)

    emit(items, md)


def use(
    target: str = typer.Argument(..., help="Board id, shortLink, URL or name."),
) -> None:
    """Set the default board used when --board is omitted."""
    with client() as c:
        b = resolve.board_id(c, target)
        known = {x.get("id"): x for x in resolve.boards(c)}
        known.update({x.get("shortLink"): x for x in resolve.boards(c)})
    path = config.set_default_board(b)
    name = (known.get(b) or {}).get("name", b)
    emit({"board": b, "name": name, "path": str(path)}, f"default board → {name} [{b}]")


def clear_cache() -> None:
    """Drop every cached lookup (boards, lists, labels, members, fields)."""
    cache.clear()
    emit({"cleared": True}, "cache cleared")

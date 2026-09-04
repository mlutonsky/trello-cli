"""Board columns."""

from __future__ import annotations

import typer

from .. import resolve
from ._common import board, client, ok, write

app = typer.Typer(no_args_is_help=True, help="Create and archive board columns.")


@app.command("create")
def create(
    name: str = typer.Option(..., "--name", help="Column name."),
    pos: str = typer.Option("bottom", "--pos", help="top, bottom or a number."),
) -> None:
    """Create a column on the board."""
    with client() as c:
        b = board(c)
        created = write(
            c,
            command="list.create",
            method="POST",
            path="/lists",
            params={"name": name, "idBoard": b, "pos": pos},
        )
    ok(created, f"created column {created.get('name')}")


@app.command("archive")
def archive(
    column: str = typer.Argument(..., help="Column name or id."),
) -> None:
    """Archive a column. Trello has no delete for lists — archiving is the only removal."""
    with client() as c:
        b = board(c)
        lid = resolve.list_id(c, b, column)
        changed = write(
            c, command="list.archive", method="PUT", path=f"/lists/{lid}", params={"closed": True}
        )
    ok(changed, f"archived column {changed.get('name')}")

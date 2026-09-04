"""Card comments."""

from __future__ import annotations

import typer

from .. import render, resolve
from ..output import emit
from ._common import client, ok, read_text, write

app = typer.Typer(no_args_is_help=True, help="Read and write card comments.")


@app.command("list")
def list_comments(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum comments to return."),
) -> None:
    """List a card's comments, newest first, with the ids needed to edit them."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        actions = c.get(
            f"/cards/{cid}/actions",
            filter="commentCard",
            limit=min(max(limit, 1), 1000),
            memberCreator=True,
            member_fields="username,fullName",
        )
    emit(actions, lambda: "\n".join(render.comments(actions)) or "_(no comments)_")


@app.command("add")
def add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    text: str = typer.Argument(..., help="Comment text; `@file` or `-` for stdin."),
) -> None:
    """Add a comment to a card."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        action = write(
            c,
            command="comment.add",
            method="POST",
            path=f"/cards/{cid}/actions/comments",
            params={"text": read_text(text)},
        )
    ok(action, f"comment added ({action.get('id')})")


@app.command("edit")
def edit(
    action_id: str = typer.Argument(..., help="Comment id, from `trello comment list`."),
    text: str = typer.Argument(..., help="Replacement text; `@file` or `-` for stdin."),
) -> None:
    """Edit a comment. Trello only allows editing your own comments."""
    with client() as c:
        action = write(
            c,
            command="comment.edit",
            method="PUT",
            path=f"/actions/{action_id}",
            params={"text": read_text(text)},
        )
    ok(action, f"comment edited ({action_id})")


@app.command("rm")
def remove(
    action_id: str = typer.Argument(..., help="Comment id, from `trello comment list`."),
    yes: bool = typer.Option(False, "--yes", help="Required — deleting a comment is permanent."),
) -> None:
    """Delete a comment permanently."""
    if not yes:
        from ..errors import InputError

        raise InputError("deleting a comment cannot be undone — pass --yes to confirm")
    with client() as c:
        write(c, command="comment.rm", method="DELETE", path=f"/actions/{action_id}")
    ok({"deleted": action_id}, f"comment deleted ({action_id})")

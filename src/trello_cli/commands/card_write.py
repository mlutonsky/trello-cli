"""Creating and changing cards."""

from __future__ import annotations

from typing import Any

import typer

from .. import resolve
from ..errors import InputError
from ._common import board, client, ok, read_text, write


def create(
    name: str = typer.Option(..., "--name", help="Card title."),
    column: str = typer.Option(..., "--list", "-l", help="Target column."),
    desc: str = typer.Option(None, "--desc", help="Description; `@file` or `-` for stdin."),
    label: list[str] = typer.Option(None, "--label", help="Label name or colour; repeatable."),
    member: list[str] = typer.Option(None, "--member", help="Username or id; repeatable."),
    due: str = typer.Option(None, "--due", help="Due date, e.g. 2026-09-10 or an ISO timestamp."),
    start: str = typer.Option(None, "--start", help="Start date."),
    pos: str = typer.Option("bottom", "--pos", help="top, bottom or a number."),
    checklist: list[str] = typer.Option(
        None, "--checklist", help="'Name:item1,item2'; repeatable."
    ),
) -> None:
    """Create a card, with labels, members, dates and checklists in one go."""
    with client() as c:
        b = board(c)
        params: dict[str, Any] = {
            "idList": resolve.list_id(c, b, column),
            "name": name,
            "desc": read_text(desc),
            "due": due,
            "start": start,
            "pos": pos,
        }
        if label:
            params["idLabels"] = [resolve.label_id(c, b, x) for x in label]
        if member:
            params["idMembers"] = [resolve.member_id(c, b, x) for x in member]
        created = write(c, command="card.create", method="POST", path="/cards", params=params)

        for spec in checklist or []:
            title, _, items = spec.partition(":")
            cl = write(
                c,
                command="card.create.checklist",
                method="POST",
                path=f"/cards/{created['id']}/checklists",
                params={"name": title.strip() or "Checklist"},
            )
            for item in (i.strip() for i in items.split(",")):
                if item:
                    write(
                        c,
                        command="card.create.checkitem",
                        method="POST",
                        path=f"/checklists/{cl['id']}/checkItems",
                        params={"name": item},
                    )

    ok(created, f"created {created.get('shortUrl')} · {created.get('name')}")


def update(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    name: str = typer.Option(None, "--name", help="New title."),
    desc: str = typer.Option(None, "--desc", help="New description; `@file` or `-` for stdin."),
    due: str = typer.Option(None, "--due", help="Due date, or 'null' to clear it."),
    start: str = typer.Option(None, "--start", help="Start date, or 'null' to clear it."),
    done: bool = typer.Option(None, "--done/--undone", help="Mark the due date complete."),
) -> None:
    """Change a card's title, description or dates."""
    params: dict[str, Any] = {
        "name": name,
        "desc": read_text(desc),
        "due": due,
        "start": start,
        "dueComplete": done,
    }
    if all(v is None for v in params.values()):
        raise InputError("nothing to update — pass at least one of --name/--desc/--due/--start/--done")
    with client() as c:
        cid = resolve.card_id(c, identifier)
        card = write(c, command="card.update", method="PUT", path=f"/cards/{cid}", params=params)
    ok(card, f"updated {card.get('shortUrl')} · {card.get('name')}")


def move(
    identifiers: list[str] = typer.Argument(..., help="One or more cards."),
    column: str = typer.Option(..., "--list", "-l", help="Target column."),
    to_board: str = typer.Option(None, "--to-board", help="Move to a different board."),
    pos: str = typer.Option(None, "--pos", help="top, bottom or a number."),
) -> None:
    """Move cards to another column, optionally on another board."""
    moved = []
    warning = ""
    with client() as c:
        target_board = board(c, to_board) if to_board else board(c)
        params_base: dict[str, Any] = {"idList": resolve.list_id(c, target_board, column), "pos": pos}
        if to_board:
            # Trello needs both together; idBoard alone leaves the card without a valid list.
            params_base["idBoard"] = target_board
            warning = (
                "\nnote: a cross-board move silently drops labels, members and custom field "
                "values that do not exist on the target board"
            )
        for identifier in identifiers:
            cid = resolve.card_id(c, identifier)
            moved.append(
                write(
                    c,
                    command="card.move",
                    method="PUT",
                    path=f"/cards/{cid}",
                    params=dict(params_base),
                )
            )
    ok(
        moved,
        "\n".join(f"moved {m.get('name')} → {column}" for m in moved) + warning,
    )


def _set_closed(identifiers: list[str], closed: bool, verb: str) -> None:
    changed = []
    with client() as c:
        for identifier in identifiers:
            cid = resolve.card_id(c, identifier)
            changed.append(
                write(
                    c,
                    command=f"card.{verb}",
                    method="PUT",
                    path=f"/cards/{cid}",
                    params={"closed": closed},
                )
            )
    ok(changed, "\n".join(f"{verb}d {x.get('name')}" for x in changed))


def archive(
    identifiers: list[str] = typer.Argument(..., help="One or more cards."),
) -> None:
    """Archive cards. Reversible — this is the only removal the tool offers."""
    _set_closed(identifiers, True, "archive")


def unarchive(
    identifiers: list[str] = typer.Argument(..., help="One or more cards."),
) -> None:
    """Restore archived cards."""
    _set_closed(identifiers, False, "unarchive")


label_app = typer.Typer(no_args_is_help=True, help="Add or remove card labels.")
member_app = typer.Typer(no_args_is_help=True, help="Assign or unassign card members.")


@label_app.command("add")
def label_add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    labels: list[str] = typer.Argument(..., help="Label names or colours."),
) -> None:
    """Attach existing board labels to a card."""
    with client() as c:
        b = board(c)
        cid = resolve.card_id(c, identifier)
        for name in labels:
            # POST /cards/{id}/labels would create a NEW board label; idLabels attaches an existing one.
            write(
                c,
                command="card.label.add",
                method="POST",
                path=f"/cards/{cid}/idLabels",
                params={"value": resolve.label_id(c, b, name)},
            )
    ok({"card": cid, "labels": labels}, f"labels added: {', '.join(labels)}")


@label_app.command("rm")
def label_rm(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    labels: list[str] = typer.Argument(..., help="Label names or colours."),
) -> None:
    """Remove labels from a card."""
    with client() as c:
        b = board(c)
        cid = resolve.card_id(c, identifier)
        for name in labels:
            lid = resolve.label_id(c, b, name)
            write(
                c,
                command="card.label.rm",
                method="DELETE",
                path=f"/cards/{cid}/idLabels/{lid}",
            )
    ok({"card": cid, "labels": labels}, f"labels removed: {', '.join(labels)}")


@member_app.command("add")
def member_add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    people: list[str] = typer.Argument(..., help="Usernames, full names or ids."),
) -> None:
    """Assign members to a card."""
    with client() as c:
        b = board(c)
        cid = resolve.card_id(c, identifier)
        for person in people:
            write(
                c,
                command="card.member.add",
                method="POST",
                path=f"/cards/{cid}/idMembers",
                params={"value": resolve.member_id(c, b, person)},
            )
    ok({"card": cid, "members": people}, f"members added: {', '.join(people)}")


@member_app.command("rm")
def member_rm(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    people: list[str] = typer.Argument(..., help="Usernames, full names or ids."),
) -> None:
    """Unassign members from a card."""
    with client() as c:
        b = board(c)
        cid = resolve.card_id(c, identifier)
        for person in people:
            mid = resolve.member_id(c, b, person)
            write(
                c,
                command="card.member.rm",
                method="DELETE",
                path=f"/cards/{cid}/idMembers/{mid}",
            )
    ok({"card": cid, "members": people}, f"members removed: {', '.join(people)}")

"""Checklists and their items."""

from __future__ import annotations

from typing import Any

import typer

from .. import render, resolve
from ..errors import ResolutionError
from ..output import emit
from ._common import client, ok, write

app = typer.Typer(no_args_is_help=True, help="Read and write card checklists.")


def _checklists(c, card_id: str) -> list[dict[str, Any]]:
    return c.get(f"/cards/{card_id}/checklists", fields="id,name,pos", checkItem_fields="id,name,state,pos")


def _find_item(checklists: list[dict[str, Any]], needle: str) -> dict[str, Any]:
    items = [i for cl in checklists for i in (cl.get("checkItems") or [])]
    return resolve.match_by_name(items, needle, kind="check item")


@app.command("show")
def show(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
) -> None:
    """Show a card's checklists."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        checklists = _checklists(c, cid)
    emit(checklists, lambda: "\n".join(render.checklists(checklists)) or "_(no checklists)_")


@app.command("add")
def add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    name: str = typer.Option(..., "--name", help="Checklist name."),
    item: list[str] = typer.Option(None, "--item", help="Item to add; repeatable."),
) -> None:
    """Add a checklist to a card, optionally with its items."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        checklist = write(
            c,
            command="check.add",
            method="POST",
            path=f"/cards/{cid}/checklists",
            params={"name": name},
        )
        for entry in item or []:
            write(
                c,
                command="check.item.add",
                method="POST",
                path=f"/checklists/{checklist['id']}/checkItems",
                params={"name": entry},
            )
    ok(checklist, f"checklist '{name}' added with {len(item or [])} item(s)")


@app.command("item")
def item_add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    name: str = typer.Argument(..., help="Item text."),
    checklist: str = typer.Option(None, "--checklist", help="Which checklist (default: the only one)."),
) -> None:
    """Add an item to an existing checklist."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        lists = _checklists(c, cid)
        if checklist:
            target = resolve.match_by_name(lists, checklist, kind="checklist")
        elif len(lists) == 1:
            target = lists[0]
        else:
            raise ResolutionError(
                "the card has several checklists — pass --checklist",
                details={"checklists": [x.get("name") for x in lists]},
            )
        created = write(
            c,
            command="check.item.add",
            method="POST",
            path=f"/checklists/{target['id']}/checkItems",
            params={"name": name},
        )
    ok(created, f"added '{name}' to {target.get('name')}")


def _set_state(identifier: str, needle: str, state_value: str) -> None:
    with client() as c:
        cid = resolve.card_id(c, identifier)
        item = _find_item(_checklists(c, cid), needle)
        # The route is singular `checkItem` and carries no checklist segment.
        updated = write(
            c,
            command=f"check.{state_value}",
            method="PUT",
            path=f"/cards/{cid}/checkItem/{item['id']}",
            params={"state": state_value},
        )
    mark = "x" if state_value == "complete" else " "
    ok(updated, f"[{mark}] {item.get('name')}")


@app.command("tick")
def tick(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    item: str = typer.Argument(..., help="Item text (prefix or substring is enough)."),
) -> None:
    """Mark a checklist item complete."""
    _set_state(identifier, item, "complete")


@app.command("untick")
def untick(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    item: str = typer.Argument(..., help="Item text (prefix or substring is enough)."),
) -> None:
    """Mark a checklist item incomplete."""
    _set_state(identifier, item, "incomplete")

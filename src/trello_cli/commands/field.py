"""Custom fields (the first-party Power-Up)."""

from __future__ import annotations

from typing import Any

import typer

from .. import render, resolve
from ..errors import InputError
from ..output import emit
from ._common import board, client, ok, write

app = typer.Typer(no_args_is_help=True, help="Read and write card custom fields.")


def _body(definition: dict[str, Any], raw: str | None) -> dict[str, Any]:
    """Build the PUT body. `list` fields take an option id, everything else a typed value."""
    kind = definition.get("type")
    if raw is None:  # clearing
        return {"idValue": ""} if kind == "list" else {"value": ""}
    if kind == "list":
        options = definition.get("options") or []
        match = resolve.match_by_name(
            [{"name": (o.get("value") or {}).get("text"), "id": o.get("id")} for o in options],
            raw,
            kind="option",
        )
        return {"idValue": match["id"]}
    if kind == "checkbox":
        return {"value": {"checked": raw.strip().lower() in {"1", "true", "yes", "on"}}}
    if kind == "number":
        # Trello wants the number as a string, oddly enough.
        return {"value": {"number": str(raw).strip()}}
    if kind == "date":
        return {"value": {"date": raw}}
    return {"value": {"text": raw}}


@app.command("show")
def show(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
) -> None:
    """Show a card's custom field values."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        card = c.get(f"/cards/{cid}", fields="idBoard", customFieldItems=True)
        definitions = resolve.custom_fields(c, card["idBoard"])
    by_id = {d.get("id"): d for d in definitions}
    items = card.get("customFieldItems") or []

    def md() -> str:
        if not items:
            return "_(no custom field values set)_"
        return "\n".join(
            f"{(by_id.get(i.get('idCustomField')) or {}).get('name')}: "
            f"{render.custom_field_value(i, by_id.get(i.get('idCustomField')) or {})}"
            for i in items
        )

    emit(items, md)


@app.command("set")
def set_value(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    name: str = typer.Argument(..., help="Custom field name."),
    value: str = typer.Argument(None, help="The value; omit with --clear."),
    clear: bool = typer.Option(False, "--clear", help="Clear the field instead of setting it."),
) -> None:
    """Set or clear a custom field on a card."""
    if value is None and not clear:
        raise InputError("give a value, or pass --clear")
    with client() as c:
        b = board(c)
        cid = resolve.card_id(c, identifier)
        definition = resolve.custom_field(c, b, name)
        body = _body(definition, None if clear else value)
        write(
            c,
            command="field.set",
            method="PUT",
            path=f"/cards/{cid}/customField/{definition['id']}/item",
            json_body=body,
        )
    shown = "(cleared)" if clear else value
    ok({"card": cid, "field": definition.get("name"), "value": shown}, f"{definition.get('name')}: {shown}")

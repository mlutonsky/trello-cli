"""Read commands. `card` is the important one — the whole card in a single request."""

from __future__ import annotations

from typing import Any

import typer

from .. import render, resolve
from ..output import emit
from ._common import board, client

CARD_FIELDS = "all"
ATTACHMENT_FIELDS = "id,name,url,bytes,mimeType,isUpload,date"
LIST_CARD_FIELDS = "id,idShort,shortLink,name,labels,due,dueComplete,badges,closed"


def card(
    identifier: str = typer.Argument(..., help="Card id, shortLink, trello.com URL or #number."),
    comments: int = typer.Option(10, "--comments", "-c", help="How many comments to show."),
    full: bool = typer.Option(False, "--full", help="Show every comment."),
    no_comments: bool = typer.Option(False, "--no-comments", help="Skip comments entirely."),
) -> None:
    """Show a card in full: description, checklists, custom fields, attachments, comments."""
    limit = 0 if no_comments else (1000 if full else max(comments, 0))
    with client() as c:
        cid = resolve.card_id(c, identifier)
        params: dict[str, Any] = {
            "fields": CARD_FIELDS,
            "attachments": True,
            "attachment_fields": ATTACHMENT_FIELDS,
            "checklists": "all",  # a string enum, not a boolean
            "checklist_fields": "all",
            "members": True,
            "member_fields": "username,fullName",
            "customFieldItems": True,
            "board": True,
            "board_fields": "name",
            "list": True,
        }
        if limit:
            params.update(
                {
                    "actions": "commentCard",
                    "actions_limit": min(limit, 1000),
                    "action_fields": "id,date,data,type",
                    "action_memberCreator_fields": "username,fullName",
                }
            )
        data = c.get(f"/cards/{cid}", **params)
        definitions = (
            resolve.custom_fields(c, data.get("idBoard", "")) if data.get("customFieldItems") else []
        )

    actions = [a for a in (data.get("actions") or []) if a.get("type") == "commentCard"]
    total = (data.get("badges") or {}).get("comments")
    emit(
        data,
        lambda: render.card_context(
            data,
            board_name=(data.get("board") or {}).get("name", ""),
            list_name=(data.get("list") or {}).get("name", ""),
            comment_actions=actions,
            comment_total=total,
            field_definitions=definitions,
        ),
    )


def cards(
    column: str = typer.Argument(..., help="List/column name on the board."),
    archived: bool = typer.Option(False, "--archived", help="Show archived cards instead."),
) -> None:
    """List the cards in one column."""
    with client() as c:
        b = board(c)
        lid = resolve.list_id(c, b, column)
        items = c.get(
            f"/lists/{lid}/cards",
            fields=LIST_CARD_FIELDS,
            members=True,
            member_fields="username",
            filter="closed" if archived else "open",
        )
    emit(items, lambda: render.cards(items, title=column))


def snapshot(
    limit: int = typer.Option(0, "--limit", "-n", help="Cards per column (0 = all)."),
) -> None:
    """Show the whole board as columns and their cards — orientation in one request."""
    with client() as c:
        b = board(c)
        columns = c.get(
            f"/boards/{b}/lists",
            fields="id,name",
            cards="open",
            card_fields=LIST_CARD_FIELDS,
        )

    def md() -> str:
        out: list[str] = []
        for col in columns:
            items = col.get("cards") or []
            shown = items[:limit] if limit else items
            out.append(f"## {col.get('name')} ({len(items)})")
            out.extend(render.card_line(x) for x in shown)
            if len(items) > len(shown):
                out.append(f"… {len(items) - len(shown)} more")
            out.append("")
        return "\n".join(out).rstrip() or "_(empty board)_"

    emit(columns, md)


def search(
    query: str = typer.Argument(..., help="Trello search query, e.g. 'export label:bug is:open'."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum cards to return."),
    all_boards: bool = typer.Option(False, "--all-boards", help="Search every board, not just the current one."),
) -> None:
    """Search cards. Supports Trello's operators: label:, list:, @me, due:week, is:open, sort:due."""
    with client() as c:
        params: dict[str, Any] = {
            "query": query,
            "modelTypes": "cards",
            "cards_limit": min(max(limit, 1), 1000),
            "card_fields": LIST_CARD_FIELDS,
            "card_board": True,
            "card_list": True,
            "partial": True,
        }
        if not all_boards:
            params["idBoards"] = board(c)
        # The OpenAPI spec claims an array here; the API really returns an object.
        result = c.get("/search", **params)
    items = result.get("cards", []) if isinstance(result, dict) else []

    def md() -> str:
        if not items:
            return "_(no matches)_"
        out = []
        for item in items:
            place = " › ".join(
                p
                for p in (
                    (item.get("board") or {}).get("name", ""),
                    (item.get("list") or {}).get("name", ""),
                )
                if p
            )
            out.append(render.card_line(item) + (f" · {place}" if place else ""))
        return "\n".join(out)

    emit(items, md)


def mine(
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum cards to return."),
) -> None:
    """List the cards assigned to me across all boards."""
    with client() as c:
        items = c.get("/members/me/cards", fields=LIST_CARD_FIELDS + ",idBoard")[:limit]
        names = {b.get("id"): b.get("name") for b in resolve.boards(c)}

    def md() -> str:
        if not items:
            return "_(no cards assigned)_"
        return "\n".join(
            render.card_line(x) + (f" · {names[x['idBoard']]}" if names.get(x.get("idBoard")) else "")
            for x in items
        )

    emit(items, md)


def history(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    limit: int = typer.Option(30, "--limit", "-n", help="Maximum actions to return."),
    moves: bool = typer.Option(False, "--moves", help="Only column-to-column moves."),
) -> None:
    """Show a card's history — who changed what, and when."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        actions = c.get(
            f"/cards/{cid}/actions",
            filter="updateCard:idList" if moves else "all",
            limit=min(max(limit, 1), 1000),
            memberCreator=True,
            member_fields="username",
        )

    def md() -> str:
        if not actions:
            return "_(no history)_"
        out = []
        for a in actions:
            who = (a.get("memberCreator") or {}).get("username") or "?"
            data = a.get("data") or {}
            what = a.get("type", "")
            before, after = data.get("listBefore"), data.get("listAfter")
            if before and after:
                what = f"moved {before.get('name')} → {after.get('name')}"
            elif what == "commentCard":
                what = f"commented: {(data.get('text') or '')[:80]}"
            elif what == "updateCard" and "closed" in (data.get("old") or {}):
                what = "unarchived" if data.get("old", {}).get("closed") else "archived"
            out.append(f"[{render.date(a.get('date'), with_time=True)}] {who}: {what}")
        return "\n".join(out)

    emit(actions, md)

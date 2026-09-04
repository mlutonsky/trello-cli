"""Turning whatever the caller typed into Trello ids.

The point of this module is that an agent should never have to chain a lookup request
just to obtain an id. Cards accept a full id, an 8-character shortLink, a pasted
trello.com URL or `#87`; boards, lists, labels, members and custom fields accept a
name. Everything derivable is cached, and a cache miss re-fetches instead of failing.
"""

from __future__ import annotations

import re
from typing import Any

from . import cache
from .client import TrelloClient
from .config import default_board
from .errors import InputError, ResolutionError
from .state import state

BOARDS_TTL = 24 * 60 * 60  # seconds

_FULL_ID = re.compile(r"^[0-9a-fA-F]{24}$")
_SHORT_LINK = re.compile(r"^[0-9a-zA-Z]{8}$")
_CARD_URL = re.compile(r"trello\.com/c/([0-9a-zA-Z]{8})")
_BOARD_URL = re.compile(r"trello\.com/b/([0-9a-zA-Z]{24}|[0-9a-zA-Z]{8})")
_IDSHORT = re.compile(r"^#?(\d+)$")

BOARD_FIELDS = "id,name,shortLink,shortUrl,closed"


# --- generic name matching ---------------------------------------------------

def match_by_name(
    candidates: list[dict[str, Any]],
    needle: str,
    *,
    kind: str,
    key: str = "name",
) -> dict[str, Any]:
    """Exact match wins, then prefix, then substring. Ambiguity is an error, not a guess."""
    lowered = needle.strip().lower()
    if not lowered:
        raise InputError(f"empty {kind} name")

    def named(item: dict[str, Any]) -> str:
        return str(item.get(key) or "").strip().lower()

    for predicate in (
        lambda n: n == lowered,
        lambda n: n.startswith(lowered),
        lambda n: lowered in n,
    ):
        hits = [c for c in candidates if predicate(named(c))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ResolutionError(
                f"{kind} {needle!r} is ambiguous",
                details={"candidates": [c.get(key) for c in hits]},
            )
    raise ResolutionError(
        f"{kind} {needle!r} not found",
        details={"available": [c.get(key) for c in candidates]},
    )


# --- boards ------------------------------------------------------------------

def _fetch_boards(client: TrelloClient) -> list[dict[str, Any]]:
    boards = client.get("/members/me/boards", fields=BOARD_FIELDS, filter="open")
    cache.put_boards(boards)
    return boards


def boards(client: TrelloClient, *, refresh: bool = False) -> list[dict[str, Any]]:
    cached, age = cache.get_boards()
    if refresh or state.refresh or not cached or age > BOARDS_TTL:
        return _fetch_boards(client)
    return cached


def board_id(client: TrelloClient, raw: str | None = None) -> str:
    """Resolve a board reference. `None` falls back to `--board`, then the default board."""
    value = (raw or state.board or default_board() or "").strip()
    if not value:
        raise InputError(
            "no board given — pass --board, or set a default with `trello use <board>`"
        )
    if _FULL_ID.match(value):
        return value
    url_match = _BOARD_URL.search(value)
    if url_match:
        return url_match.group(1)
    if _SHORT_LINK.match(value):
        return value
    # A name: match against the cache, and refetch once before giving up.
    known = boards(client)
    try:
        return str(match_by_name(known, value, kind="board")["id"])
    except ResolutionError:
        if state.refresh:
            raise
        return str(match_by_name(_fetch_boards(client), value, kind="board")["id"])


# --- cards -------------------------------------------------------------------

def card_id(client: TrelloClient, raw: str) -> str:
    """Accept a full id, a shortLink, a card URL, or `#87` within the current board."""
    value = raw.strip()
    if not value:
        raise InputError("empty card identifier")
    url_match = _CARD_URL.search(value)
    if url_match:
        return url_match.group(1)
    if _FULL_ID.match(value) or _SHORT_LINK.match(value):
        return value
    short = _IDSHORT.match(value)
    if short:
        return _card_by_idshort(client, int(short.group(1)))
    raise InputError(
        f"{raw!r} is not a card id, shortLink, URL or #number",
        details={"hint": "pass the card URL if you have it — no lookup is needed for that"},
    )


def _card_by_idshort(client: TrelloClient, idshort: int) -> str:
    """`idShort` has no direct endpoint and Trello documents it as subject to change,
    so it is looked up live and never cached as a key."""
    board = board_id(client)
    cards = client.get(
        f"/boards/{board}/cards", fields="idShort,name,shortLink", filter="all"
    )
    for card in cards:
        if card.get("idShort") == idshort:
            return str(card.get("shortLink") or card.get("id"))
    raise ResolutionError(f"no card #{idshort} on this board", details={"board": board})


# --- per-board reference data ------------------------------------------------

def _board_collection(
    client: TrelloClient, board: str, kind: str, path: str, *, refresh: bool = False, **params: Any
) -> list[dict[str, Any]]:
    if not (refresh or state.refresh):
        cached = cache.get_board_map(board, kind)
        if cached and isinstance(cached.get("items"), list):
            return cached["items"]
    items = client.get(path, **params)
    cache.put_board_map(board, kind, {"items": items})
    return items


def lists(client: TrelloClient, board: str, *, refresh: bool = False) -> list[dict[str, Any]]:
    return _board_collection(
        client, board, "lists", f"/boards/{board}/lists",
        refresh=refresh, fields="id,name,pos,closed",
    )


def labels(client: TrelloClient, board: str, *, refresh: bool = False) -> list[dict[str, Any]]:
    return _board_collection(
        client, board, "labels", f"/boards/{board}/labels",
        refresh=refresh, fields="id,name,color", limit=1000,
    )


def members(client: TrelloClient, board: str, *, refresh: bool = False) -> list[dict[str, Any]]:
    return _board_collection(
        client, board, "members", f"/boards/{board}/members",
        refresh=refresh, fields="id,username,fullName",
    )


def custom_fields(
    client: TrelloClient, board: str, *, refresh: bool = False
) -> list[dict[str, Any]]:
    return _board_collection(
        client, board, "fields", f"/boards/{board}/customFields", refresh=refresh
    )


def _resolve_one(
    client: TrelloClient,
    board: str,
    value: str,
    *,
    kind: str,
    fetch,
    key: str = "name",
) -> dict[str, Any]:
    """Match `value` against a cached board collection, refetching once on a miss.

    The refetch is what makes the cache safe to be stale: a list renamed on the board
    resolves on the second try instead of erroring.
    """
    needle = value.strip()
    items = fetch(client, board)
    if _FULL_ID.match(needle):
        for item in items:
            if item.get("id") == needle:
                return item
        return {"id": needle}
    try:
        return match_by_name(items, needle, kind=kind, key=key)
    except ResolutionError:
        if state.refresh:
            raise  # the caller already forced a fresh fetch; the name really is absent
        return match_by_name(fetch(client, board, refresh=True), needle, kind=kind, key=key)


def list_id(client: TrelloClient, board: str, value: str) -> str:
    return str(_resolve_one(client, board, value, kind="list", fetch=lists)["id"])


def label_id(client: TrelloClient, board: str, value: str) -> str:
    """Labels are identified by name, or by colour when the name is blank."""
    needle = value.strip()
    if _FULL_ID.match(needle):
        return needle
    items = labels(client, board)
    named = [i for i in items if (i.get("name") or "").strip()]
    try:
        return str(match_by_name(named, needle, kind="label")["id"])
    except ResolutionError:
        return str(match_by_name(items, needle, kind="label", key="color")["id"])


def member_id(client: TrelloClient, board: str, value: str) -> str:
    """Card member endpoints take the 24-hex id — a username is never accepted."""
    needle = value.strip()
    if _FULL_ID.match(needle):
        return needle
    items = members(client, board)
    try:
        return str(match_by_name(items, needle, kind="member", key="username")["id"])
    except ResolutionError:
        return str(match_by_name(items, needle, kind="member", key="fullName")["id"])


def custom_field(client: TrelloClient, board: str, value: str) -> dict[str, Any]:
    return _resolve_one(client, board, value, kind="custom field", fetch=custom_fields)

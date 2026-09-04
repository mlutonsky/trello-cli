"""Markdown renderers.

This is where most of the tool's value sits: the same Trello payloads an agent would
otherwise dump as raw JSON, rendered so they cost a fraction of the tokens and read
like a card rather than like a data structure.

Section headings are English on purpose — the repo, the CLI and the agent-facing guide
are English; only the card's own content is passed through in whatever language it is.
"""

from __future__ import annotations

from typing import Any

MAX_DESC_PREVIEW = 160


def date(value: Any, *, with_time: bool = False) -> str:
    """Trim Trello's ISO timestamps to something readable. Unparseable values pass through."""
    if not value:
        return ""
    text = str(value)
    if len(text) >= 16 and text[10] in "T ":
        return text[:16].replace("T", " ") if with_time else text[:10]
    return text


def _size(num: Any) -> str:
    try:
        n = float(num)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def label_names(labels: list[dict[str, Any]] | None) -> str:
    """`bug(red), P1(orange)` — a nameless label shows as its colour alone."""
    out = []
    for lab in labels or []:
        name = (lab.get("name") or "").strip()
        color = (lab.get("color") or "").strip()
        if name and color:
            out.append(f"{name}({color})")
        else:
            out.append(name or color or "?")
    return ", ".join(out)


def member_names(members: list[dict[str, Any]] | None) -> str:
    return ", ".join(f"@{m.get('username') or m.get('fullName') or m.get('id')}" for m in members or [])


def _due(card: dict[str, Any]) -> str:
    if not card.get("due"):
        return ""
    stamp = date(card["due"])
    return f"due {stamp}" + (" ✓" if card.get("dueComplete") else "")


def card_line(card: dict[str, Any]) -> str:
    """One card on one line — the unit of every listing."""
    short = card.get("shortLink") or card.get("id") or ""
    parts = [f"#{card.get('idShort')}" if card.get("idShort") else "", f"[{short}]"]
    head = " ".join(p for p in parts if p)
    bits = [f"{head} {card.get('name', '')}".strip()]
    extras = [
        label_names(card.get("labels")),
        member_names(card.get("members")),
        _due(card),
    ]
    badges = card.get("badges") or {}
    counters = []
    if badges.get("comments"):
        counters.append(f"{badges['comments']}c")
    if badges.get("attachments"):
        counters.append(f"{badges['attachments']}a")
    if badges.get("checkItems"):
        counters.append(f"{badges.get('checkItemsChecked', 0)}/{badges['checkItems']}☑")
    if counters:
        extras.append(" ".join(counters))
    if card.get("closed"):
        extras.append("archived")
    tail = " · ".join(e for e in extras if e)
    return f"{bits[0]} · {tail}" if tail else bits[0]


def cards(items: list[dict[str, Any]], *, title: str | None = None) -> str:
    lines = [f"# {title}"] if title else []
    if not items:
        lines.append("_(no cards)_")
        return "\n".join(lines)
    lines.extend(card_line(c) for c in items)
    return "\n".join(lines)


def checklists(items: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for cl in items or []:
        items = cl.get("checkItems") or []
        done = sum(1 for i in items if i.get("state") == "complete")
        out.append(f"{cl.get('name')} ({done}/{len(items)})")
        for item in sorted(items, key=lambda i: i.get("pos") or 0):
            box = "x" if item.get("state") == "complete" else " "
            out.append(f"  [{box}] {item.get('name')}")
    return out


def _custom_fields(card: dict[str, Any], definitions: list[dict[str, Any]]) -> list[str]:
    """A card only returns fields that have a value, so we join against the board's definitions."""
    by_id = {d.get("id"): d for d in definitions}
    rendered: list[str] = []
    for item in card.get("customFieldItems") or []:
        definition = by_id.get(item.get("idCustomField")) or {}
        name = definition.get("name") or item.get("idCustomField")
        rendered.append(f"{name}: {custom_field_value(item, definition)}")
    return [" · ".join(rendered)] if rendered else []


def custom_field_value(item: dict[str, Any], definition: dict[str, Any]) -> str:
    """Unwrap `{"value": {"text": …}}` / `{"idValue": …}` into something printable."""
    if item.get("idValue"):
        options = (definition.get("options") or definition.get("display", {}).get("options") or [])
        for opt in options:
            if opt.get("id") == item["idValue"]:
                return str((opt.get("value") or {}).get("text") or opt.get("id"))
        return str(item["idValue"])
    value = item.get("value")
    if isinstance(value, dict):
        for key in ("text", "number", "checked", "date"):
            if key in value:
                raw = value[key]
                return date(raw) if key == "date" else str(raw)
    return "" if value is None else str(value)


def attachments(items: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for idx, att in enumerate(items or [], start=1):
        kind = "upload" if att.get("isUpload") else "link"
        meta = ", ".join(m for m in (att.get("mimeType") or "", _size(att.get("bytes"))) if m)
        label = att.get("name") or att.get("url") or att.get("id")
        suffix = f" — {meta} ({kind})" if meta else f" ({kind})"
        out.append(f"{idx}. {label}{suffix}")
    return out


def comments(actions: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for action in actions:
        who = (action.get("memberCreator") or {}).get("username") or "?"
        text = ((action.get("data") or {}).get("text") or "").strip()
        out.append(f"[{date(action.get('date'), with_time=True)}] {who} ({action.get('id')}):")
        out.extend(f"  {line}" for line in text.splitlines() or [""])
    return out


def card_context(
    card: dict[str, Any],
    *,
    board_name: str = "",
    list_name: str = "",
    comment_actions: list[dict[str, Any]] | None = None,
    comment_total: int | None = None,
    field_definitions: list[dict[str, Any]] | None = None,
) -> str:
    """The whole card in one block — description, checklists, fields, attachments, comments."""
    short = card.get("shortLink") or card.get("id") or ""
    header = " ".join(
        p for p in (f"#{card['idShort']}" if card.get("idShort") else "", card.get("name", ""), f"[{short}]") if p
    )
    lines = [header]

    place = " › ".join(p for p in (board_name, list_name) if p)
    context_bits = [place, label_names(card.get("labels")), member_names(card.get("members"))]
    if card.get("closed"):
        context_bits.append("**archived**")
    context = " · ".join(b for b in context_bits if b)
    if context:
        lines.append(context)

    tail = [_due(card)]
    if card.get("start"):
        tail.append(f"start {date(card['start'])}")
    if card.get("shortUrl"):
        tail.append(card["shortUrl"])
    tail_line = " · ".join(t for t in tail if t)
    if tail_line:
        lines.append(tail_line)

    desc = (card.get("desc") or "").strip()
    if desc:
        lines += ["", "## Description", desc]

    checklist_lines = checklists(card.get("checklists"))
    if checklist_lines:
        lines += ["", "## Checklists", *checklist_lines]

    fields = _custom_fields(card, field_definitions or [])
    if fields:
        lines += ["", "## Custom fields", *fields]

    attachment_lines = attachments(card.get("attachments"))
    if attachment_lines:
        lines += ["", f"## Attachments ({len(attachment_lines)})", *attachment_lines]

    shown = comment_actions or []
    if shown:
        total = comment_total if comment_total is not None else len(shown)
        counter = f"{len(shown)} of {total}" if total > len(shown) else str(total)
        lines += ["", f"## Comments ({counter}, newest first)", *comments(shown)]

    return "\n".join(lines)

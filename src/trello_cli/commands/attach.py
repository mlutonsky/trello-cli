"""Attachments — including the download route, which is the fiddly part."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import typer

from .. import audit, render, resolve
from ..errors import InputError
from ..output import emit
from ..state import state
from ._common import client, ok, write

app = typer.Typer(no_args_is_help=True, help="List, attach and download card attachments.")

ATTACHMENT_FIELDS = "id,name,url,bytes,mimeType,isUpload,date"


def _attachments(c, card_id: str) -> list[dict]:
    return c.get(f"/cards/{card_id}/attachments", fields=ATTACHMENT_FIELDS)


def _pick(items: list[dict], needle: str) -> dict:
    """Accept an attachment id, a 1-based position, or a name."""
    for item in items:
        if item.get("id") == needle:
            return item
    if needle.isdigit():
        index = int(needle)
        if 1 <= index <= len(items):
            return items[index - 1]
        raise InputError(f"no attachment #{index} (the card has {len(items)})")
    return resolve.match_by_name(items, needle, kind="attachment")


@app.command("ls")
def ls(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
) -> None:
    """List a card's attachments."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        items = _attachments(c, cid)
    emit(items, lambda: "\n".join(render.attachments(items)) or "_(no attachments)_")


@app.command("add")
def add(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    source: str = typer.Argument(..., help="A local file path, or an http(s) URL to link."),
    name: str = typer.Option(None, "--name", help="Display name for the attachment."),
    cover: bool = typer.Option(False, "--cover", help="Use the attachment as the card cover."),
) -> None:
    """Attach a local file (uploaded) or a URL (linked) to a card."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        path = f"/cards/{cid}/attachments"
        if source.startswith(("http://", "https://")):
            created = write(
                c,
                command="attach.add.url",
                method="POST",
                path=path,
                params={"url": source, "name": name, "setCover": cover},
            )
        else:
            file_path = Path(source).expanduser()
            if not file_path.is_file():
                raise InputError(f"{file_path} is not a file")
            if state.dry_run:
                # Do not read the file just to describe the request.
                created = write(
                    c,
                    command="attach.add.file",
                    method="POST",
                    path=path,
                    params={"name": name or file_path.name, "setCover": cover},
                )
            else:
                # A multipart upload cannot go through `write()`, so audit it here.
                audit.record(
                    command="attach.add.file",
                    method="POST",
                    path=path,
                    body={"file": str(file_path), "name": name or file_path.name},
                )
                with file_path.open("rb") as fh:
                    created = c.upload(
                        path,
                        files={"file": (file_path.name, fh)},
                        name=name or file_path.name,
                        setCover=cover,
                    )
    ok(created, f"attached {created.get('name')} ({created.get('id')})")


@app.command("get")
def get(
    identifier: str = typer.Argument(..., help="Card id, shortLink, URL or #number."),
    which: str = typer.Argument(..., help="Attachment id, 1-based position, or name."),
    out: str = typer.Option(None, "--out", help="Directory to save into, or '-' for stdout."),
) -> None:
    """Download an attachment. Uploaded files need authentication; links are fetched as-is."""
    with client() as c:
        cid = resolve.card_id(c, identifier)
        item = _pick(_attachments(c, cid), which)
        if item.get("isUpload"):
            # `?key=&token=` does not work on this route — only the OAuth header does.
            filename = item.get("name") or item["id"]
            url = f"/cards/{cid}/attachments/{item['id']}/download/{quote(filename, safe='')}"
        else:
            url = item.get("url") or ""
        content, content_type = c.download(url)

    if out == "-":
        sys.stdout.buffer.write(content)
        sys.stdout.buffer.flush()
        return
    directory = Path(out).expanduser() if out else Path.cwd()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (item.get("name") or item["id"])
    target.write_bytes(content)
    emit(
        {"path": str(target), "bytes": len(content), "contentType": content_type},
        f"saved {target} ({len(content)} bytes)",
    )

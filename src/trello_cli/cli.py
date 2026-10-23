"""Command-line entry point."""

from __future__ import annotations

import typer
from typer.core import TyperGroup

from . import __version__
from .commands import attach, card_write, check, comment, field, list_, meta, read, reference
from .errors import TrelloCliError
from .output import emit, emit_error
from .state import state

_GLOBAL_FLAGS = frozenset({"--json", "--dry-run", "--refresh"})
_GLOBAL_VALUE_OPTIONS = frozenset({"--board", "-b"})


def _hoist_global_options(args: list[str]) -> list[str]:
    """Move the root options to the front, wherever they appear on the command line.

    Click parses an option only on the command that declares it, so without this
    `trello create … --dry-run` or `trello cards TODO -b office2000` fail with
    "No such option". Nothing after `--` is touched.
    """
    hoisted: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == "--":
            rest.extend(args[i:])
            break
        if token in _GLOBAL_FLAGS or token.startswith("--board="):
            hoisted.append(token)
        elif token in _GLOBAL_VALUE_OPTIONS and i + 1 < len(args):
            hoisted.extend(args[i : i + 2])
            i += 1
        else:
            rest.append(token)
        i += 1
    return hoisted + rest


class _GlobalOptionsGroup(TyperGroup):
    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        return super().parse_args(ctx, _hoist_global_options(args))


app = typer.Typer(
    name="trello",
    cls=_GlobalOptionsGroup,
    help=(
        "Markdown-first CLI over the Trello REST API, designed for LLM agents and humans. "
        "Credentials live in ~/.trello/credentials (TRELLO_API_KEY, TRELLO_TOKEN); "
        "everything else the tool discovers and caches by itself."
    ),
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of Markdown."),
    board: str = typer.Option(
        None, "--board", "-b", help="Board id, shortLink, URL or name. Overrides the default."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Describe writes without performing them."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Ignore cached lookups and refetch from the API."
    ),
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
) -> None:
    state.json_output = json_output
    state.board = board
    state.dry_run = dry_run
    state.refresh = refresh
    # Handled here rather than in an eager callback so that `--json --version` has
    # already seen `--json`; eager callbacks fire before the flags are recorded.
    if version:
        emit({"name": "trello-cli", "version": __version__}, f"trello-cli {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# Reading
app.command("card")(read.card)
app.command("cards")(read.cards)
app.command("snapshot")(read.snapshot)
app.command("search")(read.search)
app.command("mine")(read.mine)
app.command("history")(read.history)

# Reference data
app.command("boards")(reference.boards)
app.command("lists")(reference.lists)
app.command("members")(reference.members)
app.command("labels")(reference.labels)
app.command("fields")(reference.fields)
app.command("whoami")(reference.whoami)
app.command("use")(reference.use)
app.command("clear-cache")(reference.clear_cache)

# Writing
app.command("create")(card_write.create)
app.command("update")(card_write.update)
app.command("move")(card_write.move)
app.command("archive")(card_write.archive)
app.command("unarchive")(card_write.unarchive)
app.add_typer(card_write.label_app, name="label")
app.add_typer(card_write.member_app, name="member")
app.add_typer(comment.app, name="comment")
app.add_typer(attach.app, name="attach")
app.add_typer(check.app, name="check")
app.add_typer(field.app, name="field")
app.add_typer(list_.app, name="list")

# Meta
app.command("agent-guide")(meta.agent_guide)
app.command("doctor")(meta.doctor)


def main() -> None:
    """Run the CLI, funnelling every failure into the one JSON error envelope.

    `standalone_mode=False` stops Click from printing its own free-text
    "Usage: …/Error: …" and exiting, so usage errors reach the same envelope as
    everything else. Typer vendors Click, so the exceptions come from `typer`.
    """
    try:
        app(standalone_mode=False)
    except TrelloCliError as exc:
        emit_error(exc)
    except typer.Abort:
        raise SystemExit(130) from None
    except typer.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except typer.TyperException as exc:
        message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
        emit_error(TrelloCliError(message, details={"usage": True}), exit_code=2)
    except BrokenPipeError:
        raise SystemExit(0) from None

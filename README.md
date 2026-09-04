# trello-cli

A Markdown-first command-line wrapper around the Trello REST API, built for LLM agents
(and pleasant enough to use by hand).

The point is that an agent asked to "read that card and move it to done" should run two
commands, not assemble `curl` calls, chase 24-character ids, and paste a page of JSON into
its context. Reading a card returns a compact Markdown block roughly a twentieth the size
of the equivalent API payload.

```
$ trello card https://trello.com/c/6h3iK2mA/87-broken-export
#87 Broken order export [6h3iK2mA]
ClubSpire › TODO · bug(red) · @lutonsky
due 2026-09-10 · https://trello.com/c/6h3iK2mA

## Description
Steps to reproduce:
1. open the admin …

## Checklists
QA (1/3)
  [x] reproduce
  [ ] fix

## Attachments (1)
1. spec.pdf — application/pdf, 240.0 kB (upload)

## Comments (2 of 12, newest first)
[2026-09-01 10:14] lutonsky (6a3e82a8…): Reproduced on stage.
```

## Install

```bash
git clone git@github.com:mlutonsky/trello-cli.git ~/bin/trello-cli
uv tool install -e ~/bin/trello-cli
```

## Configure

One file, written by hand, and nothing else:

```bash
mkdir -p ~/.trello && chmod 700 ~/.trello
cat > ~/.trello/credentials <<'EOF'
TRELLO_API_KEY=...
TRELLO_TOKEN=...
EOF
chmod 600 ~/.trello/credentials
```

Get the key and token from <https://trello.com/power-ups/admin> (the token needs write
scope for anything beyond reading). Environment variables of the same name take priority,
so CI can supply them instead.

Then pick a default board — everything else the tool discovers for itself:

```bash
trello use "Clusbpire klienti"
trello doctor
```

There is deliberately no configuration file listing boards, lists or labels. Anything
derivable from the API is cached in `~/.trello/` and refreshed automatically; a stale
cache costs one extra request, never an error.

## Usage

```bash
trello snapshot                  # the whole board at a glance
trello card 6h3iK2mA             # one card, in full
trello search "export label:bug is:open"
trello create --name "Fix export" --list TODO --label bug --desc @/tmp/bug.md
trello comment add 6h3iK2mA -    # comment body from stdin
trello move 6h3iK2mA --list Hotovo
trello attach get 6h3iK2mA spec.pdf --out /tmp
```

Cards are accepted as a full id, an 8-character shortLink, a pasted `trello.com/c/…` URL,
or `#87`. Boards, lists, labels and members are accepted by name.

`--json` switches any command to the raw API payload. Errors are always JSON on stderr
with a non-zero exit, whatever the output format.

Writes are logged to `~/.trello/audit.log` and every write command takes `--dry-run`.

`trello agent-guide` prints the full reference intended for an LLM agent; `trello --help`
covers the rest.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
```

## License

MIT

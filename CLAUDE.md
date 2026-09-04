# trello-cli — agent guide

`trello` wraps the Trello REST API so an agent never has to hand-build `curl` calls,
parse raw JSON, or chain requests just to turn a name into an id.

## Contract

- **Stdout is Markdown by default**, compact and meant to be read straight into context.
  Pass `--json` for the raw API payload when you need to pipe into `jq`.
- **Errors are always JSON on stderr**, whatever the output format:
  `{"error": {"code": "...", "message": "...", "details": ...}}`, exit code non-zero,
  stdout empty. Codes: `config_error`, `resolution_error`, `input_error`,
  `trello_api_error` (carries `status`).
- Every command has `--help`.

## Identifiers — you never need a lookup call

Anywhere a **card** is expected, all of these work:

| Form | Example |
|---|---|
| full id | `5e839f3696a55979a932b3ad` |
| shortLink | `6h3iK2mA` |
| card URL | `https://trello.com/c/6h3iK2mA/87-broken-export` |
| board-local number | `#87` (needs a board; costs one lookup) |

Anywhere a **board** is expected (`--board/-b`): id, shortLink, board URL, or the board's
name (`-b office2000` matches "Office2000 vývoj"). Lists, labels, members and custom
fields are always given by **name** — `--list "Work in progress"`, `--label bug`,
`--member lutonsky`. Matching is case-insensitive, exact beats prefix beats substring, and
an ambiguous name is an error listing the candidates rather than a silent guess.

Omit `--board` to use the default board (`trello use <board>` sets it).

## Long text

`--desc` and comment text accept `@path/to/file` or `-` for stdin. Use them for anything
multi-line or containing backticks — do not fight shell quoting.

```bash
trello comment add 6h3iK2mA @/tmp/review.md
git log --oneline | trello comment add 6h3iK2mA -
```

## Safety

Writes are real. Every write is appended to `~/.trello/audit.log`. Every write command
accepts `--dry-run`, which prints the request it would send and exits.

**Use `--dry-run` first when** you inferred the target card from conversation rather than
being given it, when the user has not confirmed the exact column or board, or when moving
several cards at once.

Cards are never deleted — `archive` is reversible and is the only removal. `comment rm`
is permanent and therefore requires `--yes`.

## Command map

### Reading
- `trello card <card>` — **the one to reach for**: description, checklists, custom fields,
  attachments and comments in a single request. `--comments N` (default 10), `--full`,
  `--no-comments`. The comment header says `3 of 12` when output is truncated.
- `trello cards <column>` — one line per card in a column. `--archived` for archived ones.
- `trello snapshot` — the whole board, columns and cards. `-n` caps cards per column.
- `trello search "<query>"` — Trello's operators work: `label:bug`, `list:TODO`, `@me`,
  `has:attachments`, `due:week`, `is:open`, `sort:due`, `-` to negate. Scoped to the
  current board unless `--all-boards`.
- `trello mine` — cards assigned to me across boards.
- `trello history <card>` — who changed what. `--moves` for column-to-column moves only.

### Reference data
- `trello boards` · `trello lists` · `trello members` · `trello labels` · `trello fields`
- `trello whoami` · `trello use <board>` · `trello clear-cache`

### Writing
- `trello create --name "…" --list <column> [--desc @f] [--label …] [--member …] [--due …] [--pos top] [--checklist "QA:a,b"]`
- `trello update <card> [--name] [--desc] [--due] [--start] [--done/--undone]`
- `trello move <card>… --list <column> [--to-board <board>] [--pos top]`
- `trello archive <card>…` · `trello unarchive <card>…`
- `trello label add|rm <card> <label>…` · `trello member add|rm <card> <person>…`
- `trello comment list|add|edit|rm <card|comment-id> …`
- `trello attach ls|add|get <card> …`
- `trello check show|add|item|tick|untick <card> …`
- `trello field show|set <card> <name> <value>`
- `trello list create|archive`

## Recipes

```bash
# "What's on the board?"
trello -b clubspire snapshot -n 5

# "Read me that card" — the user pasted a URL
trello card https://trello.com/c/6h3iK2mA/87-broken-export

# "Find the card about the export bug"
trello search "export label:bug is:open"

# "Move it to done and say what I did"
trello comment add 6h3iK2mA @/tmp/summary.md
trello move 6h3iK2mA --list Hotovo

# "Read the spec attached to the card"
trello attach ls 6h3iK2mA
trello attach get 6h3iK2mA spec.pdf --out /tmp

# "Open a card for this bug"
trello create --name "Export drops VAT" --list TODO --label bug \
  --member lutonsky --desc @/tmp/bug.md --checklist "QA:reproduce,fix,verify"
```

## Failure modes

| Code / symptom | What it means, what to say |
|---|---|
| `config_error` | `TRELLO_API_KEY` / `TRELLO_TOKEN` missing. They belong in `~/.trello/credentials`. Run `trello doctor`. |
| `resolution_error` with `available` | The name does not exist on that board — the message lists what does. Pick from it; do not guess again. |
| `resolution_error` with `candidates` | Ambiguous; be more specific. |
| `trello_api_error` status 401/403 | The token lacks write scope or board access. Environmental — tell the user, do not retry. |
| `trello_api_error` status 429 | Rate limited despite the built-in backoff. Wait, then retry once. |
| A card "does not exist" | It is probably archived. Try `trello cards <column> --archived` or `search` with `-is:open`. |

## What this tool does not do

Webhooks; creating boards or organisations; deleting cards, boards or lists; Power-Up
`pluginData`; batch requests. Attachment uploads are capped by Trello at 10 MB on free
workspaces.

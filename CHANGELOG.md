# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-09-04

First release.

### Added

- `trello card` — a whole card in one request: description, checklists, custom fields,
  attachments and comments, rendered as Markdown roughly a twentieth the size of the
  equivalent API payload. Comments are truncated to the last 10 by default, and the
  heading says how many were left out.
- Reading: `cards`, `snapshot`, `search` (Trello's query operators), `mine`, `history`.
- Reference data: `boards`, `lists`, `members`, `labels`, `fields`, `whoami`.
- Writing: `create`, `update`, `move` (including across boards), `archive`, `unarchive`,
  `label add|rm`, `member add|rm`, `comment list|add|edit|rm`, `attach ls|add|get`,
  `check show|add|item|tick|untick`, `field show|set`, `list create|archive`.
- Cards are accepted as a full id, an 8-character shortLink, a pasted `trello.com/c/…`
  URL or `#87`. Boards, lists, labels, members and custom fields are accepted by name.
- Authenticated attachment downloads via Trello's `/download/` route, which stopped
  accepting `?key=&token=` in 2021 and needs the OAuth header.
- `--json` on every command, and a JSON error envelope on stderr in both formats.
- `--dry-run` on every write, plus an append-only audit log at `~/.trello/audit.log`.
- `agent-guide` and `doctor` for self-description and environment checks.
- A Claude Code `PreToolUse` hook that steers agents away from raw `curl` calls to the
  Trello API, with a `TRELLO_CLI_ALLOW_RAW=1` escape hatch.

### Notes

- Credentials are the only thing configured by hand, in `~/.trello/credentials`. Boards
  and per-board names are cached in `~/.trello/` and refreshed by the tool itself; a
  stale cache costs one extra request rather than an error.
- Cards are never deleted — `archive` is reversible and is the only removal offered.

[Unreleased]: https://github.com/mlutonsky/trello-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mlutonsky/trello-cli/releases/tag/v0.1.0

#!/usr/bin/env bash
# Claude Code PreToolUse hook: steer Bash calls away from the raw Trello API.
#
# Without this, an agent that does not know about `trello` reaches for curl, and we are
# back to hand-assembled API calls and pages of JSON in the context window.
#
# Register in ~/.claude/settings.json:
#   "hooks": { "PreToolUse": [ { "matcher": "Bash",
#     "hooks": [ { "type": "command", "command": "~/bin/trello-cli/hooks/block-raw-trello-api.sh" } ] } ] }
#
# Exit 0 = allow, exit 2 = block with the message on stderr.
set -uo pipefail

command_line="$(jq -r '.tool_input.command // ""' 2>/dev/null)"
[ -z "$command_line" ] && exit 0

# Deliberate escape hatch: if the tool cannot do something, this must not be a dead end.
case "$command_line" in
  *TRELLO_CLI_ALLOW_RAW=1*) exit 0 ;;
esac

hits_trello_api=false
case "$command_line" in
  *api.trello.com*|*trello.com/1/*|*clubspire-trello/trello.sh*) hits_trello_api=true ;;
esac
$hits_trello_api || exit 0

# Allow the CLI itself, which of course talks to api.trello.com.
case "$command_line" in
  trello\ *|*/trello\ *|*[\;\|\&]\ trello\ *) exit 0 ;;
esac

cat >&2 <<'MSG'
Use the `trello` CLI instead of calling the Trello API directly.

  trello card <id|shortLink|URL|#n>   read a card in full (description, checklists,
                                      attachments, comments) in one request
  trello snapshot                     the whole board
  trello search "<query>"             find cards
  trello create / update / move / archive
  trello comment add|edit|rm          comments
  trello attach ls|add|get            attachments, including authenticated downloads
  trello check / field / label / member

`trello --help` lists everything; `trello agent-guide` is the full reference.
If the CLI genuinely cannot do what you need, prefix the command with
TRELLO_CLI_ALLOW_RAW=1 to bypass this check.
MSG
exit 2

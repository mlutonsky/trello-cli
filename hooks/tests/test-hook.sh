#!/usr/bin/env bash
# Regression tests for block-raw-trello-api.sh.
#
# The hook has to tell "run curl against the Trello API" apart from "mention the Trello
# API in passing". Getting that wrong once blocked `rm old-wrapper.sh`, so every case
# below is a real command that was either wrongly blocked or must stay blocked.
set -uo pipefail
HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/block-raw-trello-api.sh"
failures=0

check() { # check <expected-exit> <description> <command-line>
  local want="$1" desc="$2" cmd="$3" got
  printf '%s' "$cmd" | jq -Rc '{tool_input:{command:.}}' | "$HOOK" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then
    printf 'ok   %s\n' "$desc"
  else
    printf 'FAIL %s (expected exit %s, got %s)\n' "$desc" "$want" "$got"
    failures=$((failures + 1))
  fi
}

check 2 "blocks a direct curl"            'curl https://api.trello.com/1/members/me'
check 2 "blocks curl piped into jq"       'curl -s "https://api.trello.com/1/cards/x?key=a" | jq .'
check 2 "blocks wget"                     'wget https://api.trello.com/1/boards/x'
check 2 "blocks curl after a separator"   'ls; curl https://api.trello.com/1/x'

check 0 "allows the trello CLI"           'trello card 6h3iK2mA'
check 0 "allows the escape hatch"         'TRELLO_CLI_ALLOW_RAW=1 curl https://api.trello.com/1/x'
check 0 "allows grep for the host"        'grep -rn api.trello.com src/'
check 0 "allows rm of a path"             'rm /home/x/.config/clubspire-trello/trello.sh'
check 0 "allows the host inside a string" 'echo "see https://api.trello.com/1/ docs"'
check 0 "allows curl to another host"     'curl https://example.com/api'

if [ "$failures" -gt 0 ]; then
  printf '\n%s check(s) failed\n' "$failures"
  exit 1
fi
printf '\nall checks passed\n'

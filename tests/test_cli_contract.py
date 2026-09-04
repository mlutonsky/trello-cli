"""The output contract the SKILL.md promises: Markdown by default, JSON on demand,
errors as a JSON envelope on stderr, and --dry-run never touching Trello."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def run(*args: str, env_extra: dict[str, str] | None = None):
    environment = dict(os.environ)
    if env_extra:
        environment.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "trello_cli", *args],
        capture_output=True,
        text=True,
        env=environment,
    )


def test_version_is_markdown_by_default():
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip().startswith("trello-cli ")


def test_version_json():
    result = run("--json", "--version")
    assert json.loads(result.stdout)["name"] == "trello-cli"


def test_usage_error_is_a_json_envelope_on_stderr():
    result = run("no-such-command")
    assert result.returncode == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "error"
    assert payload["error"]["details"] == {"usage": True}


def test_missing_credentials_report_config_error(tmp_path):
    result = run(
        "whoami",
        env_extra={
            "TRELLO_HOME": str(tmp_path),
            "TRELLO_API_KEY": "",
            "TRELLO_TOKEN": "",
        },
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "config_error"

from __future__ import annotations

from trello_cli import render

CARD = {
    "id": "5e839f3696a55979a932b3ad",
    "idShort": 87,
    "shortLink": "6h3iK2mA",
    "shortUrl": "https://trello.com/c/6h3iK2mA",
    "name": "Broken order export",
    "desc": "Steps to reproduce:\n\n1. open the admin",
    "due": "2026-09-10T12:00:00.000Z",
    "dueComplete": False,
    "labels": [{"name": "bug", "color": "red"}, {"name": "", "color": "sky"}],
    "members": [{"username": "lutonsky"}],
    "badges": {"comments": 12, "attachments": 1, "checkItems": 3, "checkItemsChecked": 2},
    "checklists": [
        {
            "name": "QA",
            "checkItems": [
                {"name": "reproduce", "state": "complete", "pos": 1},
                {"name": "fix", "state": "incomplete", "pos": 2},
            ],
        }
    ],
    "attachments": [
        {"name": "spec.pdf", "mimeType": "application/pdf", "bytes": 245760, "isUpload": True},
        {"name": "issue", "url": "https://example.com/issue", "isUpload": False},
    ],
    "customFieldItems": [{"idCustomField": "f1", "value": {"number": "4"}}],
}

DEFINITIONS = [{"id": "f1", "name": "Estimate", "type": "number"}]

COMMENTS = [
    {
        "id": "c1",
        "date": "2026-09-01T10:14:00.000Z",
        "memberCreator": {"username": "lutonsky"},
        "data": {"text": "Reproduced on stage."},
    }
]


def test_card_context_has_every_section():
    out = render.card_context(
        CARD,
        board_name="ClubSpire",
        list_name="TODO",
        comment_actions=COMMENTS,
        comment_total=12,
        field_definitions=DEFINITIONS,
    )
    assert out.startswith("#87 Broken order export [6h3iK2mA]")
    assert "ClubSpire › TODO · bug(red), sky · @lutonsky" in out
    assert "due 2026-09-10" in out
    assert "## Description" in out
    assert "## Checklists\nQA (1/2)\n  [x] reproduce\n  [ ] fix" in out
    assert "## Custom fields\nEstimate: 4" in out
    assert "## Attachments (2)" in out
    assert "1. spec.pdf — application/pdf, 240.0 kB (upload)" in out
    # Truncation must be visible, so an agent knows something is missing.
    assert "## Comments (1 of 12, newest first)" in out


def test_card_context_omits_empty_sections():
    out = render.card_context({"name": "Bare", "shortLink": "abcd1234"})
    assert "## Description" not in out
    assert "## Attachments" not in out
    assert "## Comments" not in out


def test_card_line_is_one_line_with_counters():
    line = render.card_line(CARD)
    assert "\n" not in line
    assert "#87 [6h3iK2mA] Broken order export" in line
    assert "12c 1a 2/3☑" in line


def test_archived_card_is_marked():
    assert "archived" in render.card_line({"name": "x", "shortLink": "y", "closed": True})


def test_custom_field_list_value_resolves_the_option_text():
    definition = {
        "id": "f2",
        "type": "list",
        "options": [{"id": "o1", "value": {"text": "High"}}],
    }
    assert render.custom_field_value({"idValue": "o1"}, definition) == "High"


def test_markdown_is_far_smaller_than_json():
    import json

    markdown = render.card_context(CARD, field_definitions=DEFINITIONS, comment_actions=COMMENTS)
    assert len(markdown) < len(json.dumps(CARD)) / 2

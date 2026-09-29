"""`pikslide --help TOPIC` (src/pikslide/help.py)."""

from __future__ import annotations

import pytest

from pikslide import main
from pikslide.help import _VARIABLE_DOCS, ENTRIES, _css_colors, _Style, prelude_values, render
from pikslide.pik import parse
from pikslide.pik.layout import resolve_layout
from pikslide.pik.tokens import CLASS_NAMES, KEYWORDS

PLAIN = _Style(tty=False)


@pytest.mark.parametrize("word", sorted(set(KEYWORDS) | CLASS_NAMES))
def test_every_reserved_word_has_a_help_entry(word: str):
    assert any(word in e.names for e in ENTRIES), f"no --help entry for {word!r}"


def test_every_built_in_variable_is_described():
    colors = set(_css_colors())
    missing = [n for n, v in prelude_values().items()
               if n not in colors and not v.startswith("theme ") and n not in _VARIABLE_DOCS]
    assert missing == []


# The names the entries' examples refer to.
_EXAMPLE_PRELUDE = """\
A: box at (0, 0)
B: box at (3, 1)
Web: box at (5, 0)
Row: [ box "a"; box "b" ] at (2, -2)
line from A to B
"""


@pytest.mark.parametrize(
    "entry", [e for e in ENTRIES if e.example and e.names[0] not in ("image", "include")], ids=lambda e: e.names[0]
)
def test_entry_example_lays_out(entry):
    resolve_layout(parse(_EXAMPLE_PRELUDE + entry.example + "\n"))


def test_class_help_shows_synopsis_attributes_and_prelude_defaults():
    text = render("box", PLAIN)
    assert "[Label:] box [attribute ...]" in text
    assert "ATTRIBUTES" in text and "fill C" in text
    assert f"boxwid = {prelude_values()['boxwid']}" in text


def test_color_help_lists_the_color_names():
    text = render("color", PLAIN)
    assert "aliceblue" in text and "accent1" in text


@pytest.mark.parametrize("topic", ["grammar", "spec", "keywords", "classes", "attributes", "flags",
                                   "colors", "shapes", "variables", "prelude", "boxwid", "NE", "Arrow"])
def test_topics_render(topic: str):
    assert render(topic, PLAIN)


def test_plain_output_has_no_escape_codes():
    assert "\033" not in render("colors", PLAIN)
    assert "\033" in render("colors", _Style(tty=True))


def test_cli_help_topic(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["pikslide", "--help", "chop"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("CHOP")


def test_cli_help_alone_shows_usage_and_topics(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["pikslide", "-h"])
    main()
    out = capsys.readouterr().out
    assert "usage: pikslide" in out and "Help topics" in out


def test_cli_help_unknown_topic_suggests(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["pikslide", "--help", "colr"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "did you mean color" in capsys.readouterr().err


def test_intro_example_lays_out_and_intro_is_listed():
    from pikslide.help import INTRO_EXAMPLE, topics_text

    resolve_layout(parse(INTRO_EXAMPLE + "\n"))
    assert "intro" in topics_text()
    assert INTRO_EXAMPLE.splitlines()[0] in render("intro", PLAIN)


@pytest.mark.parametrize(
    ("line", "near", "expected"),
    [
        ("box colr red", "red", ["box"]),
        ("Web: arrow from A too B", "too", ["arrow"]),
        ("box at 1 chop chop", "chop", ["box", "chop"]),
        ("zzz", "zzz", ["keywords"]),
    ],
)
def test_syntax_error_topics(line, near, expected):
    from pikslide.help import syntax_error_topics

    assert syntax_error_topics(line, near) == expected


def test_errors_point_to_help(monkeypatch, capsys, tmp_path):
    import json

    src = tmp_path / "d.pik"
    src.write_text("box fill blu\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["pikslide", str(src), "--check"])
    with pytest.raises(SystemExit):
        main()
    assert "see: pikslide --help variables, pikslide --help colors" in capsys.readouterr().err

    src.write_text("box colr red\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["pikslide", str(src), "--check", "--format", "json"])
    with pytest.raises(SystemExit):
        main()
    assert json.loads(capsys.readouterr().out)["errors"][0]["help"] == ["pikslide --help box"]

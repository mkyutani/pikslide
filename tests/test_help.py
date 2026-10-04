"""`pikslide --help TOPIC` (src/pikslide/help.py)."""

from __future__ import annotations

import pytest

from pikslide import main
from pikslide.help import _SHAPE_DOCS, _VARIABLE_DOCS, ENTRIES, _css_colors, _Style, prelude_values, render
from pikslide.pik import parse
from pikslide.pik.layout import PRESET_NAMES, THEME_SLOTS, resolve_layout
from pikslide.pik.tokens import CLASS_NAMES, KEYWORDS
from pikslide.pptx_writer import default_theme_colors

PLAIN = _Style(tty=False)


@pytest.mark.parametrize("word", sorted(set(KEYWORDS) | CLASS_NAMES))
def test_every_reserved_word_has_a_help_entry(word: str):
    assert any(word in e.names for e in ENTRIES), f"no --help entry for {word!r}"


def test_every_built_in_variable_is_described():
    colors = set(_css_colors())
    missing = [n for n, v in prelude_values().items()
               if n not in colors and not v.startswith("theme ") and n not in _VARIABLE_DOCS]
    assert missing == []


def test_color_name_help_shows_the_color_and_where_it_goes():
    text = render("cyan", PLAIN)
    assert text.startswith("CYAN — a named color")
    assert "cyan = 0x00ffff" in text and "fill cyan" in text and "--help colors" in text


def test_theme_color_help_shows_the_built_in_theme_rgb():
    text = render("accent1", PLAIN)
    assert 'accent1 = theme "accent1"' in text and "0x4f81bd with no --template" in text
    # a variable naming another color is followed to it
    assert 'primary = text2 = theme "tx2"' in render("primary", PLAIN)


def test_built_in_theme_has_every_theme_slot():
    assert sorted(default_theme_colors()) == sorted(THEME_SLOTS.values())


def test_every_preset_shape_is_described():
    assert sorted(_SHAPE_DOCS) == sorted(PRESET_NAMES.values())


def test_shapes_help_describes_each_shape():
    text = render("shapes", PLAIN)
    assert f"Preset shapes ({len(PRESET_NAMES)})" in text
    assert "callout1" in text and "leader line" in text


def test_shape_name_is_a_help_topic():
    text = render("Callout1", PLAIN)
    assert text.startswith("callout1 — ")
    assert "[Label:] shape callout1 [attribute ...]" in text and "leader line" in text
    # "as callout1, but ...": points back at the shape it's described by
    assert "--help callout1, --help shape" in render("callout2", PLAIN)


def test_class_entry_wins_over_a_preset_of_the_same_name():
    assert render("ellipse", PLAIN).startswith("ELLIPSE")


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
                                   "colors", "shapes", "variables", "prelude", "boxwid", "NE", "Arrow",
                                   "wedgeRectCallout", "template", "settings", "vmargin"])
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


@pytest.mark.parametrize(
    "message",
    [
        "no slide layout named 'Nope' in this template; it has: ...",
        "2 slide layouts in this template are named 'Title Only': ...",
        "'layout' can only be set in a template's settings file, not in a program ...",
    ],
)
def test_template_errors_point_to_the_template_topic(message: str):
    from pikslide.help import layout_error_topics

    assert layout_error_topics(message) == ["template"]
    assert render("template", PLAIN).startswith("TEMPLATE")


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

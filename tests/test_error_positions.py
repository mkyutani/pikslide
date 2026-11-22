"""A layout error points at where in the source the statement, name or
expression it is about is, as a syntax error does (issue #40,
docs/spec.md SS5)."""

from __future__ import annotations

import pytest
from pptx import Presentation

from pikslide import LayoutError, layout, parse
from pikslide.api import BuildError, build
from pikslide.pik.layout import resolve_layout


def where(src: str) -> tuple[int, int, str]:
    """The line and column of the error laying out `src` gives, and the
    error."""
    with pytest.raises(LayoutError) as e:
        resolve_layout(parse(src))
    err = e.value
    assert err.file is None
    return err.line, err.pos - (src.rfind("\n", 0, err.pos) + 1) + 1, err.message


@pytest.mark.parametrize("src, line, column, message", [
    ("box\nbox at B.e\n", 2, 8, "undefined object: B"),                 # a name, in a position
    ("box wid nosuch\n", 1, 9, "no such variable: nosuch"),              # a variable, in an expression
    ("box fill nosuchcolor\n", 1, 10, "no such variable: nosuchcolor"),  # a color
    ("gap = nosuch + 1\nbox\n", 1, 7, "no such variable: nosuch"),       # an assignment
    ("P: B.e\n", 1, 4, "undefined object: B"),                           # a label's position
    ("A: box\narrow from A.e to C.w\n", 2, 19, "undefined object: C"),   # the second of two
    ("box start triangle\n", 1, 5, "'start triangle' is only valid"),    # an attribute
    ("[\n  box at B.e\n]\n", 2, 10, "undefined object: B"),              # inside a block
    ('image "../x.png"\n', 1, 1, "image path escapes"),                  # a statement
    ("A: box\narrow attach from (3,3) to (4,3)\n", 2, 1, "'attach' on arrow 1: neither"),  # after the layout
])
def test_a_layout_error_points_at_what_it_is_about(src, line, column, message):
    found = where(src)
    assert found[:2] == (line, column) and found[2].startswith(message)


def test_in_a_macro_at_the_body_or_the_argument_it_comes_from():
    # As a syntax error does: the place of the token itself.
    assert where("define m {\n  box at B.e\n}\nm()\n")[:2] == (2, 10)
    assert where("define m {\n  box at $1.e\n}\nm(B)\n")[:2] == (4, 3)
    # An argument put in parentheses (issue #45) is still where it was.
    assert where("define m { 1 + $1 }\nbox wid m(nosuch + 1)\n")[:2] == (2, 11)


def test_the_library_gives_where_too():
    with pytest.raises(LayoutError) as e:
        layout(parse("box\nbox at B.e\n"))
    assert (e.value.line, e.value.pos, e.value.file) == (2, 11, None)


def test_build_reports_it_with_the_line_and_a_caret(tmp_path):
    with pytest.raises(BuildError) as e:
        build("box\nbox at B.e\n", "d.pik", base_dir=str(tmp_path), check=True)
    assert e.value.to_dict() == {"file": "d.pik", "line": 2, "column": 8, "message": "undefined object: B",
                                 "help": ["pikslide --help last"]}
    assert e.value.shown == "d.pik:2:8: undefined object: B\nbox at B.e\n       ^"


def test_in_an_included_file_at_its_line_there(tmp_path):
    (tmp_path / "parts.pik").write_text("gap = 1\ngap2 = nosuch\n", encoding="utf-8")
    with pytest.raises(BuildError) as e:
        build('include "parts.pik"\nbox\n', "d.pik", base_dir=str(tmp_path), check=True)
    assert (e.value.file, e.value.line, e.value.column) == (str(tmp_path / "parts.pik"), 2, 8)
    assert e.value.shown.endswith("gap2 = nosuch\n       ^")


def test_in_a_settings_file_at_its_line_there(tmp_path):
    (tmp_path / "s.pik").write_text("medium = 12pt\nmedium = nosuch\n", encoding="utf-8")
    with pytest.raises(BuildError) as e:
        build("box\n", "d.pik", base_dir=str(tmp_path), settings=str(tmp_path / "s.pik"), check=True)
    assert (e.value.file, e.value.line, e.value.column) == (str(tmp_path / "s.pik"), 2, 10)


def test_a_syntax_error_in_a_settings_file_is_reported_not_raised(tmp_path):
    # It used to escape build() as a PikSyntaxError, and the command fail
    # with a traceback.
    (tmp_path / "s.pik").write_text("medium = 12pt\nbox wid\n", encoding="utf-8")
    with pytest.raises(BuildError) as e:
        build("box\n", "d.pik", base_dir=str(tmp_path), settings=str(tmp_path / "s.pik"), check=True)
    assert (e.value.file, e.value.line) == (str(tmp_path / "s.pik"), 2)


def test_one_about_no_place_in_the_source_has_none(tmp_path):
    template = tmp_path / "t.pptx"
    Presentation().save(template)
    with pytest.raises(BuildError) as e:
        build("box\n", "d.pik", base_dir=str(tmp_path), template=str(template), layout_name="Nope", check=True)
    assert (e.value.file, e.value.line, e.value.column) == (None, None, None)
    assert e.value.shown == e.value.message

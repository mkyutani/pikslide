"""Tests for the pikchr (.pik) parser: pikslide.pik.parse().

Fixtures under tests/fixtures/examples/ are pikchr's own official example
scripts (https://pikchr.org/home/doc/tip/doc/examples.md), used here as a
"does this parse without error" regression net across real-world syntax.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pikslide.pik import ast, parse
from pikslide.pik.macros import expand_macros
from pikslide.pik.parser import Parser
from pikslide.pik.tokens import PikSyntaxError, TokType

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "examples"
EXAMPLE_FILES = sorted(FIXTURES_DIR.glob("*.pik"))


# ---------------------------------------------------------------------------
# Real-world regression: pikchr's own official examples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_official_example_parses(path: Path):
    doc = parse(path.read_text(encoding="utf-8"))
    assert isinstance(doc, ast.Document)
    assert len(doc.statements) > 0


# ---------------------------------------------------------------------------
# Basic objects and attributes
# ---------------------------------------------------------------------------


def test_simple_box():
    doc = parse('box "Hello" width 1.2in height 0.6in fill lightblue\n')
    assert len(doc.statements) == 1
    stmt = doc.statements[0]
    assert isinstance(stmt, ast.ObjectStatement)
    assert isinstance(stmt.base, ast.ClassBase)
    assert stmt.base.classname == "box"
    assert stmt.attributes[0] == ast.TextAttribute("Hello", [])
    assert stmt.attributes[1] == ast.NumProperty("width", ast.RelExpr(abs=ast.Num(1.2)))
    assert stmt.attributes[2] == ast.NumProperty("height", ast.RelExpr(abs=ast.Num(0.6)))
    assert stmt.attributes[3] == ast.ColorProperty("fill", ast.Var("lightblue"))


def test_lowercase_color_name_is_an_ordinary_variable():
    # Unlike pikchr, a colour name is not special in the grammar: pikslide
    # is not aiming for pikchr compatibility (docs/spec.md SS2), and a
    # capitalized PLACENAME is always an object reference, never a colour
    # -- "darkblue" is an ordinary Var, resolved against the prelude
    # (docs/spec.md SS3.7) at evaluation time, not parse time.
    doc = parse("box color darkblue\n")
    attr = doc.statements[0].attributes[0]
    assert attr == ast.ColorProperty("color", ast.Var("darkblue"))


def test_dashed_with_and_without_value():
    doc = parse("line dashed\nline dashed 0.05\n")
    assert doc.statements[0].attributes[0] == ast.DashProperty("dashed", None)
    assert doc.statements[1].attributes[0] == ast.DashProperty("dashed", ast.Num(0.05))


def test_arrow_direction_flags():
    doc = parse("arrow <-\narrow ->\narrow <->\n")
    assert doc.statements[0].attributes[0] == ast.ArrowDirection("left")
    assert doc.statements[1].attributes[0] == ast.ArrowDirection("right")
    assert doc.statements[2].attributes[0] == ast.ArrowDirection("both")


def test_bare_string_is_a_text_object():
    doc = parse('"floating text" bold\n')
    stmt = doc.statements[0]
    assert isinstance(stmt.base, ast.TextBase)
    assert stmt.base.text == "floating text"
    assert stmt.base.flags == ["bold"]


def test_string_escapes():
    doc = parse(r'"say \"hi\" \\ done"' + "\n")
    assert doc.statements[0].base.text == 'say "hi" \\ done'


# ---------------------------------------------------------------------------
# Numeric literals and units (pik_atof port)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", 1.0),
        ("0.5", 0.5),
        ("1in", 1.0),
        ("2.54cm", 1.0),
        ("25.4mm", 1.0),
        ("72pt", 1.0),
        ("96px", 1.0),
        ("6pc", 1.0),
    ],
)
def test_numeric_units(text: str, expected: float):
    doc = parse(f"box width {text}\n")
    value = doc.statements[0].attributes[0].value.abs
    assert value == ast.Num(expected)


def test_hex_literal_is_a_colour_not_a_number():
    # A hex literal is a colour value (ext), not a number -- unlike a
    # decimal literal, regardless of where it's used (docs/spec.md SS2).
    doc = parse('box fill 0x10\n')
    value = doc.statements[0].attributes[0].value
    assert value == ast.HexColor(16)


# ---------------------------------------------------------------------------
# Labels, object references, and positions
# ---------------------------------------------------------------------------


def test_label_and_edge_reference():
    doc = parse("A: box\narrow from A.n to A.s\n")
    labeled = doc.statements[0]
    assert labeled.label == "A"
    arrow = doc.statements[1]
    frm, to = arrow.attributes
    assert frm.position == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), "n"))
    assert to.position == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), "s"))


def test_offset_position():
    doc = parse("arrow to A.e+(0.5,0)\n")
    to = doc.statements[0].attributes[0]
    assert to.position == ast.OffsetPosition(
        ast.ObjectEdge(ast.NameRef(["A"]), "e"), "+", ast.Num(0.5), ast.Num(0.0)
    )


def test_nested_dotted_name_chain():
    doc = parse("G: Container.Sub.e\n")
    stmt = doc.statements[0]
    assert stmt.position == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["Container", "Sub"]), "e"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2nd box", ast.NthRef(2, "box")),
        ("last box", ast.NthRef(-1, "box")),
        ("3rd last circle", ast.NthRef(-3, "circle")),
        ("first box", ast.NthRef(1, "box")),
        ("last", ast.NthRef(-1, None)),
    ],
)
def test_nth_and_last_references(text: str, expected: ast.NthRef):
    doc = parse(f"L: {text}\n")
    place = doc.statements[0].position.place
    assert place.obj == expected


def test_nth_of_container():
    doc = parse("F: 1st box in Outer\n")
    place = doc.statements[0].position.place
    assert place.obj == ast.NthRef(1, "box", container=ast.NameRef(["Outer"]))


def test_nth_vertex():
    doc = parse("V: 2nd vertex of P\n")
    place = doc.statements[0].position.place
    assert place == ast.NthVertex(2, ast.NameRef(["P"]))


def test_same_as():
    doc = parse("B: circle same as A\n")
    assert doc.statements[0].attributes[0] == ast.Same(ast.NameRef(["A"]))


def test_between_two_syntaxes_are_equivalent():
    doc = parse("X: 0.5 between A.n and B.s\nY: 0.5 <A.n, B.s>\n")
    assert doc.statements[0].position == doc.statements[1].position


def test_heading_with_angle_and_with_edge():
    doc = parse(
        "arrow to 1in heading 45 from A.n\n"
        "arrow to 1in heading ne of A.n\n"
    )
    to1 = doc.statements[0].attributes[0].position
    to2 = doc.statements[1].attributes[0].position
    assert isinstance(to1, ast.HeadingOffset) and to1.angle == ast.Num(45.0) and to1.edge is None
    assert isinstance(to2, ast.HeadingOffset) and to2.edge == "ne" and to2.angle is None


# ---------------------------------------------------------------------------
# Nested [...] blocks -- where the tree actually branches
# ---------------------------------------------------------------------------


def test_nested_block_forms_a_subtree():
    doc = parse("Outer: [\n  box\n  [ box; box ]\n]\n")
    outer = doc.statements[0]
    assert isinstance(outer.base, ast.BlockBase)
    assert len(outer.base.statements) == 2
    inner_block = outer.base.statements[1]
    assert isinstance(inner_block.base, ast.BlockBase)
    assert len(inner_block.base.statements) == 2


# ---------------------------------------------------------------------------
# Directions, assignment, move/then/go
# ---------------------------------------------------------------------------


def test_direction_statement():
    doc = parse("right\ndown\n")
    assert doc.statements == [ast.DirectionStatement("right"), ast.DirectionStatement("down")]


@pytest.mark.parametrize(
    ("text", "op", "value"),
    [
        ("foo = 1\n", "=", 1.0),
        ("foo += 1\n", "+=", 1.0),
        ("foo -= 1\n", "-=", 1.0),
        ("foo *= 2\n", "*=", 2.0),
        ("foo /= 2\n", "/=", 2.0),
    ],
)
def test_assignment_operators(text: str, op: str, value: float):
    doc = parse(text)
    assert doc.statements[0] == ast.AssignStatement("foo", op, ast.Num(value))


def test_bare_then_and_then_with_heading():
    doc = parse("arrow then\narrow then heading 90 from A.n\n")
    assert doc.statements[0].attributes[0] == ast.Then()
    mv = doc.statements[1].attributes[0]
    assert isinstance(mv, ast.MoveHeading) and mv.keyword == "then" and mv.angle == ast.Num(90.0)


def test_go_until_even_with():
    doc = parse("line go right until even with A.e\n")
    attr = doc.statements[0].attributes[0]
    assert isinstance(attr, ast.GoDirection)
    assert attr.direction == "right"
    assert attr.even_with == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), "e"))


def test_leading_bare_percentage_is_current_direction():
    doc = parse("arrow 150%\n")
    assert doc.statements[0].attributes[0] == ast.LeadingDirection(ast.RelExpr(percent=ast.Num(150.0)))


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


def test_expr_precedence():
    # NOTE: 'x' and 'y' are reserved keywords (used in "place.x"/"place.y"),
    # so -- just as in upstream pikchr -- they cannot be used as plain
    # variable names; hence "foo"/"bar" here instead.
    doc = parse("foo = 1 + 2 * 3\n")
    value = doc.statements[0].value
    assert value == ast.BinOp("+", ast.Num(1.0), ast.BinOp("*", ast.Num(2.0), ast.Num(3.0)))


def test_expr_unary_and_parens():
    doc = parse("foo = -(1 + 2)\n")
    value = doc.statements[0].value
    assert value == ast.UnaryOp("-", ast.BinOp("+", ast.Num(1.0), ast.Num(2.0)))


def test_expr_function_calls():
    doc = parse("foo = sqrt(4)\nbar = max(1, 2)\n")
    assert doc.statements[0].value == ast.FuncCall("sqrt", [ast.Num(4.0)])
    assert doc.statements[1].value == ast.FuncCall("max", [ast.Num(1.0), ast.Num(2.0)])


def test_expr_dist_and_place_coord():
    doc = parse("foo = dist(A.n, B.s)\nbar = A.x\n")
    assert doc.statements[0].value == ast.Dist(
        ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), "n")),
        ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["B"]), "s")),
    )
    assert doc.statements[1].value == ast.PlaceCoord(ast.ObjectEdge(ast.NameRef(["A"]), None), "x")


def test_expr_object_property():
    doc = parse("bar = A.width\n")
    assert doc.statements[0].value == ast.ObjectProp(ast.NameRef(["A"]), "width")


# ---------------------------------------------------------------------------
# print / assert
# ---------------------------------------------------------------------------


def test_print_statement_mixes_strings_and_values():
    doc = parse('print "width is", A.width, " and color ", A.color\n')
    stmt = doc.statements[0]
    assert isinstance(stmt, ast.PrintStatement)
    assert stmt.items[0] == "width is"
    assert stmt.items[1] == ast.ObjectProp(ast.NameRef(["A"]), "width")


def test_assert_expr_and_position_forms():
    doc = parse("assert( A.width == 1.2 )\nassert( A.n == (0,0) )\n")
    assert isinstance(doc.statements[0], ast.AssertExprStatement)
    assert isinstance(doc.statements[1], ast.AssertPositionStatement)


# ---------------------------------------------------------------------------
# Macros (#define)
# ---------------------------------------------------------------------------


def test_macro_expansion_with_positional_args():
    doc = parse(
        "define pair {\n"
        "  box fit\n"
        "  arrow right 50%\n"
        "  box fit\n"
        "}\n"
        "pair(One,Two)\n"
    )
    assert len(doc.macros) == 1
    assert doc.macros[0].name == "pair"
    # the macro body expands to three statements at the call site
    assert len(doc.statements) == 3
    assert all(isinstance(s, ast.ObjectStatement) for s in doc.statements)


def test_macro_invocation_requires_adjacent_parens():
    # A space before '(' means "invoke with no args", per upstream pikchr:
    # pik_parse_macro_args() is only tried on text immediately following
    # the macro name token, so "(...)" with a preceding space is left as
    # ordinary tokens rather than being consumed as the argument list.
    tokens, _ = expand_macros("define one { box } one (ignored)\n")
    kinds = [t.type for t in tokens]
    assert kinds == [
        TokType.CLASSNAME,  # 'box', from expanding 'one'
        TokType.LP,
        TokType.ID,
        TokType.RP,
        TokType.EOL,
    ]


def test_recursive_macro_raises():
    with pytest.raises(PikSyntaxError):
        parse("define loop { loop }\nloop\n")


def test_string_literal_dollar_is_not_substituted():
    # Matches upstream pikchr: a STRING token is opaque to macro expansion,
    # so "$1" typed inside quotes is never substituted.
    tokens, _ = expand_macros('define m { box "$1" }\nm(hello)\n')
    doc = Parser(tokens).parse_document()
    assert doc.statements[0].attributes[0].text == "$1"


# ---------------------------------------------------------------------------
# A macro cannot shadow a variable (docs/spec.md SS3.6): the two directions
# of the guard, plus reserved words (which can never collide either way).
# ---------------------------------------------------------------------------


def test_define_naming_a_prelude_variable_is_an_error():
    with pytest.raises(PikSyntaxError):
        parse("define boxwid { 99 }\nbox\n")


def test_define_naming_an_earlier_program_variable_is_an_error():
    with pytest.raises(PikSyntaxError):
        parse("myvar = 1\ndefine myvar { 99 }\nbox\n")


def test_assigning_to_an_existing_macro_name_is_an_error():
    with pytest.raises(PikSyntaxError):
        parse("define legend { fill }\nlegend = 5\nbox\n")


def test_reserved_word_cannot_be_a_macro_name():
    # "small" lexes as a keyword, never an ID, so it can't even reach the
    # macro-definition rule -- this is a plain syntax error, not the
    # variable-shadow guard above.
    with pytest.raises(PikSyntaxError):
        parse("define small { 99 }\nbox\n")


def test_macro_unrelated_to_any_variable_still_works():
    doc = parse("define legend2 { box }\nlegend2\n")
    assert len(doc.statements) == 1
    assert isinstance(doc.statements[0], ast.ObjectStatement)


# ---------------------------------------------------------------------------
# Preset shapes: `shape` (docs/spec.md SS3.4)
# ---------------------------------------------------------------------------


def test_shape_with_lowercase_preset_name():
    doc = parse('shape chevron "Step 1" fit\n')
    stmt = doc.statements[0]
    assert stmt.base == ast.ShapeBase("chevron")
    assert stmt.attributes[0] == ast.TextAttribute("Step 1", [])
    assert isinstance(stmt.attributes[1], ast.Fit)


def test_shape_preset_name_can_collide_with_a_classname():
    # "ellipse"/"diamond"/"line"/"arc" lex as CLASSNAME, not ID -- the
    # preset-name rule accepts both (docs/grammar.md, Objects).
    doc = parse('shape ellipse "x"\n')
    assert doc.statements[0].base == ast.ShapeBase("ellipse")


def test_shape_preset_name_can_start_uppercase():
    # A preset name matches case-insensitively (docs/spec.md SS3.4), so an
    # uppercase-led spelling -- which the lexer can only produce as a
    # PLACENAME -- must parse too.
    doc = parse('shape RoundRect "x"\n')
    assert doc.statements[0].base == ast.ShapeBase("RoundRect")


def test_shape_can_be_labeled():
    doc = parse('A: shape hexagon "x"\n')
    assert doc.statements[0].label == "A"
    assert doc.statements[0].base == ast.ShapeBase("hexagon")


# ---------------------------------------------------------------------------
# Images: `image` (docs/spec.md SS3.5)
# ---------------------------------------------------------------------------


def test_image_with_path_and_size():
    doc = parse('image "logo.png" width 0.6in\n')
    stmt = doc.statements[0]
    assert stmt.base == ast.ImageBase("logo.png")
    assert stmt.attributes[0] == ast.NumProperty("width", ast.RelExpr(abs=ast.Num(0.6)))


def test_image_can_be_labeled():
    doc = parse('Logo: image "icons/db.svg" height 0.4in alt "Database"\n')
    stmt = doc.statements[0]
    assert stmt.label == "Logo"
    assert stmt.base == ast.ImageBase("icons/db.svg")
    assert stmt.attributes[-1] == ast.Alt("Database")


# ---------------------------------------------------------------------------
# `include` (docs/spec.md SS3.6): resolved in the macro pass, before
# parsing, so it never appears in the AST -- these tests check parse()'s
# end result, the same way the file was written by hand.
# ---------------------------------------------------------------------------


def test_include_brings_in_variables_and_macros(tmp_path: Path):
    (tmp_path / "house.pik").write_text(
        "boxwid = 1.2\ndefine card { rad 8px }\n", encoding="utf-8"
    )
    doc = parse('include "house.pik"\nbox card\n', base_dir=str(tmp_path))
    # The include's own assignment is a real statement, in place, exactly
    # as if written there (docs/spec.md SS3.6) -- followed by the object.
    assert doc.statements[0] == ast.AssignStatement("boxwid", "=", ast.Num(1.2))
    stmt = doc.statements[1]
    assert isinstance(stmt.base, ast.ClassBase) and stmt.base.classname == "box"
    # `card`'s own body (`rad 8px`) expanded in place, as if written there.
    assert stmt.attributes == [ast.NumProperty("radius", ast.RelExpr(abs=ast.Num(pytest.approx(8 / 96))))]


def test_included_file_cannot_draw_an_object(tmp_path: Path):
    (tmp_path / "bad.pik").write_text('box "oops"\n', encoding="utf-8")
    with pytest.raises(PikSyntaxError):
        parse('include "bad.pik"\nbox\n', base_dir=str(tmp_path))


def test_included_file_cannot_have_a_label(tmp_path: Path):
    (tmp_path / "bad.pik").write_text("A: 1,1\n", encoding="utf-8")
    with pytest.raises(PikSyntaxError):
        parse('include "bad.pik"\nbox\n', base_dir=str(tmp_path))


def test_included_file_can_itself_include(tmp_path: Path):
    (tmp_path / "base.pik").write_text("charwid = 0.1\n", encoding="utf-8")
    (tmp_path / "mid.pik").write_text('include "base.pik"\nboxwid = 1.5\n', encoding="utf-8")
    doc = parse('include "mid.pik"\nbox\n', base_dir=str(tmp_path))
    assert doc.statements[-1].base.classname == "box"
    assert ast.AssignStatement("boxwid", "=", ast.Num(1.5)) in doc.statements
    assert ast.AssignStatement("charwid", "=", ast.Num(0.1)) in doc.statements


def test_nested_include_resolves_relative_to_its_own_file(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.pik").write_text("boxwid = 2\n", encoding="utf-8")
    (tmp_path / "sub" / "mid.pik").write_text('include "deep.pik"\n', encoding="utf-8")
    doc = parse('include "sub/mid.pik"\nbox\n', base_dir=str(tmp_path))
    assert doc.statements[-1].base.classname == "box"
    assert ast.AssignStatement("boxwid", "=", ast.Num(2)) in doc.statements


def test_absolute_include_path_is_an_error(tmp_path: Path):
    with pytest.raises(PikSyntaxError):
        parse('include "/etc/hostname"\nbox\n', base_dir=str(tmp_path))


def test_include_path_escaping_base_dir_is_an_error(tmp_path: Path):
    with pytest.raises(PikSyntaxError):
        parse('include "../../../../../../etc/hostname"\nbox\n', base_dir=str(tmp_path))


def test_missing_include_file_is_an_error(tmp_path: Path):
    with pytest.raises(PikSyntaxError):
        parse('include "nope.pik"\nbox\n', base_dir=str(tmp_path))


def test_include_cycle_is_an_error(tmp_path: Path):
    (tmp_path / "a.pik").write_text('include "b.pik"\n', encoding="utf-8")
    (tmp_path / "b.pik").write_text('include "a.pik"\n', encoding="utf-8")
    with pytest.raises(PikSyntaxError):
        parse('include "a.pik"\nbox\n', base_dir=str(tmp_path))


def test_include_path_fallback_when_not_found_relative_to_source(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "house.pik").write_text("boxwid = 1.5\n", encoding="utf-8")
    doc = parse(
        'include "house.pik"\nbox\n',
        base_dir=str(src_dir),
        include_paths=[str(shared_dir)],
    )
    assert doc.statements[-1].base.classname == "box"
    assert ast.AssignStatement("boxwid", "=", ast.Num(1.5)) in doc.statements


def test_macro_defined_in_an_included_file_cannot_be_shadowed_by_assignment(tmp_path: Path):
    (tmp_path / "house.pik").write_text("define legend { fill }\n", encoding="utf-8")
    with pytest.raises(PikSyntaxError):
        parse('include "house.pik"\nlegend = 5\nbox\n', base_dir=str(tmp_path))


def test_variable_from_an_included_file_cannot_be_shadowed_by_a_later_define(tmp_path: Path):
    (tmp_path / "house.pik").write_text("myvar = 1\n", encoding="utf-8")
    with pytest.raises(PikSyntaxError):
        parse('include "house.pik"\ndefine myvar { 99 }\nbox\n', base_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Diagnostics: file/line/column (docs/spec.md SS5, ext)
# ---------------------------------------------------------------------------


def test_syntax_error_in_the_main_file_has_no_file_set():
    with pytest.raises(PikSyntaxError) as exc:
        parse('"unterminated\n')
    assert exc.value.file is None  # None means "the main source", docs/pik/tokens.py Token.file


def test_syntax_error_column_points_at_the_offending_character():
    with pytest.raises(PikSyntaxError) as exc:
        parse('box\n"unterminated\n')
    from pikslide.pik.tokens import column_at

    assert exc.value.line == 2
    assert column_at('box\n"unterminated\n', exc.value.pos) == 1  # the opening quote


def test_syntax_error_inside_an_include_names_the_included_file(tmp_path: Path):
    (tmp_path / "bad.pik").write_text('box "oops"\n', encoding="utf-8")
    with pytest.raises(PikSyntaxError) as exc:
        parse('include "bad.pik"\nbox\n', base_dir=str(tmp_path))
    assert exc.value.file == str(tmp_path / "bad.pik")
    assert exc.value.line == 1  # bad.pik's own line 1, not the including file's line 1


def test_syntax_error_inside_a_nested_include_names_the_deepest_file(tmp_path: Path):
    (tmp_path / "mid.pik").write_text('include "deep.pik"\n', encoding="utf-8")
    (tmp_path / "deep.pik").write_text('box "oops"\n', encoding="utf-8")
    with pytest.raises(PikSyntaxError) as exc:
        parse('include "mid.pik"\nbox\n', base_dir=str(tmp_path))
    assert exc.value.file == str(tmp_path / "deep.pik")


def test_format_syntax_error_shows_the_right_files_own_source_line(tmp_path: Path):
    from pikslide.pik import format_syntax_error

    (tmp_path / "bad.pik").write_text('box "oops"\n', encoding="utf-8")
    main_text = 'include "bad.pik"\nbox\n'
    with pytest.raises(PikSyntaxError) as exc:
        parse(main_text, base_dir=str(tmp_path))
    formatted = format_syntax_error(exc.value, "main.pik", main_text)
    assert formatted.startswith(str(tmp_path / "bad.pik") + ":1:1:")
    assert 'box "oops"' in formatted  # bad.pik's own line, not main.pik's


def test_missing_include_file_error_still_names_the_including_file(tmp_path: Path):
    # The include statement itself is in the *including* file, even though
    # the target doesn't exist -- distinct from test_syntax_error_inside_an_include*.
    with pytest.raises(PikSyntaxError) as exc:
        parse('include "nope.pik"\nbox\n', base_dir=str(tmp_path))
    assert exc.value.file is None  # the main source, not "nope.pik" (which was never read)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "box [\n",  # unterminated block
        "box width\n",  # numproperty needs a relexpr
        "1 @ 2\n",  # unrecognized token
        '"unterminated\n',  # unterminated string
    ],
)
def test_syntax_errors_raise(text: str):
    with pytest.raises(PikSyntaxError):
        parse(text)

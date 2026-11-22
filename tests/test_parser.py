"""Tests for the parser: pikslide.pik.parse().

Fixtures under tests/fixtures/examples/ are real-world example diagrams,
used here as a "does this parse without error" regression net.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pikslide.pik import ast, parse
from pikslide.pik.macros import expand_macros
from pikslide.pik.parser import Parser
from pikslide.pik.tokens import PikSyntaxError, TokType

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "examples"
EXAMPLE_FILES = sorted(FIXTURES_DIR.glob("*.pik"))


# ---------------------------------------------------------------------------
# Real-world regression: example diagrams
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
    # A color name is not special in the grammar (docs/spec.md SS2): a
    # capitalized PLACENAME is always an object reference, never a color
    # -- "darkblue" is an ordinary Var, resolved against the prelude
    # (docs/spec.md SS3.7) at evaluation time, not parse time.
    doc = parse("box fill darkblue\n")
    attr = doc.statements[0].attributes[0]
    assert attr == ast.ColorProperty("fill", ast.Var("darkblue"))


def test_dashed_with_and_without_value():
    doc = parse("line stroke dashed\nline stroke dashed 0.05\n")
    assert doc.statements[0].attributes[0] == ast.Stroke([ast.DashProperty("dashed", None)])
    assert doc.statements[1].attributes[0] == ast.Stroke([ast.DashProperty("dashed", ast.Num(0.05))])


def test_arrow_direction_flags():
    doc = parse("arrow <-\narrow ->\narrow <->\n")
    assert doc.statements[0].attributes[0] == ast.ArrowDirection("left")
    assert doc.statements[1].attributes[0] == ast.ArrowDirection("right")
    assert doc.statements[2].attributes[0] == ast.ArrowDirection("both")


def test_arrowheads_by_end():
    # issue #36: diamond and oval lex as class names, none as a color word
    doc = parse("line start diamond end open large\nline end none start oval small\n")
    assert doc.statements[0].attributes == [ast.Arrowhead("start", "diamond"), ast.Arrowhead("end", "open", "large")]
    assert doc.statements[1].attributes == [ast.Arrowhead("end", "none"), ast.Arrowhead("start", "oval", "small")]


def test_an_arrowhead_follows_a_position_and_end_of_stays_a_place():
    doc = parse("L: line\narrow from L.end end open\narrow from end of L to L.start start stealth\n")
    first, second = doc.statements[1].attributes, doc.statements[2].attributes
    assert first[1] == ast.Arrowhead("end", "open")
    assert second[0] == ast.From_(ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["L"]), "end")))
    assert second[2] == ast.Arrowhead("start", "stealth")


def test_an_end_with_no_arrowhead_is_an_error():
    with pytest.raises(PikSyntaxError, match="expected an arrowhead after 'end': triangle, open"):
        parse("line end\n")


def test_group_is_a_block_attribute():
    [stmt] = parse("[ box ] group\n").statements
    assert stmt.attributes == [ast.BoolProperty("group")]


def test_vertical_is_an_object_attribute():
    [stmt] = parse('box "店頭" vertical\n').statements
    assert stmt.attributes[-1] == ast.BoolProperty("vertical")


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
# Numeric literals and units
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


def test_hex_literal_is_a_color_not_a_number():
    # A hex literal is a color value (ext), not a number -- unlike a
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A parenthesized expression as either coordinate (issue #13).
        ("((1 + 1) / 2, 0)", ast.Coord(ast.BinOp("/", ast.BinOp("+", ast.Num(1.0), ast.Num(1.0)), ast.Num(2.0)), ast.Num(0.0))),
        ("(0, (1 + 1) / 2)", ast.Coord(ast.Num(0.0), ast.BinOp("/", ast.BinOp("+", ast.Num(1.0), ast.Num(1.0)), ast.Num(2.0)))),
        ("(1), (2)", ast.Coord(ast.Num(1.0), ast.Num(2.0))),
        ("(1 + 1) / 2 between A and B", ast.Between(
            ast.BinOp("/", ast.BinOp("+", ast.Num(1.0), ast.Num(1.0)), ast.Num(2.0)),
            ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), None)),
            ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["B"]), None)),
        )),
        # Still a parenthesized position.
        ("(A, B)", ast.XYFromPositions(
            ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), None)),
            ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["B"]), None)),
        )),
        ("(A.n)", ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), "n"))),
        ("((A.x + B.x) / 2, 0)", ast.Coord(
            ast.BinOp("/", ast.BinOp("+", ast.PlaceCoord(ast.ObjectEdge(ast.NameRef(["A"]), None), "x"),
                                     ast.PlaceCoord(ast.ObjectEdge(ast.NameRef(["B"]), None), "x")), ast.Num(2.0)),
            ast.Num(0.0),
        )),
    ],
)
def test_position_starting_with_a_paren(text: str, expected: ast.Position):
    doc = parse(f"box at {text}\n")
    assert doc.statements[0].attributes[0].position == expected


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
    doc = parse("foo = 1 + 2 * 3\n")
    value = doc.statements[0].value
    assert value == ast.BinOp("+", ast.Num(1.0), ast.BinOp("*", ast.Num(2.0), ast.Num(3.0)))


def test_expr_unary_and_parens():
    doc = parse("foo = -(1 + 2)\n")
    value = doc.statements[0].value
    assert value == ast.UnaryOp("-", ast.BinOp("+", ast.Num(1.0), ast.Num(2.0)))


def test_expr_function_calls():
    doc = parse("foo = sqrt(4)\nbar = max(1, 2)\nbaz = atan2(1, 2)\n")
    assert doc.statements[0].value == ast.FuncCall("sqrt", [ast.Num(4.0)])
    assert doc.statements[1].value == ast.FuncCall("max", [ast.Num(1.0), ast.Num(2.0)])
    assert doc.statements[2].value == ast.FuncCall("atan2", [ast.Num(1.0), ast.Num(2.0)])


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


@pytest.mark.parametrize("text", ['print "width is", A.width\n', "assert( A.width == 1.2 )\n"])
def test_pikchrs_print_and_assert_are_not_statements(text: str):
    with pytest.raises(PikSyntaxError):
        parse(text)


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
    # A space before '(' means "invoke with no args": arguments are only
    # parsed from text immediately following the macro name token, so "(...)" with a preceding space is left as
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


@pytest.mark.parametrize(
    ("text", "labels"),
    [
        ("define pair {\n  [ box; box ]\n}\nP: pair\n", ["P"]),  # issue #11
        ("define pair { [ box; box ] }\nP: pair\n", ["P"]),
        ("define pair {\n  [ box; box ]\n}\nP: pair; Q: pair\n", ["P", "Q"]),
    ],
)
def test_labeled_call_of_a_macro_whose_body_starts_on_its_own_line(text: str, labels: list[str]):
    doc = parse(text)
    assert [s.label for s in doc.statements] == labels
    assert all(isinstance(s.base, ast.BlockBase) for s in doc.statements)


def test_macro_body_of_several_statements_ends_with_the_rest_of_the_call_line():
    doc = parse("define two {\n  box\n  circle\n}\ntwo fill red\n")
    assert doc.statements == [
        ast.ObjectStatement(None, ast.ClassBase("box")),
        ast.ObjectStatement(None, ast.ClassBase("circle"), [ast.ColorProperty("fill", ast.Var("red"))]),
    ]


def test_recursive_macro_raises():
    with pytest.raises(PikSyntaxError):
        parse("define loop { loop }\nloop\n")


def test_string_literal_dollar_is_not_substituted():
    # A STRING token is opaque to macro expansion,
    # so "$1" typed inside quotes is never substituted.
    tokens, _ = expand_macros('define m { box "$1" }\nm(hello)\n')
    doc = Parser(tokens).parse_document()
    assert doc.statements[0].attributes[0].text == "$1"


# ---------------------------------------------------------------------------
# An argument or a body that is an expression is one value, as if in
# parentheses (issue #45), not text as in pikchr; anything else is text.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "meaning"),
    [
        ("define row { 5 - $1 }\nv = row(1 + 1)\n", "v = 5 - (1 + 1)\n"),
        ("define twice { $1 * 2 }\nv = twice(A.ht + 0.1)\n", "v = (A.ht + 0.1) * 2\n"),
        ("define half { 6 / $1 }\nv = half(2 * 3)\n", "v = 6 / (2 * 3)\n"),
        ("define neg { -$1 }\nv = neg(1 + 1)\n", "v = -(1 + 1)\n"),
        ("define gap { 0.5 + 0.5 }\nv = 5 - gap\n", "v = 5 - (0.5 + 0.5)\n"),
        ("define row { 5 - $1 }\nv = row(1 + 1) * 2\n", "v = (5 - (1 + 1)) * 2\n"),
        ("define one { $1 + 1 }\ndefine two { 2 * one($1) }\nv = 6 / two(3 - 1)\n",
         "v = 6 / (2 * ((3 - 1) + 1))\n"),
        ("define at2 { at ($1, -$2) }\nbox at2(1, 1 + 1)\n", "box at (1, -(1 + 1))\n"),
    ],
)
def test_an_expression_pasted_in_is_one_value(text: str, meaning: str):
    assert parse(text).statements == parse(meaning).statements


@pytest.mark.parametrize(
    ("text", "meaning"),
    [
        ('define card { box $1 fill accent1 fit }\ncard("Web" bold)\n', 'box "Web" bold fill accent1 fit\n'),
        ("define sized { box $1 }\nsized(wid 1 + 1 ht 2)\n", "box wid 1 + 1 ht 2\n"),
        ("define wide { box wid $1 }\nwide(10 + 40%)\n", "box wid 10 + 40%\n"),
        ("define near { box at $1 }\nnear(A.e + (0.5, 0))\n", "box at A.e + (0.5, 0)\n"),
        ("define size { wid 1 + 1 }\nbox size\n", "box wid 1 + 1\n"),
    ],
)
def test_what_is_not_an_expression_is_pasted_in_as_text(text: str, meaning: str):
    assert parse(text).statements == parse(meaning).statements


# ---------------------------------------------------------------------------
# A macro cannot shadow a variable (docs/spec.md SS3.6): the two directions
# of the guard, plus reserved words, and the names of points.
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


@pytest.mark.parametrize("word", ["small", "path", "box", "max", "first"])
def test_reserved_word_cannot_be_a_macro_name(word: str):
    # issue #47: an error that says why, at the name
    src = f"define {word} {{ 99 }}\nbox\n"
    with pytest.raises(PikSyntaxError, match=re.escape(f"'{word}' is a reserved word: a macro needs another name")) as exc:
        parse(src)
    assert exc.value.pos == src.index(word)


@pytest.mark.parametrize(("word", "kind"), [("n", "a point"), ("c", "a point"), ("north", "a point"),
                                            ("x", "a coordinate")])
def test_the_name_of_a_point_cannot_be_a_macro_name(word: str, kind: str):
    # It would replace the point in `A.n` too.
    with pytest.raises(PikSyntaxError, match=re.escape(f"'{word}' names {kind} (A.{word}): a macro needs another name")):
        parse(f"define {word} {{ 99 }}\nbox\n")


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


# A drive, a slash or a backslash makes a path absolute on every platform
# (issue #50): on Windows, os.path.isabs() calls none of `D:x`, `/x` or
# `\x` absolute, though each leads out of the directory. As written in a
# string in a diagram, each backslash doubled.
ABSOLUTE_PATHS =["/etc/hostname", "~/x.pik", "D:x.pik", "C:\\\\x.pik", "\\\\x.pik", "\\\\\\\\server\\\\share\\\\x.pik"]


@pytest.mark.parametrize("path", ABSOLUTE_PATHS)
def test_absolute_include_path_is_an_error(tmp_path: Path, path: str):
    with pytest.raises(PikSyntaxError, match="include path must be relative"):
        parse(f'include "{path}"\nbox\n', base_dir=str(tmp_path))


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


def test_syntax_error_inside_a_macro_expansion_points_at_the_body():
    # Issue #11: not at 1:1 of the main file.
    text = "box\nbox\ndefine pair {\n  [ box; box with ]\n}\nP: pair\n"
    with pytest.raises(PikSyntaxError) as exc:
        parse(text)
    from pikslide.pik.tokens import column_at

    assert exc.value.file is None
    assert exc.value.line == 4
    assert column_at(text, exc.value.pos) == text.split("\n")[3].index("]") + 1


def test_unrecognized_token_in_a_macro_body_points_at_the_body():
    text = "box\ndefine pair {\n  [ box; box ` ]\n}\npair\n"
    with pytest.raises(PikSyntaxError) as exc:
        parse(text)
    from pikslide.pik.tokens import column_at

    assert exc.value.line == 3
    assert column_at(text, exc.value.pos) == text.split("\n")[2].index("`") + 1


def test_syntax_error_inside_a_macro_from_an_include_names_the_included_file(tmp_path: Path):
    (tmp_path / "pair.pik").write_text("# pairs\ndefine pair {\n  [ box; box with ]\n}\n", encoding="utf-8")
    with pytest.raises(PikSyntaxError) as exc:
        parse('include "pair.pik"\nP: pair\n', base_dir=str(tmp_path))
    assert exc.value.file == str(tmp_path / "pair.pik")
    assert exc.value.line == 3


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


# ---------------------------------------------------------------------------
# Strings first, then the object's attributes (docs/grammar.md, Objects)
# ---------------------------------------------------------------------------


def test_string_attributes_bind_to_the_string_before_them():
    doc = parse('text "a" small color red "b" bold ljust at (1, 2)\n')
    a, b, just, at = doc.statements[0].attributes
    assert a == ast.TextAttribute("a", ["small"], ast.Var("red"))
    assert b == ast.TextAttribute("b", ["bold"], None)
    assert just == ast.Justify("ljust")
    assert isinstance(at, ast.At)


@pytest.mark.parametrize("text", [
    'arrow 0.4 "yes" ljust\n',
    'line right 1 "a" above then down 1 "b" below\n',
    'arrow from A.e to B.w "no" above\n',
    'box width 1 "a" bold fill red "b"\n',
])
def test_strings_may_come_among_the_attributes(text: str):
    doc = parse(text)
    texts = [a for a in doc.statements[0].attributes if isinstance(a, ast.TextAttribute)]
    assert texts and all(t.text in ("yes", "no", "a", "b") for t in texts)


def test_strings_among_the_attributes_keep_their_order_and_attributes():
    doc = parse('box width 1 "a" bold fill red "b" small\n')
    width, a, fill, b = doc.statements[0].attributes
    assert a == ast.TextAttribute("a", ["bold"], None)
    assert b == ast.TextAttribute("b", ["small"], None)
    assert isinstance(width, ast.NumProperty) and isinstance(fill, ast.ColorProperty)


def test_bare_string_takes_string_attributes_then_object_attributes():
    doc = parse('"a" italic "b" rjust at (0, 0)\n')
    stmt = doc.statements[0]
    assert stmt.base == ast.TextBase("a", ["italic"], None)
    assert stmt.attributes[0] == ast.TextAttribute("b", [], None)
    assert stmt.attributes[1] == ast.Justify("rjust")


def test_stroke_groups_color_and_line_attributes():
    doc = parse("box stroke accent2 thick dashed 0.1 fill bg1\n")
    stroke, fill = doc.statements[0].attributes
    assert stroke == ast.Stroke([
        ast.ColorProperty("stroke", ast.Var("accent2")),
        ast.BoolProperty("thick"),
        ast.DashProperty("dashed", ast.Num(0.1)),
    ])
    assert fill == ast.ColorProperty("fill", ast.Var("bg1"))


@pytest.mark.parametrize(("src", "message"), [
    # two text objects on one line: one object, with two positions
    ('"P" at (0, 0) "Q" at (1, 1)\n', "an object can have only one 'at'"),
    ('box "a" width 1 bold\n', "'bold' is a string attribute"),
    ('box "a" width 1 color red\n', "'color' is a string attribute"),
    ("box thick\n", "'thick' is a stroke attribute"),
    ('box "a" invis\n', "'invis' is a stroke attribute"),
    ("box stroke\n", "expected a color or a stroke attribute after 'stroke'"),
    ('"P" at (0, 0) at (1, 1)\n', "an object can have only one 'at'"),
    ('box "a" ljust rjust\n', "'ljust' and 'rjust' cannot both be given"),
    ('box "a" color red color blue\n', "a string can have only one 'color'"),
])
def test_misplaced_or_conflicting_attributes_are_errors(src: str, message: str):
    with pytest.raises(PikSyntaxError, match=re.escape(message)):
        parse(src)


@pytest.mark.parametrize(("src", "word"), [
    ('box "a" mono\n', "mono"),
    ('"a" monospace bold\n', "monospace"),
    ('box "a" mono width 1\n', "mono"),
])
def test_an_unsupported_word_is_an_error_that_says_so(src: str, word: str):
    # issue #46: accepted and ignored, it would look as if it worked
    with pytest.raises(PikSyntaxError, match=re.escape(f"'{word}' isn't supported")) as exc:
        parse(src)
    assert exc.value.text == word and exc.value.pos == src.index(word)


def test_connector_is_not_reserved():
    doc = parse("connector = 2\nbox width connector\n")
    assert doc.statements[0] == ast.AssignStatement("connector", "=", ast.Num(2.0))


# ---------------------------------------------------------------------------
# The names of points and coordinates are names elsewhere (issue #47)
# ---------------------------------------------------------------------------


def test_x_y_and_the_names_of_points_are_variables_elsewhere():
    doc = parse("x = 1\ny = 2\nw = 0.5\nc = 3\nt = 4\nnorth = 5\nbox at (x, y) wid w + c + t + north\n")
    assert [s.name for s in doc.statements[:6]] == ["x", "y", "w", "c", "t", "north"]
    box = doc.statements[6]
    assert box.attributes[0] == ast.At(ast.Coord(ast.Var("x"), ast.Var("y")))


def _position(src: str) -> ast.Position:
    return parse(f"A: box\nX: {src}\n").statements[1].position


@pytest.mark.parametrize(("src", "edge"), [
    ("A.ne", "ne"), ("A.c", "c"), ("A.t", "n"), ("A.bot", "s"), ("A.north", "n"), ("A.top", "n"),
])
def test_a_point_after_a_dot(src: str, edge: str):
    assert _position(src) == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), edge))


@pytest.mark.parametrize(("src", "edge"), [("ne of A", "ne"), ("c of A", "c"), ("west of A", "w")])
def test_a_point_before_of(src: str, edge: str):
    assert _position(src) == ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), edge))


def test_a_distance_toward_a_point_before_of():
    w = ast.HeadingOffset(ast.Num(1.0), edge="sw", angle=None, base=ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), None)))
    assert _position("1 sw of A") == w
    assert _position("1 heading sw of A") == w
    # a variable named like a point, beside a point
    assert _position("w sw of A") == ast.HeadingOffset(
        ast.Var("w"), edge="sw", angle=None, base=ast.PlacePosition(ast.ObjectEdge(ast.NameRef(["A"]), None)))


def test_a_variable_named_like_a_point_beside_one():
    pos = _position("A.w + (w, 0)")
    assert pos == ast.OffsetPosition(ast.ObjectEdge(ast.NameRef(["A"]), "w"), "+", ast.Var("w"), ast.Num(0.0))


@pytest.mark.parametrize("src", ["box with ne at (0, 0)\n", "box with .ne at (0, 0)\n"])
def test_a_point_after_with(src: str):
    assert parse(src).statements[0].attributes[0].edge == "ne"


@pytest.mark.parametrize(("src", "amount", "edge"), [
    ("line go 1 ne\n", ast.RelExpr(abs=ast.Num(1.0)), "ne"),
    ("line go ne\n", ast.RelExpr(), "ne"),
    ("line then 1 north\n", ast.RelExpr(abs=ast.Num(1.0)), "n"),
    ("line then se\n", ast.RelExpr(), "se"),
    ("n = 2\nline go n e\n", ast.RelExpr(abs=ast.Var("n")), "e"),
])
def test_a_point_after_a_go_or_then_amount(src: str, amount: ast.RelExpr, edge: str):
    move = parse(src).statements[-1].attributes[0]
    assert move == ast.MoveHeading(move.keyword, amount, edge=edge)


def test_a_variable_named_like_a_point_as_a_heading():
    move = parse("n = 30\nline go 1 heading n\n").statements[1].attributes[0]
    assert move == ast.MoveHeading("go", ast.RelExpr(abs=ast.Num(1.0)), angle=ast.Var("n"))


def test_x_and_y_are_coordinates_after_a_dot():
    doc = parse("A: box\nx = A.x\ny = A.y\n")
    assert doc.statements[1].value == ast.PlaceCoord(ast.ObjectEdge(ast.NameRef(["A"]), None), "x")
    assert doc.statements[2].value == ast.PlaceCoord(ast.ObjectEdge(ast.NameRef(["A"]), None), "y")


@pytest.mark.parametrize("word", ["path", "box", "max", "first", "left", "start", "center", "top"])
def test_a_reserved_word_as_a_variable_is_an_error_that_says_so(word: str):
    src = f"box\n{word} = 1\n"
    with pytest.raises(PikSyntaxError, match=re.escape(f"'{word}' is a reserved word: a variable needs another name")) as exc:
        parse(src)
    assert exc.value.pos == src.index(f"{word} =")


def test_a_reserved_word_as_a_variable_in_an_included_file(tmp_path):
    (tmp_path / "defs.pik").write_text("path = 1\n", encoding="utf-8")
    with pytest.raises(PikSyntaxError, match=re.escape("'path' is a reserved word: a variable needs another name")):
        parse('include "defs.pik"\nbox\n', base_dir=str(tmp_path))


def test_an_included_file_can_set_stroke(tmp_path):
    (tmp_path / "defs.pik").write_text("stroke = red\n", encoding="utf-8")
    parse('include "defs.pik"\nbox\n', base_dir=str(tmp_path))


def test_aligned_is_an_attribute():
    # issue #54
    doc = parse('arrow "a" above from (0, 0) to (1, 1) aligned\n')
    assert doc.statements[0].attributes[-1] == ast.BoolProperty("aligned")

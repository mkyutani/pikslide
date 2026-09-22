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

"""Recursive-descent parser for pikchr source, built on the token stream
produced by :mod:`pikslide.pik.macros` (which already lexes and expands
``#define`` macros).

This is a hand-written parser rather than a generated LALR one, so a few
of pikchr's grammar rules (chiefly around ``position``) are implemented
with small bounded backtracking instead of grammar-level precedence
declarations; see comments at each such spot. The rule shapes and token
semantics themselves are transcribed directly from pikchr's ``pikchr.y``.

Substantially ported from pikchr, Copyright (C) 2020-09-01 by
D. Richard Hipp <drh@sqlite.org>, released under the Zero-Clause BSD
license. See the NOTICE file at the root of this repository.
"""

from __future__ import annotations

from . import ast
from .macros import expand_macros
from .tokens import PikSyntaxError, Token, TokType, is_hex_number, nth_value, numeric_value, unescape_string

_DIR_NAME = {
    TokType.UP: "up",
    TokType.DOWN: "down",
    TokType.LEFT: "left",
    TokType.RIGHT: "right",
}

_NUMPROP_NAME = {
    TokType.WIDTH: "width",
    TokType.HEIGHT: "height",
    TokType.RADIUS: "radius",
    TokType.DIAMETER: "diameter",
    TokType.THICKNESS: "thickness",
}

_BOOLPROP_NAME = {
    TokType.CW: "cw",
    TokType.CCW: "ccw",
    TokType.INVIS: "invis",
    TokType.THICK: "thick",
    TokType.THIN: "thin",
    TokType.SOLID: "solid",
}

_ARROW_KIND = {
    TokType.LARROW: "left",
    TokType.RARROW: "right",
    TokType.LRARROW: "both",
}

_COLORPROP_NAME = {TokType.FILL: "fill", TokType.COLOR: "color"}
_DASHPROP_NAME = {TokType.DASHED: "dashed", TokType.DOTTED: "dotted"}

_TEXTFLAG_NAME = {
    TokType.CENTER: "center",
    TokType.LJUST: "ljust",
    TokType.RJUST: "rjust",
    TokType.ABOVE: "above",
    TokType.BELOW: "below",
    TokType.ITALIC: "italic",
    TokType.BOLD: "bold",
    TokType.MONO: "mono",
    TokType.ALIGNED: "aligned",
    TokType.BIG: "big",
    TokType.SMALL: "small",
    # pikslide ext: docs/grammar.md, Objects (text-flag)
    TokType.MAJOR: "major",
    TokType.MEDIUM: "medium",
    TokType.LARGE: "large",
}

_DOTL_PROP_NAME = {
    TokType.WIDTH: "width",
    TokType.HEIGHT: "height",
    TokType.RADIUS: "radius",
    TokType.DIAMETER: "diameter",
    TokType.THICKNESS: "thickness",
    TokType.DASHED: "dashed",
    TokType.DOTTED: "dotted",
    TokType.FILL: "fill",
    TokType.COLOR: "color",
}

_PSEUDOVAR_NAME = {
    TokType.FILL: "fill",
    TokType.COLOR: "color",
    TokType.THICKNESS: "thickness",
}

_ASSIGN_OP = {
    TokType.ASSIGN: "=",
    TokType.PLUS: "+=",
    TokType.MINUS: "-=",
    TokType.STAR: "*=",
    TokType.SLASH: "/=",
}

_EDGE_TOKENS = {
    TokType.CENTER,
    TokType.EDGEPT,
    TokType.TOP,
    TokType.BOTTOM,
    TokType.START,
    TokType.END,
    TokType.RIGHT,
    TokType.LEFT,
}

_EXPR_START = {
    TokType.NUMBER,
    TokType.ID,
    TokType.LP,
    TokType.MINUS,
    TokType.PLUS,
    TokType.FUNC1,
    TokType.FUNC2,
    TokType.DIST,
    TokType.PLACENAME,
    TokType.THIS,
    TokType.NTH,
    TokType.LAST,
}

# Tokens that can start a `basetype` (docs/grammar.md, Objects): the
# pikchr core (CLASSNAME/STRING/'[') plus pikslide's `shape`/`image` (ext).
_BASETYPE_START = {TokType.CLASSNAME, TokType.STRING, TokType.LB, TokType.SHAPE, TokType.IMAGE}

_OBJECT_START = {TokType.PLACENAME, TokType.THIS, TokType.NTH, TokType.LAST}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    # -- low-level helpers --------------------------------------------------

    def peek(self, offset: int = 0) -> Token | None:
        j = self.i + offset
        return self.toks[j] if j < len(self.toks) else None

    def at(self, *types: TokType) -> bool:
        t = self.peek()
        return t is not None and t.type in types

    def advance(self) -> Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, type_: TokType) -> Token:
        t = self.peek()
        if t is None or t.type != type_:
            self._error(f"expected {type_.name}")
        return self.advance()

    def _error(self, message: str):
        t = self.peek()
        last = self.toks[-1] if self.toks else None
        line = t.line if t is not None else (last.line if last is not None else 0)
        text = t.text if t is not None else ""
        pos = t.pos if t is not None else (last.pos if last is not None else 0)
        file = t.file if t is not None else (last.file if last is not None else None)
        raise PikSyntaxError(message, line, text, pos=pos, file=file)

    def _starts_expr(self) -> bool:
        return self.at(*_EXPR_START)

    def _at_edge_token(self) -> bool:
        return self.at(*_EDGE_TOKENS)

    # -- top level ------------------------------------------------------

    def parse_document(self) -> ast.Document:
        statements = self.parse_statement_list()
        if self.i != len(self.toks):
            self._error("unexpected trailing tokens")
        return ast.Document(statements=statements)

    def parse_statement_list(self) -> list[ast.Statement]:
        stmts: list[ast.Statement] = []
        s = self.parse_statement()
        if s is not None:
            stmts.append(s)
        while self.at(TokType.EOL):
            self.advance()
            s = self.parse_statement()
            if s is not None:
                stmts.append(s)
        return stmts

    def parse_statement(self) -> ast.Statement | None:
        t = self.peek()
        if t is None or t.type in (TokType.EOL, TokType.RB):
            return None

        if t.type in (TokType.UP, TokType.DOWN, TokType.LEFT, TokType.RIGHT):
            self.advance()
            return ast.DirectionStatement(_DIR_NAME[t.type])

        if t.type in (TokType.ID, TokType.FILL, TokType.COLOR, TokType.THICKNESS,
                      TokType.SMALL, TokType.MEDIUM, TokType.LARGE):
            name_tok = self.advance()
            op_tok = self.expect(TokType.ASSIGN)
            value = self.parse_value()
            return ast.AssignStatement(name_tok.text, _ASSIGN_OP[op_tok.code], value)

        if t.type == TokType.PLACENAME:
            nxt = self.peek(1)
            if nxt is not None and nxt.type == TokType.COLON:
                label = self.advance().text
                self.advance()  # COLON
                after = self.peek()
                if after is not None and after.type in _BASETYPE_START:
                    base, attrs = self.parse_unnamed_statement()
                    return ast.ObjectStatement(label=label, base=base, attributes=attrs)
                pos = self.parse_position()
                return ast.LabelPosition(label, pos)
            self._error("expected ':' after label")

        if t.type in _BASETYPE_START:
            base, attrs = self.parse_unnamed_statement()
            return ast.ObjectStatement(label=None, base=base, attributes=attrs)

        if t.type == TokType.PRINT:
            self.advance()
            items = self.parse_print_items()
            return ast.PrintStatement(items)

        if t.type == TokType.ASSERT:
            return self.parse_assert()

        self._error("unexpected token at start of statement")

    def parse_assert(self) -> ast.Statement:
        self.expect(TokType.ASSERT)
        self.expect(TokType.LP)
        mark = self.i
        try:
            left = self.parse_expr()
            self.expect(TokType.EQ)
            right = self.parse_expr()
            self.expect(TokType.RP)
            return ast.AssertExprStatement(left, right)
        except PikSyntaxError:
            self.i = mark
        left_pos = self.parse_position()
        self.expect(TokType.EQ)
        right_pos = self.parse_position()
        self.expect(TokType.RP)
        return ast.AssertPositionStatement(left_pos, right_pos)

    def parse_print_items(self) -> list[ast.Expr | str]:
        items = [self.parse_pritem()]
        while self.at(TokType.COMMA):
            self.advance()
            items.append(self.parse_pritem())
        return items

    def parse_pritem(self) -> ast.Expr | str:
        t = self.peek()
        if t is not None and t.type in _PSEUDOVAR_NAME:
            self.advance()
            return ast.Var(_PSEUDOVAR_NAME[t.type])
        if t is not None and t.type == TokType.STRING:
            self.advance()
            return unescape_string(t.text)
        return self.parse_expr()

    # -- objects ----------------------------------------------------------

    def parse_unnamed_statement(self) -> tuple[ast.Basetype, list[ast.Attribute]]:
        base = self.parse_basetype()
        attrs = self.parse_attribute_list()
        return base, attrs

    def parse_basetype(self) -> ast.Basetype:
        if self.at(TokType.CLASSNAME):
            return ast.ClassBase(self.advance().text)
        if self.at(TokType.STRING):
            text = unescape_string(self.advance().text)
            flags = self.parse_textposition()
            return ast.TextBase(text, flags)
        if self.at(TokType.LB):
            self.advance()
            statements = self.parse_statement_list()
            self.expect(TokType.RB)
            return ast.BlockBase(statements)
        if self.at(TokType.SHAPE):
            self.advance()
            return ast.ShapeBase(self.parse_preset_name())
        if self.at(TokType.IMAGE):
            self.advance()
            path_tok = self.expect(TokType.STRING)
            return ast.ImageBase(unescape_string(path_tok.text))
        self._error("expected an object class, a string, '[', 'shape', or 'image'")

    def parse_preset_name(self) -> str:
        # preset-name ::= ID | CLASSNAME (ext; docs/grammar.md, Objects) --
        # CLASSNAME too, since some preset names ("ellipse", "diamond",
        # "line", "arc") already lex as pikchr class-name tokens. Matched
        # case-insensitively downstream (layout._resolve_preset_name), so
        # an uppercase-led spelling ("ROUNDRECT"), which the lexer can only
        # produce as a PLACENAME, must be accepted here too -- this is the
        # one position right after `shape` where that can't be ambiguous
        # with an object reference.
        if self.at(TokType.ID, TokType.CLASSNAME, TokType.PLACENAME):
            return self.advance().text
        self._error("expected a preset shape name")

    def parse_textposition(self) -> list[str]:
        flags: list[str] = []
        while True:
            t = self.peek()
            if t is None or t.type not in _TEXTFLAG_NAME:
                break
            self.advance()
            flags.append(_TEXTFLAG_NAME[t.type])
        return flags

    def parse_attribute_list(self) -> list[ast.Attribute]:
        attrs: list[ast.Attribute] = []
        if self._starts_expr():
            attrs.append(ast.LeadingDirection(self.parse_relexpr()))
        while True:
            attr = self._try_parse_attribute()
            if attr is None:
                break
            attrs.append(attr)
        return attrs

    def _try_parse_attribute(self) -> ast.Attribute | None:
        t = self.peek()
        if t is None:
            return None
        tt = t.type

        if tt in _NUMPROP_NAME:
            self.advance()
            return ast.NumProperty(_NUMPROP_NAME[tt], self.parse_relexpr())

        if tt in _DASHPROP_NAME:
            self.advance()
            value = self.parse_expr() if self._starts_expr() else None
            return ast.DashProperty(_DASHPROP_NAME[tt], value)

        if tt in _COLORPROP_NAME:
            self.advance()
            return ast.ColorProperty(_COLORPROP_NAME[tt], self.parse_color_value())

        if tt == TokType.GO:
            self.advance()
            if self.at(TokType.UP, TokType.DOWN, TokType.LEFT, TokType.RIGHT):
                return self._parse_go_direction()
            return self._parse_move_heading("go")

        if tt in (TokType.UP, TokType.DOWN, TokType.LEFT, TokType.RIGHT):
            return self._parse_go_direction()

        if tt == TokType.THEN:
            self.advance()
            if self.at(TokType.HEADING) or self.at(TokType.EDGEPT) or self._starts_expr():
                return self._parse_move_heading("then", consumed_keyword=True)
            return ast.Then()

        if tt == TokType.CLOSE:
            self.advance()
            return ast.Close()

        if tt == TokType.CHOP:
            self.advance()
            return ast.Chop()

        if tt == TokType.FROM:
            self.advance()
            return ast.From_(self.parse_position())

        if tt == TokType.TO:
            self.advance()
            return ast.To(self.parse_position())

        if tt in _BOOLPROP_NAME:
            self.advance()
            return ast.BoolProperty(_BOOLPROP_NAME[tt])

        if tt in _ARROW_KIND:
            self.advance()
            return ast.ArrowDirection(_ARROW_KIND[tt])

        if tt == TokType.AT:
            self.advance()
            return ast.At(self.parse_position())

        if tt == TokType.WITH:
            self.advance()
            if self.at(TokType.DOT_E):
                self.advance()
            edge = self.parse_edge()
            self.expect(TokType.AT)
            return ast.With(edge, self.parse_position())

        if tt == TokType.SAME:
            self.advance()
            if self.at(TokType.AS):
                self.advance()
                return ast.Same(self.parse_object())
            return ast.Same(None)

        if tt == TokType.STRING:
            text = unescape_string(self.advance().text)
            flags = self.parse_textposition()
            return ast.TextAttribute(text, flags)

        if tt == TokType.FIT:
            self.advance()
            return ast.Fit()

        if tt == TokType.BEHIND:
            self.advance()
            return ast.Behind(self.parse_object())

        if tt == TokType.ALT:
            self.advance()
            text_tok = self.expect(TokType.STRING)
            return ast.Alt(unescape_string(text_tok.text))

        return None

    def _parse_go_direction(self) -> ast.GoDirection:
        dir_tok = self.advance()
        direction = _DIR_NAME[dir_tok.type]
        if self.at(TokType.UNTIL) or self.at(TokType.EVEN):
            if self.at(TokType.UNTIL):
                self.advance()
                self.expect(TokType.EVEN)
            else:
                self.advance()
            self.expect(TokType.WITH)
            return ast.GoDirection(direction, even_with=self.parse_position())
        return ast.GoDirection(direction, amount=self.parse_optrelexpr())

    def _parse_move_heading(self, keyword: str, consumed_keyword: bool = False) -> ast.MoveHeading:
        # keyword ('then'/'go') token already consumed by the caller.
        amount = self.parse_optrelexpr()
        if self.at(TokType.HEADING):
            self.advance()
            angle = self.parse_expr()
            return ast.MoveHeading(keyword, amount, angle=angle)
        if self.at(TokType.EDGEPT):
            edge_tok = self.advance()
            return ast.MoveHeading(keyword, amount, edge=edge_tok.edge)
        self._error(f"expected 'heading' or a compass point after '{keyword}'")

    # -- expressions --------------------------------------------------------

    def parse_expr(self, min_prec: int = 0) -> ast.Expr:
        left = self.parse_unary()
        while True:
            t = self.peek()
            if t is None:
                break
            if t.type in (TokType.PLUS, TokType.MINUS):
                prec = 1
                op = "+" if t.type == TokType.PLUS else "-"
            elif t.type in (TokType.STAR, TokType.SLASH):
                prec = 2
                op = "*" if t.type == TokType.STAR else "/"
            else:
                break
            if prec < min_prec:
                break
            self.advance()
            right = self.parse_expr(prec + 1)
            left = ast.BinOp(op, left, right)
        return left

    def parse_unary(self) -> ast.Expr:
        if self.at(TokType.MINUS):
            self.advance()
            return ast.UnaryOp("-", self.parse_unary())
        if self.at(TokType.PLUS):
            self.advance()
            return ast.UnaryOp("+", self.parse_unary())
        return self.parse_atom()

    def parse_atom(self) -> ast.Expr:
        t = self.peek()
        if t is None:
            self._error("expected an expression")

        if t.type == TokType.NUMBER:
            self.advance()
            if is_hex_number(t.text):
                return ast.HexColor(int(numeric_value(t.text)))
            return ast.Num(numeric_value(t.text))

        if t.type == TokType.ID:
            self.advance()
            return ast.Var(t.text)

        if t.type == TokType.LP:
            self.advance()
            if self.at(*_PSEUDOVAR_NAME) and self.peek(1) is not None and self.peek(1).type == TokType.RP:
                name_tok = self.advance()
                self.advance()  # RP
                return ast.Var(_PSEUDOVAR_NAME[name_tok.type])
            e = self.parse_expr()
            self.expect(TokType.RP)
            return e

        if t.type == TokType.FUNC1:
            self.advance()
            self.expect(TokType.LP)
            a = self.parse_expr()
            self.expect(TokType.RP)
            return ast.FuncCall(t.code, [a])

        if t.type == TokType.FUNC2:
            self.advance()
            self.expect(TokType.LP)
            a = self.parse_expr()
            self.expect(TokType.COMMA)
            b = self.parse_expr()
            self.expect(TokType.RP)
            return ast.FuncCall(t.code, [a, b])

        if t.type == TokType.DIST:
            self.advance()
            self.expect(TokType.LP)
            p1 = self.parse_position()
            self.expect(TokType.COMMA)
            p2 = self.parse_position()
            self.expect(TokType.RP)
            return ast.Dist(p1, p2)

        if t.type in _OBJECT_START:
            place = self.parse_place2()
            if self.at(TokType.DOT_XY):
                self.advance()
                if self.at(TokType.X):
                    self.advance()
                    return ast.PlaceCoord(place, "x")
                if self.at(TokType.Y):
                    self.advance()
                    return ast.PlaceCoord(place, "y")
                self._error("expected 'x' or 'y' after '.'")
            if self.at(TokType.DOT_L):
                if isinstance(place, ast.ObjectEdge) and place.edge is None:
                    self.advance()
                    prop_tok = self.peek()
                    if prop_tok is None or prop_tok.type not in _DOTL_PROP_NAME:
                        self._error("expected a property name after '.'")
                    self.advance()
                    return ast.ObjectProp(place.obj, _DOTL_PROP_NAME[prop_tok.type])
                self._error("'.property' is not valid on an edge or vertex reference")
            self._error("expected '.x', '.y', or '.property' after an object reference")

        self._error("expected a number, variable, or expression")

    def parse_relexpr(self) -> ast.RelExpr:
        e = self.parse_expr()
        if self.at(TokType.PERCENT):
            self.advance()
            return ast.RelExpr(percent=e)
        return ast.RelExpr(abs=e)

    def parse_optrelexpr(self) -> ast.RelExpr:
        if self._starts_expr():
            return self.parse_relexpr()
        return ast.RelExpr()

    def parse_value(self) -> ast.Expr:
        """``value`` (ext): the right-hand side of an assignment -- a
        string, or a colour value. A colour name (e.g. ``fill red``) is an
        ordinary lowercase `ID`/`Var`, resolved against the prelude at
        evaluation time (docs/grammar.md, Colours); pikslide does not
        special-case a bare `PLACENAME` as a colour name the way pikchr
        does, since pikslide is not aiming for pikchr compatibility
        (docs/spec.md SS2)."""
        if self.at(TokType.STRING):
            return ast.StrLit(unescape_string(self.advance().text))
        return self.parse_color_value()

    def parse_color_value(self) -> ast.Expr:
        """``color-value`` (ext): a colour base, with an optional
        ``lighter``/``darker`` adjustment. Also used directly wherever a
        plain number is just as valid a result (``boxwid = 1.2``) -- the
        distinction between "this holds a number" and "this holds a
        colour" is made by what the expression evaluates to (a bare hex
        literal is a colour, a decimal literal is a number), not by which
        grammar rule parsed it; see ast.HexColor."""
        base = self._parse_color_base()
        if self.at(TokType.LIGHTER, TokType.DARKER):
            op = "lighter" if self.advance().type == TokType.LIGHTER else "darker"
            amount = self.parse_expr()
            self.expect(TokType.PERCENT)
            return ast.ColorMod(base, op, amount)
        return base

    def _parse_color_base(self) -> ast.Expr:
        if self.at(TokType.THEME):
            self.advance()
            slot_tok = self.expect(TokType.STRING)
            return ast.ThemeColor(unescape_string(slot_tok.text))
        if self.at(TokType.NOCOLOR):
            self.advance()
            return ast.NoColor()
        return self.parse_expr()

    # -- positions / places / objects ---------------------------------------

    def parse_position(self) -> ast.Position:
        if self.at(TokType.LP):
            return self._parse_paren_position()
        mark = self.i
        try:
            return self._parse_expr_led_position()
        except PikSyntaxError:
            self.i = mark
        return self._parse_place_led_position()

    def _parse_paren_position(self) -> ast.Position:
        self.expect(TokType.LP)
        p1 = self.parse_position()
        if self.at(TokType.COMMA):
            self.advance()
            p2 = self.parse_position()
            self.expect(TokType.RP)
            return ast.XYFromPositions(p1, p2)
        self.expect(TokType.RP)
        return p1

    def _parse_expr_led_position(self) -> ast.Position:
        x = self.parse_expr()

        if self.at(TokType.COMMA):
            self.advance()
            y = self.parse_expr()
            return ast.Coord(x, y)

        if self.at(TokType.ABOVE):
            self.advance()
            return ast.DirectionOffset("above", x, self.parse_position())
        if self.at(TokType.BELOW):
            self.advance()
            return ast.DirectionOffset("below", x, self.parse_position())
        if self.at(TokType.LEFT):
            self.advance()
            self.expect(TokType.OF)
            return ast.DirectionOffset("left of", x, self.parse_position())
        if self.at(TokType.RIGHT):
            self.advance()
            self.expect(TokType.OF)
            return ast.DirectionOffset("right of", x, self.parse_position())

        # Note: pikchr's grammar also has "expr ON HEADING ... " variants, but
        # "on" is not present in pik_keywords, so the upstream tokenizer never
        # actually produces that token either -- those rules are unreachable
        # in real pikchr, and are intentionally not supported here.
        if self.at(TokType.HEADING):
            self.advance()
            if self._at_edge_token():
                edge = self.parse_edge()
                self.expect(TokType.OF)
                return ast.HeadingOffset(x, edge=edge, angle=None, base=self.parse_position())
            angle = self.parse_expr()
            self.expect(TokType.FROM)
            return ast.HeadingOffset(x, edge=None, angle=angle, base=self.parse_position())

        if self._at_edge_token():
            edge = self.parse_edge()
            self.expect(TokType.OF)
            return ast.HeadingOffset(x, edge=edge, angle=None, base=self.parse_position())

        if self.at(TokType.WAY):
            self.advance()
            self.expect(TokType.BETWEEN)
            p1 = self.parse_position()
            self.expect(TokType.AND)
            p2 = self.parse_position()
            return ast.Between(x, p1, p2)
        if self.at(TokType.BETWEEN):
            self.advance()
            p1 = self.parse_position()
            self.expect(TokType.AND)
            p2 = self.parse_position()
            return ast.Between(x, p1, p2)
        if self.at(TokType.OF):
            self.advance()
            self.expect(TokType.THE)
            self.expect(TokType.WAY)
            self.expect(TokType.BETWEEN)
            p1 = self.parse_position()
            self.expect(TokType.AND)
            p2 = self.parse_position()
            return ast.Between(x, p1, p2)
        if self.at(TokType.LT):
            self.advance()
            p1 = self.parse_position()
            self.expect(TokType.COMMA)
            p2 = self.parse_position()
            self.expect(TokType.GT)
            return ast.Between(x, p1, p2)

        self._error("expected a position expression after the leading number")

    def _parse_place_led_position(self) -> ast.Position:
        place = self.parse_place()
        if self.at(TokType.PLUS) or self.at(TokType.MINUS):
            op = "+" if self.at(TokType.PLUS) else "-"
            self.advance()
            if self.at(TokType.LP):
                self.advance()
                dx = self.parse_expr()
                self.expect(TokType.COMMA)
                dy = self.parse_expr()
                self.expect(TokType.RP)
            else:
                dx = self.parse_expr()
                self.expect(TokType.COMMA)
                dy = self.parse_expr()
            return ast.OffsetPosition(place, op, dx, dy)
        return ast.PlacePosition(place)

    def parse_place(self) -> ast.Place:
        if self._at_edge_token():
            mark = self.i
            edge = self.parse_edge()
            if self.at(TokType.OF):
                self.advance()
                return ast.ObjectEdge(self.parse_object(), edge)
            self.i = mark
        return self.parse_place2()

    def parse_place2(self) -> ast.Place:
        if self.at(TokType.NTH):
            mark = self.i
            n_tok = self.advance()
            if self.at(TokType.VERTEX):
                self.advance()
                self.expect(TokType.OF)
                return ast.NthVertex(nth_value(n_tok.text), self.parse_object())
            self.i = mark
        obj = self.parse_object()
        if self.at(TokType.DOT_E):
            self.advance()
            return ast.ObjectEdge(obj, self.parse_edge())
        return ast.ObjectEdge(obj, None)

    def parse_edge(self) -> str:
        t = self.peek()
        if t is None or t.type not in _EDGE_TOKENS:
            self._error("expected an edge name (n, s, e, w, top, bottom, start, end, center, ...)")
        self.advance()
        return t.edge

    def parse_object(self) -> ast.ObjectRef:
        n = self.parse_nth()
        if n is not None:
            if self.at(TokType.OF) or self.at(TokType.IN):
                self.advance()
                n.container = self.parse_object()
            return n
        return self.parse_objectname()

    def parse_nth(self) -> ast.NthRef | None:
        if self.at(TokType.NTH):
            n_tok = self.advance()
            ordv = nth_value(n_tok.text)
            neg = False
            if self.at(TokType.LAST):
                self.advance()
                neg = True
            if self.at(TokType.CLASSNAME):
                cn = self.advance().text
                return ast.NthRef(-ordv if neg else ordv, cn)
            self.expect(TokType.LB)
            self.expect(TokType.RB)
            return ast.NthRef(-ordv if neg else ordv, None)
        if self.at(TokType.LAST):
            self.advance()
            if self.at(TokType.CLASSNAME):
                cn = self.advance().text
                return ast.NthRef(-1, cn)
            if self.at(TokType.LB):
                self.advance()
                self.expect(TokType.RB)
                return ast.NthRef(-1, None)
            return ast.NthRef(-1, None)
        return None

    def parse_objectname(self) -> ast.ObjectRef:
        if self.at(TokType.THIS):
            self.advance()
            return ast.ThisRef()
        name = self.expect(TokType.PLACENAME).text
        path = [name]
        while self.at(TokType.DOT_U):
            self.advance()
            path.append(self.expect(TokType.PLACENAME).text)
        return ast.NameRef(path)


def parse(text: str, base_dir: str = ".", include_paths: list[str] | None = None) -> ast.Document:
    """Parse pikchr source text into a :class:`pikslide.pik.ast.Document` tree.

    `base_dir` is the source file's own directory (docs/spec.md SS3.6): an
    `include "path"` resolves against it first, then against each of
    `include_paths` in order (ext, for a future `--include-path`)."""
    tokens, macros = expand_macros(text, base_dir, include_paths)
    doc = Parser(tokens).parse_document()
    doc.macros = macros
    return doc

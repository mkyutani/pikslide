"""Tokenizer for the diagram language."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokType(Enum):
    EOF = auto()
    EOL = auto()
    STRING = auto()
    NUMBER = auto()
    NTH = auto()
    ID = auto()
    PLACENAME = auto()
    CLASSNAME = auto()
    CODEBLOCK = auto()

    LP = auto()
    RP = auto()
    LB = auto()
    RB = auto()
    COMMA = auto()
    COLON = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()

    ASSIGN = auto()
    EQ = auto()
    LT = auto()
    GT = auto()

    LARROW = auto()
    RARROW = auto()
    LRARROW = auto()

    DOT_E = auto()
    DOT_L = auto()
    DOT_XY = auto()
    DOT_U = auto()

    # Keyword-carrying token types (one per distinct grammar terminal)
    ABOVE = auto()
    FUNC1 = auto()
    FUNC2 = auto()
    ALIGNED = auto()
    AND = auto()
    AS = auto()
    ASSERT = auto()
    AT = auto()
    BEHIND = auto()
    BELOW = auto()
    BETWEEN = auto()
    BIG = auto()
    BOLD = auto()
    EDGEPT = auto()
    BOTTOM = auto()
    CCW = auto()
    CENTER = auto()
    CHOP = auto()
    CLOSE = auto()
    COLOR = auto()
    CW = auto()
    DASHED = auto()
    DEFINE = auto()
    DIAMETER = auto()
    DIST = auto()
    DOTTED = auto()
    DOWN = auto()
    END = auto()
    EVEN = auto()
    FILL = auto()
    FIT = auto()
    FROM = auto()
    GO = auto()
    HEADING = auto()
    HEIGHT = auto()
    IN = auto()
    INVIS = auto()
    ITALIC = auto()
    LAST = auto()
    LEFT = auto()
    LJUST = auto()
    MONO = auto()
    NTH_WORD = auto()  # 'first' -- lexes as NTH, kept separate only for clarity
    OF = auto()
    PRINT = auto()
    RADIUS = auto()
    RIGHT = auto()
    RJUST = auto()
    SAME = auto()
    SMALL = auto()
    SOLID = auto()
    START = auto()
    THE = auto()
    THEN = auto()
    THICK = auto()
    THICKNESS = auto()
    THIN = auto()
    THIS = auto()
    TO = auto()
    TOP = auto()
    UNTIL = auto()
    UP = auto()
    VERTEX = auto()
    WAY = auto()
    WIDTH = auto()
    WITH = auto()
    X = auto()
    Y = auto()

    # Extensions -- see docs/grammar.md, "Reserved words"
    SHAPE = auto()
    IMAGE = auto()
    INCLUDE = auto()
    ALT = auto()
    MAJOR = auto()
    MEDIUM = auto()
    LARGE = auto()
    THEME = auto()
    LIGHTER = auto()
    DARKER = auto()
    NOCOLOR = auto()  # "none" / "off"
    CONNECTOR = auto()  # reserved for a future object class; not used yet

    ERROR = auto()
    WHITESPACE = auto()
    PARAMETER = auto()


DIR_RIGHT, DIR_DOWN, DIR_LEFT, DIR_UP = 0, 1, 2, 3

FN1 = {"abs", "cos", "int", "sin", "sqrt"}
FN2 = {"max", "min"}

CLASS_NAMES = {
    "arc", "arrow", "box", "circle", "cylinder", "diamond", "dot",
    "ellipse", "file", "line", "move", "oval", "spline", "text",
}

# name -> (TokType, eCode, eEdge)
KEYWORDS: dict[str, tuple[TokType, object, str | None]] = {
    "above": (TokType.ABOVE, None, None),
    "abs": (TokType.FUNC1, "abs", None),
    "aligned": (TokType.ALIGNED, None, None),
    "and": (TokType.AND, None, None),
    "as": (TokType.AS, None, None),
    "assert": (TokType.ASSERT, None, None),
    "at": (TokType.AT, None, None),
    "behind": (TokType.BEHIND, None, None),
    "below": (TokType.BELOW, None, None),
    "between": (TokType.BETWEEN, None, None),
    "big": (TokType.BIG, None, None),
    "bold": (TokType.BOLD, None, None),
    "bot": (TokType.EDGEPT, None, "s"),
    "bottom": (TokType.BOTTOM, None, "s"),
    "c": (TokType.EDGEPT, None, "c"),
    "ccw": (TokType.CCW, None, None),
    "center": (TokType.CENTER, None, "c"),
    "chop": (TokType.CHOP, None, None),
    "close": (TokType.CLOSE, None, None),
    "color": (TokType.COLOR, None, None),
    "cos": (TokType.FUNC1, "cos", None),
    "cw": (TokType.CW, None, None),
    "dashed": (TokType.DASHED, None, None),
    "define": (TokType.DEFINE, None, None),
    "diameter": (TokType.DIAMETER, None, None),
    "dist": (TokType.DIST, None, None),
    "dotted": (TokType.DOTTED, None, None),
    "down": (TokType.DOWN, DIR_DOWN, None),
    "e": (TokType.EDGEPT, None, "e"),
    "east": (TokType.EDGEPT, None, "e"),
    "end": (TokType.END, None, "end"),
    "even": (TokType.EVEN, None, None),
    "fill": (TokType.FILL, None, None),
    "first": (TokType.NTH, None, None),
    "fit": (TokType.FIT, None, None),
    "from": (TokType.FROM, None, None),
    "go": (TokType.GO, None, None),
    "heading": (TokType.HEADING, None, None),
    "height": (TokType.HEIGHT, None, None),
    "ht": (TokType.HEIGHT, None, None),
    "in": (TokType.IN, None, None),
    "int": (TokType.FUNC1, "int", None),
    "invis": (TokType.INVIS, None, None),
    "invisible": (TokType.INVIS, None, None),
    "italic": (TokType.ITALIC, None, None),
    "last": (TokType.LAST, None, None),
    "left": (TokType.LEFT, DIR_LEFT, "w"),
    "ljust": (TokType.LJUST, None, None),
    "max": (TokType.FUNC2, "max", None),
    "min": (TokType.FUNC2, "min", None),
    "mono": (TokType.MONO, None, None),
    "monospace": (TokType.MONO, None, None),
    "n": (TokType.EDGEPT, None, "n"),
    "ne": (TokType.EDGEPT, None, "ne"),
    "north": (TokType.EDGEPT, None, "n"),
    "nw": (TokType.EDGEPT, None, "nw"),
    "of": (TokType.OF, None, None),
    "previous": (TokType.LAST, None, None),
    "print": (TokType.PRINT, None, None),
    "rad": (TokType.RADIUS, None, None),
    "radius": (TokType.RADIUS, None, None),
    "right": (TokType.RIGHT, DIR_RIGHT, "e"),
    "rjust": (TokType.RJUST, None, None),
    "s": (TokType.EDGEPT, None, "s"),
    "same": (TokType.SAME, None, None),
    "se": (TokType.EDGEPT, None, "se"),
    "sin": (TokType.FUNC1, "sin", None),
    "small": (TokType.SMALL, None, None),
    "solid": (TokType.SOLID, None, None),
    "south": (TokType.EDGEPT, None, "s"),
    "sqrt": (TokType.FUNC1, "sqrt", None),
    "start": (TokType.START, None, "start"),
    "sw": (TokType.EDGEPT, None, "sw"),
    "t": (TokType.TOP, None, "n"),
    "the": (TokType.THE, None, None),
    "then": (TokType.THEN, None, None),
    "thick": (TokType.THICK, None, None),
    "thickness": (TokType.THICKNESS, None, None),
    "thin": (TokType.THIN, None, None),
    "this": (TokType.THIS, None, None),
    "to": (TokType.TO, None, None),
    "top": (TokType.TOP, None, "n"),
    "until": (TokType.UNTIL, None, None),
    "up": (TokType.UP, DIR_UP, None),
    "vertex": (TokType.VERTEX, None, None),
    "w": (TokType.EDGEPT, None, "w"),
    "way": (TokType.WAY, None, None),
    "west": (TokType.EDGEPT, None, "w"),
    "wid": (TokType.WIDTH, None, None),
    "width": (TokType.WIDTH, None, None),
    "with": (TokType.WITH, None, None),
    "x": (TokType.X, None, None),
    "y": (TokType.Y, None, None),

    # Extensions -- reserved words the language adds; see docs/grammar.md, "Reserved words".
    "shape": (TokType.SHAPE, None, None),
    "image": (TokType.IMAGE, None, None),
    "include": (TokType.INCLUDE, None, None),
    "alt": (TokType.ALT, None, None),
    "major": (TokType.MAJOR, None, None),
    "medium": (TokType.MEDIUM, None, None),
    "large": (TokType.LARGE, None, None),
    "theme": (TokType.THEME, None, None),
    "lighter": (TokType.LIGHTER, None, None),
    "darker": (TokType.DARKER, None, None),
    "none": (TokType.NOCOLOR, None, None),
    "off": (TokType.NOCOLOR, None, None),
    "connector": (TokType.CONNECTOR, None, None),  # reserved; not used yet
}

ENTITIES = [
    ("&rightarrow;", TokType.RARROW),
    ("&rarr;", TokType.RARROW),
    ("&leftarrow;", TokType.LARROW),
    ("&larr;", TokType.LARROW),
    ("&leftrightarrow;", TokType.LRARROW),
]

_UNIT_DIVISORS = {"cm": 2.54, "mm": 25.4, "px": 96, "pt": 72, "pc": 6, "in": 1}


def _is_alnum_ascii(c: str) -> bool:
    return ("0" <= c <= "9") or ("a" <= c <= "z") or ("A" <= c <= "Z")


@dataclass
class Token:
    type: TokType
    text: str
    pos: int
    line: int
    code: object = None   # eCode: sub-operator for ASSIGN, direction id, fn name, ordinal...
    edge: str | None = None  # eEdge: compass/edge tag for EDGEPT-like tokens
    file: str | None = None
    """Which file this token came from (docs/spec.md SS5: an error names
    the file it's actually in) -- `None` for the main source text, an
    included file's resolved path otherwise. Set once, after lexing
    (`Lexer.tokenize()`'s own `self.file`, the same for every token in one
    lex pass), not per-token at construction."""


def column_at(text: str, pos: int) -> int:
    """1-based column for a character offset `pos` into `text` (docs/
    spec.md SS5). `pos` is always relative to whichever text actually
    produced the token at that offset -- the main source, or (for a
    token from an `include`d file) that file's own text, never the outer
    file's -- see `Token.file`."""
    line_start = text.rfind("\n", 0, pos) + 1  # 0 if no earlier newline (rfind -1, +1)
    return pos - line_start + 1


class PikSyntaxError(Exception):
    def __init__(self, message: str, line: int, text: str = "", pos: int = 0, file: str | None = None):
        super().__init__(f"line {line}: {message}" + (f" near {text!r}" if text else ""))
        self.message = message
        self.line = line
        self.text = text
        self.pos = pos
        """Character offset into whichever text is at `.file` (the main
        source if `None`) -- for `column_at()`, at display time."""
        self.file = file
        """The file this error is actually in (docs/spec.md SS5), when it
        differs from the main source being parsed -- an included file's
        resolved path. `None` means the main source itself."""


def format_syntax_error(err: PikSyntaxError, main_path: str, main_text: str) -> str:
    """`file:line:col: message`, the source line, and a caret under the
    error position (docs/spec.md SS5): "every error carries file:line:
    column, the source line, and a caret; the file is the included one
    when the error is inside an include". `err.file`, when set, is read
    again here for its own source line -- not cached anywhere, since a
    diagnostic is the rare path, not a hot one.

    `main_path` is only a display name for `err.file is None`."""
    if err.file is None:
        path, text = main_path, main_text
    else:
        path = err.file
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            text = ""
    col = column_at(text, err.pos) if text else 1
    header = f"{path}:{err.line}:{col}: {err.message}" + (f" (near {err.text!r})" if err.text else "")
    lines = text.split("\n")
    source_line = lines[err.line - 1] if text and 0 < err.line <= len(lines) else None
    if source_line is None:
        return header
    return f"{header}\n{source_line}\n{' ' * (col - 1)}^"


def unescape_string(raw: str) -> str:
    """Strip the surrounding quotes from a STRING token's raw text and
    unescape ``\\"``/``\\\\``. Lives here (not in parser.py, where it used
    to) so macros.py can use it too, for `include "path"` (ext), without a
    circular import (parser.py already imports from macros.py)."""
    inner = raw[1:-1]
    return inner.replace('\\"', '"').replace("\\\\", "\\")


def is_hex_number(token_text: str) -> bool:
    """True for a NUMBER token spelled ``0x...``/``0X...`` -- pikslide (ext)
    treats these as color literals, not plain numbers; see
    docs/spec.md SS2 and docs/grammar.md, Colors."""
    return len(token_text) >= 3 and token_text[0] == "0" and token_text[1] in "xX"


def numeric_value(token_text: str) -> float:
    """Parse a NUMBER token's text into inches."""
    if is_hex_number(token_text):
        return float(int(token_text[2:], 16))
    suffix = token_text[-2:] if len(token_text) >= 2 else ""
    if suffix in _UNIT_DIVISORS:
        num_part = token_text[:-2]
    else:
        num_part = token_text
        suffix = None
    value = float(num_part)
    if suffix is not None:
        value = value / _UNIT_DIVISORS[suffix]
    return value


def nth_value(token_text: str) -> int:
    """'2nd' -> 2, '5th' -> 5, 'first' -> 1."""
    i = 0
    neg = False
    if i < len(token_text) and token_text[i] == "-":
        neg = True
        i += 1
    start = i
    while i < len(token_text) and token_text[i].isdigit():
        i += 1
    if i == start:
        return 1 if token_text == "first" else 0
    val = int(token_text[start:i])
    return -val if neg else val


class Lexer:
    """Splits raw diagram source text into a flat list of Tokens.

    This does not perform macro expansion; see :mod:`pikslide.pik.macros`.
    """

    def __init__(self, text: str, file: str | None = None):
        self.text = text
        self.n = len(text)
        self.file = file
        """Which file `text` came from (docs/spec.md SS5) -- `None` for
        the main source; an included file's resolved path otherwise. Set
        on every token this lexer produces, and on any PikSyntaxError it
        raises."""

    def tokenize(self) -> list[Token]:
        out: list[Token] = []
        i = 0
        line = 1
        while i < self.n:
            tok, length, _ = self._lex_one(i, line)
            if tok.type == TokType.ERROR:
                raise PikSyntaxError(
                    "unrecognized token", line, self.text[i : i + max(length, 1)], pos=i, file=self.file
                )
            if tok.type != TokType.WHITESPACE:
                tok.file = self.file
                out.append(tok)
            # Count newlines in the consumed span rather than trusting a
            # per-branch "next line" value: '{...}' code blocks, block
            # comments, and backslash-continuations can all span lines.
            line += self.text.count("\n", i, i + length)
            i += length
        return out

    def _lex_one(self, i: int, line: int) -> tuple[Token, int, int]:
        z = self.text
        n = self.n
        c = z[i]

        if c == "\\":
            j = i + 1
            while j < n and z[j] in " \t\r":
                j += 1
            if j < n and z[j] == "\n":
                return Token(TokType.WHITESPACE, z[i : j + 1], i, line), j + 1 - i, line + 1
            return Token(TokType.ERROR, c, i, line), 1, line

        if c == ";" or c == "\n":
            return Token(TokType.EOL, c, i, line), 1, line

        if c == '"':
            j = i + 1
            while j < n:
                cj = z[j]
                if cj == "\\":
                    if j + 1 >= n:
                        break
                    j += 2
                    continue
                if cj == '"':
                    return Token(TokType.STRING, z[i : j + 1], i, line), j + 1 - i, line
                j += 1
            raise PikSyntaxError("unterminated string literal", line, z[i : min(j, n)], pos=i, file=self.file)

        if c in " \t\f\r":
            j = i + 1
            while j < n and z[j] in " \t\r\f":
                j += 1
            return Token(TokType.WHITESPACE, z[i:j], i, line), j - i, line

        if c == "#":
            j = i + 1
            while j < n and z[j] != "\n":
                j += 1
            return Token(TokType.WHITESPACE, z[i:j], i, line), j - i, line

        if c == "/":
            if i + 1 < n and z[i + 1] == "*":
                j = i + 2
                while j + 1 < n and not (z[j] == "*" and z[j + 1] == "/"):
                    j += 1
                if j + 1 < n:
                    return Token(TokType.WHITESPACE, z[i : j + 2], i, line), j + 2 - i, line
                raise PikSyntaxError("unterminated block comment", line, pos=i, file=self.file)
            if i + 1 < n and z[i + 1] == "/":
                j = i + 2
                while j < n and z[j] != "\n":
                    j += 1
                return Token(TokType.WHITESPACE, z[i:j], i, line), j - i, line
            if i + 1 < n and z[i + 1] == "=":
                return Token(TokType.ASSIGN, "/=", i, line, code=TokType.SLASH), 2, line
            return Token(TokType.SLASH, "/", i, line), 1, line

        if c == "+":
            if i + 1 < n and z[i + 1] == "=":
                return Token(TokType.ASSIGN, "+=", i, line, code=TokType.PLUS), 2, line
            return Token(TokType.PLUS, "+", i, line), 1, line

        if c == "*":
            if i + 1 < n and z[i + 1] == "=":
                return Token(TokType.ASSIGN, "*=", i, line, code=TokType.STAR), 2, line
            return Token(TokType.STAR, "*", i, line), 1, line

        if c == "%":
            return Token(TokType.PERCENT, c, i, line), 1, line
        if c == "(":
            return Token(TokType.LP, c, i, line), 1, line
        if c == ")":
            return Token(TokType.RP, c, i, line), 1, line
        if c == "[":
            return Token(TokType.LB, c, i, line), 1, line
        if c == "]":
            return Token(TokType.RB, c, i, line), 1, line
        if c == ",":
            return Token(TokType.COMMA, c, i, line), 1, line
        if c == ":":
            return Token(TokType.COLON, c, i, line), 1, line
        if c == ">":
            return Token(TokType.GT, c, i, line), 1, line

        if c == "=":
            if i + 1 < n and z[i + 1] == "=":
                return Token(TokType.EQ, "==", i, line), 2, line
            return Token(TokType.ASSIGN, "=", i, line, code=TokType.ASSIGN), 1, line

        if c == "-":
            if i + 1 < n and z[i + 1] == ">":
                return Token(TokType.RARROW, "->", i, line), 2, line
            if i + 1 < n and z[i + 1] == "=":
                return Token(TokType.ASSIGN, "-=", i, line, code=TokType.MINUS), 2, line
            return Token(TokType.MINUS, "-", i, line), 1, line

        if c == "<":
            if i + 1 < n and z[i + 1] == "-":
                if i + 2 < n and z[i + 2] == ">":
                    return Token(TokType.LRARROW, "<->", i, line), 3, line
                return Token(TokType.LARROW, "<-", i, line), 2, line
            return Token(TokType.LT, c, i, line), 1, line

        if c == "←":  # unicode leftwards arrow (UTF-8: e2 86 90)
            return Token(TokType.LARROW, c, i, line), 1, line
        if c == "→":
            return Token(TokType.RARROW, c, i, line), 1, line
        if c == "↔":
            return Token(TokType.LRARROW, c, i, line), 1, line

        if c == "{":
            j = i + 1
            depth = 1
            while j < n and depth > 0:
                tok, length, _ = self._lex_one(j, line)
                if length == 1:
                    if z[j] == "{":
                        depth += 1
                    elif z[j] == "}":
                        depth -= 1
                j += length
            if depth != 0:
                raise PikSyntaxError("unterminated macro code block", line, pos=i, file=self.file)
            return Token(TokType.CODEBLOCK, z[i:j], i, line), j - i, line

        if c == "&":
            for entity, ttype in ENTITIES:
                if z[i : i + len(entity)] == entity:
                    return Token(ttype, entity, i, line), len(entity), line
            return Token(TokType.ERROR, c, i, line), 1, line

        if c == "." :
            c1 = z[i + 1] if i + 1 < n else "\0"
            if c1.islower() and c1.isascii():
                j = i + 2
                while j < n and "a" <= z[j] <= "z":
                    j += 1
                word = z[i + 1 : j]
                found = KEYWORDS.get(word)
                if found and (found[2] is not None or found[0] in (TokType.EDGEPT, TokType.START, TokType.END)):
                    return Token(TokType.DOT_E, z[i:i+1], i, line), 1, line
                if found and found[0] in (TokType.X, TokType.Y):
                    return Token(TokType.DOT_XY, z[i:i+1], i, line), 1, line
                return Token(TokType.DOT_L, z[i:i+1], i, line), 1, line
            if c1.isdigit():
                pass  # fall through to number handling below
            elif c1.isupper() and c1.isascii():
                return Token(TokType.DOT_U, z[i:i+1], i, line), 1, line
            else:
                return Token(TokType.ERROR, c, i, line), 1, line

        if c.isdigit() or c == ".":
            return self._lex_number(i, line)

        if "a" <= c <= "z":
            j = i + 1
            while j < n and (_is_alnum_ascii(z[j]) or z[j] == "_"):
                j += 1
            word = z[i:j]
            found = KEYWORDS.get(word)
            if found:
                ttype, code, edge = found
                return Token(ttype, word, i, line, code=code, edge=edge), j - i, line
            if word in CLASS_NAMES:
                return Token(TokType.CLASSNAME, word, i, line), j - i, line
            return Token(TokType.ID, word, i, line), j - i, line

        if "A" <= c <= "Z":
            j = i + 1
            while j < n and (_is_alnum_ascii(z[j]) or z[j] == "_"):
                j += 1
            return Token(TokType.PLACENAME, z[i:j], i, line), j - i, line

        if c == "$" and i + 1 < n and z[i + 1] in "123456789" and not (i + 2 < n and z[i + 2].isdigit()):
            return Token(TokType.PARAMETER, z[i : i + 2], i, line, code=int(z[i + 1]) - 1), 2, line

        if c in "_$@":
            j = i + 1
            while j < n and (_is_alnum_ascii(z[j]) or z[j] == "_"):
                j += 1
            return Token(TokType.ID, z[i:j], i, line), j - i, line

        return Token(TokType.ERROR, c, i, line), 1, line

    def _lex_number(self, i: int, line: int) -> tuple[Token, int, int]:
        z = self.text
        n = self.n
        j = i
        is_int = True
        if z[j] != ".":
            j += 1
            while j < n and z[j].isdigit():
                j += 1
            if j - i == 1 and j < n and z[j] in "xX":
                j += 1
                while j < n and (z[j].isdigit() or z[j].lower() in "abcdef"):
                    j += 1
                return Token(TokType.NUMBER, z[i:j], i, line), j - i, line
        if j < n and z[j] == ".":
            is_int = False
            j += 1
            while j < n and z[j].isdigit():
                j += 1
        if j < n and z[j] in "eE":
            before = j
            k = j + 1
            if k < n and z[k] in "+-":
                k += 1
            if k < n and z[k].isdigit():
                is_int = False
                j = k
                while j < n and z[j].isdigit():
                    j += 1
            else:
                j = before
        c = z[j] if j < n else "\0"
        c2 = z[j + 1] if j + 1 < n else "\0"
        if is_int and ((c, c2) in {("t", "h"), ("r", "d"), ("n", "d"), ("s", "t")}):
            return Token(TokType.NTH, z[i : j + 2], i, line), j + 2 - i, line
        if (c, c2) in {("i", "n"), ("c", "m"), ("m", "m"), ("p", "t"), ("p", "x"), ("p", "c")}:
            j += 2
        return Token(TokType.NUMBER, z[i:j], i, line), j - i, line

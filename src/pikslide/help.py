"""`pikslide --help TOPIC`: the manuals, lists and a short help for every
keyword, for people and for LLMs driving pikslide.

TOPIC is a manual (`grammar`, `spec`: docs/*.md), a list (`keywords`,
`classes`, `attributes`, `flags`, `colors`, `shapes`, `variables`,
`prelude`), or any keyword or built-in variable (`box`, `chop`, `fill`,
`boxwid`, ...). Lists are built from the source itself -- the lexer's
keyword table, the prelude, the preset shape names -- so they can't go
stale; the keyword entries below are written by hand, and a test checks
that every reserved word has one.

Printed to a terminal, the text is formatted (bold headings, color
swatches) and long output goes through $PAGER; piped, it is plain text,
and the manuals are their Markdown source as is.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources

from .pik.layout import PRESET_NAMES
from .pik.tokens import CLASS_NAMES, KEYWORDS

# ---------------------------------------------------------------------------
# Keyword entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    names: tuple[str, ...]
    """The words this entry answers to; the first is its heading."""
    summary: str
    """One line, for the `keywords`/`classes`/`attributes` lists."""
    synopsis: tuple[str, ...] = ()
    body: str = ""
    sections: tuple[tuple[str, str], ...] = ()
    """Further (HEADING, text) sections, e.g. a class's ATTRIBUTES."""
    example: str = ""
    see: tuple[str, ...] = ()
    group: str = "keyword"
    """"class", "attribute", "flag" or "keyword": which list it's in."""
    defaults: tuple[str, ...] = ()
    """Prelude variables whose values the entry shows (DEFAULTS)."""


_CLOSED_ATTRIBUTES = """\
text     "string" [flag ...] ...  first, right after the class (--help flags)
         ljust  rjust
size     width W (wid)  height H (ht)  radius R (rad)  fit
style    fill C  stroke [C] [thickness T] [thick] [thin] [dashed [L]]
         [dotted [L]] [solid] [invis]
place    at P  with .EDGE at P  same [as X]  behind X
edges    .n .ne .e .se .s .sw .w .nw .c  (.top .bottom .left .right .center)"""

_LINE_ATTRIBUTES = """\
text     "string" [flag ...] ...  labels, right after the class (--help flags)
         ljust  rjust
path     [N]  up|down|left|right [N]  go N heading A  from P  to P  then
         right until even with P  close  chop
heads    ->  <-  <->
style    stroke [C] [thickness T] [thick] [thin] [dashed [L]] [dotted [L]]
         [solid] [invis]  fill C (a closed path)
place    same [as X]  behind X
points   .start  .end  Nth vertex of X"""


def _closed(names, summary, body, defaults, example, see=()) -> Entry:
    return Entry(
        names=names,
        summary=summary,
        synopsis=(f"[Label:] {names[0]} [attribute ...]",),
        body=body,
        sections=(("ATTRIBUTES", _CLOSED_ATTRIBUTES),),
        example=example,
        see=("classes", "attributes", "flags", "colors", *see),
        group="class",
        defaults=defaults,
    )


def _line(names, summary, body, defaults, example, see=()) -> Entry:
    return Entry(
        names=names,
        summary=summary,
        synopsis=(f"[Label:] {names[0]} [attribute ...]",),
        body=body,
        sections=(("ATTRIBUTES", _LINE_ATTRIBUTES),),
        example=example,
        see=("classes", "attributes", "chop", *see),
        group="class",
        defaults=defaults,
    )


ENTRIES: tuple[Entry, ...] = (
    # --- object classes --------------------------------------------------
    _closed(("box",), "a rectangle, square or rounded",
            "A rectangle. `radius` rounds its corners.",
            ("boxwid", "boxht", "boxrad"), 'Web: box "Web server" fill accent1 fit'),
    _closed(("circle",), "a circle",
            "A circle: width, height, radius and diameter D all keep it round.",
            ("circlerad",), 'circle "A" radius 0.3'),
    _closed(("ellipse",), "an ellipse", "An ellipse.",
            ("ellipsewid", "ellipseht"), 'ellipse "Start" fit'),
    _closed(("oval",), "a pill shape: a box with round ends", "A box whose ends are half circles.",
            ("ovalwid", "ovalht"), 'oval "Login"'),
    _closed(("diamond",), "a diamond, for a decision", "A diamond (a square on its point).",
            ("diamondwid", "diamondht"), 'diamond "ok?" fit'),
    _closed(("cylinder",), "a cylinder, for a database", "A cylinder; `radius` is the depth of its ends.",
            ("cylwid", "cylht", "cylrad"), 'cylinder "DB"'),
    _closed(("file",), "a page with a folded corner, for a document",
            "A page with its top-right corner folded down; `radius` is the fold's size.",
            ("filewid", "fileht", "filerad"), 'file "report.md"'),
    _closed(("dot",), "a small filled circle", "A small filled circle, e.g. to mark a point.",
            ("dotrad",), "dot at A.e"),
    _closed(("text",), "text alone, with no outline",
            "Text with no fill and no outline, sized by its strings. A statement that "
            'starts with a string is a text object too: `"hello" at (1, 1)`.',
            ("textwid", "textht"), 'text "Title" bold large at (2, 3)', see=("flags",)),
    Entry(("shape",), "any PowerPoint preset shape, by name",
          synopsis=("[Label:] shape PRESET [attribute ...]",),
          body="One of PowerPoint's ~180 preset geometries (chevron, roundRect, "
               "wedgeRectCallout, ...), matched case-insensitively. It behaves like a box: "
               "same default size, attributes and edges (of its bounding rectangle).",
          sections=(("ATTRIBUTES", _CLOSED_ATTRIBUTES),),
          example='shape chevron "Step 1" fit',
          see=("shapes", "box"), group="class", defaults=("boxwid", "boxht")),
    Entry(("image",), "a picture from a PNG, JPEG, GIF or SVG file",
          synopsis=('[Label:] image "PATH" [attribute ...]',),
          body="A picture; PATH is relative to the source file. Give width or height and "
               "the other follows the aspect ratio; give neither and it fits inside "
               "boxwid × boxht. An SVG needs rsvg-convert on PATH for its PNG fallback.",
          sections=(("ATTRIBUTES", "size     width W  height H\n"
                                   "text     alt \"description\"  \"caption\" ...\n"
                                   "place    at P  with .EDGE at P  behind X"),),
          example='image "icons/db.svg" height 0.4 alt "Database"',
          see=("alt",), group="class", defaults=("boxwid", "boxht")),
    Entry(("block", "[", "]"), "a group of objects with its own names: [ ... ]",
          synopsis=("[Label:] [ statement ... ] [attribute ...]",),
          body="A block: the statements inside are laid out on their own and the block is "
               "placed as one object, the size of their bounding box. Names inside are "
               "reached through the block's label (Outer.Inner). It draws nothing itself.",
          example="Row: [ A: box \"a\"; B: box \"b\" ] at (1, 1)\narrow from Row.B.e right",
          see=("classes",), group="class"),
    _line(("line",), "a straight line or polyline",
          "A line, from the previous object's exit in the current direction unless its "
          "path says otherwise.", ("linewid", "lineht"), "line from A.e to B.w"),
    _line(("arrow",), "a line with an arrowhead at its end",
          "A line with an arrowhead at its end (`->`); `<-` or `<->` change the heads.",
          ("linewid", "lineht", "arrowht", "arrowwid"), 'arrow "request" above from A to B chop'),
    _line(("spline",), "a curve through its points (drawn as a polyline)",
          "A curve through its path's points; drawn as straight segments in v1.",
          ("linewid", "lineht"), "spline right then up then right"),
    _line(("arc",), "a quarter circle arc",
          "A quarter-circle arc; `cw`/`ccw` choose which way it turns.",
          ("arcrad",), "arc cw from A.n to B.w ->", see=("cw",)),
    _line(("move",), "moves the current point, drawing nothing",
          "Like a line, but invisible: it moves where the next object goes.",
          ("movewid", "lineht"), "move right 0.5"),
    Entry(("connector",), "reserved for a future class: a link that follows its objects",
          body="Reserved, not used yet: a planned object class that stays attached to the "
               "objects it joins. Lines today are fixed geometry.",
          see=("line", "arrow")),

    # --- size, style ------------------------------------------------------
    Entry(("width", "wid"), "an object's width", synopsis=("width EXPR[%]",),
          body="Sets the width, in inches; `N%` is a percentage of the current width.",
          example="box width 1.5", group="attribute"),
    Entry(("height", "ht"), "an object's height", synopsis=("height EXPR[%]",),
          body="Sets the height, in inches; `N%` is a percentage of the current height.",
          example="box height 0.3", group="attribute"),
    Entry(("radius", "rad"), "corner radius, or a circle's or arc's radius",
          synopsis=("radius EXPR[%]",),
          body="A circle's or arc's radius; a box's (or file's) corner radius; a "
               "cylinder's end depth.", example="box rad 0.1", group="attribute"),
    Entry(("diameter",), "a circle's diameter", synopsis=("diameter EXPR[%]",),
          example="circle diameter 0.4", group="attribute"),
    Entry(("stroke",), "the line or outline: its color, thickness and dashes",
          synopsis=("stroke [COLOR] [STROKE-ATTRIBUTE ...]", "stroke = COLOR"),
          body="Groups what the object's line or outline looks like: a color first, if "
               "any, then thickness, thick, thin, dashed, dotted, solid or invis. Those "
               "are written only after `stroke`. An error on an object that draws no "
               "line (text, image, move, a block). Assigned as a variable, it sets the "
               "default line color for later objects.",
          example='box "a" stroke accent2 thick dashed', group="attribute",
          sections=(("COLORS", "{colors}"),), see=("colors", "color", "fill"),
          defaults=("stroke",)),
    Entry(("thickness",), "line thickness; as a variable, the default",
          synopsis=("stroke thickness EXPR[%]", "thickness = EXPR"),
          body="The stroke width, in inches (a stroke attribute). Assigned as a variable, "
               "it sets the default for later objects.", example="box stroke thickness 0.03",
          group="attribute", defaults=("thickness",), see=("stroke",)),
    Entry(("thick",), "1.5 times thicker", group="attribute", example="arrow stroke thick", see=("stroke",)),
    Entry(("thin",), "0.67 times as thick", group="attribute", example="line stroke thin", see=("stroke",)),
    Entry(("solid",), "solid, default-thickness stroke (undoes dashed/dotted)", group="attribute",
          synopsis=("stroke solid",), see=("stroke",)),
    Entry(("invis", "invisible"), "no outline", group="attribute",
          body="Hides the line or outline (text still shows).", example='box "label only" stroke invis',
          see=("stroke",)),
    Entry(("dashed",), "a dashed stroke", synopsis=("stroke dashed [EXPR]",),
          body="Dashes of the given length (default `dashwid`).", example="line stroke dashed",
          group="attribute", defaults=("dashwid",), see=("stroke",)),
    Entry(("dotted",), "a dotted stroke", synopsis=("stroke dotted [EXPR]",),
          body="Dots spaced by the given length (default `dashwid`).", group="attribute",
          defaults=("dashwid",), see=("stroke",)),
    Entry(("fill",), "the fill color; as a variable, the default",
          synopsis=("fill COLOR", "fill = COLOR"),
          body="Fills the object's interior. Assigned as a variable, it sets the default "
               "for later objects.", example="box fill accent1 lighter 60%",
          sections=(("COLORS", "{colors}"),), see=("colors", "theme"), group="attribute",
          defaults=("fill",)),
    Entry(("color", "colour"), "a string's color; as a variable, the default text color",
          synopsis=('"string" color COLOR', "color = COLOR"),
          body="A string attribute: colors the string right before it, and no other. "
               "Assigned as a variable, it sets the default text color for later objects. "
               "The line or outline is colored by `stroke`.",
          example='box "alert" color accent2 "details"',
          sections=(("COLORS", "{colors}"),), see=("colors", "theme", "stroke", "fill"), group="flag",
          defaults=("color",)),
    Entry(("theme",), "a theme color by slot name", synopsis=('theme "SLOT"',),
          body="A color from the deck's theme, kept linked to it: the diagram recolors "
               "with the template. SLOT is an OOXML scheme color (accent1-6, tx1, tx2, "
               "bg1, bg2, hlink, folHlink, ...); the usual ones are also variables "
               "(accent1, text1, ...).", example='box fill theme "accent3"',
          see=("colors", "lighter")),
    Entry(("lighter", "darker"), "a lighter or darker tint of a color",
          synopsis=("COLOR lighter N%", "COLOR darker N%"),
          body="A tint (lighter) or shade (darker) of a color, as PowerPoint's own "
               "theme color variants.", example="box fill accent1 lighter 60%", see=("colors",)),
    Entry(("none", "off"), "no color", synopsis=("fill none", "stroke off"),
          body="The no-color value: no fill, or no stroke.", see=("colors",)),

    # --- text -------------------------------------------------------------
    Entry(("above", "below"), "text above or below the object's center, or a line",
          synopsis=('"string" above', '"string" below', "N above POSITION"),
          body="As a string attribute: puts the string above (below) the object's center or the "
               "line, stacking with the others there. In a position: that far above "
               "(below) a point.", example='arrow "request" above "reply" below',
          group="flag", see=("flags",)),
    Entry(("ljust", "rjust"), "line the object's strings up on the left or right",
          synopsis=('CLASS "string" ... ljust', 'CLASS "string" ... rjust'),
          body="An object attribute, for all its strings at once: they line up on their "
               "left (right) edges, margin in from the left (right) side of a box or other "
               "closed shape, or from the left (right) end of a line. On a text, `at P` "
               "puts its left (right) edge at P. Not both on one object.",
          example='box "one" "three" ljust width 2', group="attribute", see=("flags", "margin")),
    Entry(("center",), "centered text; the center edge point", synopsis=('"string" center', "X.center"),
          body="As a string attribute: centered, on the center line. As an edge: the object's "
               "center (also `.c`).", group="flag", see=("flags", "edges")),
    Entry(("bold", "italic"), "bold or italic text", synopsis=('"string" bold', '"string" italic'),
          group="flag", example='box "Title" bold "subtitle" italic', see=("flags",)),
    Entry(("mono", "monospace"), "monospace text (accepted; draws in the normal font)",
          group="flag", see=("flags",)),
    Entry(("aligned",), "text along the line's direction (accepted; no effect in v1)", group="attribute"),
    Entry(("small", "medium", "large", "big"), "text size; as variables, the three sizes",
          synopsis=('"string" small', '"string" large', "small = 9pt"),
          body="Text flags for the three sizes (`big` is `large`); the last one on a "
               "string wins. Assigned as variables, they set the sizes, in points.",
          example='box "Title" large "detail" small', group="flag",
          defaults=("small", "medium", "large"), see=("flags",)),
    Entry(("major",), "text in the theme's heading font", group="flag", see=("flags", "typeface")),

    # --- placement and paths ---------------------------------------------
    Entry(("at",), "where the object's center goes", synopsis=("at POSITION",),
          example="box at (1, 2)", group="attribute", see=("with",)),
    Entry(("with",), "which point of the object goes at a position",
          synopsis=("with .EDGE at POSITION",), example="box with .nw at A.se",
          group="attribute", see=("edges", "at")),
    Entry(("from", "to"), "a line's start and end points", synopsis=("from POSITION", "to POSITION"),
          body="Where a line starts and (another segment) ends. Naming an object "
               "(`to B`) means its center; with `chop`, its outline.",
          example="arrow from A.e to B.w", group="attribute", see=("chop", "then")),
    Entry(("then",), "starts a new segment of a line's path",
          synopsis=("then", "then [N] heading A", "then [N] EDGE"),
          example="line right then down then right", group="attribute"),
    Entry(("go",), "moves the path", synopsis=("go DIRECTION [N]", "go N heading A", "go N EDGE"),
          example="line go up 0.5 then go right", group="attribute"),
    Entry(("heading",), "a compass angle, in degrees (0 is up)",
          synopsis=("go N heading A", "N heading A from POSITION"),
          example="arrow go 1 heading 45", group="attribute"),
    Entry(("up", "down", "left", "right"), "a direction: of chaining, or of a line's path",
          synopsis=("up", "right [N]", "right until even with POSITION", "N left of POSITION"),
          body="A statement on its own changes the current direction, in which objects "
               "chain edge to edge. On a line, it moves the path that way. In a position, "
               "`N left of P` is N inches to the left of P.",
          example="down\nbox; box\narrow right 0.5", group="attribute"),
    Entry(("until", "even"), "a move that stops level with a point",
          synopsis=("DIRECTION until even with POSITION", "DIRECTION even with POSITION"),
          example="line down until even with B then right", group="attribute"),
    Entry(("close",), "closes a line's path back to its start", group="attribute",
          example="line right then up then left close"),
    Entry(("chop",), "trims a line's ends to the outlines of the objects it joins",
          body="Ends a line at the outline of the object named by its `from`/`to`, not "
               "at its center.", example="arrow from A to B chop", group="attribute"),
    Entry(("cw", "ccw"), "an arc's direction: clockwise or counterclockwise",
          group="attribute", example="arc cw"),
    Entry(("same",), "copies size and style from another object",
          synopsis=("same", "same as OBJECT"),
          body="Copies size and style from the previous object of the same class, or "
               "from the one named.", example="box same as Web", group="attribute"),
    Entry(("fit",), "sizes the object to its text",
          body="Makes the object just big enough for its text, measured in the fonts the "
               "deck is drawn in, plus margin at each side.",
          example='box "a longer label" fit', group="attribute", see=("margin",)),
    Entry(("behind",), "draws the object just below another in z-order",
          synopsis=("behind OBJECT",), example="box fill bg2 behind Web", group="attribute"),
    Entry(("alt",), "an image's accessibility description", synopsis=('alt "TEXT"',),
          group="attribute", see=("image",)),

    # --- positions and references ------------------------------------------
    Entry(("edges", "n", "north", "ne", "e", "east", "se", "s", "south", "sw", "w", "west", "nw",
           "c", "t", "top", "bot", "bottom", "start", "end"),
          "points on an object: .n .ne .e ... .c, start/end of a line",
          synopsis=("OBJECT.EDGE", "EDGE of OBJECT"),
          body="Compass points of an object's bounding box: n, ne, e, se, s, sw, w, nw "
               "(north, east, ... ; top = t = n, bottom = bot = s), and c (center). A "
               "line also has start and end.", example="arrow from A.e to B.nw",
          see=("with", "vertex")),
    Entry(("of", "the", "way", "between", "and"), "positions between two points",
          synopsis=("F of the way between P and Q", "F between P and Q", "F <P, Q>",
                    "EDGE of OBJECT"),
          body="A point a fraction F of the way from P to Q (0.5 is the middle).",
          example="dot at 1/3 of the way between A and B"),
    Entry(("first", "last", "previous", "nth"), "objects by order: 2nd box, last arrow",
          synopsis=("Nth [last] CLASS", "last [CLASS]", "previous"),
          body="The Nth (1st, 2nd, 3rd, ...; first) object of a class, counting from the "
               "start, or from the end with last. `previous` is the object just before.",
          example="arrow from 1st box to last box", see=("this", "in")),
    Entry(("in",), "narrows a reference to a block", synopsis=("Nth CLASS in BLOCK",),
          example="arrow from 2nd box in Row to Web"),
    Entry(("this",), "the object being defined", example="box with .w at this.e"),
    Entry(("vertex",), "a point of a line's path", synopsis=("Nth vertex of OBJECT",),
          example="dot at 2nd vertex of last line"),
    Entry(("x", "y"), "a point's coordinates", synopsis=("POSITION.x", "POSITION.y"),
          example="box at (A.x, B.y)"),
    Entry(("dist",), "the distance between two points", synopsis=("dist(P, Q)",),
          example="line right dist(A, B)"),
    Entry(("functions", "abs", "cos", "sin", "sqrt", "int", "min", "max"), "math functions",
          synopsis=("abs(X)", "cos(X)", "sin(X)", "sqrt(X)", "int(X)", "min(X, Y)", "max(X, Y)"),
          body="cos and sin take degrees."),

    # --- statements -----------------------------------------------------
    Entry(("define",), "defines a macro", synopsis=("define NAME { BODY }", "NAME(ARG, ...)"),
          body="Defines a macro; `$1` ... `$9` in BODY are its arguments. The name must "
               "start with a lowercase letter and not already be a variable.",
          example='define card { box $1 fill accent1 fit }\ncard("Web")'),
    Entry(("include",), "reads definitions from another file", synopsis=('include "PATH"',),
          body="Reads variables and macros from PATH (relative to the file, or a "
               "--include-path directory). An included file can't draw anything.",
          example='include "house.pik"'),
    Entry(("print",), "prints values (no effect on the drawing)", synopsis=("print ITEM, ...",)),
    Entry(("assert",), "checks two values are equal (no effect on the drawing)",
          synopsis=("assert(EXPR == EXPR)", "assert(POSITION == POSITION)")),
    Entry(("as",), "names the object `same` copies", synopsis=("same as OBJECT",), see=("same",)),
)


# ---------------------------------------------------------------------------
# The prelude: built-in variables and color names
# ---------------------------------------------------------------------------

_VARIABLE_DOCS = {
    "arcrad": "default arc radius",
    "arrowhead": "(accepted; no effect in v1)",
    "arrowht": "arrowhead length",
    "arrowwid": "arrowhead width",
    "boxht": "default box height",
    "boxrad": "default box corner radius",
    "boxwid": "default box width",
    "charht": "text line height, when no real font is measured",
    "charwid": "character width, when no real font is measured",
    "circlerad": "default circle radius",
    "color": "default text color",
    "cylht": "default cylinder height",
    "cylrad": "default depth of a cylinder's ends",
    "cylwid": "default cylinder width",
    "dashwid": "default dash length of dashed/dotted",
    "diamondht": "default diamond height",
    "diamondwid": "default diamond width",
    "dotrad": "dot radius",
    "ellipseht": "default ellipse height",
    "ellipsewid": "default ellipse width",
    "fileht": "default file height",
    "filerad": "default size of a file's folded corner",
    "filewid": "default file width",
    "fill": "default fill color",
    "lineht": "default length of a vertical line",
    "linewid": "default length of a horizontal line",
    "margin": "space between text and an object's sides, or a line's ends",
    "movewid": "default length of a move",
    "ovalht": "default oval height",
    "ovalwid": "default oval width",
    "scale": "(accepted; no effect in v1)",
    "stroke": "default line and outline color",
    "textht": "default height of a text object with no strings",
    "textwid": "default width of a text object with no strings",
    "thickness": "default line thickness",
    "small": "the small text size",
    "medium": "the medium (default) text size",
    "large": "the large text size",
    "typeface": 'font family for all text; "" means the theme\'s',
    "layout": "the --template slide layout to use (settings file only)",
    "primary": "a house color, for a template's settings file to repoint",
    "emphasis": "a house accent color, for a template's settings file to repoint",
}


def prelude_text() -> str:
    return resources.files("pikslide").joinpath("prelude.pik").read_text(encoding="utf-8")


def prelude_values() -> dict[str, str]:
    """Each prelude assignment's value, as written (`0.75`, `9pt`,
    `0xf0f8ff`, `theme "accent1"`, `text2`)."""
    values = {}
    for line in prelude_text().splitlines():
        m = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def _css_colors() -> dict[str, int]:
    return {name: int(v, 16) for name, v in prelude_values().items() if re.fullmatch(r"0x[0-9a-fA-F]{6}", v)}


def _theme_colors() -> dict[str, str]:
    return {name: v for name, v in prelude_values().items() if v.startswith("theme ")}


# ---------------------------------------------------------------------------
# Text: formatting, for a terminal or plain
# ---------------------------------------------------------------------------


@dataclass
class _Style:
    tty: bool
    width: int = 80

    def bold(self, s: str) -> str:
        return f"\033[1m{s}\033[0m" if self.tty else s

    def swatch(self, rgb: int) -> str:
        if not self.tty:
            return ""
        r, g, b = rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF
        return f"\033[48;2;{r};{g};{b}m    \033[0m "


def _indent(text: str, n: int = 4) -> str:
    return "\n".join((" " * n + line) if line else "" for line in text.splitlines())


def _wrap(text: str, width: int, n: int = 4) -> str:
    import textwrap

    return "\n".join(textwrap.fill(p, width=width - n, initial_indent=" " * n, subsequent_indent=" " * n)
                     for p in text.split("\n"))


def _color_list(style: _Style) -> str:
    theme = _theme_colors()
    lines = ["Theme colors (follow the deck's theme):"]
    lines += [f"  {name:<10} {value}" for name, value in theme.items()]
    lines += ["  theme \"SLOT\"  any OOXML scheme color; COLOR lighter N% / darker N% for tints",
              "  none, off    no color", "", "Named colors (CSS):"]
    for name, rgb in _css_colors().items():
        lines.append(f"  {style.swatch(rgb)}{name:<22} 0x{rgb:06x}")
    return "\n".join(lines)


def _format_entry(entry: Entry, style: _Style) -> str:
    values = prelude_values()
    out = [style.bold(" ".join(n.upper() for n in entry.names[:1])) + " — " + entry.summary]
    if len(entry.names) > 1:
        out.append(f"    also: {', '.join(entry.names[1:])}")
    if entry.synopsis:
        out += ["", style.bold("SYNOPSIS"), _indent("\n".join(entry.synopsis))]
    if entry.body:
        body = _INLINE_CODE.sub(lambda m: style.bold(m.group(1)) if style.tty else m.group(0), entry.body)
        out += ["", style.bold("DESCRIPTION"), _wrap(body, style.width)]
    if entry.defaults:
        out += ["", style.bold("DEFAULTS"),
                _indent("\n".join(f"{name} = {values.get(name, '?')}" for name in entry.defaults))]
    for heading, text in entry.sections:
        text = text.replace("{colors}", _color_list(style))
        out += ["", style.bold(heading), _indent(text)]
    if entry.example:
        out += ["", style.bold("EXAMPLE"), _indent(entry.example)]
    if entry.see:
        out += ["", style.bold("SEE ALSO"), _indent(", ".join(f"--help {s}" for s in entry.see))]
    return "\n".join(out) + "\n"


def _format_variable(name: str, style: _Style) -> str:
    value = prelude_values()[name]
    desc = _VARIABLE_DOCS.get(name) or ("a named color" if name in _css_colors() else "a theme color")
    return (f"{style.bold(name.upper())} — {desc}\n\n{style.bold('DEFAULT')}\n    {name} = {value}\n\n"
            "A built-in variable, set by the prelude: assign it to change it from then on, in the\n"
            "program or in a template's settings file.\n\n"
            f"{style.bold('SEE ALSO')}\n    --help variables, --help prelude\n")


def _columns(words: list[str], width: int) -> str:
    """`words` in as many columns as fit `width`, read down each column."""
    cell = max(len(w) for w in words) + 2
    cols = max(1, (width - 2) // cell)
    rows = -(-len(words) // cols)
    lines = []
    for r in range(rows):
        row = [words[c * rows + r] for c in range(cols) if c * rows + r < len(words)]
        lines.append("  " + "".join(f"{w:<{cell}}" for w in row).rstrip())
    return "\n".join(lines) + "\n"


def _format_list(title: str, rows: list[tuple[str, str]], style: _Style) -> str:
    width = max(len(n) for n, _ in rows) + 2
    return style.bold(title) + "\n\n" + "\n".join(f"  {n:<{width}}{s}" for n, s in rows) + "\n"


_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_STRONG = re.compile(r"\*\*([^*]+)\*\*")


def _format_markdown(text: str, style: _Style) -> str:
    """A manual for a terminal: bold headings and emphasis, code blocks
    indented, links as their text. Plain output keeps the Markdown."""
    if not style.tty:
        return text
    out = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append("    " + line)
            continue
        m = re.match(r"(#+)\s+(.*)", line)
        if m:
            heading = m.group(2)
            out.append(style.bold(heading.upper() if len(m.group(1)) <= 2 else heading))
            continue
        line = _LINK.sub(r"\1", line)
        line = _STRONG.sub(lambda m: style.bold(m.group(1)), line)
        line = _INLINE_CODE.sub(lambda m: style.bold(m.group(1)), line)
        out.append(line)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# intro: the way in, for a person or an LLM new to pikslide
# ---------------------------------------------------------------------------

INTRO_EXAMPLE = """\
Client: box "Client" fit
arrow "request" above
Web: box "Web server" bold "(nginx)" small fill accent1 lighter 60% fit
arrow
DB: cylinder "Orders" fit
Cache: box "Cache" stroke dashed fit with .n at 0.5 below Web.s
arrow from Web.s to Cache.n <->"""

_INTRO = f"""\
INTRO — pikslide in one page

pikslide draws a diagram written as text into a one-slide PowerPoint deck of
native, editable shapes, colored by the deck's theme:

    pikslide diagram.pik diagram.pptx [--template corp.potx] [--png diagram.png]

A program is statements, one per line (or separated by `;`):

    CLASS [attribute ...]    an object: box circle ellipse oval diamond cylinder
                             file dot text line arrow spline arc move,
                             shape NAME, image "PATH", [ ... ] (a block)
    Name: CLASS ...          a labeled object: refer to it as Name, Name.e, ...
    right | down | left | up the direction objects chain in
    name = value             a variable: boxwid = 1, fill = accent2

Placement. Each object goes after the previous one, edge to edge, in the
current direction (right, to start with); a line starts where the previous
object ends. `at P` or `with .EDGE at P` place an object explicitly;
`from P to Q` and `then` shape a line; `chop` ends a line at the outlines of
the objects it joins. P is a point: A.e, (1, 2), 0.5 below A.s, ...

Text. Strings right after the class are lines of text: box "Title" bold
"note" small. A string attribute (bold, small, above, color C, ...) belongs to
the string before it; the object's own attributes (ljust, at, fill, ...) come
after all of its strings. `fit` sizes the object to its text.

Lines. `stroke` sets a line or outline: box stroke accent2 thick dashed.

Colors. Theme colors follow the deck: accent1..accent6, text1, text2, bg1,
bg2, with `lighter N%` / `darker N%`; CSS names (steelblue, ...) are fixed.

EXAMPLE
{_indent(INTRO_EXAMPLE)}

GOING FURTHER
    --help keywords       every keyword, one line each; then --help WORD
    --help box            a class: synopsis, attributes, defaults (arrow, ...)
    --help attributes     also: flags, colors, shapes, variables, prelude
    --help grammar        the full grammar; --help spec for the design
    --check               lay a diagram out without writing, to test it
"""


# ---------------------------------------------------------------------------
# Hints: which topic helps with an error
# ---------------------------------------------------------------------------

_LAYOUT_ERROR_TOPICS = (
    ("no such variable", ("variables", "colors")),
    ("unknown theme slot", ("theme",)),
    ("unknown preset shape", ("shapes",)),
    ("image", ("image",)),
    ("undefined object", ("last",)),
    ("nth/last reference", ("last",)),
    ("'this'", ("this",)),
    ("'alt'", ("alt",)),
    ("color", ("colors",)),
)


def layout_error_topics(message: str) -> list[str]:
    """The help topics for a layout error `message`."""
    for fragment, topics in _LAYOUT_ERROR_TOPICS:
        if fragment in message:
            return list(topics)
    return []


def syntax_error_topics(source_line: str, near: str) -> list[str]:
    """The help topics for a syntax error on `source_line`, near the token
    `near`: the statement's class or keyword, and the keyword at the error
    if it has an entry; else the keyword list."""
    entries = _entry_index()
    words = re.findall(r"[A-Za-z_][\w]*|\[", re.sub(r"^\s*[A-Z]\w*\s*:", "", source_line))
    topics = []
    for word in (words[:1] + [near]):
        if word and word.lower() in entries and word.lower() not in topics:
            topics.append(word.lower())
    return topics or ["keywords"]


def hint(topics: list[str]) -> str:
    return "see: " + ", ".join(f"pikslide --help {t}" for t in topics)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

_LISTS = {
    "keywords": "every reserved word, with what it's for",
    "classes": "the object classes",
    "attributes": "the attributes objects take",
    "flags": "the string attributes",
    "colors": "color names and theme colors",
    "shapes": "PowerPoint preset shape names, for `shape NAME`",
    "variables": "the built-in variables and their defaults",
    "prelude": "the prelude itself: every built-in definition",
}
_MANUALS = {"intro": "start here: the language in one page, with an example",
            "grammar": "the grammar, in BNF", "spec": "the language specification"}
_ALIASES = {"colours": "colors", "keyword": "keywords", "class": "classes", "attribute": "attributes",
            "text-flags": "flags", "variable": "variables", "vars": "variables", "presets": "shapes",
            "specification": "spec", "bnf": "grammar", "topics": "help"}


def _entry_index() -> dict[str, Entry]:
    return {name.lower(): e for e in ENTRIES for name in e.names}


def topics_text(style: _Style | None = None) -> str:
    style = style or _Style(tty=False)
    rows = [(k, v) for k, v in _MANUALS.items()] + [(k, v) for k, v in _LISTS.items()]
    return (style.bold("Help topics") + "  (pikslide --help TOPIC)\n\n"
            + "\n".join(f"  {k:<12}{v}" for k, v in rows)
            + "\n\n  and any keyword or built-in variable, e.g. box, arrow, chop, fill, ljust, boxwid\n")


def render(topic: str, style: _Style) -> str | None:
    """The help text for `topic`, or None if there's no such topic."""
    key = topic.lower()
    key = _ALIASES.get(key, key)
    entries = _entry_index()
    values = prelude_values()
    if key == "help":
        return topics_text(style)
    if key == "intro":
        return _INTRO
    if key in _MANUALS:
        text = resources.files("pikslide").joinpath("docs", f"{key}.md").read_text(encoding="utf-8")
        return _format_markdown(text, style)
    if key == "prelude":
        return prelude_text()
    if key == "colors":
        return style.bold("Colors") + "  (fill COLOR, color COLOR)\n\n" + _color_list(style) + "\n"
    if key == "shapes":
        names = sorted(PRESET_NAMES.values(), key=str.lower)
        return style.bold(f"Preset shapes ({len(names)})") + "  (shape NAME)\n\n" + _columns(names, style.width)
    if key == "variables":
        rows = [(n, f"{values[n]:<10} {d}") for n, d in _VARIABLE_DOCS.items() if n in values]
        return _format_list("Built-in variables  (NAME = VALUE to change)", rows, style) + (
            "\n  and the color names: --help colors\n")
    if key in ("keywords", "classes", "attributes", "flags"):
        group = {"keywords": None, "classes": "class", "attributes": "attribute", "flags": "flag"}[key]
        rows = [(", ".join(e.names), e.summary) for e in ENTRIES if group is None or e.group == group]
        return _format_list(key.capitalize(), rows, style)
    if key in entries:
        return _format_entry(entries[key], style)
    if key in values:
        return _format_variable(key, style)
    return None


def _all_topics() -> list[str]:
    return list(dict.fromkeys([*_MANUALS, *_LISTS, *_entry_index(), *prelude_values()]))


def show(topic: str | None) -> int:
    """Print `topic`'s help (or the topic list), paged on a terminal.
    Returns the exit status."""
    tty = sys.stdout.isatty()
    style = _Style(tty=tty, width=shutil.get_terminal_size((80, 24)).columns)
    if topic is None:
        _page(topics_text(style), tty)
        return 0
    text = render(topic, style)
    if text is None:
        near = difflib.get_close_matches(topic.lower(), _all_topics(), n=4)
        hint = f" -- did you mean {', '.join(near)}?" if near else ""
        print(f"error: no help for {topic!r}{hint}\n", file=sys.stderr)
        print(topics_text(), file=sys.stderr)
        return 1
    _page(text, tty)
    return 0


def _page(text: str, tty: bool) -> None:
    """Through $PAGER (default `less -R`) when it won't fit a terminal."""
    if tty and text.count("\n") >= shutil.get_terminal_size((80, 24)).lines:
        pager = os.environ.get("PAGER") or "less -R"
        try:
            subprocess.run(pager, shell=True, input=text.encode("utf-8"), check=False)
            return
        except OSError:
            pass
    sys.stdout.write(text)

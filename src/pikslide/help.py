"""`pikslide --help TOPIC`: the manuals, lists and a short help for every
keyword, for people and for LLMs driving pikslide.

TOPIC is a manual (`grammar`, `spec`: docs/*.md), a list (`keywords`,
`classes`, `attributes`, `flags`, `colors`, `shapes`, `variables`,
`prelude`), or any keyword, built-in variable, color or preset shape
(`box`, `chop`, `fill`, `boxwid`, `cyan`, `callout1`, ...). Lists are built
from the source itself -- the lexer's keyword table, the prelude, the preset
shape names -- so they can't go stale; the keyword entries and the shape
descriptions below are written by hand, and tests check that every reserved
word and every preset shape has one.

Printed to a terminal, the text is formatted (bold headings, color
swatches) and long output goes through $PAGER; piped, it is plain text,
and the manuals are their Markdown source as is.
"""

from __future__ import annotations

import difflib
import functools
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
               "same default size, attributes and edges (of its bounding rectangle). Its text "
               "goes in the preset's own text area, often less than the box (a diamond's "
               "middle half), and `fit` and the overflow warning follow it. "
               "`--help shapes` lists them all with what each looks like; `--help NAME` "
               "describes one.",
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
               "deck is drawn in, plus margin at each side and vmargin above and below. A "
               "shape whose text goes in less "
               "than its whole box is made bigger to match: a circle or a diamond, or a preset "
               "shape such as flowChartInputOutput, whose text leaves out its slanted ends.",
          example='box "a longer label" fit', group="attribute", see=("margin", "vmargin")),
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
    "margin": "space between text and an object's sides, or a line's ends; a --template may set it",
    "movewid": "default length of a move",
    "ovalht": "default oval height",
    "ovalwid": "default oval width",
    "scale": "(accepted; no effect in v1)",
    "stroke": "default line and outline color",
    "textht": "default height of a text object with no strings",
    "textwid": "default width of a text object with no strings",
    "thickness": "default line thickness",
    "vmargin": "space between text and an object's top and bottom; a --template may set it",
    "small": "the small text size",
    "medium": "the medium (default) text size",
    "large": "the large text size",
    "typeface": 'font family for all text; "" means the theme\'s',
    "layout": "the --template slide layout to use (settings file only; content_left, content_top, "
              "content_right and content_bottom set where on it the diagram goes)",
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


# What each theme slot is for, by the name `theme "SLOT"` takes.
_THEME_SLOT_DOCS = {
    "tx1": "dark 1 color, for text", "bg1": "light 1 color, for backgrounds",
    "tx2": "dark 2 color", "bg2": "light 2 color",
    **{f"accent{i}": f"accent color {i}" for i in range(1, 7)},
    "hlink": "hyperlink color", "folHlink": "followed-hyperlink color",
}


@functools.cache
def _builtin_theme_colors() -> dict[str, int]:
    from .pptx_writer import default_theme_colors  # opens python-pptx's template: only when shown

    return default_theme_colors()


def _color_chain(name: str) -> list[str]:
    """Variable `name`'s value, and on through any variable it names, to a
    color: `primary` gives [`text2`, `theme "tx2"`]. [] if `name` isn't a
    color."""
    values, chain = prelude_values(), []
    while name in values and values[name] not in chain:
        name = values[name]
        chain.append(name)
        if re.fullmatch(r"0x[0-9a-fA-F]{6}", name) or name.startswith("theme "):
            return chain
    return []


# ---------------------------------------------------------------------------
# Preset shapes: what each one looks like
#
# Written by hand from each preset as PowerPoint draws it at its default
# geometry (pikslide sets no adjustment handles); a test checks the keys are
# exactly PRESET_NAMES.
# ---------------------------------------------------------------------------

# Above the list (`--help shapes`), and below one shape's description
# (`--help NAME`).
_SHAPES_NOTE = (
    "Each is drawn with PowerPoint's default geometry (no adjustment handles), stretched to "
    "the object's box. A callout's leader line or pointer reaches outside the box; edges and "
    "chop still use the box. Action buttons are pictures only: no click action is attached."
)
_SHAPE_NOTE = (
    "Drawn with PowerPoint's default geometry (no adjustment handles), stretched to the "
    "object's box. Edges and chop use the box, even where the shape reaches outside it."
)

_SHAPE_DOCS = {
    "accentBorderCallout1": "as borderCallout1, with a vertical accent bar between the box and the line",
    "accentBorderCallout2": "as borderCallout2, with a vertical accent bar between the box and the line",
    "accentBorderCallout3": "as borderCallout3, with a vertical accent bar between the box and the line",
    "accentCallout1": "as callout1, with a vertical accent bar between the box and the line",
    "accentCallout2": "as callout2, with a vertical accent bar between the box and the line",
    "accentCallout3": "as callout3, with a vertical accent bar between the box and the line",
    "actionButtonBackPrevious": "a button with a left-pointing triangle (back)",
    "actionButtonBeginning": "a button with a triangle pointing left at a bar (to the start)",
    "actionButtonBlank": "a plain button, no icon",
    "actionButtonDocument": "a button with a page icon",
    "actionButtonEnd": "a button with a triangle pointing right at a bar (to the end)",
    "actionButtonForwardNext": "a button with a right-pointing triangle (next)",
    "actionButtonHelp": "a button with a question mark",
    "actionButtonHome": "a button with a house",
    "actionButtonInformation": 'a button with an "i" in a circle',
    "actionButtonMovie": "a button with a movie camera",
    "actionButtonReturn": "a button with a U-turn arrow",
    "actionButtonSound": "a button with a loudspeaker",
    "arc": "a curved line: the top-right quarter of an ellipse's outline "
           "(a fill shows the quarter pie under it)",
    "bentArrow": "a block arrow rising from the lower left, curving round, pointing right",
    "bentUpArrow": "a block arrow running right along the bottom, turning sharply up",
    "bevel": "a box framed by a sloped rim, like a raised button",
    "blockArc": "a thick arch: the top half of a ring",
    "borderCallout1": "an outlined box with a straight leader line out of its left side, "
                      "ending below and to the left",
    "borderCallout2": "as borderCallout1, but the leader line bends once",
    "borderCallout3": "as borderCallout1, but the leader line bends twice",
    "bracePair": "a pair of curly braces { } on the box's sides (a fill shows between them)",
    "bracketPair": "a pair of round-cornered brackets ( ) on the box's sides (a fill shows between them)",
    "callout1": "a box with no outline (unfilled, only the line shows) and a straight leader "
                "line out of its left side, ending below and to the left",
    "callout2": "as callout1, but the leader line bends once",
    "callout3": "as callout1, but the leader line bends twice",
    "can": "an upright cylinder, as the cylinder class",
    "chartPlus": "a plus (+) of two lines across the box, no outline",
    "chartStar": "an asterisk of three lines across the box: an X and a vertical",
    "chartX": "an X of two lines from corner to corner, no outline",
    "chevron": "a band pointing right, notched on the left: a > arrow",
    "chord": "an ellipse with its upper right sliced off by a straight line",
    "circularArrow": "a thin curved block arrow arching over the top, clockwise",
    "cloud": "a cloud",
    "cloudCallout": "a thought bubble: a cloud with a trail of small circles to the lower left",
    "corner": "an L: a thick right angle",
    "cornerTabs": "small triangles in the four corners, nothing between",
    "cube": "a 3-D box: a front face with the top and right sides showing",
    "curvedDownArrow": "a block arrow arching up from the lower left and down to the right",
    "curvedLeftArrow": "a block arrow looping round on the right, pointing back left",
    "curvedRightArrow": "a block arrow looping round on the left, pointing back right",
    "curvedUpArrow": "a block arrow dipping down in a U, pointing up at the right",
    "decagon": "a 10-sided polygon",
    "diagStripe": "a diagonal band across the upper left, from corner to corner",
    "diamond": "a diamond, as the diamond class",
    "dodecagon": "a 12-sided polygon",
    "donut": "a ring: an ellipse with an elliptical hole",
    "doubleWave": "a flag: a band whose top and bottom edges wave twice",
    "downArrow": "a block arrow pointing down",
    "downArrowCallout": "a box with a block arrow pointing down from its bottom",
    "ellipse": "an ellipse, as the ellipse class",
    "ellipseRibbon": "a banner curving down in the middle: a front panel between folded-back ends",
    "ellipseRibbon2": "a banner arching up in the middle: a front panel between folded-back ends",
    "flowChartAlternateProcess": "flowchart alternate process: a rounded rectangle",
    "flowChartCollate": "flowchart collate: an hourglass of two triangles tip to tip",
    "flowChartConnector": "flowchart connector: an ellipse",
    "flowChartDecision": "flowchart decision: a diamond",
    "flowChartDelay": "flowchart delay: a D, flat on the left and round on the right",
    "flowChartDisplay": "flowchart display: pointed on the left, round on the right",
    "flowChartDocument": "flowchart document: a rectangle with a wavy bottom",
    "flowChartExtract": "flowchart extract: a triangle pointing up",
    "flowChartInputOutput": "flowchart data (input/output): a parallelogram",
    "flowChartInternalStorage": "flowchart internal storage: a rectangle with lines along its top "
                                "and left",
    "flowChartMagneticDisk": "flowchart disk (database): an upright cylinder",
    "flowChartMagneticDrum": "flowchart direct access storage: a cylinder on its side",
    "flowChartMagneticTape": "flowchart tape: a circle with a tail at the lower right",
    "flowChartManualInput": "flowchart manual input: a box whose top slopes up to the right",
    "flowChartManualOperation": "flowchart manual operation: a trapezoid, wide at the top",
    "flowChartMerge": "flowchart merge: a triangle pointing down",
    "flowChartMultidocument": "flowchart documents: a stack of wavy-bottomed pages",
    "flowChartOfflineStorage": "flowchart offline storage: a down triangle with a line across its tip",
    "flowChartOffpageConnector": "flowchart off-page connector: a box pointed at the bottom",
    "flowChartOnlineStorage": "flowchart stored data: round on the left, hollowed on the right",
    "flowChartOr": "flowchart or: an ellipse with a plus (+) inside",
    "flowChartPredefinedProcess": "flowchart predefined process: a box with doubled sides",
    "flowChartPreparation": "flowchart preparation: a hexagon pointed left and right",
    "flowChartProcess": "flowchart process: a rectangle",
    "flowChartPunchedCard": "flowchart card: a box with its top left corner cut off",
    "flowChartPunchedTape": "flowchart punched tape: a band with wavy top and bottom edges",
    "flowChartSort": "flowchart sort: a diamond split by a horizontal line",
    "flowChartSummingJunction": "flowchart summing junction: an ellipse with an X inside",
    "flowChartTerminator": "flowchart terminator: a box with half-round ends",
    "foldedCorner": "a page with its lower right corner folded, as the file class",
    "frame": "a picture frame: a thick border round a rectangular hole",
    "funnel": "a funnel: a cone, point down, under an open rim",
    "gear6": "a gear with 6 teeth",
    "gear9": "a gear with 9 teeth",
    "halfFrame": "the top and left sides of a frame: an upside-down L",
    "heart": "a heart",
    "heptagon": "a 7-sided polygon",
    "hexagon": "a hexagon, pointed left and right",
    "homePlate": "a box pointed on the right, like a process-step arrow",
    "horizontalScroll": "a parchment scroll, unrolled sideways",
    "irregularSeal1": "an explosion: a jagged starburst",
    "irregularSeal2": "an explosion: a jagged starburst, more irregular",
    "leftArrow": "a block arrow pointing left",
    "leftArrowCallout": "a box with a block arrow pointing left from its left side",
    "leftBrace": "a left curly brace { (a fill shows on its open side)",
    "leftBracket": "a left bracket [ with rounded corners (a fill shows on its open side)",
    "leftCircularArrow": "a thin curved block arrow along the bottom, counterclockwise",
    "leftRightArrow": "a block arrow pointing both left and right",
    "leftRightArrowCallout": "a box with block arrows out of its left and right sides",
    "leftRightCircularArrow": "a thin curved block arrow arching over the top, a head at each end",
    "leftRightRibbon": "a ribbon: an arrow pointing left at the top, folding under to point right "
                       "at the bottom",
    "leftRightUpArrow": "a T of block arrows, heads left, right and up",
    "leftUpArrow": "an L of block arrows, heads left and up",
    "lightningBolt": "a lightning bolt",
    "lineInv": "a straight line from the lower left corner to the upper right",
    "mathDivide": "a thick division sign: a bar between two dots",
    "mathEqual": "a thick equals sign (=)",
    "mathMinus": "a thick minus sign (-)",
    "mathMultiply": "a thick multiplication sign (x)",
    "mathNotEqual": "a thick not-equal sign: = struck through",
    "mathPlus": "a thick plus sign (+)",
    "moon": "a crescent moon, its points to the right",
    "noSmoking": 'a "no" sign: a ring with a diagonal bar',
    "nonIsoscelesTrapezoid": "a trapezoid whose sides may slope differently (by default, as trapezoid)",
    "notchedRightArrow": "a block arrow pointing right, with a notch in its tail",
    "octagon": "an octagon: a box with its four corners cut off",
    "parallelogram": "a parallelogram leaning right",
    "pentagon": "a pentagon, point up",
    "pie": "a pie with its upper right quarter cut out",
    "pieWedge": "a quarter disc, its square corner at the lower right",
    "plaque": "a box with scooped-out corners",
    "plaqueTabs": "quarter-circle tabs in the four corners, nothing between",
    "plus": "a thick cross (+) filling the box",
    "quadArrow": "block arrows pointing up, down, left and right",
    "quadArrowCallout": "a box with block arrows out of all four sides",
    "rect": "a rectangle, as the box class",
    "ribbon": "a banner: a front panel set lower than its two folded-back ends",
    "ribbon2": "a banner: a front panel set higher than its two folded-back ends",
    "rightArrow": "a block arrow pointing right",
    "rightArrowCallout": "a box with a block arrow pointing right from its right side",
    "rightBrace": "a right curly brace } (a fill shows on its open side)",
    "rightBracket": "a right bracket ] with rounded corners (a fill shows on its open side)",
    "round1Rect": "a rectangle with its top right corner rounded",
    "round2DiagRect": "a rectangle with its top left and bottom right corners rounded",
    "round2SameRect": "a rectangle with its top two corners rounded",
    "roundRect": "a rounded rectangle, as a box with rad",
    "rtTriangle": "a right triangle, the right angle at the lower left",
    "smileyFace": "a smiley face",
    "snip1Rect": "a rectangle with its top right corner cut off",
    "snip2DiagRect": "a rectangle with its top right and bottom left corners cut off",
    "snip2SameRect": "a rectangle with its top two corners cut off",
    "snipRoundRect": "a rectangle with its top left corner rounded and its top right cut off",
    "squareTabs": "small squares in the four corners, nothing between",
    "star10": "a 10-point star",
    "star12": "a 12-point star",
    "star16": "a 16-point star",
    "star24": "a 24-point star",
    "star32": "a 32-point star",
    "star4": "a 4-point star",
    "star5": "a 5-point star",
    "star6": "a 6-point star",
    "star7": "a 7-point star",
    "star8": "an 8-point star",
    "stripedRightArrow": "a block arrow pointing right, with stripes at its tail",
    "sun": "a sun: an ellipse ringed by triangular rays",
    "swooshArrow": "a sweeping curved arrow, rising to the right",
    "teardrop": "a teardrop: an ellipse with a pointed upper right corner",
    "trapezoid": "a trapezoid, narrow at the top",
    "triangle": "an isosceles triangle, point up",
    "upArrow": "a block arrow pointing up",
    "upArrowCallout": "a box with a block arrow pointing up from its top",
    "upDownArrow": "a block arrow pointing both up and down",
    "upDownArrowCallout": "a box with block arrows out of its top and bottom",
    "uturnArrow": "a U-turn block arrow: up, over the top, and back down",
    "verticalScroll": "a parchment scroll, unrolled downward",
    "wave": "a flag: a band whose top and bottom edges wave once",
    "wedgeEllipseCallout": "a speech bubble: an ellipse with a pointer below, left of center",
    "wedgeRectCallout": "a speech bubble: a rectangle with a pointer below, left of center",
    "wedgeRoundRectCallout": "a speech bubble: a rounded rectangle with a pointer below, left of center",
}


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
    builtin = _builtin_theme_colors()
    lines = ["Theme colors (follow the deck's theme; RGB as in the built-in Office theme):"]
    for name, value in _theme_colors().items():
        rgb = builtin[value.split('"')[1]]
        lines.append(f"  {style.swatch(rgb)}{name:<10} {value:<18} 0x{rgb:06x}")
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


_VARIABLE_NOTE = ("A built-in variable, set by the prelude: assign it to change it from then on, in the\n"
                  "program or in a template's settings file.")


def _format_variable(name: str, style: _Style) -> str:
    value = prelude_values()[name]
    desc = _VARIABLE_DOCS.get(name, "a built-in variable")
    return (f"{style.bold(name.upper())} — {desc}\n\n{style.bold('DEFAULT')}\n    {name} = {value}\n\n"
            f"{_VARIABLE_NOTE}\n\n{style.bold('SEE ALSO')}\n    --help variables, --help prelude\n")


def _format_color(name: str, chain: list[str], style: _Style) -> str:
    """A color variable's page (`chain` from _color_chain()): what it
    looks like, and where a color goes."""
    m = re.fullmatch(r'theme "(\w+)"', chain[-1])
    value = " = ".join([name, *chain])
    out = []
    if m:
        rgb = _builtin_theme_colors()[m.group(1)]
        desc = f"a theme color: the theme's {_THEME_SLOT_DOCS[m.group(1)]}"
        value += f"\n{style.swatch(rgb)}0x{rgb:06x} with no --template (the built-in Office theme)"
        out += ["", style.bold("DESCRIPTION"),
                _wrap("Kept linked to the deck's theme, not its RGB: the diagram recolors with "
                      "the template.", style.width)]
        see = ("colors", "theme", "lighter", "fill", "stroke", "color")
    else:
        desc, value = "a named color (CSS)", style.swatch(int(chain[-1], 16)) + value
        see = ("colors", "lighter", "fill", "stroke", "color")
    synopsis = (f"fill {name}", f"stroke {name}", f'"string" color {name}',
                f"{name} lighter N%, {name} darker N%")
    return "\n".join([
        f"{style.bold(name.upper())} — {_VARIABLE_DOCS.get(name, desc)}",
        "", style.bold("SYNOPSIS"), _indent("\n".join(synopsis)), *out,
        "", style.bold("DEFAULT"), _indent(value),
        "", _VARIABLE_NOTE,
        "", style.bold("SEE ALSO"), _indent(", ".join(f"--help {s}" for s in see)),
    ]) + "\n"


def _shape_list(style: _Style) -> str:
    """Every preset shape and what it looks like, the description wrapped
    under its own column."""
    import textwrap

    names = sorted(PRESET_NAMES.values(), key=str.lower)
    cell = max(len(n) for n in names) + 2
    width = max(style.width - 2, cell + 32)
    return "\n".join(textwrap.fill(_SHAPE_DOCS[n], width=width, initial_indent=f"  {n:<{cell}}",
                                   subsequent_indent=" " * (2 + cell)) for n in names) + "\n"


def _format_shape(name: str, style: _Style) -> str:
    doc = _SHAPE_DOCS[name]
    body = f"{doc[0].upper()}{doc[1:]}.\n\n{_SHAPE_NOTE}"
    if name.startswith("actionButton"):
        body += " A picture only: no click action is attached."
    see = ["shape", "shapes"]
    m = re.match(r"as (\w+)", doc)  # "as callout1, but ...": see that one too
    if m and m.group(1).lower() in PRESET_NAMES:
        see.insert(0, m.group(1))
    return (f"{style.bold(name)} — a PowerPoint preset shape\n\n"
            f"{style.bold('SYNOPSIS')}\n    [Label:] shape {name} [attribute ...]\n\n"
            f"{style.bold('DESCRIPTION')}\n{_wrap(body, style.width)}\n\n"
            f"{style.bold('SEE ALSO')}\n    {', '.join(f'--help {s}' for s in see)}\n")


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
    "shapes": "PowerPoint preset shapes, for `shape NAME`, and what each looks like",
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
            + "\n\n  and any keyword, built-in variable, color or preset shape, e.g. box, arrow, chop, fill,"
            "\n  ljust, boxwid, accent1, cyan, callout1\n")


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
        return (style.bold(f"Preset shapes ({len(PRESET_NAMES)})") + "  (shape NAME)\n\n"
                + _wrap(_SHAPES_NOTE, style.width, 0) + "\n\n" + _shape_list(style))
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
        chain = _color_chain(key)
        return _format_color(key, chain, style) if chain else _format_variable(key, style)
    if key in PRESET_NAMES:
        return _format_shape(PRESET_NAMES[key], style)
    return None


def _all_topics() -> list[str]:
    return list(dict.fromkeys([*_MANUALS, *_LISTS, *_entry_index(), *prelude_values(), *PRESET_NAMES]))


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

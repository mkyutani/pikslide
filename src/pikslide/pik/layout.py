"""Resolve a parsed pik AST (:mod:`pikslide.pik.ast`) into concrete 2-D geometry.

This is a pragmatic *subset* of pikchr's own layout engine (the
``pik_elem_new`` / ``pik_after_adding_attributes`` / per-class
``xInit``/``xOffset``/``xChop`` functions in pikchr.y): default object
sizes, current-direction sequential placement, ``at``/``with``/``from``/
``to``/``then``/``go``/``same``/``chop``, and box/ellipse/diamond edge
geometry are all ported faithfully from that source. Deliberately NOT
ported, in line with a "good enough for common diagrams" scope:

- spline/arc curve shapes are treated as straight polylines,
- "fit" text sizing defaults to an estimate from charwid/charht constants;
  pass a real `FontMetrics` (e.g. pptx_writer's Pillow-backed one) to
  `resolve_layout()` for sizing that tracks actual text content instead of
  a flat per-character guess,
- chopping against diamond/cylinder/file uses their rectangle-like
  xOffset via the same 8-direction dispatch as pikchr's own boxChop,
  rather than each shape's true outline,
- name resolution is a simplified version of pikchr's scope-chain search.

All coordinates are inches, with y pointing *up* (matching pikchr) --
callers producing screen/slide coordinates (y-down) must flip y.

Substantially ported from pikchr, Copyright (C) 2020-09-01 by
D. Richard Hipp <drh@sqlite.org>, released under the Zero-Clause BSD
license. See the NOTICE file at the root of this repository.
"""

from __future__ import annotations

import difflib
import math
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
from typing import Protocol

from . import ast
from .parser import parse


class FontMetrics(Protocol):
    """Real text measurement for _autosize_text(), pluggable per renderer
    so a fitted object's size tracks the font that will actually draw it
    rather than a flat per-character estimate. `flags` are a text item's
    position/style flags (see ast.TextAttribute) -- only "big"/"small"
    matter here, for the font-size step pikchr's own pik_font_scale() applies.

    `text_sizes`, if given, is the small/medium/large (inches) to measure
    with -- the *object's own* `Shape.text_sizes` (docs/spec.md SS3.3,
    ext), not necessarily this metrics' own default, so a `medium`/etc.
    override elsewhere in the document doesn't retroactively change how
    an already-`fit` object was measured. `None` (the default, for a
    caller with no particular object in mind) falls back to whatever this
    metrics implementation would otherwise use."""

    def text_width(self, text: str, flags: list[str] = (), text_sizes: dict[str, float] | None = None) -> float:
        """Width, in inches, of one line of `text` at this flags' size,
        including whatever margin this metrics considers standard (mirrors
        pik_size_to_fit()'s own "+ one charWidth" margin)."""
        ...

    def line_height(self, flags: list[str] = (), text_sizes: dict[str, float] | None = None) -> float:
        """Height, in inches, of one line of text at this flags' size."""
        ...


class ImageMetrics(Protocol):
    """Real image-dimension reading, for `image`'s aspect-ratio sizing
    (docs/spec.md SS3.5) -- pluggable per renderer, the same way
    FontMetrics is. Unlike text, there is no sensible flat estimate for an
    image's aspect ratio without reading the file, so unlike
    `_ApproxMetrics`, the default implementation (`_PILImageMetrics`,
    below) does read it, with Pillow (already a hard dependency)."""

    def size(self, path: str) -> tuple[float, float]:
        """The image's natural (width, height) -- any consistent unit,
        since only their ratio is used. `path` is already resolved
        (absolute)."""
        ...


class _PILImageMetrics:
    """Default ImageMetrics: opens the file directly with Pillow -- or,
    for an SVG (docs/spec.md SS3.5), rasterizes it first (`rasterize_svg`),
    since Pillow itself can't read an SVG's dimensions."""

    def size(self, path: str) -> tuple[float, float]:
        from io import BytesIO

        from PIL import Image

        if path.lower().endswith(".svg"):
            with Image.open(BytesIO(rasterize_svg(path))) as img:
                return float(img.width), float(img.height)
        with Image.open(path) as img:
            return float(img.width), float(img.height)


N, NE, E, SE, S, SW, W, NW, C, END, START = "n", "ne", "e", "se", "s", "sw", "w", "nw", "c", "end", "start"

DIR_RIGHT, DIR_DOWN, DIR_LEFT, DIR_UP = 0, 1, 2, 3
_DIR_CODE = {"right": DIR_RIGHT, "down": DIR_DOWN, "left": DIR_LEFT, "up": DIR_UP}
_OPPOSITE_EDGE = {DIR_RIGHT: W, DIR_LEFT: E, DIR_UP: S, DIR_DOWN: N}
_HEADING_ANGLE = {N: 0.0, NE: 45.0, E: 90.0, SE: 135.0, S: 180.0, SW: 225.0, W: 270.0, NW: 315.0, C: 0.0}

ELLIPSE_LIKE = {"circle", "ellipse", "oval"}
LINE_LIKE = {"line", "arrow", "spline", "arc", "move"}
NOT_RENDERED = {"move", "point"}  # pseudo-objects: real for placement/naming, never drawn


# ---------------------------------------------------------------------------
# Values: pikslide's color type (docs/spec.md SS2, SS3.3)
#
# A pikslide value is a plain float (a length or other number), a Color
# (below), or a str (docs/grammar.md, Colors: "A variable can also hold a
# string"). Unlike pikchr, where every value -- including a color -- is a
# 24-bit number, a color here is a value of its own type: never produced
# by arithmetic, and never itself usable in arithmetic (see _as_number()).
# ---------------------------------------------------------------------------

# The OOXML `schemeClr val="..."` values a shape can reference (checked
# against a real theme part; see docs/spec.md SS3.3). Note these are the
# *reference* names, not the `<a:clrScheme>` element names a theme is
# *defined* with (`dk1`/`lt1`/`dk2`/`lt2`): the default `<a:clrMap>` maps
# `tx1`->`dk1`, `bg1`->`lt1`, `tx2`->`dk2`, `bg2`->`lt2`, so a fill uses
# `tx1`/`bg1`/`tx2`/`bg2`, never `dk1`/`lt1`/`dk2`/`lt2` directly. Matched
# case-insensitively.
THEME_SLOTS = {
    "tx1": "tx1", "bg1": "bg1", "tx2": "tx2", "bg2": "bg2",
    "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
    "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
    "hlink": "hlink", "folhlink": "folHlink",
}

# `shape preset-name` (docs/spec.md SS3.4): every OOXML preset geometry
# (ECMA-376 ST_ShapeType) python-pptx knows -- checked against
# python-pptx 1.0.2's own MSO_SHAPE table (177 distinct names, excluding
# MSO_SHAPE.MIXED, which is not a real preset). Keyed lowercase for
# case-insensitive matching; values are the canonical `prst` spelling
# pptx_writer.py passes to python-pptx.
_PRESET_NAME_LIST = [
    "accentBorderCallout1", "accentBorderCallout2", "accentBorderCallout3", "accentCallout1",
    "accentCallout2", "accentCallout3", "actionButtonBackPrevious", "actionButtonBeginning",
    "actionButtonBlank", "actionButtonDocument", "actionButtonEnd", "actionButtonForwardNext",
    "actionButtonHelp", "actionButtonHome", "actionButtonInformation", "actionButtonMovie",
    "actionButtonReturn", "actionButtonSound", "arc", "bentArrow", "bentUpArrow", "bevel",
    "blockArc", "borderCallout1", "borderCallout2", "borderCallout3", "bracePair",
    "bracketPair", "callout1", "callout2", "callout3", "can", "chartPlus", "chartStar",
    "chartX", "chevron", "chord", "circularArrow", "cloud", "cloudCallout", "corner",
    "cornerTabs", "cube", "curvedDownArrow", "curvedLeftArrow", "curvedRightArrow",
    "curvedUpArrow", "decagon", "diagStripe", "diamond", "dodecagon", "donut", "doubleWave",
    "downArrow", "downArrowCallout", "ellipse", "ellipseRibbon", "ellipseRibbon2",
    "flowChartAlternateProcess", "flowChartCollate", "flowChartConnector", "flowChartDecision",
    "flowChartDelay", "flowChartDisplay", "flowChartDocument", "flowChartExtract",
    "flowChartInputOutput", "flowChartInternalStorage", "flowChartMagneticDisk",
    "flowChartMagneticDrum", "flowChartMagneticTape", "flowChartManualInput",
    "flowChartManualOperation", "flowChartMerge", "flowChartMultidocument",
    "flowChartOfflineStorage", "flowChartOffpageConnector", "flowChartOnlineStorage",
    "flowChartOr", "flowChartPredefinedProcess", "flowChartPreparation", "flowChartProcess",
    "flowChartPunchedCard", "flowChartPunchedTape", "flowChartSort",
    "flowChartSummingJunction", "flowChartTerminator", "foldedCorner", "frame", "funnel",
    "gear6", "gear9", "halfFrame", "heart", "heptagon", "hexagon", "homePlate",
    "horizontalScroll", "irregularSeal1", "irregularSeal2", "leftArrow", "leftArrowCallout",
    "leftBrace", "leftBracket", "leftCircularArrow", "leftRightArrow", "leftRightArrowCallout",
    "leftRightCircularArrow", "leftRightRibbon", "leftRightUpArrow", "leftUpArrow",
    "lightningBolt", "lineInv", "mathDivide", "mathEqual", "mathMinus", "mathMultiply",
    "mathNotEqual", "mathPlus", "moon", "noSmoking", "nonIsoscelesTrapezoid",
    "notchedRightArrow", "octagon", "parallelogram", "pentagon", "pie", "pieWedge", "plaque",
    "plaqueTabs", "plus", "quadArrow", "quadArrowCallout", "rect", "ribbon", "ribbon2",
    "rightArrow", "rightArrowCallout", "rightBrace", "rightBracket", "round1Rect",
    "round2DiagRect", "round2SameRect", "roundRect", "rtTriangle", "smileyFace", "snip1Rect",
    "snip2DiagRect", "snip2SameRect", "snipRoundRect", "squareTabs", "star10", "star12",
    "star16", "star24", "star32", "star4", "star5", "star6", "star7", "star8",
    "stripedRightArrow", "sun", "swooshArrow", "teardrop", "trapezoid", "triangle", "upArrow",
    "upArrowCallout", "upDownArrow", "upDownArrowCallout", "uturnArrow", "verticalScroll",
    "wave", "wedgeEllipseCallout", "wedgeRectCallout", "wedgeRoundRectCallout",
]
PRESET_NAMES = {name.lower(): name for name in _PRESET_NAME_LIST}


@dataclass(frozen=True)
class Color:
    """A color value: either a literal RGB, or a reference to a theme
    slot (docs/spec.md SS3.3) -- kept symbolic, never resolved to RGB here,
    so a renderer can emit `schemeClr` and the color stays linked to
    whatever theme the diagram lands in. Exactly one of `rgb`/`theme_slot`
    is set. `lum_mod`/`lum_off` (0..1, 1.0/0.0 = no change) are PowerPoint's
    own "Lighter N%"/"Darker N%" transform, from a `lighter`/`darker`
    modifier (docs/grammar.md, Colors) -- applicable to either kind of
    color. A later `lighter`/`darker` on the same base *replaces* these
    rather than compounding them, matching PowerPoint's own color-swatch
    picker (one adjustment level, not a stack of them)."""

    rgb: int | None = None
    theme_slot: str | None = None
    lum_mod: float = 1.0
    lum_off: float = 0.0


PikValue = float | Color | str


def _as_number(value: PikValue, what: str = "a numeric value") -> float:
    """Unwrap a value expected to be a plain number, e.g. for arithmetic or
    a size (docs/spec.md SS3.3: "arithmetic on a color is an error")."""
    if isinstance(value, (int, float)):
        return float(value)
    kind = "color" if isinstance(value, Color) else "string"
    raise LayoutError(f"expected {what}, got a {kind}")


def _as_string(value: PikValue, what: str = "a string value") -> str:
    """Unwrap a value expected to be a string, e.g. `typeface` (docs/spec.md
    SS3.3/SS3.8)."""
    if isinstance(value, str):
        return value
    kind = "a color" if isinstance(value, Color) else "a number"
    raise LayoutError(f"expected {what}, got {kind}")


def _as_color(value: PikValue | None) -> Color | None:
    """Coerce a value to what `fill`/`color` hold: a Color, or None for
    "no color". A bare number is accepted as a legacy RGB color (pikchr
    itself lets any expression stand for a fill/color, e.g. `fill -1` for
    "invisible"); a string cannot be a color."""
    if value is None or isinstance(value, Color):
        return value
    if isinstance(value, str):
        raise LayoutError("a string cannot be used as a color")
    n = int(value)
    return None if n < 0 else Color(rgb=n)


def assign_text_slots(texts: list[tuple[str, list[str]]]) -> list[str]:
    """Port of pik_txt_vertical_layout(): decide, for each text item that
    has no explicit above/below/center flag, which vertical slot it goes
    in -- e.g. two un-flagged texts split "above" / "below" the object's
    reference point/line, not both centered on it."""
    n = len(texts)
    if n == 0:
        return []

    slots: list[str | None] = []
    justs: list[str | None] = []
    for _text, flags in texts:
        if "above" in flags:
            slots.append("above")
        elif "below" in flags:
            slots.append("below")
        elif "center" in flags:
            slots.append("center")
        else:
            slots.append(None)
        justs.append("ljust" if "ljust" in flags else "rjust" if "rjust" in flags else None)

    if n == 1:
        return [slots[0] or "center"]

    seen = False
    for i in range(n - 1, -1, -1):
        if slots[i] == "above":
            if not seen:
                seen = True
            else:
                slots[i] = "above2"
                break
    seen = False
    for i in range(n):
        if slots[i] == "below":
            if not seen:
                seen = True
            else:
                slots[i] = "below2"
                break

    used = {s for s in slots if s is not None}
    if n == 2 and {justs[0], justs[1]} == {"ljust", "rjust"}:
        free = ["center", "center"]
    else:
        free = []
        if n >= 4 and "above2" not in used:
            free.append("above2")
        if "above" not in used:
            free.append("above")
        if n % 2 != 0:
            free.append("center")
        if "below" not in used:
            free.append("below")
        if n >= 4 and "below2" not in used:
            free.append("below2")

    it = iter(free)
    return [s if s is not None else next(it) for s in slots]


class LayoutError(Exception):
    pass


# ---------------------------------------------------------------------------
# Shape: the resolved, renderer-facing geometry for one object
# ---------------------------------------------------------------------------


@dataclass
class Shape:
    kind: str
    name: str | None
    cx: float
    cy: float
    w: float
    h: float
    rad: float = 0.0
    sw: float = 0.015
    dashed: float = 0.0
    dotted: float = 0.0
    fill: Color | None = None
    color: Color | None = None
    larrow: bool = False
    rarrow: bool = False
    cw: bool = True
    closed: bool = False
    texts: list[tuple[str, list[str]]] = field(default_factory=list)
    path: list[tuple[float, float]] | None = None
    enter: tuple[float, float] = (0.0, 0.0)
    exit: tuple[float, float] = (0.0, 0.0)
    in_dir: int = DIR_RIGHT
    out_dir: int = DIR_RIGHT
    sublist: list["Shape"] = field(default_factory=list)
    sublist_names: dict[str, "Shape"] = field(default_factory=dict)
    preset: str | None = None
    """The OOXML preset name (docs/spec.md SS3.4), when `kind == "shape"`."""
    image_path: str | None = None
    """Resolved (absolute) path to the picture file, when `kind == "image"`
    (docs/spec.md SS3.5)."""
    alt_text: str | None = None
    """An image's accessibility description, from `alt STRING`."""
    text_sizes: dict[str, float] = field(default_factory=dict)
    """`small`/`medium`/`large` (inches) as they stood when *this* object
    was written (docs/spec.md SS3.3, ext), captured once in
    `_layout_object()` before its own attributes are applied -- since an
    object's own attributes can never themselves reassign these (that
    needs a separate top-level `AssignStatement`, never nested inside an
    object's attribute list), any point during this object's own
    processing gives the same answer. A renderer draws this object's own
    text at *these* sizes, not `LayoutResult.text_sizes` (the document's
    final ones): `box "a" small\\nsmall = 20pt\\nbox "b" small` renders
    "a" at 9pt and "b" at 20pt, not both at 20pt (checked -- this was the
    bug before this field existed)."""
    typeface: str = ""
    """Like `text_sizes`, but for the `typeface` variable (docs/spec.md
    SS3.3): this object's own text renders in the family that was in
    effect when it was written, not the document's final one."""
    fit: bool = False
    """Set by `_autosize_text()` (explicit `fit`, docs/spec.md SS3.3, or
    the implicit case -- no size given at all, ext): this shape's own
    `.w`/`.h` were computed to exactly hold `.texts` at the size a
    renderer will actually draw it, using real font metrics where
    available (`PilFontMetrics`). A renderer should therefore *not* also
    word-wrap this shape's text (ext): wrapping is for a *fixed*,
    author-chosen size that text may legitimately overflow, which this
    isn't -- and word-wrap masks a `fit` measurement that came out too
    small (the measuring font substitute isn't metrically identical to
    whatever the real theme font turns out to be) as silent, layout-
    changing reflow instead of a visible (and diagnosable) overflow."""

    def offset(self, edge: str | None) -> tuple[float, float]:
        return _edge_offset(self, edge)

    def edge_point(self, edge: str | None) -> tuple[float, float]:
        if edge == START:
            return self.enter
        if edge == END:
            return self.exit
        dx, dy = self.offset(edge)
        return (self.cx + dx, self.cy + dy)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        if self.path is not None and self.path:
            xs = [p[0] for p in self.path]
            ys = [p[1] for p in self.path]
            return (min(xs), min(ys), max(xs), max(ys))
        w2, h2 = self.w / 2, self.h / 2
        return (self.cx - w2, self.cy - h2, self.cx + w2, self.cy + h2)


@dataclass
class LayoutResult:
    shapes: list[Shape]
    """The top-level shapes, in source (z-)order. A "block" shape (docs/
    spec.md SS3.1, ext) is *not* flattened into this list -- its own
    children stay nested under its `.sublist`, recursively, mirroring the
    source's own nesting, even though a renderer flattens it right back
    out when drawing (pikslide never emits a PowerPoint group, docs/
    spec.md SS3.1). Use `flatten_shapes()` for a flat view (bounding-box
    math, mainly)."""
    bbox: tuple[float, float, float, float]
    text_sizes: dict[str, float] = field(default_factory=dict)
    """The resolved `small`/`medium`/`large` text sizes (ext, inches), so a
    renderer draws text at the sizes this document actually used -- which
    may differ from the prelude's own 9/10.5/12pt if the program or a
    template's settings file (SS3.8) overrode them."""
    typeface: str = ""
    """The resolved `typeface` variable (docs/spec.md SS3.3, ext): empty
    means "the theme's own font" (a renderer should emit a symbolic
    `+mn-lt`/`+mj-lt` reference, not a literal name); non-empty is a literal
    family the program or a template's settings file (SS3.8) asked for
    explicitly, overriding the theme."""
    layout_name: str = ""
    """The resolved `layout` variable (docs/spec.md SS3.8, ext): empty
    means "the first blank-type layout of the template's first master, or
    that master's own first layout if it has none"; settable only by the
    prelude or a settings file, never a program (`_eval_assignment()`
    enforces this) -- used only when making a *new* slide from a
    `--template` (inserting into an existing deck's slide, that slide
    already has its layout)."""
    content_area: tuple[float, float, float, float] | None = None
    """(left, top, width, height) in inches, from a settings file's
    `content_left`/`content_top`/`content_right`/`content_bottom` (docs/
    spec.md SS3.8) -- the default target region (SS4.2) when inserting
    into an existing deck and neither `--region` nor `--rect` is given.
    `None` unless a settings file defines all four (there is no prelude
    default for them: without a template, there is no "the slide" to
    place a default region on)."""


# ---------------------------------------------------------------------------
# Edge/offset/chop geometry -- ported from box/ellipse/diamond Offset+Chop
# ---------------------------------------------------------------------------


def _box_offset(w: float, h: float, rad: float, edge: str) -> tuple[float, float]:
    w2, h2 = w / 2, h / 2
    rx = 0.0
    if rad > 0.0:
        rad = min(rad, w2, h2)
        rx = 0.29289321881345252392 * rad
    return {
        N: (0.0, h2), NE: (w2 - rx, h2 - rx), E: (w2, 0.0), SE: (w2 - rx, -(h2 - rx)),
        S: (0.0, -h2), SW: (-(w2 - rx), -(h2 - rx)), W: (-w2, 0.0), NW: (-(w2 - rx), h2 - rx),
    }.get(edge, (0.0, 0.0))


def _ellipse_offset(w: float, h: float, edge: str) -> tuple[float, float]:
    w2, h2 = w / 2, h / 2
    wd, hd = w2 * 0.70710678118654747608, h2 * 0.70710678118654747608
    return {
        N: (0.0, h2), NE: (wd, hd), E: (w2, 0.0), SE: (wd, -hd),
        S: (0.0, -h2), SW: (-wd, -hd), W: (-w2, 0.0), NW: (-wd, hd),
    }.get(edge, (0.0, 0.0))


def _diamond_offset(w: float, h: float, edge: str) -> tuple[float, float]:
    w2, w4, h2, h4 = w / 2, w / 4, h / 2, h / 4
    return {
        N: (0.0, h2), NE: (w4, h4), E: (w2, 0.0), SE: (w4, -h4),
        S: (0.0, -h2), SW: (-w4, -h4), W: (-w2, 0.0), NW: (-w4, h4),
    }.get(edge, (0.0, 0.0))


def _edge_offset(shape: Shape, edge: str | None) -> tuple[float, float]:
    if edge is None or edge == C:
        return (0.0, 0.0)
    if shape.kind in ELLIPSE_LIKE:
        return _ellipse_offset(shape.w, shape.h, edge)
    if shape.kind == "diamond":
        return _diamond_offset(shape.w, shape.h, edge)
    return _box_offset(shape.w, shape.h, shape.rad, edge)


def _octant_for(w: float, h: float, dx: float, dy: float) -> str:
    """Pick the compass point that a ray from the center towards (dx, dy)
    exits through -- the same 8-way slope comparison as pikchr's boxChop."""
    if w <= 0 or h <= 0:
        return C
    sdx = dx * h / w
    if sdx > 0:
        if dy >= 2.414 * sdx:
            return N
        if dy >= 0.414 * sdx:
            return NE
        if dy >= -0.414 * sdx:
            return E
        if dy > -2.414 * sdx:
            return SE
        return S
    if dy >= -2.414 * sdx:
        return N
    if dy >= -0.414 * sdx:
        return NW
    if dy >= 0.414 * sdx:
        return W
    if dy > 2.414 * sdx:
        return SW
    return S


def _ellipse_chop(shape: Shape, from_pt: tuple[float, float]) -> tuple[float, float]:
    dx, dy = from_pt[0] - shape.cx, from_pt[1] - shape.cy
    if shape.w <= 0 or shape.h <= 0:
        return (shape.cx, shape.cy)
    s = shape.h / shape.w
    dq = dx * s
    dist = math.hypot(dq, dy)
    if dist < shape.h:
        return (shape.cx, shape.cy)
    return (shape.cx + 0.5 * dq * shape.h / (dist * s), shape.cy + 0.5 * dy * shape.h / dist)


def chop_point(shape: Shape, from_pt: tuple[float, float]) -> tuple[float, float]:
    """Where the segment from `from_pt` towards shape's center crosses its
    boundary (pikchr's xChop)."""
    if shape.kind in ELLIPSE_LIKE:
        return _ellipse_chop(shape, from_pt)
    dx, dy = from_pt[0] - shape.cx, from_pt[1] - shape.cy
    edge = _octant_for(shape.w, shape.h, dx, dy)
    ox, oy = shape.offset(edge)
    return (shape.cx + ox, shape.cy + oy)


def _translate(shape: Shape, dx: float, dy: float) -> None:
    shape.cx += dx
    shape.cy += dy
    shape.enter = (shape.enter[0] + dx, shape.enter[1] + dy)
    shape.exit = (shape.exit[0] + dx, shape.exit[1] + dy)
    if shape.path is not None:
        shape.path = [(x + dx, y + dy) for x, y in shape.path]
    for child in shape.sublist:
        _translate(child, dx, dy)


# ---------------------------------------------------------------------------
# Expression / position / place evaluation
# ---------------------------------------------------------------------------


def _find_by_text(pool: list[Shape], name: str) -> Shape | None:
    for shape in reversed(pool):
        if any(text == name for text, _flags in shape.texts):
            return shape
    return None


def _index_by_identity(pool: list[Shape], target: Shape) -> int:
    """`pool.index(target)`, but by identity (`is`), not `Shape`'s
    generated `==` -- see `_place()` in `_layout_statements()`."""
    for i, shape in enumerate(pool):
        if shape is target:
            return i
    raise LayoutError("internal error: behind-target not found in its own scope")


class _ApproxMetrics:
    """Default FontMetrics: pikchr's own charwid/charht constants applied
    as a flat per-character/per-line estimate. Used whenever no real font
    metrics are supplied -- accurate enough for layout-only work, but a
    renderer that cares about matching its own font should supply its own
    FontMetrics to resolve_layout() instead (see pptx_writer.PilFontMetrics)."""

    def __init__(self, ctx: "_Ctx"):
        self._ctx = ctx

    def text_width(self, text: str, flags: list[str] = (), text_sizes: dict[str, float] | None = None) -> float:
        # Reads ctx.vars live, at call time -- always the object's own
        # (never stale, unlike PilFontMetrics below, so the explicit
        # `text_sizes` override this Protocol method accepts is unneeded
        # here and ignored.
        charw = self._ctx.vars["charwid"] * _font_scale(flags, self._ctx)
        return charw * len(text) + charw

    def line_height(self, flags: list[str] = (), text_sizes: dict[str, float] | None = None) -> float:
        return self._ctx.vars["charht"] * _font_scale(flags, self._ctx)


def _text_size_name(flags: list[str]) -> str:
    """Which of small/medium/large a text item's flags select (ext);
    pikslide's own three fixed sizes, not pikchr's big/small percentage
    scaling -- see docs/spec.md SS3.3. `big` is a synonym for `large`; the
    *last* size flag on the string wins."""
    name = "medium"
    for f in flags:
        if f in ("small", "medium", "large"):
            name = f
        elif f == "big":
            name = "large"
    return name


def _font_scale(flags: list[str], ctx: "_Ctx") -> float:
    """A text item's size, relative to `medium` (the default) -- the ratio
    the approximate metrics scale pikchr's own charht/charwid by. Reads
    `ctx.vars["small"/"medium"/"large"]` (ext), so a program's own override
    of those (`medium = 11pt`) is honoured, not just the prelude default."""
    medium = _as_number(ctx.vars.get("medium", 10.5 / 72.0), "a text size")
    if medium <= 0:
        return 1.0
    size = _as_number(ctx.vars.get(_text_size_name(flags), medium), "a text size")
    return size / medium


# ---------------------------------------------------------------------------
# The prelude (docs/spec.md SS3.7): read once, before every program.
# ---------------------------------------------------------------------------

_prelude_document_cache: ast.Document | None = None


def _prelude_document() -> ast.Document:
    """Parse `prelude.pik` (cached: the prelude is fixed at install time,
    packaged beside this module -- `uv build --wheel` checked to include it)."""
    global _prelude_document_cache
    if _prelude_document_cache is None:
        text = resources.files("pikslide").joinpath("prelude.pik").read_text(encoding="utf-8")
        _prelude_document_cache = parse(text)
    return _prelude_document_cache


def _eval_assignment(stmt: ast.AssignStatement, ctx: "_Ctx") -> None:
    """Evaluate one `name = expr`/`+=`/`-=`/`*=`/`/=` statement into
    `ctx.vars` -- shared by the prelude, a settings file, an included
    file, and a program's own top-level assignments, so all four follow
    the same rules (docs/spec.md SS2: "arithmetic on a color is an
    error"; fill/color are always coerced to a Color or None).

    `layout` (docs/spec.md SS3.8, ext) can be set only while loading the
    prelude or a settings file, never by a program (or anything a program
    brings in via `include`): "a .pik never chooses the deck's structure"."""
    if stmt.name == "layout" and not ctx._layout_assignment_allowed:
        raise LayoutError(
            "'layout' can only be set in a template's settings file, not in a "
            "program (docs/spec.md SS3.8): a .pik never chooses the deck's structure"
        )
    current = ctx.vars.get(stmt.name, 0.0)
    rhs = eval_expr(stmt.value, ctx)
    if stmt.op == "=":
        result: PikValue = rhs
    else:
        if current is None or rhs is None or isinstance(current, (Color, str)) or isinstance(rhs, (Color, str)):
            raise LayoutError(f"'{stmt.name} {stmt.op}' requires a number, not a color or string")
        result = {
            "+=": current + rhs, "-=": current - rhs,
            "*=": current * rhs, "/=": current / rhs if rhs != 0 else current,
        }[stmt.op]
    if stmt.name in ("fill", "color"):
        result = _as_color(result)
    ctx.vars[stmt.name] = result


def _load_prelude(ctx: "_Ctx") -> None:
    """Run the prelude's own assignments into `ctx.vars`, in order. Its
    grammar is "definitions only" (docs/spec.md SS3.6/SS3.7: `define` and
    assignment); anything else appearing here would be a bug in
    `prelude.pik` itself, not user input, so it is asserted rather than
    reported as a normal diagnostic."""
    for stmt in _prelude_document().statements:
        assert isinstance(stmt, ast.AssignStatement), (
            f"prelude.pik: only assignments are allowed, found {type(stmt).__name__}"
        )
        _eval_assignment(stmt, ctx)


def _load_settings(ctx: "_Ctx", settings_text: str, settings_base_dir: str) -> None:
    """Run a template's settings file's own assignments into `ctx.vars`,
    after the prelude and before the program (docs/spec.md SS3.8): the
    same "definitions only" format as an included file (SS3.6). This is a
    full, independent `parse()` of its own -- a settings file is never
    merged into the *program*'s own macro-expansion pass the way an
    `include` inside the program is, so there's no circular-import
    constraint here forcing a token-shape scan the way `include`'s
    `_validate_definitions_only()` needs; `define` and `include` both work
    inside it, resolved against `settings_base_dir` (its own directory)."""
    doc = parse(settings_text, base_dir=settings_base_dir)
    for stmt in doc.statements:
        if not isinstance(stmt, ast.AssignStatement):
            raise LayoutError(
                "a settings file must contain definitions only (docs/spec.md SS3.8): "
                f"found a {type(stmt).__name__}"
            )
        _eval_assignment(stmt, ctx)


def default_text_sizes() -> dict[str, float]:
    """The prelude's own `small`/`medium`/`large` sizes, in inches -- for a
    renderer that needs a FontMetrics *before* calling `resolve_layout()`
    itself (docs/spec.md SS3.7; see `PilFontMetrics` in pptx_writer.py).
    Fixed to the prelude's own defaults: it does not reflect a later
    `medium = ...` override inside the document being rendered, since
    that override isn't known until layout is already under way."""
    ctx = _Ctx()
    return {name: _as_number(ctx.vars[name]) for name in ("small", "medium", "large")}


class _Ctx:
    def __init__(
        self,
        metrics: FontMetrics | None = None,
        image_metrics: ImageMetrics | None = None,
        base_dir: str = ".",
        settings_text: str | None = None,
        settings_base_dir: str = ".",
    ) -> None:
        self.vars: dict[str, PikValue] = {}
        self.scope_stack: list[dict[str, Shape]] = [{}]
        self.pool_stack: list[list[Shape]] = [[]]
        self.current: Shape | None = None
        self.metrics: FontMetrics = metrics if metrics is not None else _ApproxMetrics(self)
        self.image_metrics: ImageMetrics = image_metrics if image_metrics is not None else _PILImageMetrics()
        self.base_dir = base_dir
        # `layout` (docs/spec.md SS3.8) may be assigned while loading the
        # prelude or a settings file, below, but not once the actual
        # program starts (_eval_assignment() checks this).
        self._layout_assignment_allowed = True
        _load_prelude(self)
        if settings_text is not None:
            _load_settings(self, settings_text, settings_base_dir)
        self._layout_assignment_allowed = False

    def lookup_name(self, path: list[str]) -> Shape | None:
        """Port of pik_find_byname(): a name resolves against the *current*
        scope only (no chaining out through enclosing blocks) -- first by
        an explicit "NAME: ..." label, then, if none matches, by exact text
        content on any object in that same scope."""
        head, rest = path[0], path[1:]
        shape = self.scope_stack[-1].get(head) or _find_by_text(self.pool_stack[-1], head)
        for part in rest:
            if shape is None:
                return None
            shape = shape.sublist_names.get(part) or _find_by_text(shape.sublist, part)
        return shape


_FUNCS = {
    "abs": abs,
    "cos": lambda x: math.cos(math.radians(x)),
    "sin": lambda x: math.sin(math.radians(x)),
    "sqrt": math.sqrt,
    "int": lambda x: float(int(x)),
    "max": max,
    "min": min,
}

_PROP_GETTERS = {
    "width": lambda s: s.w, "height": lambda s: s.h, "radius": lambda s: s.rad,
    "diameter": lambda s: s.rad * 2, "thickness": lambda s: s.sw,
    "dashed": lambda s: s.dashed, "dotted": lambda s: s.dotted,
    "fill": lambda s: s.fill, "color": lambda s: s.color,
}


def eval_expr(e: ast.Expr, ctx: _Ctx) -> PikValue | None:
    """Evaluate any value expression -- a number, a color, `None` (the
    `none`/`off` "no color" value), or a string (ext) -- to whatever it
    denotes. Arithmetic nodes (`BinOp` etc.) require numeric operands; see
    `_as_number()`. This also serves as `color-value`/`value` evaluation
    (docs/grammar.md): pikslide has no separate rvalue-only evaluator the
    way pikchr's color-name special case used to need."""
    if isinstance(e, ast.Num):
        return e.value
    if isinstance(e, ast.HexColor):
        return Color(rgb=e.rgb)
    if isinstance(e, ast.ThemeColor):
        return Color(theme_slot=_resolve_theme_slot(e.slot))
    if isinstance(e, ast.NoColor):
        return None
    if isinstance(e, ast.ColorMod):
        base = eval_expr(e.base, ctx)
        if not isinstance(base, Color):
            kind = "no color" if base is None else "a number" if isinstance(base, (int, float)) else "a string"
            raise LayoutError(f"'{e.op}' requires a color, not {kind}")
        amount = _as_number(eval_expr(e.amount, ctx), "a lighter/darker percentage") / 100.0
        if e.op == "lighter":
            return replace(base, lum_mod=1.0 - amount, lum_off=amount)
        return replace(base, lum_mod=1.0 - amount, lum_off=0.0)  # 'darker'
    if isinstance(e, ast.StrLit):
        return e.value
    if isinstance(e, ast.Var):
        # Matches real pikchr (checked: `box width undefinedvar` -> "ERROR:
        # no such variable"), not the silent-0.0 default a variable lookup
        # used to fall back to here. "did you mean accent1?" for a typo'd
        # `accent7` is docs/spec.md SS3.3's own example of this.
        if e.name not in ctx.vars:
            raise LayoutError(f"no such variable: {e.name}{_did_you_mean(e.name, ctx.vars.keys())}")
        return ctx.vars[e.name]
    if isinstance(e, ast.BinOp):
        left = _as_number(eval_expr(e.left, ctx))
        right = _as_number(eval_expr(e.right, ctx))
        if e.op == "+":
            return left + right
        if e.op == "-":
            return left - right
        if e.op == "*":
            return left * right
        return left / right if right != 0 else 0.0
    if isinstance(e, ast.UnaryOp):
        v = _as_number(eval_expr(e.operand, ctx))
        return -v if e.op == "-" else v
    if isinstance(e, ast.FuncCall):
        args = [_as_number(eval_expr(a, ctx)) for a in e.args]
        return float(_FUNCS[e.name](*args))
    if isinstance(e, ast.Dist):
        p1, p2 = eval_position(e.p1, ctx), eval_position(e.p2, ctx)
        return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if isinstance(e, ast.PlaceCoord):
        pt = eval_place(e.place, ctx)
        return pt[0] if e.axis == "x" else pt[1]
    if isinstance(e, ast.ObjectProp):
        shape = resolve_object(e.obj, ctx)
        return _PROP_GETTERS.get(e.prop, lambda s: 0.0)(shape)
    raise LayoutError(f"cannot evaluate expression node: {type(e).__name__}")


def _did_you_mean(name: str, candidates) -> str:
    """"; did you mean X, Y, Z?" for the closest matches to `name` among
    `candidates`, or "" if nothing is close enough (docs/spec.md SS5:
    "unknown names ... are errors with suggestions, not silent
    fallbacks") -- shared so every "unknown name" error (an undefined
    variable, an image file, a region) gives one the same way, not just
    `_resolve_preset_name()`, which is where this pattern started."""
    suggestions = difflib.get_close_matches(name, candidates, n=3)
    return f"; did you mean {', '.join(suggestions)}?" if suggestions else ""


def _resolve_theme_slot(slot: str) -> str:
    """Validate and canonicalize a `theme "slot"` name (docs/spec.md
    SS3.3): matched case-insensitively, an unknown name is an error that
    lists the ones this tool knows."""
    canonical = THEME_SLOTS.get(slot.lower())
    if canonical is None:
        known = ", ".join(sorted(THEME_SLOTS.values()))
        raise LayoutError(f"unknown theme slot {slot!r}; known slots are: {known}")
    return canonical


def _resolve_preset_name(name: str) -> str:
    """Validate and canonicalize a `shape preset-name` (docs/spec.md SS3.4):
    matched case-insensitively; an unknown name is an error that lists the
    nearest matches (too many presets, 177, to list them all)."""
    canonical = PRESET_NAMES.get(name.lower())
    if canonical is not None:
        return canonical
    raise LayoutError(f"unknown preset shape {name!r}{_did_you_mean(name, PRESET_NAMES.values())}")


# PNG/JPEG/GIF are handled entirely by Pillow and python-pptx's own
# add_picture(). SVG (docs/spec.md SS3.5, for icons that stay sharp at any
# size) is neither: Pillow can't read its dimensions (raises
# UnidentifiedImageError, checked) and add_picture() can't embed it
# (raises TypeError, checked) -- both need a real SVG renderer instead,
# see rasterize_svg() and pptx_writer.py's _add_image_shape().
_SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg"}


def _resolve_image_path(raw_path: str, base_dir: str) -> str:
    """Resolve an `image` object's path against `base_dir` (the source
    file's own directory, docs/spec.md SS3.5), and check it exists and is
    a format pikslide can read.

    Rejects an absolute path or one that escapes `base_dir`, the same
    containment `include` applies (docs/spec.md SS3.6) and for the same
    reason: a diagram may be written by an LLM, and must not be able to
    reach, or reveal the existence of, arbitrary local files."""
    if os.path.isabs(raw_path) or raw_path.startswith(("~",)):
        raise LayoutError(f"image path must be relative, not {raw_path!r}")
    base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(base, raw_path))
    if os.path.commonpath([base, resolved]) != base:
        raise LayoutError(f"image path escapes its source directory: {raw_path!r}")
    if not os.path.isfile(resolved):
        try:
            siblings = os.listdir(os.path.dirname(resolved))
        except OSError:
            siblings = []
        raise LayoutError(f"image file not found: {raw_path!r}{_did_you_mean(os.path.basename(raw_path), siblings)}")
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in _SUPPORTED_IMAGE_EXTENSIONS:
        raise LayoutError(f"unsupported image format {ext!r}: {raw_path!r}")
    return resolved


def _rsvg_convert_path() -> str:
    """The `rsvg-convert` (librsvg) executable SVG handling needs (docs/
    spec.md SS3.5), or a clear error naming it -- "without it, an .svg is
    an error that names the missing tool" -- rather than a confusing
    failure once it turns out to be missing partway through."""
    import shutil

    path = shutil.which("rsvg-convert")
    if path is None:
        raise LayoutError(
            "SVG images need rsvg-convert (from librsvg) on PATH, to produce the "
            "PNG fallback older PowerPoint versions show (docs/spec.md SS3.5); it was not found"
        )
    return path


@lru_cache(maxsize=128)
def rasterize_svg(svg_path: str) -> bytes:
    """PNG bytes for `svg_path`, via `rsvg-convert` (docs/spec.md SS3.5) --
    used both for `image`'s own aspect-ratio sizing (`_PILImageMetrics`,
    below: Pillow itself can't read an SVG's dimensions) and, by
    `pptx_writer.py`, for the actual embedded fallback bitmap -- the same
    icon is often placed more than once in one diagram, or sized (here)
    and then embedded (there) from the same file, so this is cached by
    path rather than re-running the external tool each time. Only a
    *successful* result is cached (`lru_cache` never caches a raised
    exception), so a missing-tool/bad-file error still surfaces on every
    call, not just the first."""
    import subprocess

    exe = _rsvg_convert_path()
    result = subprocess.run([exe, "--format=png", svg_path], capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise LayoutError(f"rsvg-convert failed on {svg_path!r}: {stderr}")
    return result.stdout


def eval_place(place: ast.Place, ctx: _Ctx) -> tuple[float, float]:
    if isinstance(place, ast.ObjectEdge):
        shape = resolve_object(place.obj, ctx)
        return shape.edge_point(place.edge)
    if isinstance(place, ast.NthVertex):
        shape = resolve_object(place.obj, ctx)
        pts = shape.path if shape.path else _rect_corners(shape)
        idx = (place.ordinal - 1) % len(pts)
        return pts[idx]
    raise LayoutError(f"cannot evaluate place node: {type(place).__name__}")


def _rect_corners(shape: Shape) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = shape.bbox
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def eval_position(pos: ast.Position, ctx: _Ctx) -> tuple[float, float]:
    if isinstance(pos, ast.Coord):
        return (_as_number(eval_expr(pos.x, ctx)), _as_number(eval_expr(pos.y, ctx)))
    if isinstance(pos, ast.PlacePosition):
        return eval_place(pos.place, ctx)
    if isinstance(pos, ast.OffsetPosition):
        bx, by = eval_place(pos.base, ctx)
        dx, dy = _as_number(eval_expr(pos.dx, ctx)), _as_number(eval_expr(pos.dy, ctx))
        return (bx + dx, by + dy) if pos.op == "+" else (bx - dx, by - dy)
    if isinstance(pos, ast.XYFromPositions):
        x, _ = eval_position(pos.x_from, ctx)
        _, y = eval_position(pos.y_from, ctx)
        return (x, y)
    if isinstance(pos, ast.Between):
        f = _as_number(eval_expr(pos.fraction, ctx))
        x1, y1 = eval_position(pos.p1, ctx)
        x2, y2 = eval_position(pos.p2, ctx)
        return (x1 + f * (x2 - x1), y1 + f * (y2 - y1))
    if isinstance(pos, ast.DirectionOffset):
        d = _as_number(eval_expr(pos.distance, ctx))
        bx, by = eval_position(pos.base, ctx)
        if pos.direction == "above":
            return (bx, by + d)
        if pos.direction == "below":
            return (bx, by - d)
        if pos.direction == "left of":
            return (bx - d, by)
        return (bx + d, by)  # "right of"
    if isinstance(pos, ast.HeadingOffset):
        d = _as_number(eval_expr(pos.distance, ctx))
        bx, by = eval_position(pos.base, ctx)
        angle = _HEADING_ANGLE.get(pos.edge, 0.0) if pos.edge is not None else _as_number(eval_expr(pos.angle, ctx))
        rad = math.radians(angle)
        return (bx + d * math.sin(rad), by + d * math.cos(rad))
    raise LayoutError(f"cannot evaluate position node: {type(pos).__name__}")


def _position_object_ref(pos: ast.Position, ctx: _Ctx) -> Shape | None:
    """If `pos` names an object directly (for chop purposes), return it."""
    if isinstance(pos, ast.PlacePosition) and isinstance(pos.place, ast.ObjectEdge):
        try:
            return resolve_object(pos.place.obj, ctx)
        except LayoutError:
            return None
    return None


def resolve_object(ref: ast.ObjectRef, ctx: _Ctx) -> Shape:
    if isinstance(ref, ast.ThisRef):
        if ctx.current is None:
            raise LayoutError("'this' used outside of an object definition")
        return ctx.current
    if isinstance(ref, ast.NameRef):
        shape = ctx.lookup_name(ref.path)
        if shape is None:
            raise LayoutError(f"undefined object: {'.'.join(ref.path)}")
        return shape
    if isinstance(ref, ast.NthRef):
        if ref.container is not None:
            container = resolve_object(ref.container, ctx)
            pool = container.sublist
        else:
            pool = ctx.pool_stack[-1]
        if ref.classname:
            pool = [s for s in pool if s.kind == ref.classname]
        if not pool:
            raise LayoutError("no matching object for an nth/last reference")
        idx = ref.ordinal - 1 if ref.ordinal > 0 else len(pool) + ref.ordinal
        if not 0 <= idx < len(pool):
            raise LayoutError("nth/last reference index out of range")
        return pool[idx]
    raise LayoutError(f"cannot resolve object reference: {type(ref).__name__}")


def _resolve_rel(rel: ast.RelExpr, default: float, ctx: _Ctx) -> float:
    if rel.abs is not None:
        return _as_number(eval_expr(rel.abs, ctx))
    if rel.percent is not None:
        return default * (_as_number(eval_expr(rel.percent, ctx)) / 100.0)
    return default


def _resolve_rel_current(rel: ast.RelExpr, current: float, ctx: _Ctx) -> float:
    if rel.abs is not None:
        return _as_number(eval_expr(rel.abs, ctx))
    if rel.percent is not None:
        return current * (_as_number(eval_expr(rel.percent, ctx)) / 100.0)
    return current


# ---------------------------------------------------------------------------
# Per-class default sizing (xInit)
# ---------------------------------------------------------------------------

# name -> (width-var, height-var) for the simple "look up two defaults" classes.
_SIMPLE_DEFAULTS = {
    "arrow": ("linewid", "lineht"),
    "line": ("linewid", "lineht"),
    "spline": ("linewid", "lineht"),
    "move": ("movewid", "lineht"),
    "box": ("boxwid", "boxht"),
    "cylinder": ("cylwid", "cylht"),
    "file": ("filewid", "fileht"),
    "ellipse": ("ellipsewid", "ellipseht"),
    "oval": ("ovalwid", "ovalht"),
    "diamond": ("diamondwid", "diamondht"),
}


def _var_number(ctx: "_Ctx", name: str) -> float:
    """A built-in default variable's value, as a number -- guards against
    e.g. `boxwid = red` leaving a Color where every size/geometry
    computation expects a float."""
    return _as_number(ctx.vars[name], f"a numeric value for {name!r}")


def _init_class_defaults(shape: Shape, classname: str, ctx: _Ctx) -> None:
    v = ctx.vars
    if classname in _SIMPLE_DEFAULTS:
        wname, hname = _SIMPLE_DEFAULTS[classname]
        shape.w, shape.h = _var_number(ctx, wname), _var_number(ctx, hname)
        if classname == "box":
            shape.rad = _var_number(ctx, "boxrad")
        elif classname == "cylinder":
            shape.rad = _var_number(ctx, "cylrad")
        elif classname == "file":
            shape.rad = _var_number(ctx, "filerad")
        if classname == "arrow":
            shape.rarrow = True
    elif classname == "circle":
        shape.w = shape.h = _var_number(ctx, "circlerad") * 2
        shape.rad = 0.5 * shape.w
    elif classname == "dot":
        shape.rad = _var_number(ctx, "dotrad")
        shape.w = shape.h = shape.rad * 2
        shape.fill = shape.color
    elif classname == "arc":
        shape.w = shape.h = _var_number(ctx, "arcrad")
    elif classname == "text":
        shape.w = shape.h = 0.0
    elif classname == "shape":
        shape.w, shape.h = _var_number(ctx, "boxwid"), _var_number(ctx, "boxht")
        shape.rad = _var_number(ctx, "boxrad")
    else:
        raise LayoutError(f"unknown object class: {classname}")


def _apply_circle_constraint(shape: Shape) -> None:
    if shape.kind != "circle":
        return
    d = max(shape.w, shape.h)
    shape.w = shape.h = d
    shape.rad = 0.5 * d


def _autosize_text(shape: Shape, ctx: _Ctx) -> None:
    """Approximate pik_size_to_fit() using ctx.metrics: real pikchr (and,
    for the pptx backend, PilFontMetrics) measures actual glyph widths;
    only the fallback _ApproxMetrics estimates from flat constants.

    Measures at `shape.text_sizes` (docs/spec.md SS3.3, ext) -- captured
    when this object was created, in `_layout_object()` -- not whatever
    text_sizes a renderer's FontMetrics might otherwise default to, so a
    `medium`/etc. override elsewhere in the document can't retroactively
    change how an earlier "fit" object was measured."""
    if not shape.texts:
        return
    m = ctx.metrics
    sizes = shape.text_sizes
    shape.w = max((m.text_width(text, flags, sizes) for text, flags in shape.texts), default=0.0)
    shape.h = sum(m.line_height(flags, sizes) for _text, flags in shape.texts) + 0.75 * m.line_height([], sizes)
    if shape.kind == "diamond":
        # A diamond's text sits well inside its points, so needs extra room.
        shape.w *= 1.6
        shape.h *= 1.6
    elif shape.kind in ("circle", "ellipse", "oval"):
        # The largest axis-aligned rectangle inscribed in an ellipse of
        # full width/height (W, H) is (W/sqrt(2)) x (H/sqrt(2)) -- so to
        # give the text box that exact size, the ellipse's own bounding
        # box (what shape.w/.h become) must be sqrt(2) times bigger in
        # each dimension, the same idea as diamond's correction above.
        shape.w *= math.sqrt(2)
        shape.h *= math.sqrt(2)
    elif shape.kind == "cylinder":
        # A cylinder's top end is drawn as an ellipse dipping into the
        # shape from the top, so the usable (rectangular) text area is
        # shorter than the full bounding height -- checked empirically
        # (rendered, at a few heights): the fit-computed height needs
        # about this much more before text clears the end's curve. Only
        # height is affected -- the end doesn't narrow the usable width.
        shape.h *= 1.5
    _apply_circle_constraint(shape)
    shape.fit = True


def _size_image(shape: Shape, ctx: _Ctx) -> None:
    """Apply docs/spec.md SS3.5's sizing rule: both `width` and `height`
    given -> stretched (already done by plain NumProperty application, and
    needs no image read at all); one given -> the other follows the aspect
    ratio; neither given -> fit inside boxwid x boxht, aspect preserved."""
    if shape.w > 0.0 and shape.h > 0.0:
        return
    assert shape.image_path is not None
    nat_w, nat_h = ctx.image_metrics.size(shape.image_path)
    if nat_w <= 0.0 or nat_h <= 0.0:
        raise LayoutError(f"image has no size: {shape.image_path}")
    aspect = nat_w / nat_h
    if shape.w > 0.0:
        shape.h = shape.w / aspect
    elif shape.h > 0.0:
        shape.w = shape.h * aspect
    else:
        box_w, box_h = _var_number(ctx, "boxwid"), _var_number(ctx, "boxht")
        if aspect > box_w / box_h:
            shape.w, shape.h = box_w, box_w / aspect
        else:
            shape.w, shape.h = box_h * aspect, box_h


# ---------------------------------------------------------------------------
# Attribute application
# ---------------------------------------------------------------------------


@dataclass
class _Build:
    direction: int
    at: tuple[float, float] | None = None
    with_edge: str | None = None
    with_pos: tuple[float, float] | None = None
    path: list[tuple[float, float]] = field(default_factory=list)
    seg_objs: list[Shape | None] = field(default_factory=list)  # parallel to path[1:]
    from_obj: Shape | None = None
    chop: bool = False
    fit: bool = False
    then_flag: bool = False
    behind: Shape | None = None
    """The object `behind X` names (docs/spec.md SS3.1, ext), resolved here
    during attribute application (where `ast.Behind`'s target is a plain
    `ast.ObjectRef`, same as `same as X`); `_layout_statements()` reorders
    the finished shape to sit immediately before it once `_layout_object()`
    returns, since it isn't in any pool yet at attribute-application time."""
    mtpath: int = 0  # bitmask on the *current* point: 1 = x already set, 2 = y already set


def _start_point(shape: Shape, build: "_Build") -> tuple[float, float]:
    return build.at if build.at is not None else (shape.cx, shape.cy)


def _ensure_start(build: "_Build", shape: Shape) -> None:
    if not build.path:
        build.path.append(_start_point(shape, build))


def _new_point(build: "_Build") -> None:
    """Port of pik_next_rpath(): start a new path point as a copy of the
    current last one (so a lone axis-move from it becomes a diagonal)."""
    build.path.append(build.path[-1])
    build.seg_objs.append(None)
    build.mtpath = 0


def _append_segment(build: "_Build", shape: Shape, pt: tuple[float, float], obj: Shape | None) -> None:
    """Always-new-point movement, for absolute moves ('to', heading)."""
    _ensure_start(build, shape)
    if len(build.path) == 1 or build.mtpath == 3 or build.then_flag:
        _new_point(build)
    build.path[-1] = pt
    build.seg_objs[-1] = obj
    build.mtpath = 3
    build.then_flag = False


def _apply_attribute(attr: ast.Attribute, shape: Shape, build: "_Build", ctx: _Ctx) -> None:
    if isinstance(attr, ast.LeadingDirection):
        length = _resolve_rel(attr.amount, ctx.vars["linewid"], ctx)
        _move_current_direction(build, shape, build.direction, length)
    elif isinstance(attr, ast.NumProperty):
        current = {"width": shape.w, "height": shape.h, "radius": shape.rad,
                   "diameter": shape.rad * 2, "thickness": shape.sw}[attr.name]
        value = _resolve_rel_current(attr.value, current, ctx)
        if attr.name == "width":
            shape.w = value
            if shape.kind == "circle":
                shape.h, shape.rad = value, value / 2
        elif attr.name == "height":
            shape.h = value
            if shape.kind == "circle":
                shape.w, shape.rad = value, value / 2
        elif attr.name == "radius":
            shape.rad = value
            if shape.kind == "circle":
                shape.w = shape.h = value * 2
        elif attr.name == "diameter":
            shape.rad = value / 2
            if shape.kind == "circle":
                shape.w = shape.h = value
        elif attr.name == "thickness":
            shape.sw = value
    elif isinstance(attr, ast.DashProperty):
        value = eval_expr(attr.value, ctx) if attr.value is not None else ctx.vars["dashwid"]
        if attr.name == "dashed":
            shape.dashed, shape.dotted = value, 0.0
        else:
            shape.dotted, shape.dashed = value, 0.0
    elif isinstance(attr, ast.ColorProperty):
        value = _as_color(eval_expr(attr.value, ctx))
        if attr.name == "fill":
            shape.fill = value
        else:
            shape.color = value
    elif isinstance(attr, ast.BoolProperty):
        if attr.name == "cw":
            shape.cw = True
        elif attr.name == "ccw":
            shape.cw = False
        elif attr.name == "thick":
            shape.sw *= 1.5
        elif attr.name == "thin":
            shape.sw *= 0.67
        elif attr.name == "solid":
            shape.sw = ctx.vars["thickness"]
            shape.dashed = shape.dotted = 0.0
        elif attr.name == "invis":
            shape.sw = -0.00001
    elif isinstance(attr, ast.ArrowDirection):
        shape.larrow = attr.kind in ("left", "both")
        shape.rarrow = attr.kind in ("right", "both")
    elif isinstance(attr, ast.TextAttribute):
        shape.texts.append((attr.text, attr.flags))
    elif isinstance(attr, ast.Fit):
        build.fit = True
    elif isinstance(attr, ast.Behind):
        build.behind = resolve_object(attr.obj, ctx)
    elif isinstance(attr, ast.Alt):
        if shape.kind != "image":
            raise LayoutError("'alt' is only valid on an image")
        shape.alt_text = attr.text
    elif isinstance(attr, ast.At):
        build.at = eval_position(attr.position, ctx)
        build.with_edge = C
        build.with_pos = build.at
    elif isinstance(attr, ast.With):
        build.with_edge = attr.edge if attr.edge is not None else C
        build.with_pos = eval_position(attr.position, ctx)
    elif isinstance(attr, ast.Same):
        # Port of pik_same(): copies size, radius, and the full visual
        # style (not just dimensions) from the reference object.
        same_from = resolve_object(attr.obj, ctx) if attr.obj is not None else _find_same_class(ctx, shape.kind)
        if same_from is not None:
            if shape.kind not in LINE_LIKE:
                shape.w, shape.h = same_from.w, same_from.h
            shape.rad = same_from.rad
            shape.sw = same_from.sw
            shape.dashed = same_from.dashed
            shape.dotted = same_from.dotted
            shape.fill = same_from.fill
            shape.color = same_from.color
            shape.cw = same_from.cw
            shape.larrow = same_from.larrow
            shape.rarrow = same_from.rarrow
            shape.closed = same_from.closed
    elif isinstance(attr, ast.From_):
        pt = eval_position(attr.position, ctx)
        if build.path:
            # Port of pik_set_from(): re-base the whole path already built
            # from earlier movement attributes, rather than discarding it.
            dx, dy = pt[0] - build.path[0][0], pt[1] - build.path[0][1]
            build.path = [(x + dx, y + dy) for x, y in build.path]
        else:
            build.path = [pt]
        build.from_obj = _position_object_ref(attr.position, ctx)
    elif isinstance(attr, ast.To):
        pt = eval_position(attr.position, ctx)
        _append_segment(build, shape, pt, _position_object_ref(attr.position, ctx))
    elif isinstance(attr, ast.Then):
        build.then_flag = True
    elif isinstance(attr, ast.Close):
        shape.closed = True
    elif isinstance(attr, ast.Chop):
        build.chop = True
    elif isinstance(attr, ast.GoDirection):
        build.direction = _DIR_CODE[attr.direction]
        if attr.even_with is not None:
            target = eval_position(attr.even_with, ctx)
            _move_even_with(build, shape, build.direction, target)
        else:
            default = ctx.vars["linewid"] if attr.direction in ("left", "right") else ctx.vars["lineht"]
            length = _resolve_rel(attr.amount, default, ctx) if attr.amount is not None else default
            _move_current_direction(build, shape, build.direction, length)
    elif isinstance(attr, ast.MoveHeading):
        default = ctx.vars["linewid"]
        length = _resolve_rel(attr.amount, default, ctx)
        angle = _HEADING_ANGLE.get(attr.edge, 0.0) if attr.edge is not None else eval_expr(attr.angle, ctx)
        start = build.path[-1] if build.path else _start_point(shape, build)
        rad = math.radians(angle)
        pt = (start[0] + length * math.sin(rad), start[1] + length * math.cos(rad))
        _append_segment(build, shape, pt, None)
    else:
        raise LayoutError(f"unsupported attribute: {type(attr).__name__}")


def _move_current_direction(build: "_Build", shape: Shape, direction: int, length: float) -> None:
    """Port of pik_add_direction()'s path-point bookkeeping: a lone move
    merges into the current point (so "right 1 up 1" makes one diagonal
    point), but a repeated move on the same axis, or one after an explicit
    "then", starts a fresh point."""
    _ensure_start(build, shape)
    axis_bit = 2 if direction in (DIR_UP, DIR_DOWN) else 1
    if build.then_flag or build.mtpath == 3 or len(build.path) == 1:
        _new_point(build)
        build.then_flag = False
    if build.mtpath & axis_bit:
        _new_point(build)
    x, y = build.path[-1]
    if direction == DIR_UP:
        y += length
    elif direction == DIR_DOWN:
        y -= length
    elif direction == DIR_RIGHT:
        x += length
    else:
        x -= length
    build.path[-1] = (x, y)
    build.mtpath |= axis_bit


def _move_even_with(build: "_Build", shape: Shape, direction: int, target: tuple[float, float]) -> None:
    """Port of pik_evenwith(): move in `direction` until aligned with
    `target` on the relevant axis -- same point-merge rules as a plain
    direction move, but snapping to an absolute coordinate."""
    _ensure_start(build, shape)
    axis_bit = 2 if direction in (DIR_UP, DIR_DOWN) else 1
    if build.then_flag or build.mtpath == 3 or len(build.path) == 1:
        _new_point(build)
        build.then_flag = False
    if build.mtpath & axis_bit:
        _new_point(build)
    x, y = build.path[-1]
    if axis_bit == 2:
        y = target[1]
    else:
        x = target[0]
    build.path[-1] = (x, y)
    build.mtpath |= axis_bit


def _find_same_class(ctx: _Ctx, kind: str) -> Shape | None:
    for shape in reversed(ctx.pool_stack[-1]):
        if shape.kind == kind:
            return shape
    return None


# ---------------------------------------------------------------------------
# Per-object and per-statement-list layout
# ---------------------------------------------------------------------------


def _set_exit(shape: Shape, direction: int) -> None:
    """Port of pik_elem_set_exit(): retroactively updates an already-placed
    object's exit point when the ambient direction changes after it."""
    shape.out_dir = direction
    if shape.kind in LINE_LIKE and not shape.closed:
        return
    shape.exit = shape.cx, shape.cy
    dx, dy = {DIR_RIGHT: (shape.w * 0.5, 0.0), DIR_LEFT: (-shape.w * 0.5, 0.0),
              DIR_UP: (0.0, shape.h * 0.5), DIR_DOWN: (0.0, -shape.h * 0.5)}[direction]
    shape.exit = (shape.cx + dx, shape.cy + dy)


def _layout_object(stmt: ast.ObjectStatement, direction: int, prev: Shape | None, ctx: _Ctx) -> tuple[Shape, Shape | None]:
    """Returns the finished shape, plus the object a `behind X` attribute
    (docs/spec.md SS3.1, ext) named, if any -- for `_layout_statements()`
    to place it correctly, since the shape isn't in any pool yet here."""
    base = stmt.base
    # Captured once, up front -- see Shape.text_sizes/.typeface -- rather
    # than read from ctx.vars again wherever text is drawn, by which
    # point a later object's own override may already have changed them.
    text_sizes_now = {name: _as_number(ctx.vars[name]) for name in ("small", "medium", "large")}
    typeface_now = _as_string(ctx.vars.get("typeface", ""), "typeface")

    if isinstance(base, ast.BlockBase):
        ctx.scope_stack.append({})
        ctx.pool_stack.append([])
        local_shapes, _end_dir, local_bbox = _layout_statements(base.statements, direction, ctx)
        local_names = ctx.scope_stack.pop()
        ctx.pool_stack.pop()
        lx0, ly0, lx1, ly1 = local_bbox
        shape = Shape(kind="block", name=None, cx=(lx0 + lx1) / 2, cy=(ly0 + ly1) / 2,
                      w=lx1 - lx0, h=ly1 - ly0)
        shape.sublist = local_shapes
        shape.sublist_names = local_names
        local_center = (shape.cx, shape.cy)
        is_line = False
    elif isinstance(base, ast.TextBase):
        shape = Shape(kind="text", name=None, cx=0.0, cy=0.0, w=0.0, h=0.0,
                      sw=ctx.vars["thickness"], fill=ctx.vars["fill"], color=ctx.vars["color"])
        shape.texts.append((base.text, base.flags))
        is_line = False
    elif isinstance(base, ast.ShapeBase):
        shape = Shape(kind="shape", name=None, cx=0.0, cy=0.0, w=0.0, h=0.0,
                      sw=ctx.vars["thickness"], fill=ctx.vars["fill"], color=ctx.vars["color"],
                      preset=_resolve_preset_name(base.preset))
        _init_class_defaults(shape, "shape", ctx)
        is_line = False
    elif isinstance(base, ast.ImageBase):
        shape = Shape(kind="image", name=None, cx=0.0, cy=0.0, w=0.0, h=0.0,
                      sw=ctx.vars["thickness"], fill=ctx.vars["fill"], color=ctx.vars["color"],
                      image_path=_resolve_image_path(base.path, ctx.base_dir))
        is_line = False
    else:
        classname = base.classname
        shape = Shape(kind=classname, name=None, cx=0.0, cy=0.0, w=0.0, h=0.0,
                      sw=ctx.vars["thickness"], fill=ctx.vars["fill"], color=ctx.vars["color"])
        _init_class_defaults(shape, classname, ctx)
        is_line = classname in LINE_LIKE

    shape.text_sizes = text_sizes_now
    shape.typeface = typeface_now
    shape.in_dir = direction
    shape.out_dir = direction

    if prev is None:
        shape.cx, shape.cy = 0.0, 0.0
        with_pos, with_edge = (0.0, 0.0), C
    else:
        shape.cx, shape.cy = prev.exit
        with_pos, with_edge = prev.exit, _OPPOSITE_EDGE[direction]

    ctx.current = shape
    build = _Build(direction=direction)
    for attr in stmt.attributes:
        _apply_attribute(attr, shape, build, ctx)
    ctx.current = None

    if build.at is not None:
        with_pos, with_edge = build.at, C
    elif build.with_pos is not None:
        with_pos, with_edge = build.with_pos, build.with_edge

    if build.fit:
        _autosize_text(shape, ctx)

    shape.out_dir = build.direction

    if not is_line:
        if shape.kind == "image":
            _size_image(shape, ctx)
        elif (shape.w <= 0.0 or shape.h <= 0.0) and shape.texts:
            _autosize_text(shape, ctx)
        ofst = shape.offset(with_edge)
        shape.cx = with_pos[0] - ofst[0]
        shape.cy = with_pos[1] - ofst[1]
        if shape.kind == "block":
            dx, dy = shape.cx - local_center[0], shape.cy - local_center[1]
            for child in shape.sublist:
                _translate(child, dx, dy)
        w2, h2 = shape.w / 2, shape.h / 2
        _set_exit(shape, shape.out_dir)
        dxin, dyin = {DIR_RIGHT: (-w2, 0.0), DIR_LEFT: (w2, 0.0), DIR_UP: (0.0, -h2), DIR_DOWN: (0.0, h2)}[shape.in_dir]
        shape.enter = (shape.cx + dxin, shape.cy + dyin)
    else:
        if len(build.path) < 2:
            length = shape.w if direction in (DIR_RIGHT, DIR_LEFT) else shape.h
            build.path = [_start_point(shape, build)]
            _move_current_direction(build, shape, direction, length)
        if build.chop:
            if build.seg_objs and build.seg_objs[-1] is not None:
                build.path[-1] = chop_point(build.seg_objs[-1], build.path[-2])
            if build.from_obj is not None:
                build.path[0] = chop_point(build.from_obj, build.path[1])
        if shape.closed and build.path[0] != build.path[-1]:
            build.path.append(build.path[0])
        shape.path = build.path
        shape.enter, shape.exit = build.path[0], build.path[-1]
        x0, y0, x1, y1 = shape.bbox
        shape.cx, shape.cy = (x0 + x1) / 2, (y0 + y1) / 2
        shape.w, shape.h = x1 - x0, y1 - y0

    return shape, build.behind


def _layout_statements(
    statements: list[ast.Statement], direction: int, ctx: _Ctx
) -> tuple[list[Shape], int, tuple[float, float, float, float]]:
    shapes: list[Shape] = []
    prev: Shape | None = None
    # Default names (docs/spec.md SS3.1, ext): "<class> <n>", n = this
    # kind's ordinal *in this scope* -- a fresh count per _layout_statements()
    # call, so numbering restarts inside each block, same as `ctx.pool_stack`.
    class_counts: dict[str, int] = {}

    def _place(shape: Shape, behind_target: Shape | None) -> None:
        """Append `shape` to this scope's pool -- at the end (source-order
        z-order, the default), or immediately before `behind_target`
        (docs/spec.md SS3.1, ext: `behind X`). Finds `behind_target` by
        identity, not `list.index()`'s `==` -- `Shape` is a plain
        (unfrozen) dataclass, so two structurally-identical shapes (e.g.
        two bare `box`es before either gets a distinguishing attribute)
        compare equal, and `index()` would silently insert before the
        wrong one of them."""
        if behind_target is None:
            shapes.append(shape)
            ctx.pool_stack[-1].append(shape)
        else:
            shapes.insert(_index_by_identity(shapes, behind_target), shape)
            pool = ctx.pool_stack[-1]
            pool.insert(_index_by_identity(pool, behind_target), shape)

    for stmt in statements:
        if isinstance(stmt, ast.DirectionStatement):
            direction = _DIR_CODE[stmt.direction]
            if prev is not None:
                _set_exit(prev, direction)
            continue
        if isinstance(stmt, ast.AssignStatement):
            _eval_assignment(stmt, ctx)
            continue
        if isinstance(stmt, (ast.PrintStatement, ast.AssertExprStatement, ast.AssertPositionStatement)):
            continue
        if isinstance(stmt, ast.LabelPosition):
            pt = eval_position(stmt.position, ctx)
            shape = Shape(kind="point", name=stmt.label, cx=pt[0], cy=pt[1], w=0.0, h=0.0,
                          enter=pt, exit=pt, in_dir=direction, out_dir=direction)
            _place(shape, None)
            ctx.scope_stack[-1][stmt.label] = shape
            prev = shape
            continue
        if isinstance(stmt, ast.ObjectStatement):
            shape, behind_target = _layout_object(stmt, direction, prev, ctx)
            # Counts every object of this kind, labeled or not (matching
            # NthRef's own pool-filter-by-kind in resolve_object() above),
            # so a default name's ordinal always agrees with what "Nth
            # <class>" would address, even with labeled objects in between.
            class_counts[shape.kind] = class_counts.get(shape.kind, 0) + 1
            if stmt.label:
                shape.name = stmt.label
                ctx.scope_stack[-1][stmt.label] = shape
            else:
                shape.name = f"{shape.kind} {class_counts[shape.kind]}"
            _place(shape, behind_target)
            prev = shape
            direction = shape.out_dir
            continue
        raise LayoutError(f"unsupported statement: {type(stmt).__name__}")

    if shapes:
        x0 = min(s.bbox[0] for s in shapes)
        y0 = min(s.bbox[1] for s in shapes)
        x1 = max(s.bbox[2] for s in shapes)
        y1 = max(s.bbox[3] for s in shapes)
        bbox = (x0, y0, x1, y1)
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    return shapes, direction, bbox


def flatten_shapes(shapes: list[Shape]) -> list[Shape]:
    """Every drawable shape in `shapes`, recursively -- a "block" shape
    (docs/spec.md SS3.1, ext) contributes its `sublist`'s own drawable
    shapes in its place, not itself, and a `move`/`point` pseudo-object
    (never drawn -- `NOT_RENDERED`) is dropped. `LayoutResult.shapes` keeps
    the *tree* (a block shape and its `sublist` intact), mirroring the
    source's own nesting even though a renderer flattens it back out when
    drawing (SS3.1: blocks are a source-level grouping construct, never a
    PowerPoint group); this is for callers that just need every eventual
    on-slide shape regardless of nesting -- bounding-box math, mainly."""
    out: list[Shape] = []
    for shape in shapes:
        if shape.kind == "block":
            out.extend(flatten_shapes(shape.sublist))
        elif shape.kind not in NOT_RENDERED:
            out.append(shape)
    return out


_CONTENT_AREA_VARS = ("content_left", "content_top", "content_right", "content_bottom")


def resolve_layout(
    doc: ast.Document,
    metrics: FontMetrics | None = None,
    image_metrics: ImageMetrics | None = None,
    base_dir: str = ".",
    settings_text: str | None = None,
    settings_base_dir: str = ".",
) -> LayoutResult:
    """Resolve a parsed pik :class:`~pikslide.pik.ast.Document` into concrete,
    ready-to-render geometry. See the module docstring for what this
    pragmatic layout engine does and does not faithfully reproduce.

    `metrics`, if given, is used to size "fit" objects from their actual
    text content instead of the built-in charwid/charht approximation --
    pass a renderer-specific FontMetrics (e.g. pptx_writer.PilFontMetrics)
    to get "fit" sizes that track what will actually be drawn.

    `base_dir` is the source file's own directory (docs/spec.md SS3.5): an
    `image` object's path is resolved against it, and rejected if it
    escapes it. `image_metrics`, if given, overrides how an image's
    natural size is read (default: Pillow, directly).

    `settings_text`, if given, is a template's settings file (docs/spec.md
    SS3.8), read after the prelude and before `doc` itself, so its
    definitions override the prelude's and the program's override its in
    turn; `settings_base_dir` is the directory its own `include`s (if any)
    resolve against."""
    ctx = _Ctx(metrics, image_metrics, base_dir, settings_text, settings_base_dir)
    shapes, _direction, _bbox = _layout_statements(doc.statements, DIR_RIGHT, ctx)
    flat = flatten_shapes(shapes)
    if flat:
        x0 = min(s.bbox[0] for s in flat)
        y0 = min(s.bbox[1] for s in flat)
        x1 = max(s.bbox[2] for s in flat)
        y1 = max(s.bbox[3] for s in flat)
        bbox = (x0, y0, x1, y1)
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    text_sizes = {name: _as_number(ctx.vars[name]) for name in ("small", "medium", "large")}
    typeface = _as_string(ctx.vars.get("typeface", ""), "typeface")
    layout_name = _as_string(ctx.vars.get("layout", ""), "layout")
    content_area = None
    if all(name in ctx.vars for name in _CONTENT_AREA_VARS):
        left, top, right, bottom = (_as_number(ctx.vars[name], name) for name in _CONTENT_AREA_VARS)
        content_area = (left, top, right - left, bottom - top)
    return LayoutResult(
        shapes=shapes, bbox=bbox, text_sizes=text_sizes, typeface=typeface, layout_name=layout_name, content_area=content_area
    )

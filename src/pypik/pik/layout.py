"""Resolve a parsed pik AST (:mod:`pypik.pik.ast`) into concrete 2-D geometry.

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
- "behind" only affects nothing yet (parsed, not yet used for z-order),
- name resolution is a simplified version of pikchr's scope-chain search.

All coordinates are inches, with y pointing *up* (matching pikchr) --
callers producing screen/slide coordinates (y-down) must flip y.

Substantially ported from pikchr, Copyright (C) 2020-09-01 by
D. Richard Hipp <drh@sqlite.org>, released under the Zero-Clause BSD
license. See the NOTICE file at the root of this repository.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from . import ast
from .colors import COLOR_NAMES


class FontMetrics(Protocol):
    """Real text measurement for _autosize_text(), pluggable per renderer
    so a fitted object's size tracks the font that will actually draw it
    rather than a flat per-character estimate. `flags` are a text item's
    position/style flags (see ast.TextAttribute) -- only "big"/"small"
    matter here, for the font-size step pikchr's own pik_font_scale() applies."""

    def text_width(self, text: str, flags: list[str] = ()) -> float:
        """Width, in inches, of one line of `text` at this flags' size,
        including whatever margin this metrics considers standard (mirrors
        pik_size_to_fit()'s own "+ one charWidth" margin)."""
        ...

    def line_height(self, flags: list[str] = ()) -> float:
        """Height, in inches, of one line of text at this flags' size."""
        ...

N, NE, E, SE, S, SW, W, NW, C, END, START = "n", "ne", "e", "se", "s", "sw", "w", "nw", "c", "end", "start"

DIR_RIGHT, DIR_DOWN, DIR_LEFT, DIR_UP = 0, 1, 2, 3
_DIR_CODE = {"right": DIR_RIGHT, "down": DIR_DOWN, "left": DIR_LEFT, "up": DIR_UP}
_OPPOSITE_EDGE = {DIR_RIGHT: W, DIR_LEFT: E, DIR_UP: S, DIR_DOWN: N}
_HEADING_ANGLE = {N: 0.0, NE: 45.0, E: 90.0, SE: 135.0, S: 180.0, SW: 225.0, W: 270.0, NW: 315.0, C: 0.0}

# Transcribed from pikchr's aBuiltin[] default-variable table.
DEFAULTS = {
    "arcrad": 0.25, "arrowhead": 2.0, "arrowht": 0.08, "arrowwid": 0.06,
    "boxht": 0.5, "boxrad": 0.0, "boxwid": 0.75,
    "charht": 0.14, "charwid": 0.08,
    "circlerad": 0.25, "color": 0.0,
    "cylht": 0.5, "cylrad": 0.075, "cylwid": 0.75,
    "dashwid": 0.05, "diamondht": 0.75, "diamondwid": 1.0, "dotrad": 0.015,
    "ellipseht": 0.5, "ellipsewid": 0.75,
    "fileht": 0.75, "filerad": 0.15, "filewid": 0.5, "fill": -1.0,
    "lineht": 0.5, "linewid": 0.5, "movewid": 0.5,
    "ovalht": 0.5, "ovalwid": 1.0,
    "scale": 1.0, "textht": 0.5, "textwid": 0.75, "thickness": 0.015,
}

ELLIPSE_LIKE = {"circle", "ellipse", "oval"}
LINE_LIKE = {"line", "arrow", "spline", "arc", "move"}
_NOT_RENDERED = {"move", "point"}


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
    fill: float = -1.0
    color: float = 0.0
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
    bbox: tuple[float, float, float, float]


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


class _ApproxMetrics:
    """Default FontMetrics: pikchr's own charwid/charht constants applied
    as a flat per-character/per-line estimate. Used whenever no real font
    metrics are supplied -- accurate enough for layout-only work, but a
    renderer that cares about matching its own font should supply its own
    FontMetrics to resolve_layout() instead (see pptx_writer.PilFontMetrics)."""

    def __init__(self, ctx: "_Ctx"):
        self._ctx = ctx

    def text_width(self, text: str, flags: list[str] = ()) -> float:
        charw = self._ctx.vars["charwid"] * _font_scale(flags)
        return charw * len(text) + charw

    def line_height(self, flags: list[str] = ()) -> float:
        return self._ctx.vars["charht"] * _font_scale(flags)


def _font_scale(flags: list[str]) -> float:
    """Port of pik_font_scale()."""
    if "big" in flags:
        return 1.25
    if "small" in flags:
        return 0.8
    return 1.0


class _Ctx:
    def __init__(self, metrics: FontMetrics | None = None) -> None:
        self.vars: dict[str, float] = dict(DEFAULTS)
        self.scope_stack: list[dict[str, Shape]] = [{}]
        self.pool_stack: list[list[Shape]] = [[]]
        self.current: Shape | None = None
        self.metrics: FontMetrics = metrics if metrics is not None else _ApproxMetrics(self)

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


def eval_expr(e: ast.Expr, ctx: _Ctx) -> float:
    if isinstance(e, ast.Num):
        return e.value
    if isinstance(e, ast.Var):
        return ctx.vars.get(e.name, 0.0)
    if isinstance(e, ast.BinOp):
        left, right = eval_expr(e.left, ctx), eval_expr(e.right, ctx)
        if e.op == "+":
            return left + right
        if e.op == "-":
            return left - right
        if e.op == "*":
            return left * right
        return left / right if right != 0 else 0.0
    if isinstance(e, ast.UnaryOp):
        v = eval_expr(e.operand, ctx)
        return -v if e.op == "-" else v
    if isinstance(e, ast.FuncCall):
        args = [eval_expr(a, ctx) for a in e.args]
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
    if isinstance(e, ast.ColorName):
        return float(COLOR_NAMES.get(e.name.lower(), 0))
    raise LayoutError(f"cannot evaluate expression node: {type(e).__name__}")


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
        return (eval_expr(pos.x, ctx), eval_expr(pos.y, ctx))
    if isinstance(pos, ast.PlacePosition):
        return eval_place(pos.place, ctx)
    if isinstance(pos, ast.OffsetPosition):
        bx, by = eval_place(pos.base, ctx)
        dx, dy = eval_expr(pos.dx, ctx), eval_expr(pos.dy, ctx)
        return (bx + dx, by + dy) if pos.op == "+" else (bx - dx, by - dy)
    if isinstance(pos, ast.XYFromPositions):
        x, _ = eval_position(pos.x_from, ctx)
        _, y = eval_position(pos.y_from, ctx)
        return (x, y)
    if isinstance(pos, ast.Between):
        f = eval_expr(pos.fraction, ctx)
        x1, y1 = eval_position(pos.p1, ctx)
        x2, y2 = eval_position(pos.p2, ctx)
        return (x1 + f * (x2 - x1), y1 + f * (y2 - y1))
    if isinstance(pos, ast.DirectionOffset):
        d = eval_expr(pos.distance, ctx)
        bx, by = eval_position(pos.base, ctx)
        if pos.direction == "above":
            return (bx, by + d)
        if pos.direction == "below":
            return (bx, by - d)
        if pos.direction == "left of":
            return (bx - d, by)
        return (bx + d, by)  # "right of"
    if isinstance(pos, ast.HeadingOffset):
        d = eval_expr(pos.distance, ctx)
        bx, by = eval_position(pos.base, ctx)
        angle = _HEADING_ANGLE.get(pos.edge, 0.0) if pos.edge is not None else eval_expr(pos.angle, ctx)
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
        return eval_expr(rel.abs, ctx)
    if rel.percent is not None:
        return default * (eval_expr(rel.percent, ctx) / 100.0)
    return default


def _resolve_rel_current(rel: ast.RelExpr, current: float, ctx: _Ctx) -> float:
    if rel.abs is not None:
        return eval_expr(rel.abs, ctx)
    if rel.percent is not None:
        return current * (eval_expr(rel.percent, ctx) / 100.0)
    return current


def eval_rvalue(value: ast.Expr, ctx: _Ctx) -> float:
    if isinstance(value, ast.ColorName):
        return float(COLOR_NAMES.get(value.name.lower(), 0))
    if isinstance(value, ast.Var):
        # A lowercase-starting color name (e.g. "fill white") parses as a
        # plain Var, not ast.ColorName, since only capitalized PLACENAMEs
        # take that path (see Parser.parse_rvalue). Real pikchr scripts
        # overwhelmingly use lowercase color names, so check the color
        # table before falling back to a variable lookup.
        color = COLOR_NAMES.get(value.name.lower())
        if color is not None:
            return float(color)
    return eval_expr(value, ctx)


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


def _init_class_defaults(shape: Shape, classname: str, ctx: _Ctx) -> None:
    v = ctx.vars
    if classname in _SIMPLE_DEFAULTS:
        wname, hname = _SIMPLE_DEFAULTS[classname]
        shape.w, shape.h = v[wname], v[hname]
        if classname == "box":
            shape.rad = v["boxrad"]
        elif classname == "cylinder":
            shape.rad = v["cylrad"]
        elif classname == "file":
            shape.rad = v["filerad"]
        if classname == "arrow":
            shape.rarrow = True
    elif classname == "circle":
        shape.w = shape.h = v["circlerad"] * 2
        shape.rad = 0.5 * shape.w
    elif classname == "dot":
        shape.rad = v["dotrad"]
        shape.w = shape.h = v["dotrad"] * 2
        shape.fill = shape.color
    elif classname == "arc":
        shape.w = shape.h = v["arcrad"]
    elif classname == "text":
        shape.w = shape.h = 0.0
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
    only the fallback _ApproxMetrics estimates from flat constants."""
    if not shape.texts:
        return
    m = ctx.metrics
    shape.w = max((m.text_width(text, flags) for text, flags in shape.texts), default=0.0)
    shape.h = sum(m.line_height(flags) for _text, flags in shape.texts) + 0.75 * m.line_height([])
    if shape.kind == "diamond":
        # A diamond's text sits well inside its points, so needs extra room.
        shape.w *= 1.6
        shape.h *= 1.6
    _apply_circle_constraint(shape)


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
        elif attr.name == "height":
            shape.h = value
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
        value = eval_rvalue(attr.value, ctx)
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
        pass  # z-ordering hint; not yet used by the renderers
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


def _layout_object(stmt: ast.ObjectStatement, direction: int, prev: Shape | None, ctx: _Ctx) -> Shape:
    base = stmt.base

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
    else:
        classname = base.classname
        shape = Shape(kind=classname, name=None, cx=0.0, cy=0.0, w=0.0, h=0.0,
                      sw=ctx.vars["thickness"], fill=ctx.vars["fill"], color=ctx.vars["color"])
        _init_class_defaults(shape, classname, ctx)
        is_line = classname in LINE_LIKE

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
        if (shape.w <= 0.0 or shape.h <= 0.0) and shape.texts:
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

    return shape


def _layout_statements(
    statements: list[ast.Statement], direction: int, ctx: _Ctx
) -> tuple[list[Shape], int, tuple[float, float, float, float]]:
    shapes: list[Shape] = []
    prev: Shape | None = None

    for stmt in statements:
        if isinstance(stmt, ast.DirectionStatement):
            direction = _DIR_CODE[stmt.direction]
            if prev is not None:
                _set_exit(prev, direction)
            continue
        if isinstance(stmt, ast.AssignStatement):
            current = ctx.vars.get(stmt.name, 0.0)
            rhs = eval_rvalue(stmt.value, ctx)
            ctx.vars[stmt.name] = {
                "=": rhs, "+=": current + rhs, "-=": current - rhs,
                "*=": current * rhs, "/=": current / rhs if rhs != 0 else current,
            }[stmt.op]
            continue
        if isinstance(stmt, (ast.PrintStatement, ast.AssertExprStatement, ast.AssertPositionStatement)):
            continue
        if isinstance(stmt, ast.LabelPosition):
            pt = eval_position(stmt.position, ctx)
            shape = Shape(kind="point", name=stmt.label, cx=pt[0], cy=pt[1], w=0.0, h=0.0,
                          enter=pt, exit=pt, in_dir=direction, out_dir=direction)
            shapes.append(shape)
            ctx.pool_stack[-1].append(shape)
            ctx.scope_stack[-1][stmt.label] = shape
            prev = shape
            continue
        if isinstance(stmt, ast.ObjectStatement):
            shape = _layout_object(stmt, direction, prev, ctx)
            shapes.append(shape)
            ctx.pool_stack[-1].append(shape)
            if stmt.label:
                shape.name = stmt.label
                ctx.scope_stack[-1][stmt.label] = shape
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


def _flatten(shapes: list[Shape]) -> list[Shape]:
    out: list[Shape] = []
    for shape in shapes:
        if shape.kind == "block":
            out.extend(_flatten(shape.sublist))
        elif shape.kind not in _NOT_RENDERED:
            out.append(shape)
    return out


def resolve_layout(doc: ast.Document, metrics: FontMetrics | None = None) -> LayoutResult:
    """Resolve a parsed pik :class:`~pypik.pik.ast.Document` into concrete,
    ready-to-render geometry. See the module docstring for what this
    pragmatic layout engine does and does not faithfully reproduce.

    `metrics`, if given, is used to size "fit" objects from their actual
    text content instead of the built-in charwid/charht approximation --
    pass a renderer-specific FontMetrics (e.g. pptx_writer.PilFontMetrics)
    to get "fit" sizes that track what will actually be drawn."""
    ctx = _Ctx(metrics)
    shapes, _direction, _bbox = _layout_statements(doc.statements, DIR_RIGHT, ctx)
    flat = _flatten(shapes)
    if flat:
        x0 = min(s.bbox[0] for s in flat)
        y0 = min(s.bbox[1] for s in flat)
        x1 = max(s.bbox[2] for s in flat)
        y1 = max(s.bbox[3] for s in flat)
        bbox = (x0, y0, x1, y1)
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    return LayoutResult(shapes=flat, bbox=bbox)

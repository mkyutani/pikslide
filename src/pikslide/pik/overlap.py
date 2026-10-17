"""Find where a laid-out diagram's objects, text and lines overlap (issue
#19), and where a line's labels sit badly on it (issue #1): the faults an
LLM would otherwise look for in the PNG, named so that it can fix them and
check again.

Warns about:

- two objects that partly overlap;
- text on text: an object's strings, or a line's labels, on another's;
- a line's label on another line, or partly on an object;
- a line passing through an object other than the ones at its ends, or
  through an object's text;
- a line's label on the line itself, or off it: a bent line's labels go
  at the middle of the box round it, which may be on none of its
  segments.

Overlaps that are meant don't warn: an object wholly inside another (a
frame round a group, a pin on a map), an object drawn `behind` another,
and a line's ends on the objects they join. Touching isn't overlapping:
everything here allows `TOLERANCE`. What isn't drawn doesn't count: an
`invis` line, and an `invis` object with no fill but for its text.

Outlines are convex polygons: a circle or an ellipse as one, a diamond as
its four corners, a `text` object as its strings, and anything else, a
preset shape too, as its bounding box. A line is the points it is drawn
through, an arc its curve in short straight pieces. Where a string goes
is the renderer's to say, so callers pass `text_rects`: each of a
shape's strings' rectangles, as drawn."""

from __future__ import annotations

import math
from typing import Callable

from .layout import LINE_LIKE, LayoutWarning, Shape, line_points

Point = tuple[float, float]
Polygon = list[Point]
Rect = tuple[float, float, float, float]
"""(x0, y0, x1, y1), inches, y up."""

TOLERANCE = 0.02
"""How far (inches) two things may run into each other before it counts:
less than a line's width, and than the gap round a line of text."""

_ELLIPSE_SIDES = 48
_ELLIPSES = {"circle", "ellipse", "oval"}
_ELLIPSE_PRESETS = {"ellipse", "flowChartConnector"}
_DIAMOND_PRESETS = {"diamond", "flowChartDecision"}


def find_overlaps(shapes: list[Shape], text_rects: Callable[[Shape], list[Rect]]) -> list[LayoutWarning]:
    """The overlaps among `shapes`, the drawn ones (flatten_shapes()), and
    the lines whose labels are on them or off them, in source order; each
    pair of things is named once."""
    lines = [s for s in shapes if s.kind in LINE_LIKE and s.path and len(s.path) > 1]
    drawn = [line for line in lines if line.sw >= 0]
    objects = [s for s in shapes if s.kind not in LINE_LIKE]
    strings = {id(s): [(t, _Convex(_corners(r))) for (t, _f), r in zip(s.texts, text_rects(s))] for s in shapes}
    outline = {id(o): _outline(o, [r for _t, r in strings[id(o)]]) for o in objects}
    points = {id(line): line_points(line) for line in lines}
    paths = {id(line): _Convex(points[id(line)]) for line in lines}
    warnings: list[LayoutWarning] = []
    named: set[frozenset[int]] = set()

    def warn(a: Shape, b: Shape, message: str) -> None:
        named.add(frozenset((id(a), id(b))))
        warnings.append(LayoutWarning(message, (a.name or "", b.name or "")))

    def warn_about(line: Shape, message: str) -> None:
        warnings.append(LayoutWarning(message, (line.name or "",)))

    def done(a: Shape, b: Shape) -> bool:
        return frozenset((id(a), id(b))) in named

    for i, a in enumerate(objects):
        for b in objects[i + 1:]:
            if _meant(a, b):
                continue
            pa, pb = outline[id(a)], outline[id(b)]
            if _overlap(pa, pb) and not (_within(pa, pb) or _within(pb, pa)):
                warn(a, b, f"{a.name} and {b.name} overlap: move one off the other, or wholly inside it; "
                           f"if it's meant, draw one `behind` the other")

    for i, a in enumerate(shapes):
        for b in shapes[i + 1:]:
            if done(a, b):
                continue
            hit = next(((ta, tb) for ta, ra in strings[id(a)] for tb, rb in strings[id(b)]
                        if _overlap([ra], [rb])), None)
            if hit is not None:
                warn(a, b, f'text on text: {_whose(a, hit[0])} and {_whose(b, hit[1])}')

    for line in lines:
        segments = list(zip(points[id(line)], points[id(line)][1:]))
        labels = strings[id(line)]
        if line.sw >= 0 and labels:
            on = next((t for t, r in labels if any(_crosses(p, q, [r]) for p, q in segments)), None)
            if on is not None:
                warn_about(line, f"{_whose(line, on)} is on the line itself: make it above or below, "
                                 f"or beside a vertical line, ljust or rjust")
            elif not any(_crosses(p, q, [_near(labels)]) for p, q in segments):
                who = _whose(line, labels[0][0]) + " is" if len(labels) == 1 else f"{line.name}'s labels are"
                warn_about(line, f"{who} off the line, at the middle of the box round it: label a straight "
                                 f"line instead, or place the text as an object of its own")
        for text, rect in labels:
            label = [rect]
            for o in objects:
                if done(line, o) or _meant(line, o):
                    continue
                po = outline[id(o)]
                if _overlap(label, po) and not _within(label, po):
                    warn(line, o, f'{_whose(line, text)} is on {o.name}: move it (above, below, ljust, '
                                  f'rjust) or move the line')
            for other in drawn:
                if other is line or done(line, other):
                    continue
                if any(_crosses(p, q, label) for p, q in zip(points[id(other)], points[id(other)][1:])):
                    warn(line, other, f'{_whose(line, text)} is on {other.name}: move it (above, below, '
                                      f'ljust, rjust) or move one of the lines')
        if line.sw < 0:
            continue
        ends = [o for o in objects if _at_end(line, outline[id(o)])]
        for o in objects:
            if done(line, o) or _meant(line, o):
                continue
            po = outline[id(o)]
            if not any(o is e for e in ends) and not _within([paths[id(line)]], po):
                if any(_crosses(p, q, po) for p, q in segments):
                    warn(line, o, f"{line.name} passes through {o.name}, which is at neither of its ends: "
                                  f"route it round")
                continue
            # A line inside the object, or ending on it, may still cross its text.
            text = next((t for t, r in strings[id(o)] if any(_crosses(p, q, [r]) for p, q in segments)), None)
            if text is not None:
                warn(line, o, f"{line.name} passes through {_whose(o, text)}")
    return warnings


def _whose(shape: Shape, text: str) -> str:
    what = "label" if shape.kind in LINE_LIKE else "text"
    return f'{shape.name}\'s {what} "{text}"'


def _meant(a: Shape, b: Shape) -> bool:
    return a.behind is b or b.behind is a


def _near(labels: list[tuple[str, _Convex]]) -> _Convex:
    """The box round a line's labels, grown by a label's height: how
    near the line has to come for them to be its."""
    x0, y0, x1, y1 = (f(r.box[k] for _t, r in labels) for f, k in ((min, 0), (min, 1), (max, 2), (max, 3)))
    gap = labels[0][1].box[3] - labels[0][1].box[1]
    return _Convex(_corners((x0 - gap, y0 - gap, x1 + gap, y1 + gap)))


def _at_end(line: Shape, parts: list[_Convex]) -> bool:
    assert line.path is not None
    return any(_within([_Convex([p])], parts) for p in (line.path[0], line.path[-1]))


# ---------------------------------------------------------------------------
# Outlines: each a list of convex polygons
# ---------------------------------------------------------------------------


class _Convex:
    """A convex polygon's corners, or a path's points, with the box round
    them, to rule a pair out cheaply, and, once asked for, its sides."""

    def __init__(self, points: Polygon):
        self.points = points
        xs = [x for x, _y in points]
        ys = [y for _x, y in points]
        self.box = (min(xs), min(ys), max(xs), max(ys))
        self._planes: list[tuple[float, float, float]] | None = None

    @property
    def planes(self) -> list[tuple[float, float, float]]:
        """(nx, ny, d) for each side, n its outward unit normal: the
        polygon is where n.p <= d for every side. Sides of no length are
        skipped."""
        if self._planes is None:
            poly = self.points
            n = len(poly)
            cx = sum(x for x, _y in poly) / n
            cy = sum(y for _x, y in poly) / n
            self._planes = []
            for i in range(n):
                (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
                length = math.hypot(bx - ax, by - ay)
                if length < 1e-12:
                    continue
                nx, ny = (by - ay) / length, -(bx - ax) / length
                d = nx * ax + ny * ay
                if nx * cx + ny * cy > d:
                    nx, ny, d = -nx, -ny, -d
                self._planes.append((nx, ny, d))
        return self._planes


def _outline(shape: Shape, text: list[_Convex]) -> list[_Convex]:
    if shape.kind == "text" or (shape.kind != "image" and shape.sw < 0 and shape.fill is None):
        return text
    x0, y0, x1, y1 = shape.bbox
    if shape.kind in _ELLIPSES or shape.preset in _ELLIPSE_PRESETS:
        rx, ry = shape.w / 2, shape.h / 2
        return [_Convex([(shape.cx + rx * math.cos(a), shape.cy + ry * math.sin(a))
                         for a in (2 * math.pi * k / _ELLIPSE_SIDES for k in range(_ELLIPSE_SIDES))])]
    if shape.kind == "diamond" or shape.preset in _DIAMOND_PRESETS:
        return [_Convex([(shape.cx, y1), (x1, shape.cy), (shape.cx, y0), (x0, shape.cy)])]
    return [_Convex(_corners(shape.bbox))]


def _corners(rect: Rect) -> Polygon:
    x0, y0, x1, y1 = rect
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ---------------------------------------------------------------------------
# Convex geometry
# ---------------------------------------------------------------------------


def _box_depth(a: Rect, b: Rect) -> tuple[float, float]:
    """How far two boxes overlap across, and up and down."""
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def _depth(p: _Convex, q: _Convex) -> float:
    """How far two convex polygons run into each other: the least overlap
    of their projections on any side's normal (separating axes); 0 or
    less when they don't."""
    best = math.inf
    for nx, ny, _d in p.planes + q.planes:
        pa = [nx * x + ny * y for x, y in p.points]
        qa = [nx * x + ny * y for x, y in q.points]
        best = min(best, min(max(pa), max(qa)) - max(min(pa), min(qa)))
    return best


def _overlap(ps: list[_Convex], qs: list[_Convex]) -> bool:
    return any(min(_box_depth(p.box, q.box)) > TOLERANCE and _depth(p, q) > TOLERANCE for p in ps for q in qs)


def _within(ps: list[_Convex], qs: list[_Convex]) -> bool:
    """Whether each of `ps` (polygons, or a path's points) lies within one
    of `qs`, grown by TOLERANCE."""
    def inside(p: _Convex, q: _Convex) -> bool:
        (px0, py0, px1, py1), (qx0, qy0, qx1, qy1) = p.box, q.box
        if px0 < qx0 - TOLERANCE or py0 < qy0 - TOLERANCE or px1 > qx1 + TOLERANCE or py1 > qy1 + TOLERANCE:
            return False
        return all(nx * x + ny * y <= d + TOLERANCE for x, y in p.points for nx, ny, d in q.planes)

    return all(any(inside(p, q) for q in qs) for p in ps)


def _crosses(a: Point, b: Point, parts: list[_Convex]) -> bool:
    """Whether the segment a-b runs into any of `parts`, shrunk by
    TOLERANCE (clipped to each side in turn: Cyrus-Beck)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    sx0, sx1 = min(a[0], b[0]), max(a[0], b[0])
    sy0, sy1 = min(a[1], b[1]), max(a[1], b[1])
    for poly in parts:
        x0, y0, x1, y1 = poly.box
        if sx1 <= x0 + TOLERANCE or sx0 >= x1 - TOLERANCE or sy1 <= y0 + TOLERANCE or sy0 >= y1 - TOLERANCE:
            continue
        t0, t1 = 0.0, 1.0
        for nx, ny, d in poly.planes:
            room = d - TOLERANCE - (nx * a[0] + ny * a[1])
            rate = nx * dx + ny * dy
            if abs(rate) < 1e-12:
                if room < 0:
                    break
                continue
            t = room / rate
            if rate > 0:
                t1 = min(t1, t)
            else:
                t0 = max(t0, t)
            if t0 >= t1:
                break
        else:
            if t1 - t0 > 1e-9:
                return True
    return False

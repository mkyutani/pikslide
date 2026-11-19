"""A preset shape's outline: its paths (preset_paths.py, ECMA-376 Part 1,
20.1.9.15) for a shape of a given size, as polygons, for --renderer direct
to draw (issue #34).

Each path is filled (with the shape's fill, none, or a lighter or darker
shade of it) and outlined, or not, on its own: a cylinder is a body, a
lighter top over it, and an outline with the top's front edge in it. A
path's curves are flattened to points close enough apart to draw.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .preset_paths import PATHS
from .text_area import EMU_PER_INCH, _guides

# Points per whole turn of an arc, and per Bezier curve: at the sizes a
# diagram's shapes are drawn, finer than a pixel's worth of error.
_ARC_POINTS = 144
_BEZIER_POINTS = 32


@dataclass
class OutlinePath:
    """One path of a preset's outline, in inches from the shape's top
    left, y down, as PowerPoint draws it unturned."""

    subpaths: list[tuple[list[tuple[float, float]], bool]]
    """Each subpath's points, and whether it's closed."""
    fill: str
    """norm (the shape's fill), none, lighten, lightenLess, darken or
    darkenLess."""
    stroke: bool


def outline(preset: str, w: float, h: float, adjust: dict[str, float] | None = None) -> list[OutlinePath]:
    """The paths of `preset` drawn `w` x `h` inches, `adjust` setting its
    adjust values as text_area.text_rect() takes them."""
    guides, paths = PATHS[preset]
    value = _guides(guides, w, h, adjust)
    W, H = w * EMU_PER_INCH, h * EMU_PER_INCH
    out = []
    for pw, ph, fill, stroke, commands in paths:
        # A path with a w and h of its own is drawn in that space, scaled
        # to the shape's.
        sx = W / value(pw) if pw and value(pw) else 1.0
        sy = H / value(ph) if ph and value(ph) else 1.0
        out.append(OutlinePath(_subpaths(commands, value, sx, sy), fill, stroke))
    return out


def _subpaths(commands, value, sx: float, sy: float) -> list[tuple[list[tuple[float, float]], bool]]:
    subpaths: list[tuple[list[tuple[float, float]], bool]] = []
    points: list[tuple[float, float]] = []
    start = cur = (0.0, 0.0)

    def end_subpath(closed: bool) -> None:
        nonlocal points
        if len(points) > 1:
            subpaths.append(([(x / EMU_PER_INCH, y / EMU_PER_INCH) for x, y in points], closed))
        points = []

    def pt(x: str, y: str) -> tuple[float, float]:
        return value(x) * sx, value(y) * sy

    for letter, *args in commands:
        if letter == "M":
            end_subpath(False)
            start = cur = pt(*args)
            points = [cur]
        elif letter == "Z":
            end_subpath(True)
            # A command after a close starts from where the subpath did
            # (accentBorderCallout1 draws a line on from there).
            cur = start
        else:
            if not points:
                points = [cur]
            if letter == "L":
                cur = pt(*args)
                points.append(cur)
            elif letter == "A":
                arc = _arc(cur, *(value(a) for a in args), sx, sy)
                points += arc
                cur = arc[-1] if arc else cur
            else:
                controls = [pt(args[i], args[i + 1]) for i in range(0, len(args), 2)]
                curve = _bezier([cur, *controls])
                points += curve
                cur = curve[-1]
    end_subpath(False)
    return subpaths


def _arc(cur: tuple[float, float], wr: float, hr: float, st: float, sw: float, sx: float, sy: float) -> list[tuple[float, float]]:
    """arcTo from `cur`: an arc of the ellipse with radii wR and hR, from
    stAng through swAng (60000ths of a degree, clockwise, y down), which
    starts at `cur`. The angles are where a point is seen from the
    ellipse's center, not the parameter of its equation, as PowerPoint
    draws them (and Apache POI's and LibreOffice's renderers do): a
    quarter of a wide ellipse's arc ends at its side, not short of it."""
    if wr == 0 or hr == 0:
        return []
    a0 = math.radians(st / 60000)
    a1 = math.radians((st + sw) / 60000)
    t0, t1 = _parameter(a0, wr, hr), _parameter(a1, wr, hr)
    rx, ry = wr * sx, hr * sy
    cx, cy = cur[0] - rx * math.cos(t0), cur[1] - ry * math.sin(t0)
    n = max(2, math.ceil(abs(t1 - t0) / (2 * math.pi) * _ARC_POINTS))
    return [(cx + rx * math.cos(t0 + (t1 - t0) * i / n), cy + ry * math.sin(t0 + (t1 - t0) * i / n))
            for i in range(1, n + 1)]


def _parameter(angle: float, wr: float, hr: float) -> float:
    """The parameter of the point at `angle` as seen from an ellipse's
    center, in the same turn as `angle`: the two are in the same
    quadrant, so never as much as a quarter turn apart."""
    t = math.atan2(wr * math.sin(angle), hr * math.cos(angle))
    return t + round((angle - t) / (2 * math.pi)) * 2 * math.pi


def _bezier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """A quadratic or cubic Bezier curve from points[0], less that point."""
    n = len(points) - 1
    out = []
    for i in range(1, _BEZIER_POINTS + 1):
        t = i / _BEZIER_POINTS
        coeffs = [math.comb(n, k) * (1 - t) ** (n - k) * t**k for k in range(n + 1)]
        out.append((sum(c * p[0] for c, p in zip(coeffs, points)), sum(c * p[1] for c, p in zip(coeffs, points))))
    return out

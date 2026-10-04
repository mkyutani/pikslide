"""Where PowerPoint sets a preset shape's text: its text rectangle.

Every preset geometry (ECMA-376 Part 1, 20.1.9) has one, `<rect l t r b>`,
and PowerPoint lays the text out inside it -- less the text frame's own
insets (`margin`) -- not inside the whole bounding box. For many presets
it's smaller: a diamond's is its middle half, a parallelogram's leaves
out its slanted ends. Its sides are shape guides, formulas in the shape's
width, height and adjust values; preset_text_rects.py holds them, and
this evaluates them.
"""

from __future__ import annotations

import math
import re

from .preset_text_rects import TEXT_RECTS

EMU_PER_INCH = 914400

# The built-in guides that aren't a length divided by a number (wd2, hd4,
# ssd8, ...): angles are in 60000ths of a degree.
_ANGLES = {
    "cd2": 10800000, "cd4": 5400000, "cd8": 2700000,
    "3cd4": 16200000, "3cd8": 8100000, "5cd8": 13500000, "7cd8": 18900000,
}
_DIVIDED = re.compile(r"(w|h|ss)d(\d+)$")


def _rad(angle: float) -> float:
    return math.radians(angle / 60000)


def _div(x: float, y: float) -> float:
    return x / y if y else 0.0


# The guide formula operators (ECMA-376 Part 1, 20.1.10.30, ST_GeomGuideFormula).
_OPS = {
    "val": lambda x: x,
    "abs": abs,
    "sqrt": lambda x: math.sqrt(max(x, 0.0)),
    "max": max,
    "min": min,
    "*/": lambda x, y, z: _div(x * y, z),
    "+-": lambda x, y, z: x + y - z,
    "+/": lambda x, y, z: _div(x + y, z),
    "?:": lambda x, y, z: y if x > 0 else z,
    "pin": lambda x, y, z: x if y < x else z if y > z else y,
    "mod": lambda x, y, z: math.sqrt(x * x + y * y + z * z),
    "sin": lambda x, y: x * math.sin(_rad(y)),
    "cos": lambda x, y: x * math.cos(_rad(y)),
    "tan": lambda x, y: x * math.tan(_rad(y)),
    "at2": lambda x, y: math.degrees(math.atan2(y, x)) * 60000,
    "cat2": lambda x, y, z: x * math.cos(math.atan2(z, y)),
    "sat2": lambda x, y, z: x * math.sin(math.atan2(z, y)),
}


def text_rect(
    preset: str, w: float, h: float, adjust: dict[str, float] | None = None
) -> tuple[float, float, float, float]:
    """The text rectangle (left, top, right, bottom) of `preset` drawn
    `w` x `h` inches, in inches from its top left corner. `adjust` sets
    adjust values (`adj`, `adj1`, ...) as OOXML writes them, 100000 for 1;
    the rest keep their defaults, as pikslide draws them."""
    guides, sides = TEXT_RECTS[preset]
    W, H = w * EMU_PER_INCH, h * EMU_PER_INCH
    ss = min(W, H)
    env = {"w": W, "h": H, "l": 0.0, "t": 0.0, "r": W, "b": H, "hc": W / 2, "vc": H / 2,
           "ss": ss, "ls": max(W, H), **_ANGLES}

    def value(arg: str) -> float:
        if arg in env:
            return env[arg]
        if m := _DIVIDED.match(arg):
            return {"w": W, "h": H, "ss": ss}[m.group(1)] / int(m.group(2))
        return float(arg)

    for name, fmla in guides:
        if adjust is not None and name in adjust:
            env[name] = adjust[name]
            continue
        op, *args = fmla.split()
        env[name] = _OPS[op](*map(value, args))
    left, top, right, bottom = (value(side) / EMU_PER_INCH for side in sides)
    return left, top, right, bottom


def fit_size(preset: str, text_w: float, text_h: float) -> tuple[float, float]:
    """The smallest size (by area) to draw `preset` at, at its default
    adjust values, for its text rectangle to hold a text box `text_w` x
    `text_h` (inches).

    A text rectangle grows in proportion when the whole shape does, so
    each shape of one aspect ratio has exactly one size that holds the
    text; this finds the aspect ratio whose size is smallest. That's
    seldom the text's own: a parallelogram's text rectangle leaves out its
    slanted ends, so it has to be wider, and an arrow's leaves out a head
    as long as its shorter side is, so how wide it has to be depends on
    how tall it is."""
    if text_w <= 0 or text_h <= 0:
        return text_w, text_h

    def size(aspect: float) -> tuple[float, float]:
        left, top, right, bottom = text_rect(preset, aspect, 1.0)
        if right - left <= 0 or bottom - top <= 0:
            return math.inf, math.inf
        scale = max(text_w / (right - left), text_h / (bottom - top))
        return aspect * scale, scale

    def area(log_aspect: float) -> float:
        w, h = size(math.exp(log_aspect))
        return w * h

    # Every aspect ratio from a hundredth of the text's to a hundred times
    # it, on a grid; then, between the best point's neighbors, a golden-
    # section search. Of equally small sizes, the closest to the text's
    # own shape wins.
    log_text = math.log(text_w / text_h)
    step = math.log(100) / 60
    grid = [log_text + i * step for i in range(-60, 61)]
    areas = [area(x) for x in grid]
    least = min(areas)
    best = min((i for i, a in enumerate(areas) if a <= least * (1 + 1e-9)), key=lambda i: abs(grid[i] - log_text))
    lo, hi = grid[max(best - 1, 0)], grid[min(best + 1, len(grid) - 1)]
    inv_phi = (math.sqrt(5) - 1) / 2
    for _ in range(40):
        a, b = hi - inv_phi * (hi - lo), lo + inv_phi * (hi - lo)
        if area(a) <= area(b):
            hi = b
        else:
            lo = a
    x = (lo + hi) / 2
    return size(math.exp(x)) if area(x) <= areas[best] else size(math.exp(grid[best]))

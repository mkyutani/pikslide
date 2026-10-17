"""The route of an elbow connector between two connection sites, as
PowerPoint's own elbow connector takes it (issue #18): `path elbow`.

PowerPoint routes an elbow connector itself whenever a shape it is
attached to moves; pikslide routes it the same way, so that the slide
shows what PowerPoint would draw, and nothing jumps when a person first
moves a shape. The rules below were found by having PowerPoint attach
connectors between rectangles of many sizes and places, every pair of
sites, and reading back the routes it wrote; they reproduce all of a
grid of 736 of them, and 199 of 200 placed at random. (Between ellipses'
diagonal sites, PowerPoint seems to weigh the outline, not the box; 4 in
5 of those come out the same.)

- The route has the fewest segments it can: one, then an L, then three,
  four, five.
- It leaves a site at least STANDOFF straight out, and keeps STANDOFF
  clear of both shapes' boxes, but where the boxes face each other across
  less than twice that, it runs down the middle of the gap between them.
  An L (one bend) only has to miss the shapes.
- Of routes with as few segments, one that starts away from the other
  shape goes round on that shape's side; then the shortest; then one down
  the middle of a gap; then one that turns the way PowerPoint does when
  the two sides are alike.

Coordinates are inches with y up, as everywhere in layout; the rules
themselves work with y down, as PowerPoint does, since its choices
between mirror images depend on which way is down.
"""

from __future__ import annotations

import itertools

Point = tuple[float, float]
Box = tuple[float, float, float, float]
"""(x0, y0, x1, y1)."""

STANDOFF = 0.25
"""How far (inches) a route leaves a site straight out, and keeps clear of
the shapes: PowerPoint's 18pt."""

_EPS = 1e-6


def route(start: Point, start_dir: tuple[int, int], end: Point, end_dir: tuple[int, int],
          start_box: Box, end_box: Box) -> list[Point] | None:
    """An elbow connector's route from `start`, on `start_box`, to `end`, on
    `end_box`: its points, from start to end, each segment horizontal or
    vertical. `start_dir` and `end_dir` are the directions out of each
    shape at its site (unit vectors along an axis). y up; None if no route
    of five segments or fewer fits."""
    flip = lambda p: (p[0], -p[1])  # noqa: E731
    flip_box = lambda b: (b[0], -b[3], b[2], -b[1])  # noqa: E731
    points = _route(flip(start), flip(start_dir), flip(end), flip(end_dir), flip_box(start_box), flip_box(end_box))
    return None if points is None else [flip(p) for p in points]


def _route(S: Point, ds: Point, E: Point, de: Point, A: Box, B: Box) -> list[Point] | None:
    """route(), with y down."""
    gaps = [_gap(A[0], A[2], B[0], B[2]), _gap(A[1], A[3], B[1], B[3])]
    mids = [None if g is None else (g[0] + g[1]) / 2 for g in gaps]
    # Each box grown by STANDOFF, but by only half the gap on a side facing
    # the other box across less than twice that.
    GA, GB = [A[0] - STANDOFF, A[1] - STANDOFF, A[2] + STANDOFF, A[3] + STANDOFF], \
        [B[0] - STANDOFF, B[1] - STANDOFF, B[2] + STANDOFF, B[3] + STANDOFF]
    for axis in (0, 1):
        g = gaps[axis]
        if g is not None and g[1] - g[0] < 2 * STANDOFF:
            lo, hi = (GA, GB) if A[axis + 2] <= B[axis] else (GB, GA)
            lo[axis + 2] = hi[axis] = (g[0] + g[1]) / 2
    # Where a route may turn: STANDOFF off either box's sides or out of
    # either site, or the middle of a gap between the boxes.
    turns: list[set[float]] = [{A[0] - STANDOFF, A[2] + STANDOFF, B[0] - STANDOFF, B[2] + STANDOFF},
                               {A[1] - STANDOFF, A[3] + STANDOFF, B[1] - STANDOFF, B[3] + STANDOFF}]
    for axis in (0, 1):
        if mids[axis] is not None:
            turns[axis].add(mids[axis])
    first, last = (0 if ds[0] else 1), (0 if de[0] else 1)
    turns[first].add(S[first] + STANDOFF * ds[first])
    turns[last].add(E[last] + STANDOFF * de[last])
    candidates = [sorted(t) for t in turns]
    ac, bc = ((A[0] + A[2]) / 2, (A[1] + A[3]) / 2), ((B[0] + B[2]) / 2, (B[1] + B[3]) / 2)
    # Starting away from the other shape, the route goes round on its side.
    away_from_b = ds[0] * (bc[0] - ac[0]) + ds[1] * (bc[1] - ac[1]) < 0
    same_facing = tuple(ds) == tuple(de)

    best = None
    for n in range(1, 6):
        axes = [(first + i) % 2 for i in range(n)]
        if axes[-1] != last:
            continue
        # turn[i]: where segment i ends, along its axis; the turn before the
        # last segment is level with the end.
        choices = [candidates[axes[i]] for i in range(n - 2)] + ([[E[axes[n - 2]]]] if n >= 2 else [])
        for turn in itertools.product(*choices):
            pts = [S]
            cur = list(S)
            for i in range(n - 1):
                cur[axes[i]] = turn[i]
                pts.append((cur[0], cur[1]))
            cur[last] = E[last]
            if abs(cur[0] - E[0]) > _EPS or abs(cur[1] - E[1]) > _EPS:
                continue
            pts.append(E)
            if not _fits(pts, axes, ds, de, A, B, GA, GB, gaps, mids):
                continue
            segments = list(zip(pts, pts[1:]))
            length = sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in segments)
            off_side = sum(1 for i, t in enumerate(turn[:-1]) if away_from_b
                           and abs(bc[axes[i]] - ac[axes[i]]) > _EPS and (t - ac[axes[i]]) * (bc[axes[i]] - ac[axes[i]]) < 0)
            in_gaps = sum(1 for i, t in enumerate(turn) if _is(t, mids[axes[i]]))
            area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
            wrong_turn = area > _EPS if same_facing else area < -_EPS
            key = (n, off_side, round(length, 9), -in_gaps, wrong_turn, tuple(-t for t in turn))
            if best is None or key < best[0]:
                best = (key, pts)
    return None if best is None else best[1]


def _fits(pts: list[Point], axes: list[int], ds: Point, de: Point, A: Box, B: Box,
          GA: list[float], GB: list[float], gaps: list, mids: list) -> bool:
    n = len(pts) - 1
    segments = list(zip(pts, pts[1:]))
    if any(abs(p[0] - q[0]) < _EPS and abs(p[1] - q[1]) < _EPS for p, q in segments):
        return False
    first, last = axes[0], axes[-1]
    (p, q), (r, s) = segments[0], segments[-1]
    # Out of the start site, and into the end site.
    if (q[first] - p[first]) * ds[first] <= 0 or (s[last] - r[last]) * -de[last] <= 0:
        return False
    # Through neither shape (a site inside its box, as an ellipse's
    # diagonal ones are, starts or ends a route there).
    if any((i > 0 and _crosses(p, q, A)) or (i < n - 1 and _crosses(p, q, B)) for i, (p, q) in enumerate(segments)):
        return False
    if n < 3:
        return True
    # At least STANDOFF out of each site, unless turning in a gap's middle.
    if abs(q[first] - p[first]) < STANDOFF - _EPS and not _is(q[first], mids[first]):
        return False
    if abs(s[last] - r[last]) < STANDOFF - _EPS and not _is(r[last], mids[last]):
        return False
    # The rest clear of both grown boxes; on a route of four segments or
    # more, the turn out of a site's stub need only clear the other's.
    for i in range(1, n - 1):
        p, q = segments[i]
        if (i != 1 or n < 4) and _crosses(p, q, GA):
            return False
        if (i != n - 2 or n < 4) and _crosses(p, q, GB):
            return False
    if n == 4:
        # The turn before the last stub keeps clear of both boxes' extents,
        # where they overlap along it.
        p, q = segments[2]
        axis = 0 if abs(p[0] - q[0]) < _EPS else 1
        lo, hi = min(A[axis], B[axis]) - STANDOFF, max(A[axis + 2], B[axis + 2]) + STANDOFF
        if gaps[axis] is None and lo + _EPS < p[axis] < hi - _EPS:
            return False
    return True


def _gap(a0: float, a1: float, b0: float, b1: float) -> tuple[float, float] | None:
    """The gap between two intervals, if they don't overlap."""
    if a1 < b0:
        return a1, b0
    if b1 < a0:
        return b1, a0
    return None


def _is(value: float, mid: float | None) -> bool:
    return mid is not None and abs(value - mid) < _EPS


def _crosses(p: Point, q: Point, box, eps: float = 1e-4) -> bool:
    """Whether the horizontal or vertical segment p-q runs into `box`'s
    inside (touching its edge doesn't count)."""
    x0, y0, x1, y1 = box
    if abs(p[1] - q[1]) < _EPS:
        lo, hi = sorted((p[0], q[0]))
        return y0 + eps < p[1] < y1 - eps and lo < x1 - eps and hi > x0 + eps
    lo, hi = sorted((p[1], q[1]))
    return x0 + eps < p[0] < x1 - eps and lo < y1 - eps and hi > y0 + eps

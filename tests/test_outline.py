"""`pikslide.pik.outline` -- a preset shape's paths, as polygons, for
--renderer direct (issue #34)."""

from __future__ import annotations

import math

import pytest

from pikslide.pik.layout import PRESET_NAMES
from pikslide.pik.outline import outline


@pytest.mark.parametrize("preset", sorted(PRESET_NAMES.values()))
@pytest.mark.parametrize("w, h", [(1.0, 0.5), (0.5, 1.0)])
def test_every_preset_has_an_outline(preset: str, w: float, h: float):
    paths = outline(preset, w, h)
    assert paths
    points = [p for path in paths for subpath, _closed in path.subpaths for p in subpath]
    assert points and all(math.isfinite(x) and math.isfinite(y) for x, y in points)


def test_a_rectangle_is_its_four_corners():
    [path] = outline("rect", 2.0, 1.0)
    assert path.subpaths == [([(0, 0), (2, 0), (2, 1), (0, 1)], True)]
    assert (path.fill, path.stroke) == ("norm", True)


def test_an_ellipse_is_on_the_ellipse():
    [path] = outline("ellipse", 2.0, 1.0)
    [(points, closed)] = path.subpaths
    assert closed
    for x, y in points:
        assert ((x - 1) / 1) ** 2 + ((y - 0.5) / 0.5) ** 2 == pytest.approx(1)


def test_an_arcs_angles_are_seen_from_its_center():
    # `arc` runs from 270 degrees (straight up) to 0 (right): on a wide
    # ellipse, from the top middle to the right middle, which the
    # parameter of the ellipse's equation would fall short of.
    [fill, line] = outline("arc", 2.0, 1.0)
    [(points, closed)] = line.subpaths
    assert not closed and line.fill == "none"
    assert points[0] == pytest.approx((1.0, 0.0))
    assert points[-1] == pytest.approx((2.0, 0.5))
    assert not fill.stroke


def test_a_cylinder_has_a_lighter_top_and_an_outline_of_its_own():
    body, top, edge = outline("can", 1.0, 1.0)
    assert [(p.fill, p.stroke) for p in (body, top, edge)] == [("norm", False), ("lighten", False), ("none", True)]


def test_adjust_values_change_the_outline():
    sharp = outline("roundRect", 1.0, 1.0, {"adj": 0})
    round_ = outline("roundRect", 1.0, 1.0, {"adj": 50000})
    assert len(sharp[0].subpaths[0][0]) < len(round_[0].subpaths[0][0])
    # a circle, at the most
    for x, y in round_[0].subpaths[0][0]:
        assert math.hypot(x - 0.5, y - 0.5) == pytest.approx(0.5, abs=1e-6) or min(x, y) < 1e-9 or max(x, y) > 1 - 1e-9


def test_a_path_in_a_space_of_its_own_is_scaled_to_the_shape():
    # cloud's paths are drawn in a 43200 x 43200 space
    paths = outline("cloud", 2.0, 1.0)
    xs = [x for path in paths for points, _ in path.subpaths for x, _y in points]
    ys = [y for path in paths for points, _ in path.subpaths for _x, y in points]
    # within its box but for its arcs' slight overshoot, as defined
    assert -0.01 <= min(xs) and max(xs) <= 2.01
    assert -0.01 <= min(ys) and max(ys) <= 1.01
    assert max(xs) - min(xs) > 1.8


def test_a_line_after_a_close_starts_where_the_subpath_did():
    # accentBorderCallout1's accent bar: M x1 t, Z, L x1 b
    _box, bar, _leader = outline("accentBorderCallout1", 1.0, 1.0)
    assert [points for points, _closed in bar.subpaths][-1] == [pytest.approx((-0.08333, 0.0), abs=1e-4),
                                                                pytest.approx((-0.08333, 1.0), abs=1e-4)]

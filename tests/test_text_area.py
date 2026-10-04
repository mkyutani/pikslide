"""Tests for pikslide.pik.text_area: where PowerPoint sets a preset
shape's text (issue #12)."""

from __future__ import annotations

import pytest

from pikslide.pik.layout import PRESET_NAMES
from pikslide.pik.preset_text_rects import TEXT_RECTS
from pikslide.pik.text_area import fit_size, text_rect


def test_every_preset_has_a_text_rectangle():
    assert set(TEXT_RECTS) == set(PRESET_NAMES.values())


def test_text_rectangle_is_inside_the_shape():
    outside = []
    for preset in TEXT_RECTS:
        for w, h in [(1.0, 0.7), (2.0, 0.45), (0.5, 2.0)]:
            left, top, right, bottom = text_rect(preset, w, h)
            if not (0 <= left < right <= w + 1e-9 and 0 <= top < bottom <= h + 1e-9):
                outside.append((preset, w, h))
    assert outside == []


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("rect", (0, 0, 1.6, 0.7)),
        # The middle half, both ways.
        ("diamond", (0.4, 0.175, 1.2, 0.525)),
        ("flowChartDecision", (0.4, 0.175, 1.2, 0.525)),
        # Leaves out the slanted ends: a fifth of the width each.
        ("flowChartInputOutput", (0.32, 0, 1.28, 0.7)),
        # The inscribed rectangle.
        ("ellipse", (0.8 - 0.8 / 2**0.5, 0.35 - 0.35 / 2**0.5, 0.8 + 0.8 / 2**0.5, 0.35 + 0.35 / 2**0.5)),
        # The definitions swap pie's top and right; it's the ellipse's.
        ("pie", (0.8 - 0.8 / 2**0.5, 0.35 - 0.35 / 2**0.5, 0.8 + 0.8 / 2**0.5, 0.35 + 0.35 / 2**0.5)),
    ],
)
def test_text_rectangle(preset: str, expected: tuple[float, ...]):
    assert text_rect(preset, 1.6, 0.7) == pytest.approx(expected)


def test_adjust_values_move_the_text_rectangle():
    # roundRect's text is inset 0.29 of its corner radius, a fraction
    # (adj, 100000 for 1) of the shorter side.
    assert text_rect("roundRect", 2.0, 1.0, {"adj": 50000})[0] == pytest.approx(0.5 * 0.29289)
    assert text_rect("roundRect", 2.0, 1.0)[0] == pytest.approx(0.16667 * 0.29289)


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("rect", (1.2, 0.3)),
        ("diamond", (2.4, 0.6)),
        ("flowChartInputOutput", (2.0, 0.3)),
    ],
)
def test_fit_size(preset: str, expected: tuple[float, float]):
    assert fit_size(preset, 1.2, 0.3) == pytest.approx(expected)


def test_fit_size_just_holds_the_text():
    wrong = []
    for preset in TEXT_RECTS:
        for text_w, text_h in [(1.0, 0.3), (0.2, 0.3), (2.0, 1.0)]:
            left, top, right, bottom = text_rect(preset, *fit_size(preset, text_w, text_h))
            spare = (right - left - text_w, bottom - top - text_h)
            # Room for the text, and on one side at least, none to spare.
            if not (min(spare) > -1e-6 and min(spare) < 1e-3):
                wrong.append((preset, text_w, text_h, spare))
    assert wrong == []

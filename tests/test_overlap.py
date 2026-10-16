"""Tests for pikslide.pik.overlap: warnings about objects, text and lines
that overlap (issue #19), and a line's labels on it or off it (issue #1),
through resolve_for_pptx(), which places the text as the deck draws it."""

from __future__ import annotations

import pathlib

import pytest

from pikslide.pik import parse
from pikslide.pptx_writer import resolve_for_pptx

COOKBOOK = sorted((pathlib.Path(__file__).parent.parent / "docs" / "cookbook").glob("*.pik"))


def overlaps(src: str) -> list[tuple[str, ...]]:
    """The objects each warning names; overflow warnings name one."""
    return [w.objects for w in resolve_for_pptx(parse(src)).warnings if len(w.objects) == 2]


def messages(src: str) -> list[str]:
    return [w.message for w in resolve_for_pptx(parse(src)).warnings if len(w.objects) == 2]


def alone(src: str) -> list[str]:
    """The warnings that name one line: its labels on it or off it."""
    return [w.message for w in resolve_for_pptx(parse(src)).warnings
            if len(w.objects) == 1 and "overflows" not in w.message]


def test_objects_that_partly_overlap_warn():
    assert overlaps("A: box\nB: box at A + (0.3, 0.2)\n") == [("A", "B")]
    [m] = messages("A: box\nB: box at A + (0.3, 0.2)\n")
    assert m.startswith("A and B overlap")


def test_objects_that_touch_or_nest_dont_warn():
    assert overlaps("right\nbox\nbox\ndown\nbox\n") == []
    assert overlaps("F: box wid 3 ht 2\nbox at F\ncircle at F + (1, 0)\n") == []


def test_circles_are_their_outline_not_their_box():
    # Their bounding boxes overlap at the corners; the circles don't.
    assert overlaps("circle rad 0.5\ncircle rad 0.5 at 1st circle + (0.8, 0.8)\n") == []
    assert overlaps("circle rad 0.5\ncircle rad 0.5 at 1st circle + (0.6, 0.6)\n") == [("circle 1", "circle 2")]


def test_an_object_drawn_behind_another_doesnt_warn_about_it():
    assert overlaps("A: box\nB: box at A + (0.3, 0.2) behind A\n") == []
    # Only about that one: drawn behind A, B still overlaps C.
    assert overlaps("A: box\nC: box at A + (0.6, -0.6)\nB: box at A + (0.3, -0.2) behind A\n") == [("B", "C")]


def test_text_on_text_warns():
    # The frame's text is under the inner box's, which is wholly inside it.
    assert overlaps('F: box "Frame" wid 2 ht 1\nbox "Inner" at F\n') == [("F", "box 2")]
    [m] = messages('F: box "Frame" wid 2 ht 1\nbox "Inner" at F\n')
    assert m == 'text on text: F\'s text "Frame" and box 2\'s text "Inner"'
    # Two lines' labels, once for the pair.
    assert overlaps('line "aaaa" from (0, 0) right 2\nline "bbbb" from (0, 0.05) right 2\n') == [("line 1", "line 2")]


def test_text_objects_are_their_strings():
    # The object is taller than its string, above the point it is placed at.
    assert overlaps('B: box\n"note" small above at B.ne + (0.3, 0)\n') == []
    assert overlaps('B: box\n"a long note" at B.e\n') == [("B", "text 1")]


def test_a_label_partly_on_an_object_warns():
    src = 'right\nA: box "A"\narrow "a long label" 0.2\nB: box "B"\n'
    assert overlaps(src) == [("arrow 1", "A"), ("arrow 1", "B")]
    [m, _] = messages(src)
    assert m.startswith('arrow 1\'s label "a long label" is on A')


def test_a_label_wholly_inside_a_frame_doesnt_warn():
    assert overlaps('F: box wid 3 ht 2\narrow "label" from F.w + (0.5, 0) right 1\n') == []
    # Across its edge, it does.
    assert overlaps('F: box wid 3 ht 2\narrow "label" from F.w - (0.5, 0) right 1\n') == [("arrow 1", "F")]


def test_a_label_on_another_line_warns():
    assert overlaps('line "label" from (0, 0) right 2\nline from (1, -0.5) up 1\n') == [("line 1", "line 2")]
    assert overlaps('line "label" above from (0, 0) right 2\nline from (1, -0.5) up 0.4\n') == []


def test_a_line_through_an_object_not_at_its_ends_warns():
    src = "right\nA: box\nmove\nB: box\nmove\nC: box\n"
    assert overlaps(src + "arrow from A.e to C.w\n") == [("arrow 1", "B")]
    assert overlaps(src + "arrow from A.e to B.w\n") == []
    [m] = messages(src + "arrow from A.e to C.w\n")
    assert m.startswith("arrow 1 passes through B, which is at neither of its ends")


def test_a_line_inside_a_frame_doesnt_warn_unless_it_crosses_its_text():
    src = "F: box wid 4 ht 2\nA: box at F - (1, 0)\nC: box at F + (1, 0)\n"
    assert overlaps(src + "arrow from A.e to C.w\n") == []
    framed = 'F: box "Frame" wid 4 ht 2\narrow from F.w + (0.2, 0) to F.e - (0.2, 0)\n'
    assert overlaps(framed) == [("arrow 1", "F")]
    assert messages(framed) == ['arrow 1 passes through F\'s text "Frame"']


def test_a_line_from_an_objects_center_crosses_its_text():
    src = 'A: box "A"\nB: box "B" at A + (2, 0)\n'
    assert overlaps(src + "arrow from A to B\n") == [("arrow 1", "A"), ("arrow 1", "B")]
    assert overlaps(src + "arrow from A to B chop\n") == []


def test_a_label_on_its_own_line_warns():
    [m] = alone('arrow "label" right 2\n')
    assert m.startswith('arrow 1\'s label "label" is on the line itself')
    assert alone('arrow "label" above right 2\n') == []
    assert alone('arrow "a" "b" right 2\n') == []
    # Above a vertical line is still on it; beside it isn't.
    assert len(alone('arrow "label" above down 1\n')) == 1
    assert alone('arrow "label" ljust down 1\n') == []
    assert alone('arrow "label" rjust down 1\n') == []


def test_a_bent_lines_labels_off_its_segments_warn():
    [m] = alone('arrow "label" above right 1 then down 1\n')
    assert m.startswith('arrow 1\'s label "label" is off the line, at the middle of the box round it')
    [m] = alone('arrow "a" "b" right 1 then down 1\n')
    assert m.startswith("arrow 1's labels are off the line")
    # Within a label's height of a segment, they're the line's.
    assert alone('arrow "label" above right 2 then down 0.6\n') == []


def test_what_isnt_drawn_doesnt_count():
    # An invisible line, or an invisible object with no fill but for its text.
    assert alone('line "label" stroke invis right 2\n') == []
    assert overlaps('line "label" above from (0, 0) right 2\nline stroke invis from (1, -0.5) up 1\n') == []
    src = "right\nA: box\nmove\nB: box\nmove\nC: box\n"
    assert overlaps(src + "line stroke invis from A.e to C.w\n") == []
    assert overlaps(src.replace("B: box", "B: box stroke invis") + "arrow from A.e to C.w\n") == []
    assert overlaps("A: box\nbox stroke invis at A + (0.3, 0.2)\n") == []
    assert overlaps("A: box\nbox stroke invis fill red at A + (0.3, 0.2)\n") == [("A", "box 2")]
    assert overlaps('A: box\nbox "a long string" stroke invis at A + (0.6, 0)\n') == [("A", "box 2")]


@pytest.mark.parametrize("path", COOKBOOK, ids=lambda p: p.name)
def test_cookbook_recipes_dont_overlap(path: pathlib.Path):
    # A recipe is drawn as the diagram should be. Not overflow: with a
    # wider font standing in for the theme's, its text may overflow.
    result = resolve_for_pptx(parse(path.read_text(encoding="utf-8"), base_dir=str(path.parent)),
                              base_dir=str(path.parent))
    assert [w.message for w in result.warnings if "overflows" not in w.message] == []

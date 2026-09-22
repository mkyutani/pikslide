"""Tests for pikslide.pik.layout: resolving a parsed AST into concrete geometry.

This engine is a deliberately pragmatic subset of pikchr's own layout
engine -- see the module docstring in layout.py for what is and isn't
faithfully reproduced. These tests check the mechanics that *are* ported
(default sizes, sequential chaining, at/with/from/to/same/chop, direction
changes, nested blocks, nth/last including the by-text-content fallback)
rather than pixel-perfect agreement with upstream pikchr's own renderer.
"""

from __future__ import annotations

import math
import pathlib

import pytest

from pikslide.pik import parse
from pikslide.pik.layout import Colour, LayoutError, resolve_layout

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "examples"
EXAMPLE_FILES = sorted(FIXTURES_DIR.glob("*.pik"))


def layout(text: str):
    return resolve_layout(parse(text))


# ---------------------------------------------------------------------------
# Official examples: layout must not raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_official_example_lays_out_without_error(path: pathlib.Path):
    result = layout(path.read_text(encoding="utf-8"))
    assert len(result.shapes) > 0
    x0, y0, x1, y1 = result.bbox
    assert x1 >= x0 and y1 >= y0


# ---------------------------------------------------------------------------
# Default sizes and sequential chaining
# ---------------------------------------------------------------------------


def test_default_box_size_and_first_object_at_origin():
    result = layout("box\n")
    box = result.shapes[0]
    assert box.kind == "box"
    assert (box.w, box.h) == (0.75, 0.5)
    assert (box.cx, box.cy) == (0.0, 0.0)


def test_boxes_chain_edge_to_edge_when_flowing_right():
    result = layout("box; box\n")
    b1, b2 = result.shapes
    # b2's west edge should land exactly on b1's east edge (touching, no gap/overlap)
    assert b2.cx - b2.w / 2 == pytest.approx(b1.cx + b1.w / 2)
    assert b2.cy == pytest.approx(b1.cy)


def test_direction_statement_changes_chaining_axis():
    result = layout("box; down; box\n")
    b1, b2 = result.shapes
    assert b2.cy + b2.h / 2 == pytest.approx(b1.cy - b1.h / 2)
    assert b2.cx == pytest.approx(b1.cx)


def test_circle_and_ellipse_defaults():
    result = layout("circle; ellipse; oval\n")
    circle, ellipse, oval = result.shapes
    assert (circle.w, circle.h) == (0.5, 0.5)
    assert (ellipse.w, ellipse.h) == (0.75, 0.5)
    assert (oval.w, oval.h) == (1.0, 0.5)


# ---------------------------------------------------------------------------
# at / with / from / to / same / chop
# ---------------------------------------------------------------------------


def test_at_pins_absolute_center():
    result = layout("box at (2,3)\n")
    box = result.shapes[0]
    assert (box.cx, box.cy) == (2.0, 3.0)


def test_named_object_edge_reference():
    result = layout("A: box at (0,0)\nB: box at (5,0)\narrow from A.e to B.w\n")
    arrow = result.shapes[2]
    assert arrow.path[0] == pytest.approx((0.375, 0.0))
    assert arrow.path[-1] == pytest.approx((4.625, 0.0))


def test_same_copies_dimensions():
    result = layout("A: box width 2 height 1\nB: box same\n")
    a, b = result.shapes
    assert (b.w, b.h) == (a.w, a.h) == (2.0, 1.0)


def test_chop_trims_line_to_box_boundary():
    result = layout("A: box at (0,0) width 2 height 2\nB: box at (5,0) width 2 height 2\narrow from A to B chop\n")
    arrow = result.shapes[2]
    # A chopped endpoint must land exactly on A's east edge (x=1), not at its center.
    assert arrow.path[0] == pytest.approx((1.0, 0.0))
    assert arrow.path[-1] == pytest.approx((4.0, 0.0))


def test_name_resolves_by_text_content_when_unlabeled():
    # Ported straight from pikchr's own pik_find_byname() fallback: an
    # object with no explicit "NAME: " label can still be referenced by
    # the exact text it contains (two of pikchr's own official examples
    # rely on exactly this).
    result = layout('box "Foo"\narrow from Foo.e to Foo.e+(1,0)\n')
    box, arrow = result.shapes
    assert arrow.path[0] == pytest.approx(box.edge_point("e"))


# ---------------------------------------------------------------------------
# Line paths: then / go / heading / even-with
# ---------------------------------------------------------------------------


def test_then_forces_separate_path_points():
    result = layout("line right 1 then up 1\n")
    line = result.shapes[0]
    assert line.path == [pytest.approx((0, 0)), pytest.approx((1, 0)), pytest.approx((1, 1))]


def test_consecutive_perpendicular_moves_merge_into_one_diagonal_point():
    # No "then" between them: matches pik_add_direction()'s point-merging.
    result = layout("line right 1 up 1\n")
    line = result.shapes[0]
    assert line.path == [pytest.approx((0, 0)), pytest.approx((1, 1))]


def test_heading_move_uses_compass_angle():
    result = layout("line go 1 heading 90\n")
    line = result.shapes[0]
    # heading 90 == due east
    assert line.path[-1] == pytest.approx((1.0, 0.0), abs=1e-9)


def test_go_until_even_with():
    result = layout("A: box at (5,3)\nline right until even with A\n")
    line = result.shapes[1]
    assert line.path[-1][0] == pytest.approx(5.0)


def test_from_after_movement_rebases_the_whole_path():
    # Matches pik_set_from(): a "from" appearing *after* a movement
    # attribute shifts every already-recorded point, it doesn't discard them.
    result = layout("line right 1 from (10,10)\n")
    line = result.shapes[0]
    assert line.path == [pytest.approx((10, 10)), pytest.approx((11, 10))]


# ---------------------------------------------------------------------------
# Nested [...] blocks
# ---------------------------------------------------------------------------


def test_nested_block_children_are_translated_to_global_coordinates():
    result = layout("Outer: [ A: box; B: box ] at (10, 10)\n")
    a = next(s for s in result.shapes if s.name == "A")
    b = next(s for s in result.shapes if s.name == "B")
    # children keep their relative layout (edge-to-edge, flowing right)...
    assert b.cx - b.w / 2 == pytest.approx(a.cx + a.w / 2)
    # ...translated so the block's own bbox center sits at (10, 10).
    assert (a.cx + b.cx) / 2 == pytest.approx(10.0)


def test_nth_and_last_within_current_scope():
    # "LABEL: last box" names a *point* at the last box's center (per the
    # PLACENAME COLON position grammar rule) rather than aliasing the box
    # itself, so it isn't drawn -- check it indirectly via a position use.
    result = layout("box; box; box\nP: last box\narrow from P to P+(1,0)\n")
    boxes = [s for s in result.shapes if s.kind == "box"]
    arrow = next(s for s in result.shapes if s.kind == "arrow")
    assert arrow.path[0] == pytest.approx((boxes[-1].cx, boxes[-1].cy))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_undefined_name_raises_layout_error():
    with pytest.raises(LayoutError):
        layout("arrow from Nope.e to Nope.w\n")


def test_expr_evaluates_functions_and_variables():
    result = layout("scale = 2\nbox width sqrt(4)*scale\n")
    box = result.shapes[0]
    assert box.w == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Colours (docs/spec.md SS2, SS3.3, SS3.7): a type of their own, not a
# number, defined by the prelude rather than a lexer table.
# ---------------------------------------------------------------------------


def test_prelude_defines_css_colour_names_as_variables():
    result = layout('box fill red\n')
    assert result.shapes[0].fill == Colour(rgb=0xFF0000)


def test_colour_name_is_overridable_like_any_variable():
    # Unlike pikchr's own colour-name table, a prelude colour is an
    # ordinary variable: a later assignment wins.
    result = layout('red = 0x00FF00\nbox fill red\n')
    assert result.shapes[0].fill == Colour(rgb=0x00FF00)


def test_hex_literal_and_none_are_colours():
    result = layout('box fill 0x123456\nbox fill none\n')
    assert result.shapes[0].fill == Colour(rgb=0x123456)
    assert result.shapes[1].fill is None


def test_theme_colour_stays_symbolic_with_lighter_darker():
    result = layout('box fill accent1 lighter 40%\nbox color accent2 darker 25%\n')
    assert result.shapes[0].fill == Colour(theme_slot="accent1", lum_mod=0.6, lum_off=0.4)
    assert result.shapes[1].color == Colour(theme_slot="accent2", lum_mod=0.75, lum_off=0.0)


def test_unknown_theme_slot_is_an_error():
    with pytest.raises(LayoutError):
        layout('box fill theme "notaslot"\n')


def test_arithmetic_on_a_colour_is_an_error():
    # "x"/"y" are reserved (pikchr's own .x/.y coordinate access), so this
    # uses an ordinary name instead.
    with pytest.raises(LayoutError):
        layout('myvar = red + 1\nbox\n')


def test_default_text_sizes_come_from_the_prelude():
    result = layout('box "hi"\n')
    assert result.text_sizes["small"] == pytest.approx(9 / 72)
    assert result.text_sizes["medium"] == pytest.approx(10.5 / 72)
    assert result.text_sizes["large"] == pytest.approx(12 / 72)


def test_text_size_is_overridable_like_fill_and_color():
    result = layout('medium = 11pt\nbox "hi"\n')
    assert result.text_sizes["medium"] == pytest.approx(11 / 72)


def test_default_typeface_is_empty_meaning_the_theme_font():
    result = layout('box "hi"\n')
    assert result.typeface == ""


def test_typeface_is_overridable_like_fill_and_color():
    result = layout('typeface = "BIZ UDPGothic"\nbox "hi"\n')
    assert result.typeface == "BIZ UDPGothic"


def test_typeface_must_be_a_string_not_a_number():
    with pytest.raises(LayoutError):
        layout("typeface = 5\nbox\n")


# ---------------------------------------------------------------------------
# Preset shapes: `shape` (docs/spec.md SS3.4)
# ---------------------------------------------------------------------------


def test_shape_default_size_matches_box():
    result = layout('shape chevron "x"\n')
    box_result = layout('box "x"\n')
    shape_obj, box_obj = result.shapes[0], box_result.shapes[0]
    assert shape_obj.w == pytest.approx(box_obj.w)
    assert shape_obj.h == pytest.approx(box_obj.h)
    assert shape_obj.kind == "shape"
    assert shape_obj.preset == "chevron"


def test_shape_preset_name_is_canonicalised():
    result = layout('shape ROUNDRECT "x"\n')
    assert result.shapes[0].preset == "roundRect"


def test_unknown_preset_name_is_an_error_with_a_suggestion():
    with pytest.raises(LayoutError, match="roundRect"):
        layout('shape roundRact "x"\n')


def test_shape_supports_edges_and_same_like_box():
    result = layout('A: shape hexagon "A" width 2 height 1\n'
                     'B: shape hexagon "B" same at 4 right of A.e\n')
    a, b = result.shapes
    assert b.w == pytest.approx(a.w)
    assert b.h == pytest.approx(a.h)
    assert b.cx == pytest.approx(a.edge_point("e")[0] + 4)


# ---------------------------------------------------------------------------
# Images: `image` (docs/spec.md SS3.5)
# ---------------------------------------------------------------------------


def _make_image(dir_path: pathlib.Path, name: str = "logo.png", size: tuple[int, int] = (400, 200)) -> None:
    from PIL import Image

    Image.new("RGB", size, "white").save(dir_path / name)


def test_image_with_both_dimensions_is_stretched(tmp_path: pathlib.Path):
    _make_image(tmp_path)  # 400x200, a 2:1 aspect ratio
    result = resolve_layout(parse('image "logo.png" width 2 height 2\n'), base_dir=str(tmp_path))
    img = result.shapes[0]
    assert img.kind == "image"
    assert (img.w, img.h) == pytest.approx((2.0, 2.0))


def test_image_with_only_width_follows_aspect_ratio(tmp_path: pathlib.Path):
    _make_image(tmp_path)  # 2:1
    result = resolve_layout(parse('image "logo.png" width 2\n'), base_dir=str(tmp_path))
    img = result.shapes[0]
    assert (img.w, img.h) == pytest.approx((2.0, 1.0))


def test_image_with_only_height_follows_aspect_ratio(tmp_path: pathlib.Path):
    _make_image(tmp_path)  # 2:1
    result = resolve_layout(parse('image "logo.png" height 1\n'), base_dir=str(tmp_path))
    img = result.shapes[0]
    assert (img.w, img.h) == pytest.approx((2.0, 1.0))


def test_image_with_neither_dimension_fits_inside_the_default_box(tmp_path: pathlib.Path):
    _make_image(tmp_path)  # 2:1, wider than boxwid/boxht's 1.5:1
    result = resolve_layout(parse('image "logo.png"\n'), base_dir=str(tmp_path))
    img = result.shapes[0]
    # width-constrained: boxwid=0.75, height = 0.75 / 2.0
    assert (img.w, img.h) == pytest.approx((0.75, 0.375))


def test_image_path_resolves_relative_to_base_dir(tmp_path: pathlib.Path):
    (tmp_path / "icons").mkdir()
    _make_image(tmp_path / "icons", "db.png")
    result = resolve_layout(parse('image "icons/db.png"\n'), base_dir=str(tmp_path))
    assert result.shapes[0].image_path == str((tmp_path / "icons" / "db.png").resolve())


def test_absolute_image_path_is_an_error(tmp_path: pathlib.Path):
    with pytest.raises(LayoutError):
        resolve_layout(parse('image "/etc/hostname"\n'), base_dir=str(tmp_path))


def test_image_path_escaping_base_dir_is_an_error(tmp_path: pathlib.Path):
    with pytest.raises(LayoutError):
        resolve_layout(parse('image "../../../etc/hostname"\n'), base_dir=str(tmp_path))


def test_missing_image_file_is_an_error(tmp_path: pathlib.Path):
    with pytest.raises(LayoutError):
        resolve_layout(parse('image "nope.png"\n'), base_dir=str(tmp_path))


def test_svg_image_is_a_clear_error_not_yet_supported(tmp_path: pathlib.Path):
    # Not implemented yet (docs/implementation-plan.md); this must fail
    # cleanly, not with a raw PIL.UnidentifiedImageError (checked).
    (tmp_path / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(LayoutError, match="SVG"):
        resolve_layout(parse('image "icon.svg"\n'), base_dir=str(tmp_path))
    with pytest.raises(LayoutError, match="SVG"):
        resolve_layout(parse('image "icon.svg" width 1 height 1\n'), base_dir=str(tmp_path))


def test_alt_on_a_non_image_is_an_error(tmp_path: pathlib.Path):
    with pytest.raises(LayoutError):
        resolve_layout(parse('box "x" alt "nope"\n'), base_dir=str(tmp_path))


def test_alt_text_is_captured(tmp_path: pathlib.Path):
    _make_image(tmp_path)
    result = resolve_layout(parse('image "logo.png" alt "A logo"\n'), base_dir=str(tmp_path))
    assert result.shapes[0].alt_text == "A logo"


def test_image_participates_in_positioning_like_any_object(tmp_path: pathlib.Path):
    _make_image(tmp_path)
    result = resolve_layout(
        parse('Logo: image "logo.png" width 1\nbox "Caption" at 0.2 below Logo.s\n'),
        base_dir=str(tmp_path),
    )
    logo, caption = result.shapes
    assert caption.cy == pytest.approx(logo.edge_point("s")[1] - 0.2)

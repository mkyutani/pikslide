"""Tests for pikslide.pptx_writer: rendering a resolved layout to PowerPoint."""

from __future__ import annotations

import pathlib

import pytest
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_FILL_TYPE, MSO_THEME_COLOR
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE

from pikslide.pik import parse
from pikslide.pptx_writer import resolve_for_pptx, write_pptx

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "examples"
EXAMPLE_FILES = sorted(FIXTURES_DIR.glob("*.pik"))


def render(text: str, tmp_path: pathlib.Path, name: str = "out.pptx") -> Presentation:
    # Uses resolve_for_pptx() (real font-metrics-based "fit" sizing), the
    # same path the CLI takes, so these tests exercise it too.
    result = resolve_for_pptx(parse(text))
    out = tmp_path / name
    write_pptx(result, str(out))
    return Presentation(str(out))


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_official_example_renders_without_error(path: pathlib.Path, tmp_path: pathlib.Path):
    prs = render(path.read_text(encoding="utf-8"), tmp_path, path.stem + ".pptx")
    assert len(prs.slides) == 1


def test_box_becomes_a_shape_with_text(tmp_path: pathlib.Path):
    prs = render('box "Hello"\n', tmp_path)
    slide = prs.slides[0]
    assert len(slide.shapes) == 1
    shape = slide.shapes[0]
    assert shape.text_frame.text == "Hello"


def test_two_point_arrow_becomes_a_connector(tmp_path: pathlib.Path):
    prs = render("arrow right\n", tmp_path)
    slide = prs.slides[0]
    assert len(slide.shapes) == 1
    assert slide.shapes[0].shape_type == MSO_SHAPE_TYPE.LINE


def test_arrow_labels_render_as_textboxes_above_and_below(tmp_path: pathlib.Path):
    # A connector shape has no text_frame of its own in python-pptx, so an
    # arrow's text must show up as separate floating textboxes -- and two
    # un-flagged texts split above/below the line (pik_txt_vertical_layout()).
    prs = render('arrow right "Top" "Bottom"\n', tmp_path)
    slide = prs.slides[0]
    textboxes = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]
    assert {tb.text_frame.text for tb in textboxes} == {"Top", "Bottom"}
    top_box = next(tb for tb in textboxes if tb.text_frame.text == "Top")
    bottom_box = next(tb for tb in textboxes if tb.text_frame.text == "Bottom")
    # slide y grows downward, so the "above the line" label has the smaller top.
    assert top_box.top < bottom_box.top


def test_rounded_box_gets_rounded_rectangle_with_scaled_corner(tmp_path: pathlib.Path):
    prs = render("box rad 0.1 width 1 height 1\n", tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.adjustments[0] == pytest.approx(0.1, abs=0.01)


def test_multipoint_line_becomes_a_freeform(tmp_path: pathlib.Path):
    prs = render("line right 1 then up 1\n", tmp_path)
    slide = prs.slides[0]
    assert len(slide.shapes) == 1
    assert slide.shapes[0].shape_type == MSO_SHAPE_TYPE.FREEFORM


def test_slide_size_matches_diagram_bbox_plus_margin(tmp_path: pathlib.Path):
    result = resolve_for_pptx(parse("box\n"))
    out = tmp_path / "sized.pptx"
    write_pptx(result, str(out), margin=0.5)
    prs = Presentation(str(out))
    x0, y0, x1, y1 = result.bbox
    assert prs.slide_width.inches == pytest.approx((x1 - x0) + 1.0, abs=0.01)
    assert prs.slide_height.inches == pytest.approx((y1 - y0) + 1.0, abs=0.01)


def test_fill_color_is_applied(tmp_path: pathlib.Path):
    # Unlike pikchr, a colour name is an ordinary lowercase variable,
    # defined by the prelude (docs/spec.md SS2, SS3.7) -- not a capitalized
    # PLACENAME the way pikchr's own colour-name shorthand works.
    prs = render("box fill red\n", tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.fill.fore_color.rgb == RGBColor(0xFF, 0x00, 0x00)


def test_invis_object_has_no_outline(tmp_path: pathlib.Path):
    prs = render("box invis\n", tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.line.fill.type == MSO_FILL_TYPE.BACKGROUND


def test_theme_colour_is_emitted_as_schemeclr_not_resolved_rgb(tmp_path: pathlib.Path):
    # docs/spec.md SS3.3: emitted as schemeClr, never as resolved RGB, so
    # swapping the theme restyles the diagram.
    prs = render('box fill accent1 lighter 40%\n', tmp_path)
    shape = prs.slides[0].shapes[0]
    fore = shape.fill.fore_color
    assert fore.theme_color == MSO_THEME_COLOR.ACCENT_1
    assert fore.brightness == pytest.approx(0.4)


def test_no_fill_leaves_the_shape_transparent(tmp_path: pathlib.Path):
    # The prelude's own default (`fill = none`, docs/spec.md SS3.7).
    prs = render('box "hi"\n', tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.fill.type == MSO_FILL_TYPE.BACKGROUND


def test_text_size_flag_selects_the_large_point_size(tmp_path: pathlib.Path):
    prs = render('box "small" small\nbox "large" large\n', tmp_path)
    small_run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    large_run = prs.slides[0].shapes[1].text_frame.paragraphs[0].runs[0]
    assert small_run.font.size.pt == pytest.approx(9.0)
    assert large_run.font.size.pt == pytest.approx(12.0)


def test_overriding_medium_changes_the_default_text_size(tmp_path: pathlib.Path):
    prs = render('medium = 14pt\nbox "hi"\n', tmp_path)
    run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.size.pt == pytest.approx(14.0)


def test_preset_shape_renders_as_the_named_autoshape(tmp_path: pathlib.Path):
    prs = render('shape chevron "Step 1"\n', tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.auto_shape_type == MSO_SHAPE.CHEVRON
    assert shape.text_frame.text == "Step 1"


def test_bare_round_rect_preset_keeps_pptx_own_default_corner(tmp_path: pathlib.Path):
    # Checked: python-pptx's own fresh-shape default is ~1/6, not 0 -- a
    # bare `shape roundRect` (no explicit `rad`) must not flatten that.
    prs = render('shape roundRect "x"\n', tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE
    assert shape.adjustments[0] == pytest.approx(0.16667, abs=0.001)


def test_explicit_rad_on_a_round_rect_preset_overrides_the_corner(tmp_path: pathlib.Path):
    prs = render('shape roundRect "x" rad 0.1 width 1 height 1\n', tmp_path)
    shape = prs.slides[0].shapes[0]
    assert shape.adjustments[0] == pytest.approx(0.1, abs=0.01)

"""Tests for pikslide.pptx_writer: rendering a resolved layout to PowerPoint."""

from __future__ import annotations

import pathlib

import pytest
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_FILL_TYPE, MSO_THEME_COLOR
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches

from pikslide.pik import parse
from pikslide.pik.layout import LayoutError
from pikslide.pptx_writer import resolve_for_pptx, write_pptx

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "examples"
EXAMPLE_FILES = sorted(FIXTURES_DIR.glob("*.pik"))


def render(text: str, tmp_path: pathlib.Path, name: str = "out.pptx") -> Presentation:
    # Uses resolve_for_pptx() (real font-metrics-based "fit" sizing), the
    # same path the CLI takes, so these tests exercise it too. base_dir
    # defaults to tmp_path itself, so an `image "x.png"` resolves against
    # whatever the test already wrote there.
    result = resolve_for_pptx(parse(text), base_dir=str(tmp_path))
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


# ---------------------------------------------------------------------------
# Fonts (docs/spec.md SS3.3): symbolic theme references by default, `major`,
# `typeface` -- checked, as elsewhere, against what's actually saved to disk
# (not just what's readable back in memory before saving).
# ---------------------------------------------------------------------------


def _ea_typeface(run) -> str | None:
    ea = run.font._rPr.find(qn("a:ea"))
    return ea.get("typeface") if ea is not None else None


def test_default_font_is_the_symbolic_minor_theme_reference(tmp_path: pathlib.Path):
    prs = render('box "hi"\n', tmp_path)
    run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "+mn-lt"
    assert _ea_typeface(run) == "+mn-ea"


def test_major_flag_selects_the_major_theme_reference(tmp_path: pathlib.Path):
    prs = render('box "Heading" major\n', tmp_path)
    run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "+mj-lt"
    assert _ea_typeface(run) == "+mj-ea"


def test_typeface_variable_overrides_with_a_literal_family(tmp_path: pathlib.Path):
    prs = render('typeface = "Comic Sans MS"\nbox "hi" major\n', tmp_path)
    run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    # Overrides both slots, and applies regardless of `major` (docs/spec.md
    # SS3.3: "a specific family" -- one value for everything, not a
    # major/minor pair of its own).
    assert run.font.name == "Comic Sans MS"
    assert _ea_typeface(run) == "Comic Sans MS"


def test_typeface_must_be_a_string(tmp_path: pathlib.Path):
    with pytest.raises(LayoutError):
        resolve_for_pptx(parse("typeface = 5\nbox\n"))


def test_line_label_and_image_caption_also_get_the_theme_font(tmp_path: pathlib.Path):
    # _add_line_text() and _add_image_shape() build runs independently of
    # _apply_text() -- checked separately, since nothing shares that code path.
    _make_image(tmp_path)
    prs = render('arrow right "Label"\nimage "logo.png" width 50% "Caption"\n', tmp_path, name="fonts.pptx")
    slide = prs.slides[0]
    label = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX and s.text_frame.text == "Label")
    caption = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX and s.text_frame.text == "Caption")
    for box in (label, caption):
        run = box.text_frame.paragraphs[0].runs[0]
        assert run.font.name == "+mn-lt"
        assert _ea_typeface(run) == "+mn-ea"


# ---------------------------------------------------------------------------
# Object identity: names, groups, z-order (docs/spec.md SS3.1, ext)
# ---------------------------------------------------------------------------


def test_shape_names_are_set_on_the_saved_pptx_shapes(tmp_path: pathlib.Path):
    prs = render('box "a"\nWeb: box "b"\n', tmp_path)
    names = [s.name for s in prs.slides[0].shapes]
    assert names == ["box 1", "Web"]


def test_line_and_image_shapes_are_named_too(tmp_path: pathlib.Path):
    _make_image(tmp_path)
    prs = render('arrow right\nimage "logo.png" width 1\n', tmp_path, name="named.pptx")
    names = [s.name for s in prs.slides[0].shapes]
    assert names == ["arrow 1", "image 1"]


def test_line_label_textbox_naming(tmp_path: pathlib.Path):
    prs = render('Conn: arrow right "Top" "Bottom"\n', tmp_path)
    boxes = {s.text_frame.text: s.name for s in prs.slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX}
    assert boxes["Top"] in ("Conn text 1", "Conn text 2")
    assert boxes["Bottom"] in ("Conn text 1", "Conn text 2")
    assert boxes["Top"] != boxes["Bottom"]


def test_block_becomes_a_named_powerpoint_group(tmp_path: pathlib.Path):
    prs = render('Outer: [ A: box "x"; B: box "y" ]\n', tmp_path)
    top = prs.slides[0].shapes
    assert len(top) == 1
    group = top[0]
    assert group.shape_type == MSO_SHAPE_TYPE.GROUP
    assert group.name == "Outer"
    assert [s.name for s in group.shapes] == ["A", "B"]


def test_nested_blocks_become_nested_groups_positioned_correctly(tmp_path: pathlib.Path):
    prs = render(
        'box "before"\n'
        'Outer: [\n'
        '  A: box "a"\n'
        '  Inner: [ D: box "d" ]\n'
        ']\n',
        tmp_path,
    )
    before, outer = prs.slides[0].shapes
    assert outer.name == "Outer"
    a, inner = outer.shapes
    assert inner.shape_type == MSO_SHAPE_TYPE.GROUP
    assert inner.name == "Inner"
    # Outer starts exactly where "before" ends -- proves the block's
    # position was translated into the *parent* frame, not left at its
    # post-recalculate_extents() local-frame position (checked: this was
    # wrong -- (0, 0) -- before repositioning by delta, not replacement).
    assert outer.left.inches == pytest.approx(before.left.inches + before.width.inches, abs=0.01)


def test_behind_places_the_shape_earlier_in_z_order(tmp_path: pathlib.Path):
    # Z-order is draw order (docs/spec.md SS3.1): the shape added *first*
    # ends up visually behind one added later, so "C behind A" must put C
    # before A in the saved shape list.
    prs = render('A: box "a"\nB: box "b"\nC: box "c" behind A\n', tmp_path)
    assert [s.name for s in prs.slides[0].shapes] == ["C", "A", "B"]


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


def _make_image(tmp_path: pathlib.Path, name: str = "logo.png") -> None:
    from PIL import Image

    Image.new("RGB", (400, 200), "white").save(tmp_path / name)


def test_image_renders_as_a_picture(tmp_path: pathlib.Path):
    _make_image(tmp_path)
    prs = render('image "logo.png" width 2\n', tmp_path)
    picture = prs.slides[0].shapes[0]
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    assert picture.width.inches == pytest.approx(2.0)
    assert picture.height.inches == pytest.approx(1.0)  # 400x200 source, aspect preserved


def test_image_alt_text_is_the_actual_saved_description(tmp_path: pathlib.Path):
    # python-pptx 1.0.2 has no real alt_text property (checked: a plain
    # instance attribute, never serialized) -- this must be the real
    # p:cNvPr/@descr the saved file actually carries.
    _make_image(tmp_path)
    prs = render('image "logo.png" alt "A logo"\n', tmp_path)
    picture = prs.slides[0].shapes[0]
    descr = picture._element.nvPicPr.cNvPr.get("descr")
    assert descr == "A logo"


def test_image_text_becomes_a_centred_caption_textbox(tmp_path: pathlib.Path):
    _make_image(tmp_path)
    prs = render('image "logo.png" width 2 "Caption"\n', tmp_path)
    picture, caption = prs.slides[0].shapes
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    assert caption.shape_type == MSO_SHAPE_TYPE.TEXT_BOX
    assert caption.text_frame.text == "Caption"
    # centred over the picture, not offset above/below like a line's label.
    assert caption.left == picture.left
    assert caption.top == picture.top


# ---------------------------------------------------------------------------
# Inserting into an existing deck (docs/spec.md SS4.2)
# ---------------------------------------------------------------------------


def _existing_deck(tmp_path: pathlib.Path, name: str = "deck.pptx") -> pathlib.Path:
    """A deck with a title-and-content slide: an empty "Content
    Placeholder 2" (python-pptx's own default name for it) as a stand-in
    for a real region, plus an ordinary named shape "Figure"."""
    from pptx import Presentation as _P
    from pptx.util import Inches as _In

    prs = _P()
    prs.slide_width, prs.slide_height = _In(10), _In(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Deck"
    fig = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _In(6), _In(5), _In(2), _In(1))
    fig.name = "Figure"
    fig.text_frame.text = "not empty"
    path = tmp_path / name
    prs.save(str(path))
    return path


def _insert(text: str, deck: pathlib.Path, **kwargs):
    from pikslide.pptx_writer import insert_into_pptx

    result = resolve_for_pptx(parse(text))
    return insert_into_pptx(result, str(deck), **kwargs)


def test_insert_into_an_empty_placeholder_region(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    prs = _insert('box "Web"\n', deck, slide_no=1, region="Content Placeholder 2", group_id="arch")
    names = [s.name for s in prs.slides[0].shapes]
    assert names == ["Title 1", "Figure", "pikslide:arch"]  # placeholder gone, title/other shapes untouched


def test_insert_into_an_ordinary_named_shape_is_not_deleted(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    prs = _insert('box "Web"\n', deck, slide_no=1, region="Figure", group_id="arch")
    names = [s.name for s in prs.slides[0].shapes]
    assert names == ["Title 1", "Content Placeholder 2", "Figure", "pikslide:arch"]


def test_insert_with_explicit_rect(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    prs = _insert('box "Web"\n', deck, slide_no=1, rect=(0.5, 0.5, 3, 3), group_id="arch")
    group = prs.slides[0].shapes[-1]
    assert (group.left.inches, group.top.inches) == pytest.approx((0.5, 0.5))


def test_insert_is_idempotent(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    out1 = tmp_path / "out1.pptx"
    _insert('box "Web"\n', deck, slide_no=1, region="Content Placeholder 2", group_id="arch").save(str(out1))
    prs = _insert('box "Web2"\n', out1, slide_no=1, region="Content Placeholder 2", group_id="arch")
    # No duplicate group; the same one was found (by falling back to the
    # existing pikslide group once the placeholder it replaced is gone)
    # and replaced with the new content, at the same z-order position.
    names = [s.name for s in prs.slides[0].shapes]
    assert names == ["Title 1", "Figure", "pikslide:arch"]
    inner = prs.slides[0].shapes[-1].shapes[0]
    assert inner.text_frame.text == "Web2"


def test_insert_preserves_z_order_position_on_replace(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    out1 = tmp_path / "out1.pptx"
    _insert('box "Web"\n', deck, slide_no=1, rect=(0.5, 0.5, 3, 3), group_id="arch").save(str(out1))
    # Add a shape *after* the diagram group, so the group is no longer last.
    prs1 = Presentation(str(out1))
    marker = prs1.slides[0].shapes.add_textbox(Inches(0), Inches(0), Inches(1), Inches(1))
    marker.name = "AfterMarker"
    prs1.save(str(out1))
    prs2 = _insert('box "Web2"\n', out1, slide_no=1, rect=(0.5, 0.5, 3, 3), group_id="arch")
    names = [s.name for s in prs2.slides[0].shapes]
    # the replaced group stays *before* AfterMarker, matching where it was.
    assert names.index("pikslide:arch") < names.index("AfterMarker")


def test_diagram_larger_than_region_is_an_error(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    with pytest.raises(LayoutError, match="larger than its region"):
        _insert('box wid 20 ht 10 "huge"\n', deck, slide_no=1, region="Content Placeholder 2")


def test_out_of_range_slide_is_an_error(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    with pytest.raises(LayoutError, match="out of range"):
        _insert('box\n', deck, slide_no=5, rect=(0, 0, 1, 1))


def test_no_region_or_rect_is_an_error(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    with pytest.raises(LayoutError, match="no target region"):
        _insert('box\n', deck, slide_no=1)


def test_region_and_rect_together_is_an_error(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    with pytest.raises(LayoutError, match="mutually exclusive"):
        _insert('box\n', deck, slide_no=1, region="Figure", rect=(0, 0, 1, 1))


def test_unknown_region_name_is_an_error(tmp_path: pathlib.Path):
    deck = _existing_deck(tmp_path)
    with pytest.raises(LayoutError, match="no shape named"):
        _insert('box\n', deck, slide_no=1, region="Nope")

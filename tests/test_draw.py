"""`pikslide.draw` -- --renderer direct (issue #34): the picture drawn by
pikslide itself. The colors, sizes and shapes checked here are
PowerPoint's own, measured from its pictures; the last test compares
every picture in docs/, which PowerPoint drew, with pikslide's."""

from __future__ import annotations

import pathlib
import re

import pytest
from PIL import Image, ImageChops, ImageFilter, ImageStat
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from pikslide.draw import _dashes, _pixels, _wrap, draw
from pikslide.fonts import installed_fonts
from pikslide.pik import parse
from pikslide.pptx_writer import resolve_for_pptx

DOCS = pathlib.Path(__file__).parent.parent / "docs"


def _draw(src: str, template: str | None = None, base_dir: str = ".") -> Image.Image:
    result = resolve_for_pptx(parse(src, base_dir=base_dir), base_dir=base_dir, template_path=template)
    return draw(result, template, result.layout_name if template else "")


def _at(image: Image.Image, slide_left: float, slide_top: float, x: float, y: float) -> tuple[int, int, int]:
    """The color at diagram point (x, y), on a slide whose top left is at
    (slide_left, slide_top) (--check's `slide`), 200 to the inch."""
    return image.getpixel((int((x - slide_left) * 200), int((slide_top - y) * 200)))


def test_the_picture_is_as_big_as_powerpoints():
    # PowerPoint rounds a slide to 576ths of an inch, then to the pixel.
    assert _pixels(2091689 / 914400, 200) == 458
    assert _pixels(10490968 / 914400, 200) == 2294
    assert _pixels(1.0, 200) == 200


def test_shaded_faces_are_powerpoints():
    # A 0x808080 fill: a lighter face blends white in, a darker one black.
    image = _draw("C: shape can fill 0x808080 stroke invis wid 1 ht 1.5\n"
                  "K: shape cube fill 0x808080 stroke invis wid 1.5 ht 1.2 at (2, 0)\n")
    left, top = -0.65, 0.9  # the slide's top left, in the diagram's own coordinates
    assert _at(image, left, top, 0, 0) == (128, 128, 128)
    assert _at(image, left, top, 0, 0.68) == (179, 179, 179)  # lighten
    assert _at(image, left, top, 2, 0.55) == (153, 153, 153)  # lightenLess
    assert _at(image, left, top, 2.68, 0) == (103, 103, 103)  # darkenLess


@pytest.fixture
def green_template(tmp_path: pathlib.Path) -> str:
    """The built-in theme, with accent1 green."""
    prs = Presentation()
    theme = prs.slide_masters[0].part.part_related_by(RT.THEME)
    theme._blob = re.sub(rb'(<a:accent1>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}', rb"\g<1>00A050", theme.blob)
    path = tmp_path / "green.pptx"
    prs.save(str(path))
    return str(path)


def test_theme_colors_are_the_templates_lighter_and_darker_as_powerpoint_has_them(green_template: str):
    image = _draw('A: box fill accent1 lighter 60% wid 1 ht 0.5\nB: box fill accent1 darker 25% wid 1 ht 0.5 at (0, -1)\n',
                  template=green_template)
    assert image.size == (2000, 1500)  # the template's slide, 10 x 7.5in
    # The diagram's top left at the content area's: (0.5in, 1.75in) on this slide.
    assert image.getpixel((int(1.0 * 200), int(2.0 * 200))) == (115, 255, 185)
    assert image.getpixel((int(1.0 * 200), int(3.0 * 200))) == (0, 120, 60)


def test_an_arrowhead_is_sized_as_powerpoint_sizes_it():
    # A 0.015in line's medium head: three times 0.7mm wide and long.
    image = _draw("line right 1 ->\n").convert("L")
    w, h = image.size
    tip = max(x for x in range(w) for y in range(h) if image.getpixel((x, y)) < 128)
    head = [sum(1 for y in range(h) if image.getpixel((x, y)) < 128) for x in range(tip - 30, tip + 1)]
    size = 3 * 0.7 / 25.4 * 200
    assert max(head) == pytest.approx(size, abs=2)  # its width
    # its length: as wide as it is long, so wider than 4 pixels for all but 4
    assert sum(1 for n in head if n > 4) == pytest.approx(size - 4, abs=2)


def test_a_turned_shape_is_drawn_turned():
    image = _draw("shape rect wid 1 ht 0.2 fill black rotate 90\n").convert("L")
    dark = [(x, y) for x in range(image.width) for y in range(image.height) if image.getpixel((x, y)) < 128]
    xs, ys = [x for x, _ in dark], [y for _, y in dark]
    assert max(ys) - min(ys) > 3 * (max(xs) - min(xs))


def test_text_is_drawn_inside_its_box():
    image = _draw('box "Hello" wid 1 ht 0.5 stroke invis\n').convert("L")
    dark = [(x, y) for x in range(image.width) for y in range(image.height) if image.getpixel((x, y)) < 128]
    # the slide is 1.3 x 0.8in: the box's 1 x 0.5 inside a 0.15in margin
    assert dark and all(30 <= x < 230 and 30 <= y < 130 for x, y in dark)


def test_text_is_drawn_with_no_font_file_at_all(monkeypatch):
    # A bare container: Pillow's own font measures and draws it, and the
    # warning says so, rather than the text going missing.
    import pikslide.pptx_writer
    from pikslide.fonts import FontIndex

    # over conftest's, which finds the Office theme's fonts anyway
    monkeypatch.setattr(pikslide.pptx_writer, "installed_fonts", lambda: FontIndex(dirs=[]))
    monkeypatch.setattr(pikslide.pptx_writer, "_MEASURE_FONT_CANDIDATES", [])
    result = resolve_for_pptx(parse('box "Hello" fit stroke invis\n'))
    assert any("Pillow's own font" in s for s in result.stand_ins)
    image = draw(result).convert("L")
    assert sum(1 for v in image.get_flattened_data() if v < 128) > 100


class _Font:
    """Ten pixels to a character."""

    def getlength(self, text: str) -> float:
        return 10.0 * len(text)


def _lines(text: str, width: float) -> list[str]:
    font = _Font()
    return ["".join(run for run, _font, _face in line) for line in _wrap([(text, font, None)], width)]


def test_text_wraps_after_a_space_between_east_asian_characters_or_in_a_word_too_long():
    assert _lines("one two three", 75) == ["one two", "three"]
    assert _lines("日本語の文", 30) == ["日本語", "の文"]
    assert _lines("abcdefgh", 30) == ["abc", "def", "gh"]


def test_dashes():
    pieces = _dashes([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], 4.0, 3.0)
    assert [p[0] for p in pieces] == [(0, 0), (7, 0), (10, 4.0)]
    assert pieces[1] == [(7, 0), (10, 0), (10, 1.0)]  # round the corner


# ---------------------------------------------------------------------------
# docs/: PowerPoint's pictures
# ---------------------------------------------------------------------------

_DOCS_PICTURES = sorted(p for p in DOCS.rglob("*.pik") if p.with_suffix(".png").exists())


def _docs_fonts_installed() -> bool:
    index = installed_fonts()
    return all(index.find(family) is not None for family in ("Calibri", "ＭＳ Ｐゴシック"))


@pytest.mark.skipif(not _docs_fonts_installed(), reason="docs/ was drawn in Calibri and MS PGothic, not installed here")
@pytest.mark.parametrize("pik", _DOCS_PICTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_docs_pictures_are_drawn_as_powerpoint_drew_them(pik: pathlib.Path):
    # Blurred a little, so that a line a pixel apart or an edge smoothed
    # another way counts for little; then the mean difference, and the
    # worst 40-pixel square's, where something missing or misplaced shows.
    # Each is a fraction of 255; today's are at most 2.5 and 15 (a star's
    # points, which PowerPoint mitres and this rounds, and dashes).
    mine = _draw(pik.read_text(encoding="utf-8"), base_dir=str(pik.parent))
    powerpoint = Image.open(pik.with_suffix(".png")).convert("RGB")
    assert mine.size == powerpoint.size
    a, b = (im.convert("L").filter(ImageFilter.GaussianBlur(2)) for im in (powerpoint, mine))
    diff = ImageChops.difference(a, b)
    assert ImageStat.Stat(diff).mean[0] < 4
    worst = max(ImageStat.Stat(diff.crop((x, y, x + 40, y + 40))).mean[0]
                for x in range(0, diff.width, 40) for y in range(0, diff.height, 40))
    assert worst < 22

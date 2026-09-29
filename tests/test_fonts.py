"""Tests for pikslide.fonts: finding installed fonts by family name, and
reading a theme's fonts."""

from __future__ import annotations

import os
import pathlib
import shutil
import zipfile

import pptx
import pytest

from pikslide.fonts import FontIndex, theme_fonts_from_xml
from pikslide.pptx_writer import _script_runs

DEJAVU = pathlib.Path("/usr/share/fonts/truetype/dejavu")


@pytest.fixture
def dejavu_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    files = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]
    if not all((DEJAVU / f).exists() for f in files):
        pytest.skip("DejaVu Sans not installed")
    for f in files:
        shutil.copy(DEJAVU / f, tmp_path / f)
    return tmp_path


def test_font_index_finds_a_family_and_its_bold_face(dejavu_dir: pathlib.Path):
    index = FontIndex(dirs=[str(dejavu_dir)])
    assert os.path.basename(index.find("DejaVu Sans").path) == "DejaVuSans.ttf"
    assert os.path.basename(index.find("DejaVu Sans", bold=True).path) == "DejaVuSans-Bold.ttf"
    # Matched regardless of case and full-width letters, as theme names may be written.
    assert index.find("ＤｅｊａＶｕ ｓａｎｓ") is not None
    assert index.find("No Such Font") is None


def test_theme_fonts_take_the_japanese_font_when_east_asian_is_empty():
    template = pathlib.Path(pptx.__file__).parent / "templates" / "default.pptx"
    with zipfile.ZipFile(template) as z:
        fonts = theme_fonts_from_xml(z.read("ppt/theme/theme1.xml"))
    assert (fonts.minor_latin, fonts.minor_ea) == ("Calibri", "ＭＳ Ｐゴシック")
    assert (fonts.major_latin, fonts.major_ea) == ("Calibri", "ＭＳ Ｐゴシック")


def test_text_splits_into_east_asian_and_other_runs():
    assert _script_runs("混在 mixed テキスト") == [(True, "混在"), (False, " mixed "), (True, "テキスト")]
    assert _script_runs("ＡＢ12") == [(True, "ＡＢ"), (False, "12")]

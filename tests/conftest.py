"""Make the tests independent of whether this machine has the built-in
Office theme's fonts (Calibri, ＭＳ Ｐゴシック): a Windows install, or WSL,
has them, a Linux CI runner doesn't. A test about the theme or `--strict`
shouldn't hinge on that, so where one of those fonts isn't installed it
is found as the substitute `fit` would measure with anyway. Any other
font is looked up as usual, so a missing one (`typeface "NoSuchFontXyz"`)
is still missing."""

from __future__ import annotations

import dataclasses

import pytest

from pikslide import pptx_writer
from pikslide.fonts import FontFace


class _WithOfficeFonts:
    def __init__(self, index, families: set[str], stand_in: str | None):
        self._index = index
        self._families = families
        self._stand_in = stand_in

    def find(self, family: str, bold: bool = False, italic: bool = False) -> FontFace | None:
        face = self._index.find(family, bold, italic)
        if face is None and family in self._families and self._stand_in:
            return FontFace(self._stand_in, 0, bold, italic)
        return face


@pytest.fixture(autouse=True)
def office_fonts(monkeypatch):
    families = {f for f in dataclasses.astuple(pptx_writer.default_theme_fonts()) if f}
    index = _WithOfficeFonts(pptx_writer.installed_fonts(), families, pptx_writer._find_measure_font())
    monkeypatch.setattr(pptx_writer, "installed_fonts", lambda: index)

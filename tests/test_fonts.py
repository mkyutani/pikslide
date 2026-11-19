"""Tests for pikslide.fonts: finding installed fonts by family name, and
reading a theme's fonts."""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
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


# ---------------------------------------------------------------------------
# --install-font (issue #37)
# ---------------------------------------------------------------------------


@pytest.fixture
def font_home(monkeypatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """A home of its own, on Linux or macOS, so nothing is written to the
    real font directory; returns where --install-font puts fonts."""
    import pikslide.fonts

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(pikslide.fonts, "on_windows", lambda: False)
    monkeypatch.setattr("pikslide.on_windows", lambda: False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return pathlib.Path(pikslide.fonts.user_font_dir())


def test_install_a_font_file_where_fonts_are_found(font_home, dejavu_dir):
    from pikslide.fonts import install_fonts

    [(path, families, already)] = install_fonts(str(dejavu_dir / "DejaVuSans.ttf"))
    assert pathlib.Path(path) == font_home / "DejaVuSans.ttf" and not already
    assert "DejaVu Sans" in families  # as written, for `typeface`
    assert FontIndex(dirs=[str(font_home)]).find("DejaVu Sans") is not None
    [(_path, _families, already)] = install_fonts(str(dejavu_dir / "DejaVuSans.ttf"))
    assert already


def _zip_of_fonts(dejavu_dir: pathlib.Path) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(dejavu_dir / "DejaVuSans.ttf", "family/fonts/DejaVuSans.ttf")
        archive.write(dejavu_dir / "DejaVuSans-Bold.ttf", "../DejaVuSans-Bold.ttf")  # never outside
        archive.writestr("family/OFL.txt", "license")
        archive.writestr("__MACOSX/family/fonts/._DejaVuSans.ttf", b"\x00\x05\x16\x07")
    return buffer.getvalue()


def test_install_a_directory_or_a_zip_of_fonts(font_home, dejavu_dir, tmp_path):
    from pikslide.fonts import install_fonts

    assert len(install_fonts(str(dejavu_dir))) == 2
    archive = tmp_path / "family.zip"
    archive.write_bytes(_zip_of_fonts(dejavu_dir))
    paths = sorted(pathlib.Path(path).name for path, _families, _already in install_fonts(str(archive)))
    assert paths == ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
    assert sorted(p.name for p in font_home.iterdir()) == paths


class _Response:
    def __init__(self, url: str, data: bytes):
        self._url, self._data = url, data

    def read(self, n: int = -1) -> bytes:
        return self._data if n < 0 else self._data[:n]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_install_fonts_from_a_url(monkeypatch, font_home, dejavu_dir):
    import pikslide.fonts
    from pikslide.fonts import install_fonts

    files = {
        "https://example.com/dl/family.zip": _zip_of_fonts(dejavu_dir),
        "https://example.com/get?id=1": (dejavu_dir / "DejaVuSans.ttf").read_bytes(),
    }
    monkeypatch.setattr(pikslide.fonts.urllib.request, "urlopen",
                        lambda request, timeout: _Response(request.full_url, files[request.full_url]))
    assert len(install_fonts("https://example.com/dl/family.zip")) == 2
    # a URL whose path names no font file: named after it, as a TrueType font
    [(path, _families, _already)] = install_fonts("https://example.com/get?id=1")
    assert pathlib.Path(path).name == "get.ttf"


def test_what_has_no_font_is_an_error(font_home, tmp_path):
    from pikslide.fonts import FontInstallError, install_fonts

    (tmp_path / "notes.txt").write_text("not a font", encoding="utf-8")
    with pytest.raises(FontInstallError, match="no font in"):
        install_fonts(str(tmp_path / "notes.txt"))
    with pytest.raises(FontInstallError, match="no such file"):
        install_fonts(str(tmp_path / "missing.ttf"))


def test_on_windows_and_wsl_it_says_powerpoint_needs_the_font_in_windows(monkeypatch, capsys, font_home, dejavu_dir):
    # Installed for `fit` and --renderer direct all the same; PowerPoint's
    # fonts are Windows', for the user to install.
    from pikslide import main

    monkeypatch.setattr("pikslide.on_windows", lambda: True)
    monkeypatch.setattr("sys.argv", ["pikslide", "--install-font", str(dejavu_dir / "DejaVuSans.ttf")])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert (font_home / "DejaVuSans.ttf").exists()
    assert "install them in Windows too" in captured.err


def test_on_windows_fonts_go_in_pikslides_own_directory(monkeypatch):
    from pikslide.fonts import user_font_dir

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "/users/u/AppData/Local")
    assert user_font_dir() == os.path.join("/users/u/AppData/Local", "pikslide", "fonts")


def test_cli_install_font(monkeypatch, capsys, font_home, dejavu_dir):
    from pikslide import main

    monkeypatch.setattr("sys.argv", ["pikslide", "--install-font", str(dejavu_dir / "DejaVuSans.ttf")])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert capsys.readouterr().out == f"installed {font_home / 'DejaVuSans.ttf'}: DejaVu Sans\n"
    monkeypatch.setattr("sys.argv", ["pikslide", "d.pik", "--install-font", "x.ttf"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2  # SOURCEs alone


# ---------------------------------------------------------------------------
# What PowerPoint draws differently from what `fit` measured (issue #37)
# ---------------------------------------------------------------------------


def test_glyph_coverage_reads_the_cmap(dejavu_dir):
    from pikslide.fonts import glyph_coverage

    coverage = glyph_coverage(str(dejavu_dir / "DejaVuSans.ttf"))
    assert ord("A") in coverage and ord("é") in coverage
    assert ord("日") not in coverage


def _dejavu_typeface_result(monkeypatch, dejavu_dir, src: str):
    import pikslide.pptx_writer
    from pikslide.pik import parse

    monkeypatch.setattr(pikslide.pptx_writer, "installed_fonts", lambda: FontIndex(dirs=[str(dejavu_dir)]))
    return pikslide.pptx_writer.resolve_for_pptx(parse('typeface = "DejaVu Sans"\n' + src))


def test_a_font_with_no_glyphs_for_some_text_is_a_warning(monkeypatch, dejavu_dir):
    # Arial for Japanese, say: PowerPoint draws it in another font, so `fit`
    # measured the wrong widths, and --renderer direct draws boxes.
    result = _dejavu_typeface_result(monkeypatch, dejavu_dir, 'A: box "Web" fit\nB: box "日本" fit\narrow "矢印"\n')
    [warning] = [w for w in result.warnings if "no glyphs" in w.message]
    assert warning.message.startswith('DejaVu Sans has no glyphs for some of "日本", "矢印": PowerPoint draws them')
    assert warning.objects == ("B", "arrow 1")


def test_a_font_powerpoint_doesnt_draw_with_is_a_stand_in(monkeypatch, dejavu_dir):
    # Under WSL, a font in WSL's own directories, not in Windows': `fit`
    # measured it, PowerPoint draws another.
    import pikslide.pptx_writer

    monkeypatch.setattr(pikslide.pptx_writer, "powerpoint_sees", lambda path: False)
    result = _dejavu_typeface_result(monkeypatch, dejavu_dir, 'box "Web" fit\n')
    assert any(s.startswith("font not installed in Windows: DejaVu Sans") for s in result.stand_ins)


def test_which_fonts_powerpoint_draws_with(monkeypatch):
    import pikslide.fonts
    from pikslide.fonts import powerpoint_sees

    monkeypatch.setattr(pikslide.fonts, "on_windows", lambda: True)
    monkeypatch.setattr(sys, "platform", "linux")  # WSL
    assert powerpoint_sees("/mnt/c/Windows/Fonts/arial.ttf")
    assert not powerpoint_sees("/usr/share/fonts/truetype/bizud-mincho/BIZUDMincho-Regular.ttf")
    monkeypatch.setattr(sys, "platform", "win32")  # Windows: not pikslide's own directory
    monkeypatch.setenv("LOCALAPPDATA", "/users/u/AppData/Local")
    assert not powerpoint_sees("/users/u/AppData/Local/pikslide/fonts/MyFont.ttf")
    assert powerpoint_sees("/windows/fonts/arial.ttf")

"""Tests for pikslide.fonts: finding installed fonts by family name, and
reading a theme's fonts."""

from __future__ import annotations

import os
import pathlib
import shutil
import struct
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


def test_theme_fonts_take_each_scripts_font_when_east_asian_is_empty():
    template = pathlib.Path(pptx.__file__).parent / "templates" / "default.pptx"
    with zipfile.ZipFile(template) as z:
        fonts = theme_fonts_from_xml(z.read("ppt/theme/theme1.xml"))
    assert (fonts.minor_latin, fonts.minor_ea) == ("Calibri", "")
    for major in (False, True):
        assert fonts.east_asian(major, "Jpan") == "ＭＳ Ｐゴシック"
        assert fonts.east_asian(major, "Hang") == "맑은 고딕"
        assert fonts.east_asian(major, "Hans") == "宋体"
        assert fonts.east_asian(major, "Hant") == "新細明體"


def test_theme_fonts_east_asian_font_is_every_scripts():
    theme = (
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements>'
        '<a:fontScheme name="x"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Meiryo"/>'
        '<a:font script="Hang" typeface="Batang"/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/></a:minorFont>'
        '</a:fontScheme></a:themeElements></a:theme>'
    ).encode()
    fonts = theme_fonts_from_xml(theme)
    assert fonts.east_asian(True, "Hang") == "Meiryo"  # <a:ea> over the script's
    assert fonts.east_asian(False, "Hang") == ""  # neither: the Latin font's, to PilFontMetrics


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
    if os.name == "posix":  # WSL's paths, which Windows' os.path takes for its own
        monkeypatch.setattr(sys, "platform", "linux")  # WSL
        assert powerpoint_sees("/mnt/c/Windows/Fonts/arial.ttf")
        assert powerpoint_sees("/mnt/c/Users/u/AppData/Local/Microsoft/FontCache/4/CloudFonts/Aptos/1.ttf")
        assert not powerpoint_sees("/usr/share/fonts/truetype/bizud-mincho/BIZUDMincho-Regular.ttf")
    monkeypatch.setattr(sys, "platform", "win32")  # Windows: not pikslide's own directory
    monkeypatch.setenv("LOCALAPPDATA", "/users/u/AppData/Local")
    assert not powerpoint_sees("/users/u/AppData/Local/pikslide/fonts/MyFont.ttf")
    assert powerpoint_sees("/windows/fonts/arial.ttf")
    assert powerpoint_sees("/users/u/AppData/Local/Microsoft/FontCache/4/CloudFonts/Aptos/1.ttf")


# ---------------------------------------------------------------------------
# Office's cloud fonts (issue #43)
# ---------------------------------------------------------------------------


def test_offices_cloud_fonts_are_searched(monkeypatch, tmp_path: pathlib.Path):
    # PowerPoint draws with the fonts Office downloads for a document, in
    # %LOCALAPPDATA%\Microsoft\FontCache\4\CloudFonts on Windows; under
    # WSL, in the Windows user's.
    import pikslide.fonts

    local = tmp_path / "Local"
    cloud = local / "Microsoft" / "FontCache" / "4" / "CloudFonts"
    cloud.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert str(cloud) in pikslide.fonts._font_dirs()

    monkeypatch.delenv("LOCALAPPDATA")
    wsl = tmp_path / "mnt" / "c" / "Users" / "u" / "AppData" / "Local" / "Microsoft" / "FontCache" / "4" / "CloudFonts"
    wsl.mkdir(parents=True)
    real_glob = pikslide.fonts.glob.glob

    def glob(pattern: str) -> list[str]:  # /mnt/c, as it is here
        return real_glob(str(tmp_path) + pattern) if pattern.startswith("/mnt/c/") else real_glob(pattern)

    monkeypatch.setattr(pikslide.fonts.glob, "glob", glob)
    assert str(wsl) in map(os.path.normpath, pikslide.fonts._font_dirs())


def test_a_cloud_font_is_found_by_its_family(dejavu_dir: pathlib.Path, tmp_path: pathlib.Path):
    # A folder for each family, its files named by number.
    family = tmp_path / "CloudFonts" / "DejaVu Sans"
    family.mkdir(parents=True)
    shutil.copy(dejavu_dir / "DejaVuSans.ttf", family / "30876484867.ttf")
    assert FontIndex(dirs=[str(tmp_path / "CloudFonts")]).find("DejaVu Sans").path == str(family / "30876484867.ttf")


# ---------------------------------------------------------------------------
# Text set as PowerPoint sets it, raqm or not (issue #49)
# ---------------------------------------------------------------------------


def _layout_table(script: bytes, feature: bytes, lookup_type: int, subtable: bytes) -> bytes:
    """A GSUB or GPOS table with one script, whose default language has one
    feature, of one lookup, of one subtable."""
    scripts = struct.pack(">H4sH", 1, script, 8) + struct.pack(">HH", 4, 0) + struct.pack(">HHHH", 0, 0xFFFF, 1, 0)
    features = struct.pack(">H4sH", 1, feature, 8) + struct.pack(">HHH", 0, 1, 0)
    lookups = struct.pack(">HH", 1, 4) + struct.pack(">HHHH", lookup_type, 0, 1, 8) + subtable
    offsets = (10, 10 + len(scripts), 10 + len(scripts) + len(features))
    return struct.pack(">HHHHH", 1, 0, *offsets) + scripts + features + lookups


# Glyph 10 then glyph 20: -50 (a pair), -30 (their classes); -40 in a `kern` table.
_PAIR_FORMAT1 = (struct.pack(">HHHHHH", 1, 12, 0x4, 0, 1, 18)  # header
                 + struct.pack(">HHH", 1, 1, 10)  # coverage: glyph 10
                 + struct.pack(">HHh", 1, 20, -50))  # pair set: glyph 20, -50
_PAIR_FORMAT2 = (struct.pack(">HHHHHHHH", 2, 24, 0x4, 0, 30, 40, 2, 2)  # header
                 + struct.pack(">hhhh", 0, 0, 0, -30)  # class 1 then class 1: -30
                 + struct.pack(">HHH", 1, 1, 10)  # coverage: glyph 10
                 + struct.pack(">HHHHH", 2, 1, 10, 10, 1)  # first classes: glyph 10, class 1
                 + struct.pack(">HHHH", 1, 20, 1, 1))  # second classes: glyph 20, class 1
_KERN_TABLE = (struct.pack(">HH", 0, 1)  # version 0, one subtable
               + struct.pack(">HHHHHHH", 0, 20, 1, 1, 6, 0, 0)  # horizontal, format 0, one pair
               + struct.pack(">HHh", 10, 20, -40))


def test_kerning_is_gpos_kern_features_pair_adjustments():
    from pikslide.fonts import _Kerning

    for subtable, value in ((_PAIR_FORMAT1, -50), (_PAIR_FORMAT2, -30)):
        kerning = _Kerning(_layout_table(b"latn", b"kern", 2, subtable), _KERN_TABLE)
        assert (kerning(10, 20), kerning(10, 21), kerning(11, 20)) == (value, 0, 0)
    extension = struct.pack(">HHI", 1, 2, 8) + _PAIR_FORMAT1  # an extension lookup's subtable
    assert _Kerning(_layout_table(b"DFLT", b"kern", 9, extension), None)(10, 20) == -50


def test_kerning_is_the_kern_tables_where_gpos_has_no_kern_feature():
    # Malgun Gothic's GPOS has no features, and its kerning is in `kern`.
    from pikslide.fonts import _Kerning

    no_latin_kern = [_layout_table(b"latn", b"liga", 2, _PAIR_FORMAT1),
                     _layout_table(b"cyrl", b"kern", 2, _PAIR_FORMAT1)]
    for gpos in (None, *no_latin_kern):
        assert _Kerning(gpos, _KERN_TABLE)(10, 20) == -40
    assert _Kerning(b"\x00\x01", None)(10, 20) == 0  # not readable: none


def test_vertical_forms_are_the_vert_features_substitutions():
    from pikslide.fonts import _EAST_ASIAN, _single_substitutions

    delta = struct.pack(">HHh", 1, 6, 100) + struct.pack(">HHH", 1, 1, 5)
    array = struct.pack(">HHHH", 2, 8, 1, 70) + struct.pack(">HHH", 1, 1, 7)
    assert _single_substitutions(_layout_table(b"hani", b"vert", 1, delta), _EAST_ASIAN, b"vert") == {5: 105}
    assert _single_substitutions(_layout_table(b"kana", b"vert", 1, array), _EAST_ASIAN, b"vert") == {7: 70}
    assert _single_substitutions(_layout_table(b"latn", b"vert", 1, array), _EAST_ASIAN, b"vert") == {}


def test_glyph_metrics_advance_and_kern(dejavu_dir: pathlib.Path):
    from pikslide.fonts import glyph_metrics

    glyphs = glyph_metrics(str(dejavu_dir / "DejaVuSans.ttf"))
    plain, kerned = glyphs.advances("AV", kern=False), glyphs.advances("AV", kern=True)
    assert kerned[0] < plain[0] and kerned[1] == plain[1]
    assert glyph_metrics(str(dejavu_dir / "nothing.ttf")) is None


def test_glyph_metrics_set_text_as_raqm_does_but_for_its_ligatures(dejavu_dir: pathlib.Path):
    # raqm (HarfBuzz) is what --renderer direct was checked against before;
    # it kerns at every size and sets ligatures, which PowerPoint doesn't.
    from PIL import ImageFont, features

    from pikslide.fonts import glyph_metrics

    if not features.check("raqm"):
        pytest.skip("no raqm to compare with")
    path = str(dejavu_dir / "DejaVuSans.ttf")
    raqm = ImageFont.truetype(path, 1000, layout_engine=ImageFont.Layout.RAQM)
    glyphs = glyph_metrics(path)
    for text in ("AVATAR Toyota WAVE", "How Japan's capital moved"):
        assert sum(glyphs.advances(text, kern=True)) * 1000 == pytest.approx(raqm.getlength(text), rel=1e-5)
    # Set vertically, with no vertical metrics: the font's height.
    assert sum(glyphs.vertical_advances("AB")) * 1000 == pytest.approx(raqm.getlength("AB", direction="ttb"), rel=1e-5)


def _template_with_kern(tmp_path: pathlib.Path, kern: str | None) -> pathlib.Path:
    """The built-in template, its text styles' `kern="1200"` set to `kern`,
    or left out."""
    src = pathlib.Path(pptx.__file__).parent / "templates" / "default.pptx"
    out = tmp_path / f"template-{kern}.pptx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in ("ppt/presentation.xml", "ppt/slideMasters/slideMaster1.xml"):
                data = data.replace(b' kern="1200"', f' kern="{kern}"'.encode() if kern else b"")
            zout.writestr(item, data)
    return out


def test_the_decks_kerning_size_is_its_text_styles(tmp_path: pathlib.Path):
    from pikslide.pptx_writer import master_kern_from

    assert master_kern_from(pptx.Presentation().slide_masters[0]) == 12.0
    assert master_kern_from(pptx.Presentation(str(_template_with_kern(tmp_path, "2000"))).slide_masters[0]) == 20.0
    assert master_kern_from(pptx.Presentation(str(_template_with_kern(tmp_path, None))).slide_masters[0]) == 0.0


def test_latin_text_is_kerned_from_the_decks_kerning_size(dejavu_dir: pathlib.Path, tmp_path: pathlib.Path):
    # PowerPoint kerns text of 12pt and more, as the built-in template's
    # text style says, and sets no ligatures (checked).
    from pikslide.fonts import glyph_metrics
    from pikslide.pik import parse
    from pikslide.pptx_writer import PilFontMetrics, resolve_for_pptx

    index = FontIndex(dirs=[str(dejavu_dir)])
    glyphs = glyph_metrics(str(dejavu_dir / "DejaVuSans.ttf"))

    def width(text: str, pt: float, kern: bool) -> float:
        return sum(glyphs.advances(text, kern)) * pt / 72

    def measured(metrics, text: str, pt: float) -> float:
        return metrics.text_width(text, [], {"medium": pt / 72}, "DejaVu Sans")

    metrics = PilFontMetrics(font_index=index)
    for pt, kern in ((10.5, False), (12, True), (24, True)):
        assert measured(metrics, "AVAVAV", pt) == pytest.approx(width("AVAVAV", pt, kern))
    always = PilFontMetrics(font_index=index, kern_from=0.0)
    assert measured(always, "AVAVAV", 10.5) == pytest.approx(width("AVAVAV", 10.5, True))
    assert measured(metrics, "office", 24) == pytest.approx(width("office", 24, True))

    # A template's own kerning size.
    src = 'typeface = "DejaVu Sans"\nmedium = 12pt\nbox "AVAVAV" fit\n'
    built_in = resolve_for_pptx(parse(src), font_index=index).shapes[0].w
    template = str(_template_with_kern(tmp_path, "2000"))
    assert resolve_for_pptx(parse(src), template_path=template, font_index=index).shapes[0].w > built_in

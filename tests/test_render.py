"""`pikslide.render` -- `--png`/`--pdf` (docs/spec.md SS4). PowerPoint and
LibreOffice are stood in for by a fake `subprocess.run`, so these check
which renderer is chosen and how it's called, not the pixels; set
PIKSLIDE_RENDER_TESTS=1 to also run a real render on this machine."""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from pikslide import main, render
from pikslide.render import DIRECT_NOTE, RenderError


class _FakeRun:
    """Records each command; `fail` names the programs that exit 1.
    soffice "writes" its output file, as the real one would."""

    def __init__(self, fail: tuple[str, ...] = ()):
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        prog = os.path.basename(argv[0])
        if prog == "wslpath":
            return subprocess.CompletedProcess(argv, 0, stdout="\\\\wsl.localhost\\Ubuntu" + argv[-1].replace("/", "\\") + "\n", stderr="")
        if prog in self.fail:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"boom")
        if prog == "soffice":
            fmt, outdir, src = argv[3], argv[5], argv[6]
            stem = os.path.splitext(os.path.basename(src))[0]
            pathlib.Path(outdir, f"{stem}.{fmt}").write_bytes(b"x")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")


def _tools(monkeypatch, *available: str) -> None:
    monkeypatch.setattr(render.shutil, "which", lambda name: f"/fake/{name}" if name in available else None)


class _Draw:
    """Stands in for pikslide.draw: records each (path, fmt) it's asked to draw."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, path: str, fmt: str) -> None:
        self.calls.append((path, fmt))


def test_powerpoint_is_preferred_when_reachable(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe", "wslpath", "soffice")
    fake, draw = _FakeRun(), _Draw()
    monkeypatch.setattr(render.subprocess, "run", fake)
    assert render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", draw=draw) == ("powerpoint", [])
    ps = next(c for c in fake.calls if c[0].endswith("powershell.exe"))
    assert ps[ps.index("-File") + 1].endswith("pptx_to_png.ps1")
    # WSL paths are handed to PowerPoint as Windows paths.
    assert ps[ps.index("-PngPath") + 1].startswith("\\\\wsl.localhost\\")
    assert ps[ps.index("-PngPath") + 1].endswith("\\d.png")
    assert not any(c[0].endswith("soffice") for c in fake.calls)
    assert draw.calls == []


def test_pdf_uses_the_pdf_script(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe")
    fake = _FakeRun()
    monkeypatch.setattr(render.subprocess, "run", fake)
    render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.pdf"), "pdf")
    ps = fake.calls[0]
    assert ps[ps.index("-File") + 1].endswith("pptx_to_pdf.ps1")
    assert ps[ps.index("-PdfPath") + 1] == str(tmp_path / "d.pdf")  # no wslpath: used as is


def test_powerpoint_failure_is_drawn_by_pikslide_with_a_note(monkeypatch, tmp_path):
    # issue #34: not LibreOffice, which is used only when named
    _tools(monkeypatch, "powershell.exe", "soffice")
    fake, draw = _FakeRun(fail=("powershell.exe",)), _Draw()
    monkeypatch.setattr(render.subprocess, "run", fake)
    out = str(tmp_path / "chart.png")
    renderer, [note] = render.render_deck(str(tmp_path / "d.pptx"), out, "png", draw=draw)
    assert renderer == "direct" and draw.calls == [(out, "png")]
    assert "boom" in note and DIRECT_NOTE in note
    assert not any(c[0].endswith("soffice") for c in fake.calls)


def test_auto_without_powershell_is_drawn_by_pikslide_with_a_note(monkeypatch, tmp_path):
    _tools(monkeypatch, "soffice")
    draw = _Draw()
    renderer, [note] = render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.pdf"), "pdf", draw=draw)
    assert renderer == "direct" and draw.calls == [(str(tmp_path / "d.pdf"), "pdf")]
    assert "powershell.exe" in note and DIRECT_NOTE in note


def test_renderer_direct_never_tries_powerpoint(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe", "soffice")
    fake, draw = _FakeRun(), _Draw()
    monkeypatch.setattr(render.subprocess, "run", fake)
    assert render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", "direct", draw) == ("direct", [])
    assert fake.calls == [] and len(draw.calls) == 1


def test_renderer_powerpoint_never_falls_back(monkeypatch, tmp_path):
    _tools(monkeypatch, "soffice")
    fake, draw = _FakeRun(), _Draw()
    monkeypatch.setattr(render.subprocess, "run", fake)
    with pytest.raises(RenderError, match="powershell.exe"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", renderer="powerpoint", draw=draw)
    assert fake.calls == [] and draw.calls == []


def test_renderer_libreoffice_skips_powerpoint_silently(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe", "soffice")
    fake = _FakeRun()
    monkeypatch.setattr(render.subprocess, "run", fake)
    assert render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", renderer="libreoffice") == (
        "libreoffice", [])
    assert [os.path.basename(c[0]) for c in fake.calls] == ["soffice"]


def test_renderer_libreoffice_without_soffice_is_an_error(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe")
    with pytest.raises(RenderError, match="soffice"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", renderer="libreoffice")


def test_with_nothing_to_draw_with_it_is_an_error(monkeypatch, tmp_path):
    _tools(monkeypatch)
    with pytest.raises(RenderError, match="powershell.exe.*nothing to draw it with"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png")


# ---------------------------------------------------------------------------
# The CLI's --png/--pdf
# ---------------------------------------------------------------------------


def _run_cli(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["pikslide", *argv])
    main()


@pytest.fixture
def rendered(monkeypatch):
    """Replace render_deck() itself, recording (pptx, out, fmt, renderer)."""
    calls = []

    def fake_render(pptx_path, out_path, fmt, renderer="auto", draw=None):
        assert os.path.isfile(pptx_path)  # the deck is written first
        calls.append((pptx_path, out_path, fmt, renderer))
        return "powerpoint", []

    monkeypatch.setattr("pikslide.api.render_deck", fake_render)
    return calls


def _src(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "d.pik"
    src.write_text('box "Web"\n', encoding="utf-8")
    return src


def test_png_and_pdf_default_beside_output(monkeypatch, capsys, tmp_path, rendered):
    out = tmp_path / "out.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", "--pdf"])
    assert rendered == [
        (str(out), str(tmp_path / "out.png"), "png", "auto"),
        (str(out), str(tmp_path / "out.pdf"), "pdf", "auto"),
    ]
    stdout = capsys.readouterr().out
    assert f"wrote {tmp_path / 'out.png'} (drawn by PowerPoint)" in stdout
    assert f"wrote {tmp_path / 'out.pdf'} (drawn by PowerPoint)" in stdout


def test_explicit_png_path(monkeypatch, tmp_path, rendered):
    out = tmp_path / "out.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", str(tmp_path / "x.png")])
    assert rendered == [(str(out), str(tmp_path / "x.png"), "png", "auto")]


def test_png_with_template_and_no_output_follows_the_default_output(monkeypatch, tmp_path, rendered):
    from pptx import Presentation

    tmpl = tmp_path / "tmpl.pptx"
    Presentation().save(str(tmpl))
    _run_cli(monkeypatch, [str(_src(tmp_path)), "--template", str(tmpl), "--png"])
    assert rendered[0][:2] == (str(tmp_path / "d.pptx"), str(tmp_path / "d.png"))


def test_renderer_flag_is_passed_through(monkeypatch, tmp_path, rendered):
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(tmp_path / "o.pptx"), "--pdf", "--renderer", "libreoffice"])
    assert rendered[0][3] == "libreoffice"


def test_a_fallback_is_a_note_not_a_warning_so_strict_allows_it(monkeypatch, capsys, tmp_path):
    from pptx import Presentation

    monkeypatch.setattr("pikslide.api.render_deck", lambda *a, **k: ("direct", ["drawn without PowerPoint"]))
    tmpl = tmp_path / "tmpl.pptx"
    Presentation().save(str(tmpl))
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(tmp_path / "o.pptx"), "--template", str(tmpl), "--png", "--strict"])
    captured = capsys.readouterr()
    assert captured.err == "note: drawn without PowerPoint\n"
    assert "(drawn by pikslide)" in captured.out


def test_png_path_with_the_wrong_extension_is_an_error(monkeypatch, capsys, tmp_path, rendered):
    # `--png OUTPUT.pptx`: the optional PATH swallowed what was meant as OUTPUT.
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, [str(_src(tmp_path)), "--png", str(tmp_path / "d.pptx")])
    assert exc.value.code == 2
    assert "must end in .png" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [[], ["--check"]])
def test_png_needs_a_written_deck(monkeypatch, tmp_path, rendered, extra):
    argv = [str(_src(tmp_path))] + ([str(tmp_path / "d.pptx")] if extra else []) + extra + ["--png"]
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, argv)
    assert exc.value.code == 2
    assert rendered == []


def test_render_failure_is_a_clean_error(monkeypatch, capsys, tmp_path):
    def failing(*args, **kwargs):
        raise RenderError("nothing to render with")

    monkeypatch.setattr("pikslide.api.render_deck", failing)
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, [str(_src(tmp_path)), str(tmp_path / "d.pptx"), "--pdf"])
    assert exc.value.code == 1
    assert "could not render" in capsys.readouterr().err
    assert (tmp_path / "d.pptx").exists()  # the deck itself was still written


@pytest.mark.parametrize("fmt, magic", [("png", b"\x89PNG"), ("pdf", b"%PDF")])
def test_direct_draws_without_powerpoint(monkeypatch, capsys, tmp_path, fmt, magic):
    # issue #34: no PowerPoint, no LibreOffice, and a picture all the same
    _tools(monkeypatch)
    out = tmp_path / "d.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), f"--{fmt}"])
    assert (tmp_path / f"d.{fmt}").read_bytes().startswith(magic)
    captured = capsys.readouterr()
    assert f"wrote {tmp_path / f'd.{fmt}'} (drawn by pikslide)" in captured.out
    assert DIRECT_NOTE in captured.err


@pytest.mark.skipif(not os.environ.get("PIKSLIDE_RENDER_TESTS"), reason="set PIKSLIDE_RENDER_TESTS=1 to run a real render")
def test_real_render(monkeypatch, tmp_path):
    out = tmp_path / "d.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", "--pdf"])
    assert (tmp_path / "d.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "d.pdf").read_bytes().startswith(b"%PDF")


@pytest.mark.skipif(not os.environ.get("PIKSLIDE_RENDER_TESTS"), reason="set PIKSLIDE_RENDER_TESTS=1 to run a real render")
@pytest.mark.parametrize("fmt", render.FORMATS)
def test_a_deck_powerpoint_cant_open_says_so(tmp_path, fmt):
    # In the console's code page (cp932 on a Japanese Windows), the message
    # used to come out garbled; now it's UTF-8 (issue #27).
    deck = tmp_path / "d.pptx"
    deck.write_bytes(b"not a deck")
    with pytest.raises(RenderError, match="PowerPoint could not open d.pptx: ") as exc:
        render.render_deck(str(deck), str(tmp_path / f"d.{fmt}"), fmt, renderer="powerpoint")
    assert "�" not in str(exc.value)

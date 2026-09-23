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
from pikslide.render import LIBREOFFICE_WARNING, RenderError


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


def test_powerpoint_is_preferred_when_reachable(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe", "wslpath", "soffice")
    fake = _FakeRun()
    monkeypatch.setattr(render.subprocess, "run", fake)
    warnings = render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png")
    assert warnings == []
    ps = next(c for c in fake.calls if c[0].endswith("powershell.exe"))
    assert ps[ps.index("-File") + 1].endswith("pptx_to_png.ps1")
    # WSL paths are handed to PowerPoint as Windows paths.
    assert ps[ps.index("-PngPath") + 1].startswith("\\\\wsl.localhost\\")
    assert ps[ps.index("-PngPath") + 1].endswith("\\d.png")
    assert not any(c[0].endswith("soffice") for c in fake.calls)


def test_pdf_uses_the_pdf_script(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe")
    fake = _FakeRun()
    monkeypatch.setattr(render.subprocess, "run", fake)
    render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.pdf"), "pdf")
    ps = fake.calls[0]
    assert ps[ps.index("-File") + 1].endswith("pptx_to_pdf.ps1")
    assert ps[ps.index("-PdfPath") + 1] == str(tmp_path / "d.pdf")  # no wslpath: used as is


def test_powerpoint_failure_falls_back_to_libreoffice_with_warnings(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe", "soffice")
    monkeypatch.setattr(render.subprocess, "run", _FakeRun(fail=("powershell.exe",)))
    out = tmp_path / "chart.png"
    warnings = render.render_deck(str(tmp_path / "d.pptx"), str(out), "png")
    assert out.exists()  # renamed from soffice's own d.png
    assert "boom" in warnings[0] and warnings[1] == LIBREOFFICE_WARNING


def test_libreoffice_alone_warns(monkeypatch, tmp_path):
    _tools(monkeypatch, "soffice")
    monkeypatch.setattr(render.subprocess, "run", _FakeRun())
    assert render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.pdf"), "pdf") == [LIBREOFFICE_WARNING]


def test_no_fallback_refuses_libreoffice(monkeypatch, tmp_path):
    _tools(monkeypatch, "soffice")
    fake = _FakeRun()
    monkeypatch.setattr(render.subprocess, "run", fake)
    with pytest.raises(RenderError, match="--strict"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png", allow_fallback=False)
    assert fake.calls == []


def test_no_renderer_at_all_is_an_error(monkeypatch, tmp_path):
    _tools(monkeypatch)
    with pytest.raises(RenderError, match="soffice"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png")


def test_powerpoint_failure_without_libreoffice_reports_both(monkeypatch, tmp_path):
    _tools(monkeypatch, "powershell.exe")
    monkeypatch.setattr(render.subprocess, "run", _FakeRun(fail=("powershell.exe",)))
    with pytest.raises(RenderError, match="boom.*soffice"):
        render.render_deck(str(tmp_path / "d.pptx"), str(tmp_path / "d.png"), "png")


# ---------------------------------------------------------------------------
# The CLI's --png/--pdf
# ---------------------------------------------------------------------------


def _run_cli(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["pikslide", *argv])
    main()


@pytest.fixture
def rendered(monkeypatch):
    """Replace render_deck() itself, recording (pptx, out, fmt, allow_fallback)."""
    calls = []

    def fake_render(pptx_path, out_path, fmt, allow_fallback=True):
        assert os.path.isfile(pptx_path)  # the deck is written first
        calls.append((pptx_path, out_path, fmt, allow_fallback))
        return []

    monkeypatch.setattr("pikslide.render_deck", fake_render)
    return calls


def _src(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "d.pik"
    src.write_text('box "Web"\n', encoding="utf-8")
    return src


def test_png_and_pdf_default_beside_output(monkeypatch, capsys, tmp_path, rendered):
    out = tmp_path / "out.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", "--pdf"])
    assert rendered == [
        (str(out), str(tmp_path / "out.png"), "png", True),
        (str(out), str(tmp_path / "out.pdf"), "pdf", True),
    ]
    stdout = capsys.readouterr().out
    assert f"wrote {tmp_path / 'out.png'}" in stdout and f"wrote {tmp_path / 'out.pdf'}" in stdout


def test_explicit_png_path(monkeypatch, tmp_path, rendered):
    out = tmp_path / "out.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", str(tmp_path / "x.png")])
    assert rendered == [(str(out), str(tmp_path / "x.png"), "png", True)]


def test_png_with_template_and_no_output_follows_the_default_output(monkeypatch, tmp_path, rendered):
    from pptx import Presentation

    tmpl = tmp_path / "tmpl.pptx"
    Presentation().save(str(tmpl))
    _run_cli(monkeypatch, [str(_src(tmp_path)), "--template", str(tmpl), "--png"])
    assert rendered[0][:2] == (str(tmp_path / "d.pptx"), str(tmp_path / "d.png"))


def test_strict_disallows_the_fallback(monkeypatch, tmp_path, rendered):
    from pptx import Presentation

    tmpl = tmp_path / "tmpl.pptx"
    Presentation().save(str(tmpl))
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(tmp_path / "o.pptx"), "--template", str(tmpl), "--pdf", "--strict"])
    assert rendered[0][3] is False


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

    monkeypatch.setattr("pikslide.render_deck", failing)
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, [str(_src(tmp_path)), str(tmp_path / "d.pptx"), "--pdf"])
    assert exc.value.code == 1
    assert "could not render" in capsys.readouterr().err
    assert (tmp_path / "d.pptx").exists()  # the deck itself was still written


@pytest.mark.skipif(not os.environ.get("PIKSLIDE_RENDER_TESTS"), reason="set PIKSLIDE_RENDER_TESTS=1 to run a real render")
def test_real_render(monkeypatch, tmp_path):
    out = tmp_path / "d.pptx"
    _run_cli(monkeypatch, [str(_src(tmp_path)), str(out), "--png", "--pdf"])
    assert (tmp_path / "d.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "d.pdf").read_bytes().startswith(b"%PDF")

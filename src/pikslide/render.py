"""Render a written .pptx to a PNG or a PDF (`--png`/`--pdf`, docs/spec.md
SS4) -- a post-processing step on the deck pikslide already wrote, not a
separate output mode.

Prefers PowerPoint itself, through COM automation (`ps/pptx_to_*.ps1`,
run with `powershell.exe`): that is the renderer pikslide's output is
meant for, so it's the one a result can actually be checked against.
Reachable on Windows, or from WSL with a Windows PowerPoint install.
Where it isn't, or fails, pikslide draws the picture itself (`direct`,
pikslide.draw), from the layout, and says so with a note: close to
PowerPoint's, but text never shows overflowing in it. LibreOffice
(`soffice`), a different rendering engine, only when named.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from importlib import resources

FORMATS = ("png", "pdf")

#: How long one PowerPoint or LibreOffice run may take before it's
#: treated as hung. A cold PowerPoint start is a few seconds; this leaves
#: plenty of room without waiting forever on a modal dialog nobody sees.
_TIMEOUT_S = 120

RENDERERS = ("auto", "powerpoint", "direct", "libreoffice")

#: What drew a picture, by renderer, as the CLI reports it.
DRAWN_BY = {"powerpoint": "PowerPoint", "direct": "pikslide", "libreoffice": "LibreOffice"}

DIRECT_NOTE = (
    "drawn by pikslide itself, not PowerPoint: close to it, but text never shows "
    "overflowing in it (the warnings say where it does)"
)


class RenderError(Exception):
    pass


def render_deck(
    pptx_path: str, out_path: str, fmt: str, renderer: str = "auto",
    draw: Callable[[str, str], None] | None = None,
) -> tuple[str, list[str]]:
    """Render the first (for pikslide's own output, the only) slide of
    `pptx_path` to `out_path` as `fmt` ("png" or "pdf"), with `renderer`
    (`--renderer`): "auto" tries PowerPoint, then draws it itself; the
    others use only that one. `draw(out_path, fmt)` draws it itself
    (pikslide.draw), from the layout the deck was written from. Returns
    which renderer drew it (DRAWN_BY's key) and notes worth telling the
    user (that it isn't PowerPoint, when that wasn't asked for); raises
    RenderError if it couldn't be rendered."""
    if renderer == "libreoffice":
        soffice = shutil.which("soffice")
        if soffice is None:
            raise RenderError("LibreOffice (soffice) is not on PATH")
        _render_libreoffice(soffice, pptx_path, out_path, fmt)
        return renderer, []
    failure = None
    if renderer in ("auto", "powerpoint"):
        powershell = shutil.which("powershell.exe")
        if powershell is None:
            failure = "PowerPoint is not reachable (no powershell.exe on PATH)"
        else:
            try:
                _render_powerpoint(powershell, pptx_path, out_path, fmt)
                return "powerpoint", []
            except RenderError as e:
                failure = f"PowerPoint COM automation failed: {e}"
        if renderer == "powerpoint":
            raise RenderError(failure)
    if draw is None:
        raise RenderError(f"{failure}; and nothing to draw it with instead" if failure else "nothing to draw it with")
    draw(out_path, fmt)
    return "direct", [f"{failure}; {DIRECT_NOTE}"] if failure else []


def _render_powerpoint(powershell: str, pptx_path: str, out_path: str, fmt: str) -> None:
    out_param = "-PngPath" if fmt == "png" else "-PdfPath"
    script = resources.files("pikslide").joinpath("ps", f"pptx_to_{fmt}.ps1")
    with resources.as_file(script) as script_path:
        _run(
            [
                powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", _windows_path(str(script_path)),
                "-PptxPath", _windows_path(pptx_path),
                out_param, _windows_path(out_path),
            ],
            "powershell.exe",
        )


def _windows_path(path: str) -> str:
    """`path` as PowerPoint (a Windows process) sees it: under WSL,
    translated with `wslpath -w`; on Windows itself, unchanged. Only the
    directory goes through `wslpath`, which needs its argument to exist
    -- an output file usually doesn't yet."""
    path = os.path.abspath(path)
    if shutil.which("wslpath") is None:
        return path
    directory, name = os.path.split(path)
    result = subprocess.run(["wslpath", "-w", directory], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RenderError(f"wslpath could not translate {directory!r}: {result.stderr.strip()}")
    return result.stdout.strip().rstrip("\\") + "\\" + name


def _render_libreoffice(soffice: str, pptx_path: str, out_path: str, fmt: str) -> None:
    # soffice names its output after the input's own stem, in --outdir,
    # never after anything the caller chose -- so convert into a private
    # directory, then move the one file it made into place.
    with tempfile.TemporaryDirectory() as tmp:
        _run([soffice, "--headless", "--convert-to", fmt, "--outdir", tmp, pptx_path], "soffice")
        stem = os.path.splitext(os.path.basename(pptx_path))[0]
        produced = os.path.join(tmp, f"{stem}.{fmt}")
        if not os.path.isfile(produced):
            raise RenderError(f"soffice reported success but wrote no {fmt.upper()}")
        shutil.move(produced, out_path)


def _run(argv: list[str], name: str) -> None:
    try:
        result = subprocess.run(argv, capture_output=True, timeout=_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise RenderError(f"{name} did not finish within {_TIMEOUT_S}s") from None
    if result.returncode != 0:
        # ps/pptx_to_*.ps1 switch powershell.exe to UTF-8, but what it
        # writes before that is in the console's code page -- this is a
        # diagnostic, so never fail on it.
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise RenderError(f"{name} exited with {result.returncode}" + (f": {detail}" if detail else ""))

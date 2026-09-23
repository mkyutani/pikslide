"""Render a written .pptx to a PNG or a PDF (`--png`/`--pdf`, docs/spec.md
SS4) -- a post-processing step on the deck pikslide already wrote, not a
separate output mode.

Prefers PowerPoint itself, through COM automation (`ps/pptx_to_*.ps1`,
run with `powershell.exe`): that is the renderer pikslide's output is
meant for, so it's the one a result can actually be checked against.
Reachable on Windows, or from WSL with a Windows PowerPoint install. Falls
back to LibreOffice (`soffice`), a different rendering engine -- good for
a quick look, not for verifying exact layout or text fit -- only when
PowerPoint isn't reachable at all, and says so with a warning.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from importlib import resources

FORMATS = ("png", "pdf")

#: How long one PowerPoint or LibreOffice run may take before it's
#: treated as hung. A cold PowerPoint start is a few seconds; this leaves
#: plenty of room without waiting forever on a modal dialog nobody sees.
_TIMEOUT_S = 120

RENDERERS = ("auto", "powerpoint", "libreoffice")

LIBREOFFICE_NOTE = (
    "rendered with LibreOffice, not PowerPoint: good for a quick look, "
    "not for checking exact layout or text fit"
)


class RenderError(Exception):
    pass


def render_deck(pptx_path: str, out_path: str, fmt: str, renderer: str = "auto") -> list[str]:
    """Render the first (for pikslide's own output, the only) slide of
    `pptx_path` to `out_path` as `fmt` ("png" or "pdf"), with `renderer`
    (`--renderer`): "auto" tries PowerPoint, then LibreOffice; the other
    two use only that one. Returns notes worth telling the user (what
    was used, when that isn't PowerPoint); raises RenderError if nothing
    could render it."""
    failure = None
    if renderer in ("auto", "powerpoint"):
        powershell = shutil.which("powershell.exe")
        if powershell is None:
            failure = "PowerPoint is not reachable (no powershell.exe on PATH)"
        else:
            try:
                _render_powerpoint(powershell, pptx_path, out_path, fmt)
                return []
            except RenderError as e:
                failure = f"PowerPoint COM automation failed: {e}"
        if renderer == "powerpoint":
            raise RenderError(failure)

    soffice = shutil.which("soffice")
    if soffice is None:
        missing = "LibreOffice (soffice) is not on PATH"
        raise RenderError(f"{failure}; and {missing} to fall back to" if failure else missing)
    _render_libreoffice(soffice, pptx_path, out_path, fmt)
    if renderer == "libreoffice":
        return []  # asked for by name: nothing to point out
    return [f"{failure}; {LIBREOFFICE_NOTE}"]


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
        # powershell.exe writes in the Windows console code page, not
        # necessarily UTF-8 -- this is a diagnostic, so never fail on it.
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise RenderError(f"{name} exited with {result.returncode}" + (f": {detail}" if detail else ""))

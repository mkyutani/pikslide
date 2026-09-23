#!/usr/bin/env bash
# Render a .pptx to a PDF.
#
# Prefers PowerPoint COM automation (pptx_to_pdf.ps1, beside this script)
# when it's available -- the actual renderer pikslide's output is meant
# for, so this is the way to check a result, not just a way. Falls back to
# LibreOffice (a different rendering engine -- good for a quick look, not
# for verifying exact layout or text fit against real PowerPoint) only
# when PowerPoint isn't reachable at all.
#
# Usage: scripts/pptx_to_pdf.sh INPUT.pptx OUTPUT.pdf

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 INPUT.pptx OUTPUT.pdf" >&2
    exit 2
fi

in=$1
out=$2
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if command -v powershell.exe >/dev/null 2>&1; then
    # WSL with a Windows PowerPoint install (or Windows Git-Bash/MSYS,
    # where paths need no wslpath conversion at all).
    if command -v wslpath >/dev/null 2>&1; then
        win_in=$(wslpath -w "$in")
        win_out=$(wslpath -w "$out")
        win_script=$(wslpath -w "$script_dir/pptx_to_pdf.ps1")
    else
        win_in=$in
        win_out=$out
        win_script="$script_dir/pptx_to_pdf.ps1"
    fi
    if powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$win_script" \
        -PptxPath "$win_in" -PdfPath "$win_out"; then
        exit 0
    fi
    echo "warning: PowerPoint COM automation failed; falling back to LibreOffice" >&2
fi

if ! command -v soffice >/dev/null 2>&1; then
    echo "error: neither PowerPoint (via powershell.exe) nor LibreOffice (soffice) is available" >&2
    exit 1
fi

out_dir=$(dirname "$out")
soffice --headless --convert-to pdf --outdir "$out_dir" "$in" >/dev/null
# soffice names its output after INPUT's own stem, not OUTPUT -- rename.
produced="$out_dir/$(basename "${in%.*}").pdf"
if [ "$produced" != "$out" ]; then
    mv "$produced" "$out"
fi

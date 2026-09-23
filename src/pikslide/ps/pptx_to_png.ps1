<#
.SYNOPSIS
    Export the first slide of a .pptx file to a PNG, via PowerPoint COM
    automation. Windows-only; requires PowerPoint to be installed.

.DESCRIPTION
    pikslide sizes its generated slide exactly to the diagram's bounding box
    (plus a small margin), so exporting the whole slide already gives an
    image of just the diagram -- no separate cropping step is needed.

    pikslide runs this itself for `--png` (src/pikslide/render.py). It
    also runs on its own from Windows PowerShell:

        .\pptx_to_png.ps1 -PptxPath .\diagram.pptx -PngPath .\diagram.png
#>
param(
    [Parameter(Mandatory=$true)][string]$PptxPath,
    [Parameter(Mandatory=$true)][string]$PngPath,
    [int]$Dpi = 200
)

# Default: a failure inside the try block below (e.g. PowerPoint isn't
# installed, so New-Object -ComObject can't find it) is a *non-terminating*
# error under -File invocation -- powershell.exe still exits 0, which would
# make a caller's own PowerPoint-vs-fallback branch (render.py)
# never actually detect the failure (checked). -Stop plus the explicit
# `exit 1` below is what makes the exit code trustworthy.
$ErrorActionPreference = "Stop"

$app = $null
$pres = $null
# Slide.Export() was found to fail intermittently -- "could not be found" --
# when $PngPath is itself a UNC path (checked: \\wsl.localhost\...
# specifically); Presentation.SaveAs() to that same kind of path works fine
# (pptx_to_pdf.ps1), so Export() always writes to a local Windows temp file
# first, and an ordinary Copy-Item (not a PowerPoint COM operation at all)
# moves it to $PngPath, UNC or not, afterward.
$tempPng = Join-Path $env:TEMP ("pikslide_" + [System.Guid]::NewGuid().ToString("N") + ".png")
try {
    $app = New-Object -ComObject PowerPoint.Application
    $pres = $app.Presentations.Open($PptxPath, $true, $true, $false)
    $slide = $pres.Slides.Item(1)

    $widthIn = $pres.PageSetup.SlideWidth / 72.0
    $heightIn = $pres.PageSetup.SlideHeight / 72.0
    $widthPx = [int]($widthIn * $Dpi)
    $heightPx = [int]($heightIn * $Dpi)

    $slide.Export($tempPng, "PNG", $widthPx, $heightPx)
    Copy-Item -Path $tempPng -Destination $PngPath -Force

    Write-Output "wrote $PngPath ($widthPx x $heightPx)"
} catch {
    Write-Error $_
    exit 1
} finally {
    if (Test-Path $tempPng) {
        Remove-Item $tempPng -Force
    }
    # Always torn down, success or failure (checked: -Stop above means a
    # mid-try failure used to skip straight to `catch` and leave `$app`
    # running -- a failed run left PowerPoint's own COM instance behind,
    # for the *next* run's New-Object -ComObject to attach to instead of
    # a fresh one, which is exactly the kind of state a later run can't
    # tell apart from a real failure. Explicit ReleaseComObject + GC
    # because Quit() alone doesn't guarantee the RCW -- and so the
    # out-of-process POWERPNT.EXE -- actually lets go this run.
    if ($pres) {
        $pres.Close()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pres) | Out-Null
    }
    if ($app) {
        $app.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

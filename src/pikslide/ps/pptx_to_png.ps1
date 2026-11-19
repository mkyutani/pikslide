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

# Whether PowerPoint shows nothing on screen: hidden, with no windows.
# What can't be read counts as shown, so in doubt PowerPoint is left
# running.
function Test-PowerPointHidden($app) {
    try {
        return ($app.Visible -eq 0) -and ($app.Windows.Count -eq 0)  # msoFalse
    } catch {
        return $false
    }
}

# pikslide reads what this writes as UTF-8, but powershell.exe writes in
# the console's code page (cp932 on a Japanese Windows), and PowerPoint's
# own errors come in Windows' language (checked: Write-Error and
# [Console]::Error both follow this). Put back in `finally`, since the
# console may be the caller's.
$consoleEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$app = $null
$pres = $null
# Slide.Export() was found to fail intermittently -- "could not be found" --
# when $PngPath is itself a UNC path (checked: \\wsl.localhost\...
# specifically); Presentation.SaveAs() to that same kind of path works fine
# (pptx_to_pdf.ps1), so Export() always writes to a local Windows temp file
# first, and an ordinary Copy-Item (not a PowerPoint COM operation at all)
# moves it to $PngPath, UNC or not, afterward.
$temp = Join-Path $env:TEMP ("pikslide_" + [System.Guid]::NewGuid().ToString("N"))
$tempPng = "$temp.png"
# PowerPoint opens a copy of the deck, under a name of its own, so that
# the presentation this closes is never one the user has open: step 3 of
# the README has them editing that very .pptx in PowerPoint, and
# Presentations.Open() of a deck already open, even untitled, returns
# that one, which Close() closes without asking (checked, issue #35).
$tempPptx = "$temp.pptx"
$tempFiles = @($tempPng, $tempPptx)
try {
    Copy-Item -LiteralPath $PptxPath -Destination $tempPptx
    $app = New-Object -ComObject PowerPoint.Application
    try {
        $pres = $app.Presentations.Open($tempPptx, $true, $true, $false)
    } catch {
        throw "PowerPoint could not open $(Split-Path -Leaf $PptxPath): $($_.Exception.Message)"
    }
    $slide = $pres.Slides.Item(1)

    $widthIn = $pres.PageSetup.SlideWidth / 72.0
    $heightIn = $pres.PageSetup.SlideHeight / 72.0
    $widthPx = [int]($widthIn * $Dpi)
    $heightPx = [int]($heightIn * $Dpi)

    $slide.Export($tempPng, "PNG", $widthPx, $heightPx)
    Copy-Item -LiteralPath $tempPng -Destination $PngPath -Force

    Write-Output "wrote $PngPath ($widthPx x $heightPx)"
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
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
    # New-Object -ComObject attaches to a PowerPoint that is already
    # running, so it's quit only if it shows nothing, as one this run
    # started does (COM starts it hidden, and the deck opens without a
    # window). The user's own is shown, and quitting it would close what
    # they're working on (issue #35): it's only let go of. One a run
    # killed by render.py's timeout left behind is hidden too, but Quit()
    # doesn't end it while the killed run's references last: it ends on
    # its own, Quit() or not, once COM lets go of them, some six minutes
    # later (checked).
    if ($app) {
        if (Test-PowerPointHidden $app) {
            $app.Quit()
        }
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    # Once PowerPoint has let go of the copy. A file left in %TEMP% is no
    # reason to fail a run that rendered.
    foreach ($path in $tempFiles) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    [Console]::OutputEncoding = $consoleEncoding
}

<#
.SYNOPSIS
    Export a .pptx file to PDF, via PowerPoint COM automation. Windows-only;
    requires PowerPoint to be installed.

.DESCRIPTION
    pikslide runs this itself for `--pdf` (src/pikslide/render.py). It
    also runs on its own from Windows PowerShell:

        .\pptx_to_pdf.ps1 -PptxPath .\diagram.pptx -PdfPath .\diagram.pdf
#>
param(
    [Parameter(Mandatory=$true)][string]$PptxPath,
    [Parameter(Mandatory=$true)][string]$PdfPath
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
try {
    $ppSaveAsPDF = 32  # PpSaveAsFileType.ppSaveAsPDF

    $app = New-Object -ComObject PowerPoint.Application
    $pres = $app.Presentations.Open($PptxPath, $true, $true, $false)
    $pres.SaveAs($PdfPath, $ppSaveAsPDF)

    Write-Output "wrote $PdfPath"
} catch {
    Write-Error $_
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
    if ($app) {
        $app.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

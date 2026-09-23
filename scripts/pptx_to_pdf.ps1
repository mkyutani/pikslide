<#
.SYNOPSIS
    Export a .pptx file to PDF, via PowerPoint COM automation. Windows-only;
    requires PowerPoint to be installed.

.EXAMPLE
    From WSL, convert Linux paths to Windows paths with wslpath first:

        WIN_PPTX=$(wslpath -w ./examples/pipeline.pptx)
        WIN_PDF=$(wslpath -w ./examples/pipeline.pdf)
        powershell.exe -NoProfile -ExecutionPolicy Bypass \
            -File "$(wslpath -w ./scripts/pptx_to_pdf.ps1)" \
            -PptxPath "$WIN_PPTX" -PdfPath "$WIN_PDF"

.EXAMPLE
    From Windows PowerShell directly:

        .\scripts\pptx_to_pdf.ps1 -PptxPath .\examples\pipeline.pptx -PdfPath .\examples\pipeline.pdf
#>
param(
    [Parameter(Mandatory=$true)][string]$PptxPath,
    [Parameter(Mandatory=$true)][string]$PdfPath
)

# Default: a failure inside the try block below (e.g. PowerPoint isn't
# installed, so New-Object -ComObject can't find it) is a *non-terminating*
# error under -File invocation -- powershell.exe still exits 0, which would
# make a caller's own PowerPoint-vs-fallback branch (scripts/pptx_to_pdf.sh)
# never actually detect the failure (checked). -Stop plus the explicit
# `exit 1` below is what makes the exit code trustworthy.
$ErrorActionPreference = "Stop"

try {
    $ppSaveAsPDF = 32  # PpSaveAsFileType.ppSaveAsPDF

    $app = New-Object -ComObject PowerPoint.Application
    $pres = $app.Presentations.Open($PptxPath, $true, $true, $false)
    $pres.SaveAs($PdfPath, $ppSaveAsPDF)

    $pres.Close()
    $app.Quit()

    Write-Output "wrote $PdfPath"
} catch {
    Write-Error $_
    exit 1
}

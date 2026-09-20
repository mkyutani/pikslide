<#
.SYNOPSIS
    Export the first slide of a .pptx file to a PNG, via PowerPoint COM
    automation. Windows-only; requires PowerPoint to be installed.

.DESCRIPTION
    pikslide sizes its generated slide exactly to the diagram's bounding box
    (plus a small margin), so exporting the whole slide already gives an
    image of just the diagram -- no separate cropping step is needed.

.EXAMPLE
    From WSL, convert Linux paths to Windows paths with wslpath first:

        WIN_PPTX=$(wslpath -w ./examples/pipeline.pptx)
        WIN_PNG=$(wslpath -w ./examples/pipeline.png)
        powershell.exe -NoProfile -ExecutionPolicy Bypass \
            -File "$(wslpath -w ./scripts/pptx_to_png.ps1)" \
            -PptxPath "$WIN_PPTX" -PngPath "$WIN_PNG"

.EXAMPLE
    From Windows PowerShell directly:

        .\scripts\pptx_to_png.ps1 -PptxPath .\examples\pipeline.pptx -PngPath .\examples\pipeline.png
#>
param(
    [Parameter(Mandatory=$true)][string]$PptxPath,
    [Parameter(Mandatory=$true)][string]$PngPath,
    [int]$Dpi = 200
)

$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open($PptxPath, $true, $true, $false)
$slide = $pres.Slides.Item(1)

$widthIn = $pres.PageSetup.SlideWidth / 72.0
$heightIn = $pres.PageSetup.SlideHeight / 72.0
$widthPx = [int]($widthIn * $Dpi)
$heightPx = [int]($heightIn * $Dpi)

$slide.Export($PngPath, "PNG", $widthPx, $heightPx)

$pres.Close()
$app.Quit()

Write-Output "wrote $PngPath ($widthPx x $heightPx)"

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildRoot = Join-Path $Root 'build'
$LwarpDir = Join-Path $BuildRoot 'lwarp'
$PdfDir = Join-Path $BuildRoot 'pdf'
$SiteDir = Join-Path $BuildRoot 'site'

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside workspace: $pathFull"
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogPath
    )

    & $FilePath @Arguments *> $LogPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Last lines from $LogPath"
        Get-Content -LiteralPath $LogPath -Tail 100
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

foreach ($tool in @('xelatex', 'latexmk', 'lwarpmk', 'node', 'npm')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required tool not found on PATH: $tool"
    }
}

$nodeVersion = (& node -p "process.versions.node").Trim()
if ([int]($nodeVersion.Split('.')[0]) -ne 24) {
    throw "Node.js 24 is required; found $nodeVersion"
}

New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
foreach ($dir in @($LwarpDir, $PdfDir, $SiteDir)) {
    Assert-ChildPath -Path $dir -Parent $Root
    if (Test-Path -LiteralPath $dir) {
        Remove-Item -LiteralPath $dir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $Root 'main-web.tex') -Destination $LwarpDir
Copy-Item -LiteralPath (Join-Path $Root 'tex') -Destination (Join-Path $LwarpDir 'tex') -Recurse
Push-Location $LwarpDir
try {
    Invoke-Checked -FilePath 'xelatex' -Arguments @('-interaction=nonstopmode', '-halt-on-error', 'main-web.tex') -LogPath (Join-Path $LwarpDir 'build-xelatex.log')
    Invoke-Checked -FilePath 'lwarpmk' -Arguments @('html') -LogPath (Join-Path $LwarpDir 'build-lwarpmk.log')
}
finally {
    Pop-Location
}

Copy-Item -LiteralPath (Join-Path $Root 'main.tex') -Destination $PdfDir
Copy-Item -LiteralPath (Join-Path $Root 'tex') -Destination (Join-Path $PdfDir 'tex') -Recurse
Push-Location $PdfDir
try {
    Invoke-Checked -FilePath 'latexmk' -Arguments @('-xelatex', '-interaction=nonstopmode', '-halt-on-error', 'main.tex') -LogPath (Join-Path $PdfDir 'build-pdf.log')
}
finally {
    Pop-Location
}

$pdfPath = Join-Path $PdfDir 'main.pdf'
if (-not (Test-Path -LiteralPath $pdfPath)) {
    throw "Expected PDF was not generated: $pdfPath"
}

Invoke-Checked -FilePath 'node' -Arguments @(
    (Join-Path $Root 'scripts\postprocess_web.mjs'),
    $LwarpDir,
    $SiteDir,
    $pdfPath
) -LogPath (Join-Path $BuildRoot 'postprocess-web.log')

Invoke-Checked -FilePath 'npm' -Arguments @('run', 'test:static', '--silent') -LogPath (Join-Path $BuildRoot 'test-static.log')

Write-Host 'LaTeX reader built successfully:'
Write-Host "  Publish root: $SiteDir"
Write-Host "  Math site:    $(Join-Path $SiteDir 'math')"
Write-Host "  PDF:          $(Join-Path $SiteDir 'math\downloads\kaoyan-math1-notes.pdf')"
Write-Host '  Pages: 53 HTML documents'

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildRoot = Join-Path $Root 'build'
$LwarpDir = Join-Path $BuildRoot 'lwarp'
$SiteDir = Join-Path $BuildRoot 'site'

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $parentFull = [System.IO.Path]::GetFullPath($Parent)
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
        Get-Content -LiteralPath $LogPath -Tail 80
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

foreach ($tool in @('xelatex', 'lwarpmk')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required tool not found on PATH: $tool"
    }
}

New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
foreach ($dir in @($LwarpDir, $SiteDir)) {
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
    Invoke-Checked -FilePath 'xelatex' -Arguments @(
        '-interaction=nonstopmode',
        '-halt-on-error',
        'main-web.tex'
    ) -LogPath (Join-Path $LwarpDir 'build-xelatex.log')
    Invoke-Checked -FilePath 'lwarpmk' -Arguments @('html') -LogPath (Join-Path $LwarpDir 'build-lwarpmk.log')
}
finally {
    Pop-Location
}

$staticExtensions = @('.js', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.ico', '.woff', '.woff2')

Get-ChildItem -LiteralPath $LwarpDir -Recurse -File |
    Where-Object {
        ($_.Extension -ieq '.html' -and ($_.Name -eq 'index.html' -or $_.Name -like 'note-*.html')) -or
        ($staticExtensions -contains $_.Extension.ToLowerInvariant())
    } |
    ForEach-Object {
        $relative = [System.IO.Path]::GetRelativePath($LwarpDir, $_.FullName)
        $target = Join-Path $SiteDir $relative
        $targetParent = Split-Path -Parent $target
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }

$lwarpCss = Join-Path $LwarpDir 'lwarp.css'
$overrideCss = Join-Path $Root 'web\math1-web.css'
$targetCss = Join-Path $SiteDir 'math1-web.css'
if (-not (Test-Path -LiteralPath $lwarpCss)) {
    throw "Expected lwarp CSS was not generated: $lwarpCss"
}
if (-not (Test-Path -LiteralPath $overrideCss)) {
    throw "Expected web CSS override was not found: $overrideCss"
}

$combinedCss = @(
    Get-Content -LiteralPath $lwarpCss -Raw
    "`r`n/* --- Math I overrides --- */`r`n"
    Get-Content -LiteralPath $overrideCss -Raw
) -join ''
Set-Content -LiteralPath $targetCss -Value $combinedCss -Encoding utf8NoBOM

Set-Content -LiteralPath (Join-Path $SiteDir '.assetsignore') -Encoding utf8NoBOM -Value @(
    '*.aux'
    '*.log'
    '*.out'
    '*.toc'
    '*.xdv'
    '*.pdf'
    '*.tex'
    '*.fdb_latexmk'
    '*.fls'
)

$indexPath = Join-Path $SiteDir 'index.html'
if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Expected HTML entrypoint was not generated: $indexPath"
}

$notePages = Get-ChildItem -LiteralPath $SiteDir -Filter 'note-*.html' -File
if ($notePages.Count -lt 1) {
    throw "Expected at least one split note page in $SiteDir"
}

$indexText = Get-Content -LiteralPath $indexPath -Raw
if ($indexText -notmatch 'MathJax') {
    throw "Expected MathJax configuration in generated index.html"
}

Write-Host "Web notes built successfully:"
Write-Host "  Source: $LwarpDir"
Write-Host "  Site:   $SiteDir"
Write-Host "  Pages:  $($notePages.Count + 1) HTML files"

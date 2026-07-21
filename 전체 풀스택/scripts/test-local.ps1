param([switch]$SkipCompose)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $Root
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'

if (-not (Test-Path $Python)) {
    throw "Project virtual environment is missing: $Python"
}

function Run-Pytest {
    param([string]$Component)
    Push-Location (Join-Path $Root $Component)
    try {
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "$Component tests failed" }
    } finally { Pop-Location }
}

Run-Pytest 'control-plane-drf'
Run-Pytest 'python-worker'
Run-Pytest 'agent-layer-nat'
Run-Pytest 'knowledge-service'

Get-ChildItem (Join-Path $Root 'frontend-php') -Recurse -Filter '*.php' | ForEach-Object {
    & php -l $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "PHP lint failed: $($_.FullName)" }
}

& node --check (Join-Path $Root 'frontend-php\public\assets\js\app.js')
if ($LASTEXITCODE -ne 0) { throw 'JavaScript syntax check failed' }
& node --check (Join-Path $Root 'frontend-php\public\assets\js\viewer.js')
if ($LASTEXITCODE -ne 0) { throw 'JavaScript syntax check failed' }

$RequiredViewerAssets = @(
    'frontend-php\public\assets\vendor\three\three.module.js',
    'frontend-php\public\assets\vendor\three\three.core.js',
    'frontend-php\public\assets\vendor\three\addons\controls\OrbitControls.js',
    'frontend-php\public\assets\vendor\three\addons\loaders\GLTFLoader.js',
    'frontend-php\public\assets\vendor\three\addons\utils\BufferGeometryUtils.js'
)
foreach ($Asset in $RequiredViewerAssets) {
    if (-not (Test-Path (Join-Path $Root $Asset))) {
        throw "Required Three.js viewer asset is missing: $Asset"
    }
}

if (-not $SkipCompose) {
    & docker compose --project-name xconcep -f (Join-Path $Root 'docker-compose.yml') config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose validation failed' }
}

Write-Host 'All local checks passed'

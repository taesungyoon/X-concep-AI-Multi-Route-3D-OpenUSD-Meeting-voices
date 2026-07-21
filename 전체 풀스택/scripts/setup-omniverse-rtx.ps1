param(
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runtimeDir = Join-Path $repoRoot ".omniverse-runtime"
$cacheDir = Join-Path $repoRoot ".cache"
$venvDir = Join-Path $repoRoot ".omniverse-venv"
$requirements = Join-Path $PSScriptRoot "..\omniverse-rtx\requirements.txt"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheDir "warp") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheDir "optix") | Out-Null

if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
    & $PythonLauncher "-$PythonVersion" -m venv $venvDir
}

$python = Join-Path $venvDir "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r $requirements
Write-Host "Omniverse RTX runtime installed: $venvDir"

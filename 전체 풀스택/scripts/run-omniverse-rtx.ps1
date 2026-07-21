param(
    [switch]$ValidateOnly,
    [int]$Width = 1280,
    [int]$Height = 720,
    [int]$Fps = 30,
    [int]$CudaDevice = 0,
    [int]$SignalingPort = 49100,
    [int]$HealthPort = 8011
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".omniverse-venv\Scripts\python.exe"
$runtime = (Resolve-Path (Join-Path $PSScriptRoot "..\omniverse-rtx\runtime.py")).Path
$runtimeRoot = Join-Path $repoRoot ".omniverse-runtime"
$cacheRoot = Join-Path $repoRoot ".cache"

if (-not (Test-Path $python)) {
    throw "Omniverse environment not found. Run scripts/setup-omniverse-rtx.ps1 first."
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "warp") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "optix") | Out-Null

$env:OVRTX_SKIP_USD_CHECK = "1"
$env:OVRTX_WIDTH = "$Width"
$env:OVRTX_HEIGHT = "$Height"
$env:OVRTX_FPS = "$Fps"
$env:OVRTX_CUDA_DEVICE = "$CudaDevice"
$env:OVSTREAM_SIGNALING_PORT = "$SignalingPort"
$env:OVSTREAM_PUBLIC_IP = "127.0.0.1"
$env:OVRTX_HEALTH_PORT = "$HealthPort"
$env:OPTIX_CACHE_PATH = (Join-Path $cacheRoot "optix")
$env:WARP_CACHE_PATH = (Join-Path $cacheRoot "warp")

$arguments = @($runtime)
if ($ValidateOnly) {
    $arguments += "--validate-only"
}
& $python @arguments

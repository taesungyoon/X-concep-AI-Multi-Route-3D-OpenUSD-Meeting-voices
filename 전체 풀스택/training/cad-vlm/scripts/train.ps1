param(
    [string]$Config = "configs\qwen3-vl-4b-qlora.json",
    [int]$GpuCount = 1
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$python = ".\.venv\Scripts\python.exe"
& $python scripts\train_vlm.py --config $Config --dry-run
$env:WORLD_SIZE = [string]$GpuCount
if ($GpuCount -gt 1) {
    & .\.venv\Scripts\accelerate.exe launch --num_processes $GpuCount scripts\train_vlm.py --config $Config
} else {
    & $python scripts\train_vlm.py --config $Config
}


$ErrorActionPreference = "Stop"

$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ParentRoot = Split-Path -Parent $PackageRoot
$RepoRoot = if (Test-Path (Join-Path $PackageRoot ".git")) {
    $PackageRoot
} elseif (Test-Path (Join-Path $ParentRoot ".git")) {
    $ParentRoot
} else {
    $PackageRoot
}
$SourceDir = Join-Path $RepoRoot ".triposr-src"
$VenvDir = Join-Path $RepoRoot ".triposr-venv"
$Requirements = Join-Path $PackageRoot "triposr-service\requirements.txt"
$PinnedCommit = "107cefdc244c39106fa830359024f6a2f1c78871"

if (-not (Test-Path $SourceDir)) {
    git clone https://github.com/VAST-AI-Research/TripoSR.git $SourceDir
}
git -C $SourceDir fetch --depth 1 origin $PinnedCommit
git -C $SourceDir checkout --detach $PinnedCommit

if (-not (Test-Path $VenvDir)) {
    py -3.12 -m venv $VenvDir
}
$Python = Join-Path $VenvDir "Scripts\python.exe"
& $Python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu129
& $Python -m pip install -r $Requirements
& $Python -m pytest (Join-Path $PackageRoot "triposr-service\test_compat.py") -q

Write-Host "TripoSR setup complete. Run scripts/run-triposr.ps1 next."

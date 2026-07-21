param(
    [int]$Port = 8081,
    [int]$DurationSeconds = 0
)

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
$Python = Join-Path $RepoRoot ".triposr-venv\Scripts\python.exe"
$ServiceDir = Join-Path $PackageRoot "triposr-service"

if (-not (Test-Path $Python)) {
    throw "TripoSR environment is missing. Run scripts/setup-triposr.ps1 first."
}

$env:TRIPOSR_SOURCE = Join-Path $RepoRoot ".triposr-src"
$env:HF_HOME = Join-Path $RepoRoot ".triposr-runtime\huggingface"
$env:U2NET_HOME = Join-Path $RepoRoot ".triposr-runtime\rembg"
$env:TRIPOSR_DEVICE = if ($env:TRIPOSR_DEVICE) { $env:TRIPOSR_DEVICE } else { "cuda:0" }
$env:TRIPOSR_MC_RESOLUTION = if ($env:TRIPOSR_MC_RESOLUTION) { $env:TRIPOSR_MC_RESOLUTION } else { "256" }
New-Item -ItemType Directory -Force $env:HF_HOME, $env:U2NET_HOME | Out-Null

$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "TripoSR is already listening at http://127.0.0.1:$Port (PID $($existing.OwningProcess))"
    exit 0
}

$processPath = $env:Path
[Environment]::SetEnvironmentVariable("PATH", $null, "Process")
[Environment]::SetEnvironmentVariable("Path", $processPath, "Process")
$RuntimeDir = Join-Path $RepoRoot ".triposr-runtime"
New-Item -ItemType Directory -Force $RuntimeDir | Out-Null
$process = Start-Process -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $ServiceDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RuntimeDir "server-out.log") `
    -RedirectStandardError (Join-Path $RuntimeDir "server-err.log")
try {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null
            $ready = $true
        } catch {}
    } while (-not $ready -and (Get-Date) -lt $deadline -and -not $process.HasExited)
    if (-not $ready) { throw "TripoSR did not become ready. Check $RuntimeDir\server-err.log" }
    Write-Host "TripoSR is ready: http://127.0.0.1:$Port"
    $stopAt = if ($DurationSeconds -gt 0) { (Get-Date).AddSeconds($DurationSeconds) } else { $null }
    while (-not $stopAt -or (Get-Date) -lt $stopAt) {
        if ($process.HasExited) { throw "TripoSR exited unexpectedly" }
        Start-Sleep -Seconds 2
    }
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "TripoSR stopped"
}

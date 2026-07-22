param(
    [string]$Python = (Join-Path $env:USERPROFILE 'Documents\ComfyUI\.venv\Scripts\python.exe'),
    [int]$Port = 8191,
    [int]$DurationSeconds = 0
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Script = Join-Path $Root 'scripts\run-image-semantic-verifier.py'
$LogDir = Join-Path $Root 'storage\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not (Test-Path -LiteralPath $Python)) { throw "Verifier Python is missing: $Python" }

try {
    Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 | Out-Null
    Write-Host "Semantic verifier is already ready at http://127.0.0.1:$Port"
    exit 0
} catch {}

$processPath = $env:Path
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', $processPath, 'Process')
$process = Start-Process -FilePath $Python -ArgumentList @(
    ('"' + $Script + '"'), '--host', '127.0.0.1', '--port', "$Port", '--offline'
) -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $LogDir 'image-semantic-verifier.out.log') `
  -RedirectStandardError (Join-Path $LogDir 'image-semantic-verifier.err.log') -WindowStyle Hidden -PassThru
try {
    $deadline = (Get-Date).AddSeconds(180)
    do {
        Start-Sleep -Seconds 2
        try {
            Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5 | Out-Null
            $ready = $true
        } catch {}
    } while (-not $ready -and (Get-Date) -lt $deadline -and -not $process.HasExited)
    if (-not $ready) { throw "Semantic verifier did not become ready. Check $LogDir\image-semantic-verifier.err.log" }
    Write-Host "Semantic verifier ready: http://127.0.0.1:$Port"
    $stopAt = if ($DurationSeconds -gt 0) { (Get-Date).AddSeconds($DurationSeconds) } else { $null }
    while (-not $stopAt -or (Get-Date) -lt $stopAt) {
        if ($process.HasExited) { throw 'Semantic verifier exited unexpectedly' }
        Start-Sleep -Seconds 2
    }
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    Write-Host 'Semantic verifier stopped'
}

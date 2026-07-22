param(
    [string]$ComfyRoot = (Join-Path $env:USERPROFILE 'Documents\ComfyUI'),
    [int]$Port = 8188,
    [int]$DurationSeconds = 0,
    [ValidateSet('high','normal','low')][string]$VramMode = 'high',
    [int]$HealthCheckSeconds = 15,
    [int]$HealthFailureLimit = 4
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Storage = Join-Path $Root 'storage'
$Runtime = Join-Path $Storage 'comfyui-runtime'
$LogDir = Join-Path $Storage 'logs'
$Python = Join-Path $ComfyRoot '.venv\Scripts\python.exe'
$Source = Join-Path $env:LOCALAPPDATA 'Programs\ComfyUI\resources\ComfyUI'
$Main = Join-Path $Source 'main.py'
$Frontend = Join-Path $Source 'web_custom_versions\desktop_app'

foreach ($required in @($Python, $Main, (Join-Path $ComfyRoot 'models\diffusion_models\flux-2-klein-base-4b-fp8.safetensors'), (Join-Path $ComfyRoot 'models\text_encoders\qwen_3_4b.safetensors'), (Join-Path $ComfyRoot 'models\vae\flux2-vae.safetensors'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "ComfyUI runtime file is missing: $required" }
}

try {
    Invoke-RestMethod "http://127.0.0.1:$Port/system_stats" -TimeoutSec 3 | Out-Null
    Write-Host "ComfyUI is already ready at http://127.0.0.1:$Port"
    exit 0
} catch {}
$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) { throw "Port $Port is occupied by a non-ComfyUI process (PID $($existing.OwningProcess))" }

$processPath = $env:Path
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', $processPath, 'Process')

$Output = Join-Path $Runtime 'output'
$Input = Join-Path $Runtime 'input'
$Temp = Join-Path $Runtime 'temp'
$User = Join-Path $Runtime 'user'
New-Item -ItemType Directory -Force -Path $Output, $Input, $Temp, $User, $LogDir | Out-Null
function Quote-Argument([string]$Value) { return '"' + $Value + '"' }
$VramArgument = switch ($VramMode) { 'normal' { '--normalvram' } 'low' { '--lowvram' } default { '--highvram' } }
$Arguments = @(
    (Quote-Argument $Main),
    '--base-directory', (Quote-Argument $ComfyRoot),
    '--output-directory', (Quote-Argument $Output),
    '--input-directory', (Quote-Argument $Input),
    '--temp-directory', (Quote-Argument $Temp),
    '--user-directory', (Quote-Argument $User),
    '--listen', '127.0.0.1', '--port', "$Port",
    '--disable-auto-launch', '--disable-all-custom-nodes', $VramArgument,
    '--front-end-root', (Quote-Argument $Frontend)
)

$process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $Source `
    -RedirectStandardOutput (Join-Path $LogDir 'comfyui.out.log') `
    -RedirectStandardError (Join-Path $LogDir 'comfyui.err.log') -WindowStyle Hidden -PassThru
try {
    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 1
        try {
            Invoke-RestMethod "http://127.0.0.1:$Port/system_stats" -TimeoutSec 3 | Out-Null
            $ready = $true
        } catch {}
    } while (-not $ready -and (Get-Date) -lt $deadline -and -not $process.HasExited)
    if (-not $ready) { throw "ComfyUI did not become ready. Check $LogDir\comfyui.err.log" }
    Write-Host "ComfyUI FLUX.2 is ready: http://127.0.0.1:$Port"
    Write-Host 'Stop: Ctrl+C'
    $stopAt = if ($DurationSeconds -gt 0) { (Get-Date).AddSeconds($DurationSeconds) } else { $null }
    $nextHealthCheck = (Get-Date).AddSeconds($HealthCheckSeconds)
    $healthFailures = 0
    while (-not $stopAt -or (Get-Date) -lt $stopAt) {
        if ($process.HasExited) { throw 'ComfyUI exited unexpectedly' }
        if ((Get-Date) -ge $nextHealthCheck) {
            try {
                Invoke-RestMethod "http://127.0.0.1:$Port/system_stats" -TimeoutSec 5 | Out-Null
                $healthFailures = 0
            } catch {
                $healthFailures += 1
                if ($healthFailures -ge $HealthFailureLimit) { throw "ComfyUI health check failed $healthFailures consecutive times" }
            }
            $nextHealthCheck = (Get-Date).AddSeconds($HealthCheckSeconds)
        }
        Start-Sleep -Seconds 2
    }
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    Write-Host 'ComfyUI stopped'
}

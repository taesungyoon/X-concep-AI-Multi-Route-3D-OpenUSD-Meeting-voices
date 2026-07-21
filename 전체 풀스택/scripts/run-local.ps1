param(
    [ValidateSet('mock', 'ollama', 'live')]
    [string]$Profile = 'mock',
    [switch]$EnableSpeech,
    [int]$DurationSeconds = 0,
    [int]$ControlPort = 8030
)

$ErrorActionPreference = 'Stop'
# Some launchers inject both PATH and Path. Windows PowerShell's Start-Process
# rejects that duplicate environment block, so normalize it once.
$ProcessPath = $env:Path
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', $ProcessPath, 'Process')
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $Root
$Storage = Join-Path $Root 'storage'
$LogDir = Join-Path $Storage 'logs'
$LocalPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $LocalPython) { $LocalPython } else { 'python' }
$Processes = @()

function Start-ServiceProcess {
    param([string]$Name, [string]$WorkingDirectory, [string[]]$Arguments)
    $stdout = Join-Path $LogDir "$Name.out.log"
    $stderr = Join-Path $LogDir "$Name.err.log"
    $process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    $script:Processes += $process
    Write-Host "Started: $Name (PID $($process.Id))"
}

function Wait-Healthy {
    param([string]$Name, [string]$Url, [int]$Seconds = 45)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) { Write-Host "Ready: $Name"; return }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "$Name did not become healthy. Check logs in $LogDir"
}

New-Item -ItemType Directory -Force -Path (Join-Path $Storage 'projects'), $LogDir | Out-Null
$PublicStorage = Join-Path $Root 'frontend-php\public\storage'
if (-not (Test-Path $PublicStorage)) {
    New-Item -ItemType Junction -Path $PublicStorage -Target $Storage | Out-Null
}

$serviceToken = [guid]::NewGuid().ToString('N')
$env:STORAGE_PATH = $Storage
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PUBLIC_STORAGE_PREFIX = '/storage'
$env:DB_ENGINE = 'sqlite'
$env:QDRANT_URL = ':memory:'
$env:EMBED_MODE = 'hash'
$env:NEMO_RETRIEVER_MODE = 'fallback'
$env:PYTHON_WORKER_URL = 'http://127.0.0.1:8001'
$env:KNOWLEDGE_SERVICE_URL = 'http://127.0.0.1:8020'
$env:AGENT_GATEWAY_URL = 'http://127.0.0.1:8010'
$env:AGENT_RUNTIME = 'fallback'
$env:SYNC_PIPELINE = 'true'
$env:INTERNAL_API_TOKEN = $serviceToken
$env:CONTROL_PLANE_TOKEN = $serviceToken
$env:CONTROL_PLANE_URL = "http://127.0.0.1:$ControlPort"
$env:DJANGO_DEBUG = 'true'

if ($Profile -eq 'mock') {
    $env:PIPELINE_MODE = 'mock'
    $env:LLM_MODE = 'mock'
    $env:OPENAI_IMAGE_MODE = 'mock'
    $env:SHAPE_MODE = 'mock'
    $env:SHAPE_PROVIDER = 'triposr'
    $env:SPEECH_MODE = 'mock'
    $env:OPENSCAD_MODE = 'mock'
    $env:BLENDER_MODE = 'mock'
} elseif ($Profile -eq 'ollama') {
    $env:PIPELINE_MODE = 'local'
    $env:LLM_MODE = 'openai_compatible'
    $env:VLLM_BASE_URL = 'http://127.0.0.1:11434/v1'
    $env:VLLM_API_KEY = 'ollama'
    $env:GEMMA_MODEL_NAME = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { 'qwen3:14b' }
    $env:OPENAI_IMAGE_MODE = 'comfyui'
    $env:COMFYUI_BASE_URL = if ($env:COMFYUI_BASE_URL) { $env:COMFYUI_BASE_URL } else { 'http://127.0.0.1:8188' }
    $env:SHAPE_MODE = 'mock'
    $env:SHAPE_PROVIDER = 'triposr'
    $env:SPEECH_MODE = 'mock'
    $env:OPENSCAD_MODE = 'auto'
    $env:BLENDER_MODE = 'auto'
}

if ($EnableSpeech) {
    $env:SPEECH_MODE = 'faster_whisper'
    $env:WHISPER_MODEL = if ($env:WHISPER_MODEL) { $env:WHISPER_MODEL } else { 'large-v3-turbo' }
    $env:WHISPER_MODEL_CACHE = Join-Path $Storage 'models\whisper'
    $env:WHISPER_DEVICE = if ($env:WHISPER_DEVICE) { $env:WHISPER_DEVICE } else { 'auto' }
    $env:WHISPER_COMPUTE_TYPE = if ($env:WHISPER_COMPUTE_TYPE) { $env:WHISPER_COMPUTE_TYPE } else { 'auto' }
}

try {
    Push-Location (Join-Path $Root 'control-plane-drf')
    & $Python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Django migration failed' }
    Pop-Location

    Start-ServiceProcess 'knowledge' (Join-Path $Root 'knowledge-service') @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8020')
    Wait-Healthy 'Knowledge' 'http://127.0.0.1:8020/health'
    Start-ServiceProcess 'worker' (Join-Path $Root 'python-worker') @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001')
    Wait-Healthy 'Worker' 'http://127.0.0.1:8001/health'
    Start-ServiceProcess 'agent' (Join-Path $Root 'agent-layer-nat') @('-m','uvicorn','gateway:app','--host','127.0.0.1','--port','8010')
    Wait-Healthy 'Agent' 'http://127.0.0.1:8010/health'
    Start-ServiceProcess 'control-plane' (Join-Path $Root 'control-plane-drf') @('manage.py','runserver',"127.0.0.1:$ControlPort",'--noreload')
    Wait-Healthy 'Control Plane' "http://127.0.0.1:$ControlPort/health"

    $phpOut = Join-Path $LogDir 'web.out.log'
    $phpErr = Join-Path $LogDir 'web.err.log'
    $web = Start-Process -FilePath 'php' -ArgumentList @('-d','max_execution_time=0','-d','default_socket_timeout=7200','-S','127.0.0.1:8080','-t','frontend-php/public','frontend-php/public/router.php') `
        -WorkingDirectory $Root -RedirectStandardOutput $phpOut -RedirectStandardError $phpErr -WindowStyle Hidden -PassThru
    $Processes += $web
    Wait-Healthy 'Web' 'http://127.0.0.1:8080/health'

    Write-Host ""
    Write-Host "Xconcep local $Profile profile is running"
    Write-Host 'UI: http://127.0.0.1:8080'
    Write-Host 'Status: http://127.0.0.1:8080/api/system-status'
    Write-Host 'Stop: Ctrl+C'
    $stopAt = if ($DurationSeconds -gt 0) { (Get-Date).AddSeconds($DurationSeconds) } else { $null }
    while (-not $stopAt -or (Get-Date) -lt $stopAt) {
        foreach ($process in $Processes) {
            if ($process.HasExited) { throw "PID $($process.Id) exited unexpectedly" }
        }
        Start-Sleep -Seconds 2
    }
} finally {
    foreach ($process in $Processes) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    Write-Host 'Local services stopped'
}

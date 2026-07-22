param(
    [string]$ComfyRoot = (Join-Path $env:USERPROFILE 'Documents\ComfyUI'),
    [int]$Port = 8188,
    [int]$DurationSeconds = 0,
    [int]$MaxRestarts = 2
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $Root 'scripts\run-comfyui.ps1'
$LogDir = Join-Path $Root 'storage\logs'
$StatePath = Join-Path $LogDir 'comfyui-supervisor-state.json'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$startedAt = Get-Date
$restartCount = 0
$vramMode = 'high'

function Write-State([string]$Status, [string]$Reason = '') {
    @{
        status = $Status
        reason = $Reason
        restart_count = $restartCount
        vram_mode = $vramMode
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

while ($true) {
    $remaining = if ($DurationSeconds -gt 0) { [Math]::Max(1, $DurationSeconds - [int]((Get-Date) - $startedAt).TotalSeconds) } else { 0 }
    Write-State 'starting'
    try {
        & $Runner -ComfyRoot $ComfyRoot -Port $Port -DurationSeconds $remaining -VramMode $vramMode
        Write-State 'completed'
        break
    } catch {
        $reason = $_.Exception.Message
        $errorLog = Join-Path $LogDir 'comfyui.err.log'
        if (Test-Path -LiteralPath $errorLog) {
            $tail = (Get-Content -LiteralPath $errorLog -Tail 200 -ErrorAction SilentlyContinue) -join "`n"
            if ($tail -match '(?i)out of memory|cuda.*alloc') { $vramMode = 'normal' }
        }
        Write-State 'recovering' $reason
        if ($restartCount -ge $MaxRestarts) { Write-State 'failed' $reason; throw }
        $restartCount += 1
        Start-Sleep -Seconds ([Math]::Min(5 * $restartCount, 15))
    }
}

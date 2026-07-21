param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$Username = "",
    [string]$Prompt = "external integration acceptance test for an industrial inspection module",
    [switch]$ConfirmExternal,
    [switch]$ConfirmPaidImage
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmExternal) {
    throw "External DB/API smoke test is blocked. Re-run with -ConfirmExternal only after the user has approved live testing."
}

function Invoke-Api([string]$Method, [string]$Path, [hashtable]$Body = $null, [hashtable]$Headers = @{}) {
    $parameters = @{
        Method = $Method
        Uri = "$($BaseUrl.TrimEnd('/'))$Path"
        Headers = $Headers
        TimeoutSec = 7200
    }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json; charset=utf-8"
        $parameters.Body = $Body | ConvertTo-Json -Depth 20
    }
    Invoke-RestMethod @parameters
}

function Wait-Project([hashtable]$Headers, [object]$Initial) {
    if (-not $Initial.job.id) { return $Initial.project }
    $deadline = (Get-Date).AddHours(2)
    while ((Get-Date) -lt $deadline) {
        $job = (Invoke-Api "Get" "/api/jobs/$($Initial.job.id)" $null $Headers).job
        if ($job.status -eq "failed") { throw "Generation job failed: $($job.error)" }
        if ($job.status -eq "completed") {
            return (Invoke-Api "Get" "/api/projects/$($Initial.project.id)" $null $Headers).project
        }
        Start-Sleep -Seconds 2
    }
    throw "Generation job timed out."
}

$authConfig = Invoke-Api "Get" "/api/auth/config"
$headers = @{}
if ($authConfig.required) {
    if ([string]::IsNullOrWhiteSpace($Username)) {
        $Username = Read-Host "Corporate MySQL username"
    }
    $securePassword = Read-Host "Corporate MySQL password" -AsSecureString
    $credential = [PSCredential]::new($Username, $securePassword)
    $plainPassword = $credential.GetNetworkCredential().Password
    try {
        $login = Invoke-Api "Post" "/api/auth/login" @{
            username = $Username
            password = $plainPassword
        }
    } finally {
        $plainPassword = $null
        $credential = $null
        $securePassword = $null
    }
    $headers.Authorization = "Bearer $($login.token)"
}

$status = Invoke-Api "Get" "/api/system-status" $null $headers
$imageMode = $status.worker.image.mode
$authStatus = $status.worker.authentication
if ($imageMode -eq "openai" -and -not $ConfirmPaidImage) {
    throw "OpenAI image generation is paid and blocked. Re-run with -ConfirmPaidImage after explicit user approval."
}
if ($imageMode -notin @("comfyui", "openai")) {
    throw "Live image provider is not active: $imageMode"
}
if ($authStatus.required -and -not $authStatus.database_connected) {
    throw "Authentication database is not connected."
}

$created = Invoke-Api "Post" "/api/projects" @{
    prompt = $Prompt
    category = "module"
    output_goal = "fast"
    quality_profile = "preview"
} $headers
$project = Wait-Project $headers $created

if ($project.status -ne "2d_ready") { throw "2D generation did not complete." }
if ($project.results_2d.Count -ne 4) { throw "Expected four accepted 2D concepts." }

[ordered]@{
    status = "pass"
    external_confirmation = $true
    paid_image_confirmation = [bool]$ConfirmPaidImage
    auth_mode = $authStatus.mode
    authentication_database_connected = $authStatus.database_connected
    image_provider = $imageMode
    image_model = $status.worker.image.model
    project_id = $project.id
    accepted_concepts = $project.results_2d.Count
    secrets_printed = $false
} | ConvertTo-Json -Depth 8

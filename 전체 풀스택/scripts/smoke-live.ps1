param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    # Keep the script-file default ASCII-safe for Windows PowerShell 5.1, which
    # otherwise decodes UTF-8-without-BOM source literals through the ANSI page.
    [string]$Prompt = "Compact industrial vision inspection module with a curved safety cover and ergonomic handle",
    [ValidateSet("hunyuan3d", "openscad", "blender", "hybrid")]
    [string]$EngineOverride = "hunyuan3d",
    [string]$Username = "",
    [string]$EnvFile = "$PSScriptRoot\..\.env",
    [switch]$RequireQualityTarget
)

$ErrorActionPreference = "Stop"

# Live smoke workflow:
# health/config -> internal-DB login -> ComfyUI four-view generation
# -> selected concept -> TripoSR GLB generation -> binary download validation.
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Read-DotEnvValue([string]$Name) {
    if (-not (Test-Path -LiteralPath $EnvFile)) { return "" }
    $line = Get-Content -LiteralPath $EnvFile -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) { return "" }
    $value = ($line -split "=", 2)[1].Trim()
    if ($value.Length -ge 2 -and (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    )) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Invoke-Api(
    [string]$Method,
    [string]$Path,
    [hashtable]$Body = $null,
    [hashtable]$Headers = @{}
) {
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
    return Invoke-RestMethod @parameters
}

function Wait-Project([hashtable]$Headers, [object]$Initial) {
    # Synchronous deployments return the completed project directly; Celery
    # deployments return HTTP 202 plus a job that must be polled.
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

$web = Invoke-Api "Get" "/health"
Assert-True ($web.status -eq "ok") "Web health check failed"

$headers = @{}
$authConfig = Invoke-Api "Get" "/api/auth/config"
if ($authConfig.required) {
    if ([string]::IsNullOrWhiteSpace($Username)) {
        $Username = Read-DotEnvValue "INTERNAL_AUTH_USERNAME"
    }
    $plainPassword = Read-DotEnvValue "INTERNAL_AUTH_PASSWORD"
    if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($plainPassword)) {
        throw "Internal DB credentials are missing. Set INTERNAL_AUTH_USERNAME and INTERNAL_AUTH_PASSWORD in the git-ignored .env file."
    }
    try {
        $login = Invoke-Api "Post" "/api/auth/login" @{
            username = $Username
            password = $plainPassword
        }
    } finally {
        # Avoid retaining or printing the plaintext secret after authentication.
        $plainPassword = $null
    }
    $headers.Authorization = "Bearer $($login.token)"
}

$status = Invoke-Api "Get" "/api/system-status" $null $headers
$worker = $status.worker
Assert-True ($worker.runtime_ready -eq $true) "Worker is not live-ready: $($worker | ConvertTo-Json -Depth 8 -Compress)"
Assert-True ($worker.image.mode -eq "comfyui") "ComfyUI is not the active 2D provider"
Assert-True ($worker.image.connected -eq $true) "ComfyUI is not connected"
Assert-True ($worker.image_to_3d.provider -eq "triposr") "TripoSR is not the active image-to-3D provider"
Assert-True ($worker.image_to_3d.connected -eq $true) "TripoSR is not connected"

$created = Invoke-Api "Post" "/api/projects" @{
    prompt = $Prompt
    category = "module"
    output_goal = "fast"
    quality_profile = "preview"
} $headers
$project = Wait-Project $headers $created
Assert-True ($project.status -eq "2d_ready") "2D project did not complete"
Assert-True ($project.results_2d.Count -eq 4) "Expected four 2D concepts"
# Prefer the alignment preflight recommendation. Falling back to the first
# concept keeps compatibility with older workers that do not return metadata.
$concept = $project.results_2d |
    Where-Object { $_.metadata.recommended_for_3d -eq $true } |
    Select-Object -First 1
if (-not $concept -and $project.pipeline.concept_alignment.recommended_concept_id) {
    $recommendedId = $project.pipeline.concept_alignment.recommended_concept_id
    $concept = $project.results_2d |
        Where-Object { $_.id -eq $recommendedId } |
        Select-Object -First 1
}
if (-not $concept) { $concept = $project.results_2d[0] }

$generated = Invoke-Api "Post" "/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = "fast"
    quality_profile = "preview"
    engine_override = $EngineOverride
} $headers
$project3d = Wait-Project $headers $generated
$result = $project3d.result_3d
Assert-True ($project3d.status -eq "completed") "3D project did not complete"
Assert-True ([bool]$result.glb_url) "3D result has no GLB URL"
Assert-True ($result.provider.engine -eq "triposr") "3D result was not generated by TripoSR"
if ($RequireQualityTarget) {
    Assert-True ($result.self_feedback.passed -eq $true) (
        "Independent quality target failed: score=$($result.self_feedback.score), " +
        "target=$($result.self_feedback.target)"
    )
}

$glb = Invoke-WebRequest -UseBasicParsing -Uri "$($BaseUrl.TrimEnd('/'))$($result.glb_url)" -Headers $headers -TimeoutSec 120
$bytes = $glb.Content
if ($bytes -is [string]) { $bytes = [Text.Encoding]::ISO8859_1.GetBytes($bytes) }
Assert-True ($bytes.Length -gt 100000) "Downloaded GLB is unexpectedly small"
$header = [Text.Encoding]::ASCII.GetString($bytes[0..3])
Assert-True ($header -eq "glTF") "Downloaded asset is not a binary GLB"

[ordered]@{
    status = "pass"
    execution_profile = $worker.execution_profile
    project_id = $project.id
    concepts = $project.results_2d.Count
    selected_concept_id = $concept.id
    selected_by_alignment = [bool]$concept.metadata.recommended_for_3d
    image_provider = $worker.image.mode
    image_model = $worker.image.model
    shape_provider = $result.provider.engine
    glb_bytes = $bytes.Length
    validation_grade = $result.validation_grade
    quality_gate_passed = [bool]$result.self_feedback.passed
    quality_score = $result.self_feedback.score
    quality_target = $result.self_feedback.target
    glb_url = $result.glb_url
} | ConvertTo-Json -Depth 6

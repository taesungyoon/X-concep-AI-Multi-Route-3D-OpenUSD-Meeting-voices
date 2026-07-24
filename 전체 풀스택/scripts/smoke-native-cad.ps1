param(
    [string]$BaseUrl = 'http://127.0.0.1:8080',
    [string]$Username = '',
    [string]$EnvFile = "$PSScriptRoot\..\.env"
)

$ErrorActionPreference = 'Stop'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Read-DotEnvValue([string]$Name) {
    if (-not (Test-Path -LiteralPath $EnvFile)) { return '' }
    $line = Get-Content -LiteralPath $EnvFile -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) { return '' }
    $value = ($line -split '=', 2)[1].Trim()
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
        $parameters.ContentType = 'application/json; charset=utf-8'
        $parameters.Body = $Body | ConvertTo-Json -Depth 20
    }
    return Invoke-RestMethod @parameters
}

function Wait-Project([hashtable]$Headers, [object]$Initial) {
    if (-not $Initial.job.id) { return $Initial.project }
    $deadline = (Get-Date).AddHours(2)
    while ((Get-Date) -lt $deadline) {
        $job = (Invoke-Api 'Get' "/api/jobs/$($Initial.job.id)" $null $Headers).job
        if ($job.status -eq 'failed') { throw "Generation job failed: $($job.error)" }
        if ($job.status -eq 'completed') {
            return (Invoke-Api 'Get' "/api/projects/$($Initial.project.id)" $null $Headers).project
        }
        Start-Sleep -Seconds 2
    }
    throw 'Generation job timed out.'
}

function Assert-Glb([string]$Url) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl$Url" -Headers $headers -TimeoutSec 120
    $bytes = $response.Content
    if ($bytes -is [string]) { $bytes = [Text.Encoding]::ISO8859_1.GetBytes($bytes) }
    Assert-True ($bytes.Length -gt 500) "GLB is unexpectedly small: $Url"
    Assert-True ([Text.Encoding]::ASCII.GetString($bytes[0..3]) -eq 'glTF') "Invalid GLB header: $Url"
    return $bytes.Length
}

$headers = @{}
$authConfig = Invoke-Api 'Get' '/api/auth/config'
if ($authConfig.required) {
    if ([string]::IsNullOrWhiteSpace($Username)) {
        $Username = Read-DotEnvValue 'INTERNAL_AUTH_USERNAME'
    }
    $plainPassword = Read-DotEnvValue 'INTERNAL_AUTH_PASSWORD'
    if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($plainPassword)) {
        throw 'Internal DB credentials are missing in the git-ignored .env file.'
    }
    try {
        $login = Invoke-Api 'Post' '/api/auth/login' @{
            username = $Username
            password = $plainPassword
        }
    } finally {
        $plainPassword = $null
    }
    $headers.Authorization = "Bearer $($login.token)"
}

$status = Invoke-Api 'Get' '/api/system-status' $null $headers
Assert-True ($status.worker.openscad.available -eq $true) 'Native OpenSCAD is unavailable'
Assert-True ($status.worker.blender.available -eq $true) 'Native Blender is unavailable'

$prompt = 'Industrial vision inspection frame, width 900mm, depth 600mm, height 1200mm, with a front safety cover and work unit'
$created = Invoke-Api 'Post' '/api/projects' @{
    prompt = $prompt
    category = 'equipment'
    output_goal = 'structural'
    quality_profile = 'standard'
} $headers
$project = Wait-Project $headers $created
Assert-True ($project.status -eq '2d_ready') '2D preparation failed'
$concept = $project.results_2d[0]

$structuralResponse = Invoke-Api 'Post' "/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = 'structural'
    quality_profile = 'standard'
    engine_override = 'openscad'
} $headers
$structuralProject = Wait-Project $headers $structuralResponse
$structural = $structuralProject.result_3d
Assert-True ($structural.provider.engine -eq 'openscad') 'Structural provider is not OpenSCAD'
Assert-True ($structural.provider.mode -eq 'native') 'OpenSCAD silently used fallback'
# A native, dimension-correct asset is "structured" when the independent
# appearance gate is below its target; only appearance-approved assets are
# promoted to "validated". Both grades prove this native CAD route worked.
Assert-True ($structural.validation_grade -in @('structured', 'validated')) "Structural validation failed: $($structural.validation_grade)"
$dimensionCheck = $structural.validation.checks | Where-Object id -eq 'dimension_contract'
Assert-True ($dimensionCheck.passed -eq $true) 'Structural dimension contract failed'
$structuralBytes = Assert-Glb $structural.glb_url

$blenderResponse = Invoke-Api 'Post' "/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = 'high_quality'
    quality_profile = 'final'
    engine_override = 'blender'
} $headers
$blenderProject = Wait-Project $headers $blenderResponse
$blender = $blenderProject.result_3d
Assert-True ($blender.active_asset -eq 'high_quality') 'Blender asset is not active'
Assert-True ($blender.provider.engine -eq 'blender') 'High-quality provider is not Blender'
Assert-True ($blender.provider.mode -eq 'native') 'Blender silently used fallback'
Assert-True ([bool]$blender.assets.high_quality.blend_url) 'Editable .blend output is missing'
Assert-True ([bool]$blender.assets.high_quality.material_manifest_url) 'Material manifest is missing'
Assert-True ([bool]$blender.openusd_root_url) 'Layered OpenUSD package is missing'
$blenderBytes = Assert-Glb $blender.glb_url

[ordered]@{
    status = 'pass'
    project_id = $project.id
    openscad = [ordered]@{
        mode = $structural.provider.mode
        duration_seconds = $structural.provider.duration_seconds
        validation_grade = $structural.validation_grade
        max_dimension_error_pct = ($dimensionCheck.value.error_pct | Measure-Object -Maximum).Maximum
        glb_bytes = $structuralBytes
    }
    blender = [ordered]@{
        mode = $blender.provider.mode
        duration_seconds = $blender.provider.duration_seconds
        validation_grade = $blender.validation_grade
        glb_bytes = $blenderBytes
        blend_url = $blender.assets.high_quality.blend_url
        openusd_root_url = $blender.openusd_root_url
    }
} | ConvertTo-Json -Depth 8

param([string]$BaseUrl = 'http://127.0.0.1:8080')

$ErrorActionPreference = 'Stop'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Post-Json([string]$Uri, [hashtable]$Body) {
    Invoke-RestMethod -Method Post -Uri $Uri -ContentType 'application/json; charset=utf-8' `
        -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec 7200
}

function Assert-Glb([string]$Url) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl$Url" -TimeoutSec 120
    $bytes = $response.Content
    if ($bytes -is [string]) { $bytes = [Text.Encoding]::ISO8859_1.GetBytes($bytes) }
    Assert-True ($bytes.Length -gt 500) "GLB is unexpectedly small: $Url"
    Assert-True ([Text.Encoding]::ASCII.GetString($bytes[0..3]) -eq 'glTF') "Invalid GLB header: $Url"
    return $bytes.Length
}

$status = Invoke-RestMethod "$BaseUrl/api/system-status" -TimeoutSec 30
Assert-True ($status.worker.openscad.available -eq $true) 'Native OpenSCAD is unavailable'
Assert-True ($status.worker.blender.available -eq $true) 'Native Blender is unavailable'

$prompt = 'Industrial vision inspection frame, width 900mm, depth 600mm, height 1200mm, with a front safety cover and work unit'
$created = Post-Json "$BaseUrl/api/projects" @{
    prompt = $prompt
    category = 'equipment'
    output_goal = 'structural'
    quality_profile = 'standard'
}
$project = $created.project
Assert-True ($project.status -eq '2d_ready') 'Mock 2D preparation failed'
$concept = $project.results_2d[0]

$structuralResponse = Post-Json "$BaseUrl/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = 'structural'
    quality_profile = 'standard'
    engine_override = 'openscad'
}
$structural = $structuralResponse.project.result_3d
Assert-True ($structural.provider.engine -eq 'openscad') 'Structural provider is not OpenSCAD'
Assert-True ($structural.provider.mode -eq 'native') 'OpenSCAD silently used fallback'
Assert-True ($structural.validation_grade -eq 'validated') "Structural validation failed: $($structural.validation_grade)"
$dimensionCheck = $structural.validation.checks | Where-Object id -eq 'dimension_contract'
Assert-True ($dimensionCheck.passed -eq $true) 'Structural dimension contract failed'
$structuralBytes = Assert-Glb $structural.glb_url

$blenderResponse = Post-Json "$BaseUrl/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = 'high_quality'
    quality_profile = 'final'
    engine_override = 'blender'
}
$blender = $blenderResponse.project.result_3d
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

param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$FixtureDir = "$PSScriptRoot\..\storage\e2e-audio\korean-industrial-meeting",
    [string]$Username = "",
    [string]$EnvFile = "$PSScriptRoot\..\.env",
    [switch]$RequireQualityTarget
)

$ErrorActionPreference = "Stop"

# Meeting E2E:
# authenticate -> create meeting -> upload real WAV chunks -> local ASR
# -> requirement analysis -> ComfyUI concepts -> parametric OpenSCAD 3D
# -> artifact and independent-quality evidence.
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

function Invoke-AudioUpload(
    [string]$ProjectId,
    [string]$AudioPath,
    [int]$ChunkIndex,
    [string]$Token
) {
    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromMinutes(20)
    $client.DefaultRequestHeaders.Authorization =
        [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $Token)
    $content = [System.Net.Http.MultipartFormDataContent]::new()
    $stream = $null
    $fileContent = $null
    try {
        $content.Add(
            [System.Net.Http.StringContent]::new([string]$ChunkIndex),
            "chunk_index"
        )
        $stream = [System.IO.File]::OpenRead($AudioPath)
        $fileContent = [System.Net.Http.StreamContent]::new($stream)
        $extension = [System.IO.Path]::GetExtension($AudioPath).ToLowerInvariant()
        $mediaType = if ($extension -eq ".mp3") { "audio/mpeg" } else { "audio/wav" }
        $fileContent.Headers.ContentType =
            [System.Net.Http.Headers.MediaTypeHeaderValue]::new($mediaType)
        $content.Add($fileContent, "audio", [System.IO.Path]::GetFileName($AudioPath))
        $uri = "$($BaseUrl.TrimEnd('/'))/api/projects/$ProjectId/meeting/chunks"
        $response = $client.PostAsync($uri, $content).GetAwaiter().GetResult()
        $json = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Audio upload/transcription failed ($([int]$response.StatusCode)): $json"
        }
        return $json | ConvertFrom-Json
    } finally {
        if ($fileContent) { $fileContent.Dispose() }
        if ($stream) { $stream.Dispose() }
        $content.Dispose()
        $client.Dispose()
    }
}

$manifestPath = Join-Path $FixtureDir "manifest.json"
Assert-True (Test-Path -LiteralPath $manifestPath) "Fixture manifest is missing: $manifestPath"
$manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
$audioFiles = @($manifest.fixtures | ForEach-Object { Join-Path $FixtureDir $_.file })
Assert-True ($audioFiles.Count -ge 3) "At least three meeting fixtures are required"
foreach ($path in $audioFiles) {
    Assert-True (Test-Path -LiteralPath $path) "Audio fixture is missing: $path"
}

$authConfig = Invoke-Api "Get" "/api/auth/config"
$headers = @{}
$token = ""
if ($authConfig.required) {
    if ([string]::IsNullOrWhiteSpace($Username)) {
        $Username = Read-DotEnvValue "INTERNAL_AUTH_USERNAME"
    }
    $plainPassword = Read-DotEnvValue "INTERNAL_AUTH_PASSWORD"
    Assert-True (
        -not [string]::IsNullOrWhiteSpace($Username) -and
        -not [string]::IsNullOrWhiteSpace($plainPassword)
    ) "Internal DB credentials are missing from the git-ignored .env file"
    try {
        $login = Invoke-Api "Post" "/api/auth/login" @{
            username = $Username
            password = $plainPassword
        }
    } finally {
        $plainPassword = $null
    }
    $token = $login.token
    $headers.Authorization = "Bearer $token"
}

$status = Invoke-Api "Get" "/api/system-status" $null $headers
Assert-True ($status.worker.speech.connected -eq $true) "Local speech provider is not connected"
Assert-True ($status.worker.image.connected -eq $true) "ComfyUI is not connected"
Assert-True ($status.worker.openscad.available -eq $true) "OpenSCAD is not available"

$created = Invoke-Api "Post" "/api/meetings" @{
    category = "equipment"
    output_goal = "structural"
    quality_profile = "standard"
} $headers
$project = $created.project

$chunkProviders = @()
for ($index = 0; $index -lt $audioFiles.Count; $index++) {
    $uploaded = Invoke-AudioUpload $project.id $audioFiles[$index] $index $token
    $project = $uploaded.project
    $chunkProviders += $uploaded.chunk.provider
}
Assert-True ($project.meeting.chunk_count -eq $audioFiles.Count) "Not all audio chunks were persisted"
Assert-True ($project.meeting.transcript.Length -ge 20) "ASR transcript is unexpectedly short"
Assert-True (($chunkProviders | Where-Object { $_ -match "faster-whisper" }).Count -eq $audioFiles.Count) (
    "Unexpected speech provider(s): $($chunkProviders -join ', ')"
)

$matchedKeywords = @($manifest.expected_keywords | Where-Object {
    $project.meeting.transcript.Contains([string]$_)
})
$keywordRecall = [math]::Round($matchedKeywords.Count / $manifest.expected_keywords.Count, 4)
Assert-True ($keywordRecall -ge 0.75) (
    "ASR keyword recall is below 75%: $keywordRecall; transcript=$($project.meeting.transcript)"
)

$analyzed = Invoke-Api "Post" "/api/projects/$($project.id)/meeting/analyze" @{
    transcript = $project.meeting.transcript
} $headers
$project = $analyzed.project
Assert-True ($project.meeting.status -eq "analyzed") "Meeting requirements were not analyzed"
Assert-True ([bool]$project.meeting.analysis.generation_prompt) "Meeting generation prompt is missing"
Assert-True (
    $null -ne $project.meeting.analysis.dimensions.width_mm -and
    $null -ne $project.meeting.analysis.dimensions.depth_mm -and
    $null -ne $project.meeting.analysis.dimensions.height_mm
) "Meeting analysis did not recover width/depth/height"

$generated2d = Invoke-Api "Post" "/api/projects/$($project.id)/meeting/generate-2d" @{} $headers
$project = Wait-Project $headers $generated2d
Assert-True ($project.status -eq "2d_ready") "Meeting 2D generation did not complete"
Assert-True ($project.results_2d.Count -eq 4) "Expected four meeting-derived concepts"

$concept = $project.results_2d |
    Where-Object { $_.metadata.recommended_for_3d -eq $true } |
    Select-Object -First 1
if (-not $concept) { $concept = $project.results_2d[0] }

$generated3d = Invoke-Api "Post" "/api/projects/$($project.id)/generate-3d" @{
    selected_2d_id = $concept.id
    output_goal = "structural"
    quality_profile = "standard"
    engine_override = "openscad_equipment"
} $headers
$project = Wait-Project $headers $generated3d
$result = $project.result_3d
Assert-True ($project.status -eq "completed") "Meeting-derived 3D generation did not complete"
Assert-True ($result.generator_mode -eq "openscad_equipment") "Specialized equipment generator was not used"
Assert-True ([bool]$result.glb_url) "Meeting-derived result has no GLB"
if ($RequireQualityTarget) {
    Assert-True ($result.self_feedback.passed -eq $true) (
        "Independent quality target failed: score=$($result.self_feedback.score), " +
        "target=$($result.self_feedback.target)"
    )
}

$glb = Invoke-WebRequest -UseBasicParsing `
    -Uri "$($BaseUrl.TrimEnd('/'))$($result.glb_url)" -Headers $headers -TimeoutSec 120
$bytes = $glb.Content
if ($bytes -is [string]) { $bytes = [Text.Encoding]::ISO8859_1.GetBytes($bytes) }
Assert-True ($bytes.Length -gt 10000) "Meeting-derived GLB is unexpectedly small"
Assert-True ([Text.Encoding]::ASCII.GetString($bytes[0..3]) -eq "glTF") "Downloaded asset is not GLB"

[ordered]@{
    status = "pass"
    project_id = $project.id
    audio_fixture_count = $audioFiles.Count
    speech_providers = @($chunkProviders | Select-Object -Unique)
    transcript = $project.meeting.transcript
    keyword_recall = $keywordRecall
    matched_keywords = $matchedKeywords
    analyzed_dimensions = $project.meeting.analysis.dimensions
    concepts = $project.results_2d.Count
    selected_concept_id = $concept.id
    generator_mode = $result.generator_mode
    validation_grade = $result.validation_grade
    quality_gate_passed = [bool]$result.self_feedback.passed
    quality_score = $result.self_feedback.score
    quality_target = $result.self_feedback.target
    glb_bytes = $bytes.Length
    glb_url = $result.glb_url
} | ConvertTo-Json -Depth 10

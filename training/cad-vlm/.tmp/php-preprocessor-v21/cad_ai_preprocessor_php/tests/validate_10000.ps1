param(
    [int]$Iterations = 10000,
    [int]$Workers = 8
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$php = if ($env:PHP_BIN) { $env:PHP_BIN } else { 'php' }
$ini = if ($env:PHP_INI) { $env:PHP_INI } else { '' }
$workerScript = Join-Path $project 'tests\validate_worker.php'
$hashScript = Join-Path $project 'tests\source_hash.php'
$reportRoot = Join-Path $project 'validation_reports'
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDir = Join-Path $reportRoot $runId
$workRoot = Join-Path ([IO.Path]::GetTempPath()) ("cad_ai_php_validation_" + $runId)
New-Item -ItemType Directory -Force -Path $runDir, $workRoot | Out-Null

$Workers = [Math]::Max(1, [Math]::Min($Workers, $Iterations))
$base = [Math]::Floor($Iterations / $Workers)
$remainder = $Iterations % $Workers
$nextCycle = 1
$processes = @()
$started = [DateTime]::UtcNow
$stopwatch = [Diagnostics.Stopwatch]::StartNew()

for ($workerId = 1; $workerId -le $Workers; $workerId++) {
    $count = [int]$base + $(if ($workerId -le $remainder) { 1 } else { 0 })
    $args = @()
    if ($ini) {
        $args += '-c'
        $args += "`"$ini`""
    }
    $args += "`"$workerScript`""
    $args += [string]$workerId
    $args += [string]$nextCycle
    $args += [string]$count
    $args += "`"$runDir`""
    $args += "`"$workRoot`""
    $processes += Start-Process -FilePath $php -ArgumentList $args -WorkingDirectory $project `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDir "worker_$workerId.stdout.log") `
        -RedirectStandardError (Join-Path $runDir "worker_$workerId.stderr.log")
    $nextCycle += $count
}

do {
    Start-Sleep -Seconds 1
    $completed = 0
    $failed = 0
    $tests = 0
    foreach ($workerId in 1..$Workers) {
        $progressPath = Join-Path $runDir "worker_${workerId}_progress.json"
        if (Test-Path -LiteralPath $progressPath) {
            try {
                $progress = Get-Content -LiteralPath $progressPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $completed += [int]$progress.completed_cycles
                $failed += [int]$progress.failed_cycles
                $tests += [int]$progress.total_tests
            } catch {
                # A worker may be replacing the progress file while it is read.
            }
        }
    }
    $summary = [ordered]@{
        run_id = $runId
        completed_cycles = $completed
        successful_cycles = $completed - $failed
        failed_cycles = $failed
        total_tests = $tests
        elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
    }
    $summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportRoot 'validation_10000_progress.json') -Encoding UTF8
    $running = @($processes | Where-Object { -not $_.HasExited }).Count
} while ($running -gt 0)

$stopwatch.Stop()
$results = @()
$durations = [Collections.Generic.List[double]]::new()
$failedDetails = @()
foreach ($workerId in 1..$Workers) {
    $resultPath = Join-Path $runDir "worker_${workerId}_result.json"
    if (-not (Test-Path -LiteralPath $resultPath)) {
        $stderrPath = Join-Path $runDir "worker_${workerId}.stderr.log"
        $stderr = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw -Encoding UTF8 } else { '' }
        throw "Worker $workerId 결과가 없습니다. $stderr"
    }
    $result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $results += $result
    foreach ($duration in $result.cycle_durations) { $durations.Add([double]$duration) }
    $failedDetails += @($result.failed_cycle_details)
}
$sorted = @($durations | Sort-Object)
$successful = [int](($results | Measure-Object successful_cycles -Sum).Sum)
$failed = [int](($results | Measure-Object failed_cycles -Sum).Sum)
$totalTests = [int](($results | Measure-Object total_tests -Sum).Sum)
$sourceHashArgs = @()
if ($ini) { $sourceHashArgs += '-c'; $sourceHashArgs += $ini }
$sourceHashArgs += $hashScript
$sourceHash = (& $php @sourceHashArgs).Trim()
$p95Index = [Math]::Max(0, [Math]::Floor($sorted.Count * 0.95) - 1)
$workerSummary = @($results | ForEach-Object {
    [ordered]@{
        worker_id = $_.worker_id
        start_cycle = $_.start_cycle
        cycle_count = $_.cycle_count
        successful_cycles = $_.successful_cycles
        failed_cycles = $_.failed_cycles
        total_tests = $_.total_tests
        duration_seconds = $_.duration_seconds
    }
})
$report = [ordered]@{
    scope = [ordered]@{
        iterations = $Iterations
        parallel_workers = $Workers
        tests_per_iteration = 4
        components = @(
            'PHP DXF parser and geometry contract',
            'PHP STEP parser and topology contract',
            'PHP full dataset package pipeline with SQLite repository',
            'PHP nearest-centroid baseline training and prediction'
        )
    }
    result = [ordered]@{
        successful_cycles = $successful
        failed_cycles = $failed
        total_tests_run = $totalTests
        pass_rate = $successful / $Iterations
        total_duration_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
        mean_cycle_seconds = [Math]::Round((($durations | Measure-Object -Average).Average), 6)
        p95_cycle_seconds = [Math]::Round($sorted[$p95Index], 6)
        max_cycle_seconds = [Math]::Round((($durations | Measure-Object -Maximum).Maximum), 6)
    }
    environment = [ordered]@{
        started_at_utc = $started.ToString('o')
        finished_at_utc = [DateTime]::UtcNow.ToString('o')
        php_version = (& $php $(if ($ini) { @('-c', $ini) } else { @() }) -r 'echo PHP_VERSION;')
        os = [Environment]::OSVersion.VersionString
        source_sha256 = $sourceHash
    }
    workers = $workerSummary
    failed_cycle_details = $failedDetails
}
$jsonPath = Join-Path $reportRoot 'validation_10000_runs.json'
$mdPath = Join-Path $reportRoot 'validation_10000_runs.md'
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
@"
# PHP 풀스택 10,000회 반복 전체 검증 결과

- 성공 회차: $successful/$Iterations
- 실패 회차: $failed
- 실행 테스트: $totalTests 건
- 통과율: $($report.result.pass_rate)
- 병렬 Worker: $Workers
- 총 소요 시간: $($report.result.total_duration_seconds)초
- 회차 평균/P95/최대: $($report.result.mean_cycle_seconds) / $($report.result.p95_cycle_seconds) / $($report.result.max_cycle_seconds)초
- PHP: $($report.environment.php_version)
- 소스 SHA-256: ``$sourceHash``

검증 범위: PHP DXF 파서, PHP STEP 파서, SQLite 저장소와 ZIP/Manifest를 포함한 전체 학습 패키지 파이프라인, 최근접 중심 기준 모델 학습·예측.
"@ | Set-Content -LiteralPath $mdPath -Encoding UTF8

$report.result | ConvertTo-Json
if ($failed -ne 0 -or $successful -ne $Iterations -or $totalTests -ne ($Iterations * 4)) {
    exit 1
}

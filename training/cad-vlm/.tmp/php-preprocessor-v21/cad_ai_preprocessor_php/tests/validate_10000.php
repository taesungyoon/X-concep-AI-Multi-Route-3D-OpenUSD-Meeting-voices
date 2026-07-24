<?php
declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require __DIR__ . '/ValidationSupport.php';

use CadAi\Tests\ValidationSupport;

$root = dirname(__DIR__);
$reportDir = $root . '/validation_reports';
$workRoot = $root . '/validation_work';
@mkdir($reportDir, 0770, true);
@mkdir($workRoot, 0770, true);
$iterations = max(1, (int)(getenv('CAD_AI_VALIDATION_ITERATIONS') ?: 10000));
$workerCount = min($iterations, max(1, (int)(getenv('CAD_AI_VALIDATION_WORKERS') ?: 8)));
$startedAt = gmdate(DATE_ATOM);
$started = hrtime(true);
$processes = [];
$base = intdiv($iterations, $workerCount);
$remainder = $iterations % $workerCount;
$startCycle = 1;
$ini = php_ini_loaded_file();

for ($workerId = 1; $workerId <= $workerCount; $workerId++) {
    $count = $base + ($workerId <= $remainder ? 1 : 0);
    $command = [PHP_BINARY];
    if (is_string($ini) && $ini !== '') {
        $command[] = '-c';
        $command[] = $ini;
    }
    array_push(
        $command,
        __DIR__ . '/validate_worker.php',
        (string)$workerId,
        (string)$startCycle,
        (string)$count,
        $reportDir,
        $workRoot
    );
    $stdout = $reportDir . '/worker_' . $workerId . '.stdout.log';
    $stderr = $reportDir . '/worker_' . $workerId . '.stderr.log';
    $process = proc_open($command, [
        0 => ['file', 'NUL', 'r'],
        1 => ['file', $stdout, 'w'],
        2 => ['file', $stderr, 'w'],
    ], $pipes, $root);
    if (!is_resource($process)) {
        throw new RuntimeException("worker {$workerId} 시작 실패");
    }
    $processes[$workerId] = $process;
    $startCycle += $count;
}

$exitCodes = [];
do {
    $running = 0;
    foreach ($processes as $workerId => $process) {
        if (array_key_exists($workerId, $exitCodes)) {
            continue;
        }
        $status = proc_get_status($process);
        if ($status['running']) {
            $running++;
        } else {
            $exitCodes[$workerId] = $status['exitcode'];
            proc_close($process);
        }
    }
    $progress = aggregateProgress($reportDir, $workerCount);
    $progress['elapsed_seconds'] = round((hrtime(true) - $started) / 1_000_000_000, 3);
    file_put_contents(
        $reportDir . '/validation_10000_progress.json',
        json_encode($progress, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT),
        LOCK_EX
    );
    if ($running > 0) {
        usleep(500000);
    }
} while ($running > 0);

$workerResults = [];
$durations = [];
$failedDetails = [];
foreach (range(1, $workerCount) as $workerId) {
    $path = $reportDir . '/worker_' . $workerId . '_result.json';
    if (!is_file($path)) {
        throw new RuntimeException("worker {$workerId} 결과가 없습니다.");
    }
    $result = json_decode((string)file_get_contents($path), true, flags: JSON_THROW_ON_ERROR);
    $workerResults[] = $result;
    array_push($durations, ...$result['cycle_durations']);
    array_push($failedDetails, ...$result['failed_cycle_details']);
}
sort($durations);
$successful = array_sum(array_column($workerResults, 'successful_cycles'));
$failed = array_sum(array_column($workerResults, 'failed_cycles'));
$totalTests = array_sum(array_column($workerResults, 'total_tests'));
$totalDuration = (hrtime(true) - $started) / 1_000_000_000;
$report = [
    'scope' => [
        'iterations' => $iterations,
        'parallel_workers' => $workerCount,
        'tests_per_iteration' => 4,
        'components' => [
            'PHP DXF parser and geometry contract',
            'PHP STEP parser and topology contract',
            'PHP full dataset package pipeline with SQLite repository',
            'PHP nearest-centroid baseline training and prediction',
        ],
    ],
    'result' => [
        'successful_cycles' => $successful,
        'failed_cycles' => $failed,
        'total_tests_run' => $totalTests,
        'pass_rate' => $successful / $iterations,
        'total_duration_seconds' => round($totalDuration, 3),
        'mean_cycle_seconds' => round(array_sum($durations) / count($durations), 6),
        'p95_cycle_seconds' => round($durations[(int)floor(count($durations) * 0.95) - 1], 6),
        'max_cycle_seconds' => round(max($durations), 6),
    ],
    'environment' => [
        'started_at_utc' => $startedAt,
        'finished_at_utc' => gmdate(DATE_ATOM),
        'php_version' => PHP_VERSION,
        'php_sapi' => PHP_SAPI,
        'os' => PHP_OS_FAMILY . ' ' . php_uname('r'),
        'source_sha256' => ValidationSupport::sourceHash($root),
    ],
    'workers' => array_map(
        static fn(array $item): array => array_diff_key($item, ['cycle_durations' => true, 'failed_cycle_details' => true]),
        $workerResults
    ),
    'failed_cycle_details' => $failedDetails,
];
$json = json_encode($report, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
file_put_contents($reportDir . '/validation_10000_runs.json', $json . PHP_EOL, LOCK_EX);
$markdown = <<<MD
# PHP 풀스택 10,000회 반복 전체 검증 결과

- 성공 회차: {$successful}/{$iterations}
- 실패 회차: {$failed}
- 실행 테스트: {$totalTests}건
- 통과율: {$report['result']['pass_rate']}
- 병렬 Worker: {$workerCount}
- 총 소요 시간: {$report['result']['total_duration_seconds']}초
- 회차 평균/P95/최대: {$report['result']['mean_cycle_seconds']} / {$report['result']['p95_cycle_seconds']} / {$report['result']['max_cycle_seconds']}초
- PHP: {$report['environment']['php_version']}
- 소스 SHA-256: `{$report['environment']['source_sha256']}`

검증 범위: PHP DXF 파서, PHP STEP 파서, SQLite 저장소와 ZIP/Manifest를 포함한 전체 학습 패키지 파이프라인, 최근접 중심 기준 모델 학습·예측.
MD;
file_put_contents($reportDir . '/validation_10000_runs.md', $markdown . PHP_EOL, LOCK_EX);
echo $json . PHP_EOL;
exit($failed === 0 && $successful === $iterations && $totalTests === $iterations * 4 ? 0 : 1);

function aggregateProgress(string $reportDir, int $workerCount): array
{
    $completed = 0;
    $failed = 0;
    $tests = 0;
    foreach (range(1, $workerCount) as $workerId) {
        $path = $reportDir . '/worker_' . $workerId . '_progress.json';
        if (!is_file($path)) {
            continue;
        }
        $item = json_decode((string)file_get_contents($path), true);
        $completed += (int)($item['completed_cycles'] ?? 0);
        $failed += (int)($item['failed_cycles'] ?? 0);
        $tests += (int)($item['total_tests'] ?? 0);
    }
    return [
        'completed_cycles' => $completed,
        'successful_cycles' => $completed - $failed,
        'failed_cycles' => $failed,
        'total_tests' => $tests,
    ];
}
